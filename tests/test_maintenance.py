"""
Tests de las tareas de mantenimiento sobre la BD ya poblada.

Cubre `reclassify_all` (rebobinar el clasificador tras afinar
CATEGORY_HINTS) y `enricher.enrich_pending` (re-enriquecer a v2 los items
históricos que aún estén en versión anterior).
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from vigia import maintenance, enricher
from vigia.storage import ENRICHMENT_VERSION, Item, Storage


_FAKE_V2_JSON = """{
  "is_relevant": true,
  "relevance_reason": "Plaza Enfermería del Trabajo",
  "process_type": "bolsa",
  "summary": "Resumen IA",
  "organismo": "CODEM",
  "centro": null,
  "plazas": 4,
  "deadline_inscripcion": null,
  "fecha_publicacion_oficial": "2026-04-25",
  "tasas_eur": null,
  "url_bases": null,
  "url_inscripcion": null,
  "requisitos_clave": [],
  "fase": "convocatoria",
  "next_action": null,
  "confidence": 0.85
}"""


def _make_item(titulo: str, categoria: str = "otro", summary=None) -> Item:
    return Item(
        source="codem",
        url=f"https://example.com/{abs(hash(titulo))}",
        titulo=titulo,
        fecha=date(2026, 4, 25),
        categoria=categoria,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# reclassify_all
# ---------------------------------------------------------------------------

class TestReclassifyAll:
    def test_bolsa_unica_pasa_de_otro_a_bolsa(self, tmp_path):
        """Caso real del CODEM: 'Bolsa única de empleo temporal' estaba
        guardada como 'otro' antes de ampliar CATEGORY_HINTS."""
        storage = Storage(db_path=tmp_path / "seen.db")
        storage.save(_make_item(
            "Bolsa única de empleo temporal de Especialista en Enfermería del Trabajo",
            categoria="otro",
        ))

        n = maintenance.reclassify_all(storage)
        assert n == 1

        row = storage._conn.execute(
            "SELECT categoria FROM items"
        ).fetchone()
        storage.close()
        assert row[0] == "bolsa"

    def test_no_toca_items_ya_bien_clasificados(self, tmp_path):
        storage = Storage(db_path=tmp_path / "seen.db")
        storage.save(_make_item(
            "Convocatoria proceso selectivo Enfermería del Trabajo",
            categoria="oposicion",
        ))
        n = maintenance.reclassify_all(storage)
        storage.close()
        assert n == 0

    def test_idempotente(self, tmp_path):
        """Ejecutarlo dos veces no debe cambiar nada en la segunda."""
        storage = Storage(db_path=tmp_path / "seen.db")
        storage.save(_make_item("Bolsa única de empleo temporal", categoria="otro"))

        n1 = maintenance.reclassify_all(storage)
        n2 = maintenance.reclassify_all(storage)
        storage.close()
        assert n1 == 1
        assert n2 == 0


# ---------------------------------------------------------------------------
# enricher.enrich_pending
# ---------------------------------------------------------------------------

class TestEnrichPending:
    """Backfill al objetivo `ENRICHMENT_VERSION`.

    `enrich_pending` reprocesa todos los items con `enriched_version`
    distinto del actual: los sin enriquecer y los que solo tenían el
    summary v1 (string-only). Los que ya están en v2 se saltan.
    """
    def _patch_anthropic(self, monkeypatch, json_text: str = _FAKE_V2_JSON):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        block = SimpleNamespace(type="text", text=json_text)
        resp = SimpleNamespace(stop_reason="end_turn", content=[block])
        client = MagicMock()
        client.messages.create.return_value = resp
        import anthropic
        monkeypatch.setattr(anthropic, "Anthropic", lambda: client)
        return client

    def test_enriquece_los_legacy_y_los_no_enriquecidos(self, tmp_path, monkeypatch):
        """Tanto items sin summary como items con summary v1 deben pasar a v2."""
        client = self._patch_anthropic(monkeypatch)
        storage = Storage(db_path=tmp_path / "seen.db")
        storage.save(_make_item("Item sin summary"))
        storage.save(_make_item("Item con summary v1", summary="resumen v1"))

        n = enricher.enrich_pending(storage)
        assert n == 2
        assert client.messages.create.call_count == 2

        rows = dict(storage._conn.execute(
            "SELECT titulo, enriched_version FROM items"
        ))
        storage.close()
        assert rows["Item sin summary"] == ENRICHMENT_VERSION
        assert rows["Item con summary v1"] == ENRICHMENT_VERSION

    def test_no_reprocesa_items_ya_en_v2(self, tmp_path, monkeypatch):
        """Si un item ya tiene enriched_version = ENRICHMENT_VERSION, se salta."""
        client = self._patch_anthropic(monkeypatch)
        storage = Storage(db_path=tmp_path / "seen.db")
        storage.save(_make_item("Item ya enriquecido"))
        # Marcamos el item como ya en v2
        storage._conn.execute(
            "UPDATE items SET enriched_version = ? WHERE titulo = ?",
            (ENRICHMENT_VERSION, "Item ya enriquecido"),
        )
        storage._conn.commit()

        n = enricher.enrich_pending(storage)
        storage.close()
        assert n == 0
        assert client.messages.create.call_count == 0

    def test_sin_api_key_no_pasa_nada(self, tmp_path, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        storage = Storage(db_path=tmp_path / "seen.db")
        storage.save(_make_item("Pendiente"))

        n = enricher.enrich_pending(storage)
        storage.close()
        assert n == 0


# ---------------------------------------------------------------------------
# Flag --maintenance integrado en main.py
# ---------------------------------------------------------------------------

class TestMainMaintenanceFlag:
    def test_flag_reclasifica_y_no_llama_a_send(
        self, tmp_path, monkeypatch
    ):
        """`python -m vigia.main --maintenance` debe reclasificar items en
        BD pero NO llamar al notifier (es solo mantenimiento)."""
        from vigia import main as main_module
        from vigia import storage as storage_module

        monkeypatch.setattr(storage_module, "DB_PATH", tmp_path / "seen.db")
        monkeypatch.setattr(
            main_module, "DASHBOARD_OUT_DIR", str(tmp_path / "dashboard"),
        )
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        # Sembramos un item mal clasificado
        storage = Storage(db_path=tmp_path / "seen.db")
        storage.save(_make_item(
            "Bolsa única de empleo temporal Enfermería del Trabajo",
            categoria="otro",
        ))
        storage.close()

        # send NO debe llamarse
        send_called = []
        monkeypatch.setattr(
            main_module, "send", lambda *a, **kw: send_called.append(True),
        )
        monkeypatch.setattr("sys.argv", ["main.py", "--maintenance"])

        with pytest.raises(SystemExit) as excinfo:
            main_module.main()
        assert excinfo.value.code == 0
        assert send_called == []

        # Verificamos que el item se ha reclasificado
        s = Storage(db_path=tmp_path / "seen.db")
        cat = s._conn.execute("SELECT categoria FROM items").fetchone()[0]
        s.close()
        assert cat == "bolsa"
