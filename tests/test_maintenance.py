"""
Tests de las tareas de mantenimiento sobre la BD ya poblada.

Cubre `reclassify_all` (rebobinar el clasificador tras afinar
CATEGORY_HINTS) y `enricher.enrich_pending` (rellenar summary IA en items
históricos sin él).
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest

from vigia import maintenance, enricher
from vigia.storage import Item, Storage


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
    def _patch_anthropic(self, monkeypatch, response_text: str = "Resumen IA"):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        block = MagicMock(); block.type = "text"; block.text = response_text
        resp = MagicMock(); resp.content = [block]
        client = MagicMock()
        client.messages.create.return_value = resp
        import anthropic
        monkeypatch.setattr(anthropic, "Anthropic", lambda: client)
        return client

    def test_enriquece_solo_los_que_no_tienen_summary(self, tmp_path, monkeypatch):
        client = self._patch_anthropic(monkeypatch)
        storage = Storage(db_path=tmp_path / "seen.db")
        storage.save(_make_item("Item sin summary"))
        storage.save(_make_item("Item con summary", summary="ya estaba"))

        n = enricher.enrich_pending(storage)
        assert n == 1
        # Sólo se llamó al SDK 1 vez (el otro ya tenía summary)
        assert client.messages.create.call_count == 1

        rows = dict(storage._conn.execute("SELECT titulo, summary FROM items"))
        storage.close()
        assert rows["Item sin summary"] == "Resumen IA"
        assert rows["Item con summary"] == "ya estaba"

    def test_sin_pendientes_no_llama_al_sdk(self, tmp_path, monkeypatch):
        client = self._patch_anthropic(monkeypatch)
        storage = Storage(db_path=tmp_path / "seen.db")
        storage.save(_make_item("Item con summary", summary="x"))

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
