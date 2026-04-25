"""
Tests del exportador a JSON que alimenta el dashboard web.

Cubre:
- items.json: orden, campos esperados, summary persistido.
- sources_status.json: integración probe + total_hits agregado.
- meta.json: contadores, days_watching, by_category.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

from vigia import dashboard
from vigia.storage import Item, Storage


def _seed(storage: Storage, items: list[Item]) -> None:
    for it in items:
        storage.save(it)


def _item(titulo: str, source: str = "boe", categoria: str = "oposicion",
          first_seen_at: datetime | None = None, summary=None) -> Item:
    it = Item(
        source=source,
        url=f"https://example.com/{titulo.lower().replace(' ', '-')}",
        titulo=titulo,
        fecha=date(2026, 4, 25),
        categoria=categoria,
        summary=summary,
    )
    if first_seen_at is not None:
        it.first_seen_at = first_seen_at
    return it


class TestItemsJson:
    def test_items_se_exportan_ordenados_por_first_seen_desc(self, tmp_path):
        storage = Storage(db_path=tmp_path / "seen.db")
        _seed(storage, [
            _item("antiguo", first_seen_at=datetime(2026, 1, 1, tzinfo=timezone.utc)),
            _item("nuevo", first_seen_at=datetime(2026, 4, 25, tzinfo=timezone.utc)),
            _item("medio", first_seen_at=datetime(2026, 3, 10, tzinfo=timezone.utc)),
        ])

        dashboard.export_all(storage, tmp_path / "out")
        storage.close()

        data = json.loads((tmp_path / "out" / "items.json").read_text(encoding="utf-8"))
        titulos = [d["titulo"] for d in data]
        assert titulos == ["nuevo", "medio", "antiguo"]

    def test_items_incluyen_summary_cuando_existe(self, tmp_path):
        storage = Storage(db_path=tmp_path / "seen.db")
        _seed(storage, [
            _item("Con resumen", summary="Resumen del item"),
            _item("Sin resumen"),
        ])
        dashboard.export_all(storage, tmp_path / "out")
        storage.close()

        data = json.loads((tmp_path / "out" / "items.json").read_text(encoding="utf-8"))
        by_titulo = {d["titulo"]: d for d in data}
        assert by_titulo["Con resumen"]["summary"] == "Resumen del item"
        assert by_titulo["Sin resumen"]["summary"] is None

    def test_items_incluyen_todos_los_campos_esperados(self, tmp_path):
        storage = Storage(db_path=tmp_path / "seen.db")
        _seed(storage, [_item("X")])
        dashboard.export_all(storage, tmp_path / "out")
        storage.close()

        item = json.loads(
            (tmp_path / "out" / "items.json").read_text(encoding="utf-8")
        )[0]
        assert set(item.keys()) == {
            "id_hash", "source", "url", "titulo", "fecha",
            "categoria", "first_seen_at", "summary",
        }


class TestSourcesStatusJson:
    def test_combina_probe_con_conteo_agregado(self, tmp_path):
        storage = Storage(db_path=tmp_path / "seen.db")
        _seed(storage, [
            _item("a", source="boe"),
            _item("b", source="boe"),
            _item("c", source="bocm"),
        ])

        probe = [
            {"name": "boe", "url": "https://boe.es", "status": "ok", "code": 200, "detail": ""},
            {"name": "bocm", "url": "https://bocm.es", "status": "ok", "code": 200, "detail": ""},
            {"name": "boam", "url": "https://madrid.es", "status": "error", "code": 403, "detail": "Forbidden"},
        ]
        dashboard.export_all(storage, tmp_path / "out", probe_results=probe)
        storage.close()

        data = json.loads(
            (tmp_path / "out" / "sources_status.json").read_text(encoding="utf-8")
        )
        by_name = {r["name"]: r for r in data}

        assert by_name["boe"]["total_hits"] == 2
        assert by_name["boe"]["status"] == "ok"
        assert by_name["bocm"]["total_hits"] == 1
        assert by_name["boam"]["total_hits"] == 0  # sin items
        assert by_name["boam"]["code"] == 403

    def test_sin_probe_devuelve_solo_contadores(self, tmp_path):
        storage = Storage(db_path=tmp_path / "seen.db")
        _seed(storage, [_item("a", source="boe"), _item("b", source="bocm")])
        dashboard.export_all(storage, tmp_path / "out")
        storage.close()

        data = json.loads(
            (tmp_path / "out" / "sources_status.json").read_text(encoding="utf-8")
        )
        by_name = {r["name"]: r for r in data}
        assert by_name["boe"]["total_hits"] == 1
        assert by_name["boe"]["status"] == "unknown"

    def test_fuente_con_hits_pero_sin_probe_se_incluye(self, tmp_path):
        """Si probe_results no contiene una fuente que sí tiene hits en BD,
        debe aparecer igualmente en el output con status=unknown."""
        storage = Storage(db_path=tmp_path / "seen.db")
        _seed(storage, [_item("x", source="codem")])

        probe = [
            {"name": "boe", "url": "https://boe.es", "status": "ok", "code": 200, "detail": ""},
        ]
        dashboard.export_all(storage, tmp_path / "out", probe_results=probe)
        storage.close()

        data = json.loads(
            (tmp_path / "out" / "sources_status.json").read_text(encoding="utf-8")
        )
        names = {r["name"] for r in data}
        assert "codem" in names
        assert "boe" in names


class TestMetaJson:
    def test_total_y_total_today(self, tmp_path):
        now_utc = datetime.now(timezone.utc)
        storage = Storage(db_path=tmp_path / "seen.db")
        _seed(storage, [
            _item("hoy", first_seen_at=now_utc),
            _item("hoy2", first_seen_at=now_utc),
            _item("hace1mes", first_seen_at=now_utc - timedelta(days=30)),
        ])
        dashboard.export_all(storage, tmp_path / "out", last_run_at=now_utc)
        storage.close()

        meta = json.loads((tmp_path / "out" / "meta.json").read_text(encoding="utf-8"))
        assert meta["total_items"] == 3
        assert meta["total_today"] == 2

    def test_days_watching_es_delta_con_first_seen_minimo(self, tmp_path):
        now_utc = datetime(2026, 4, 25, 12, 0, 0, tzinfo=timezone.utc)
        storage = Storage(db_path=tmp_path / "seen.db")
        _seed(storage, [
            _item("antiguo", first_seen_at=now_utc - timedelta(days=100)),
            _item("nuevo", first_seen_at=now_utc),
        ])
        dashboard.export_all(storage, tmp_path / "out", last_run_at=now_utc)
        storage.close()

        meta = json.loads((tmp_path / "out" / "meta.json").read_text(encoding="utf-8"))
        assert meta["days_watching"] == 100

    def test_by_category_agrega_correctamente(self, tmp_path):
        storage = Storage(db_path=tmp_path / "seen.db")
        _seed(storage, [
            _item("a", categoria="oposicion"),
            _item("b", categoria="oposicion"),
            _item("c", categoria="bolsa"),
        ])
        dashboard.export_all(storage, tmp_path / "out")
        storage.close()

        meta = json.loads((tmp_path / "out" / "meta.json").read_text(encoding="utf-8"))
        assert meta["by_category"] == {"oposicion": 2, "bolsa": 1}

    def test_bd_vacia_genera_meta_coherente(self, tmp_path):
        """Caso borde: BD recién creada sin items."""
        storage = Storage(db_path=tmp_path / "seen.db")
        dashboard.export_all(storage, tmp_path / "out")
        storage.close()

        meta = json.loads((tmp_path / "out" / "meta.json").read_text(encoding="utf-8"))
        assert meta["total_items"] == 0
        assert meta["total_today"] == 0
        assert meta["days_watching"] == 0
        assert meta["first_seen_at"] is None

    def test_meta_incluye_build_info(self, tmp_path, monkeypatch):
        """version y commit deben estar siempre presentes en meta.json."""
        monkeypatch.setenv("GITHUB_SHA", "abcdef1234567890abcdef")
        storage = Storage(db_path=tmp_path / "seen.db")
        dashboard.export_all(storage, tmp_path / "out")
        storage.close()

        meta = json.loads((tmp_path / "out" / "meta.json").read_text(encoding="utf-8"))
        assert meta["version"]  # __version__ no debe estar vacío
        assert meta["commit"] == "abcdef1"  # primeros 7 chars

    def test_commit_es_local_si_no_hay_github_sha(self, tmp_path, monkeypatch):
        monkeypatch.delenv("GITHUB_SHA", raising=False)
        storage = Storage(db_path=tmp_path / "seen.db")
        dashboard.export_all(storage, tmp_path / "out")
        storage.close()

        meta = json.loads((tmp_path / "out" / "meta.json").read_text(encoding="utf-8"))
        assert meta["commit"] == "local"

    def test_meta_incluye_sources_online_y_total(self, tmp_path):
        storage = Storage(db_path=tmp_path / "seen.db")
        _seed(storage, [_item("a", source="boe")])
        probe = [
            {"name": "boe", "url": "x", "status": "ok", "code": 200, "detail": ""},
            {"name": "bocm", "url": "x", "status": "ok", "code": 200, "detail": ""},
            {"name": "boam", "url": "x", "status": "error", "code": 403, "detail": "geo"},
        ]
        dashboard.export_all(storage, tmp_path / "out", probe_results=probe)
        storage.close()

        meta = json.loads((tmp_path / "out" / "meta.json").read_text(encoding="utf-8"))
        assert meta["sources_online"] == 2  # boe + bocm
        assert meta["sources_total"] >= 3  # al menos las 3 del probe

    def test_next_run_at_es_dia_laborable_a_las_8utc(self, tmp_path):
        from datetime import datetime, timezone
        # Lunes 2026-04-27 a las 12:00 UTC: próximo run es martes 28 a las 08:00.
        now = datetime(2026, 4, 27, 12, 0, 0, tzinfo=timezone.utc)
        storage = Storage(db_path=tmp_path / "seen.db")
        dashboard.export_all(storage, tmp_path / "out", last_run_at=now)
        storage.close()

        meta = json.loads((tmp_path / "out" / "meta.json").read_text(encoding="utf-8"))
        next_run = datetime.fromisoformat(meta["next_run_at"])
        assert next_run.hour == 8
        assert next_run.minute == 0
        assert next_run.weekday() <= 4  # L-V

    def test_next_run_at_salta_finde(self, tmp_path):
        """Viernes 14:00 UTC → siguiente run es lunes 08:00 UTC."""
        from datetime import datetime, timezone
        # 2026-04-24 es viernes
        now = datetime(2026, 4, 24, 14, 0, 0, tzinfo=timezone.utc)
        storage = Storage(db_path=tmp_path / "seen.db")
        dashboard.export_all(storage, tmp_path / "out", last_run_at=now)
        storage.close()

        meta = json.loads((tmp_path / "out" / "meta.json").read_text(encoding="utf-8"))
        next_run = datetime.fromisoformat(meta["next_run_at"])
        # Debe ser lunes 27
        assert next_run.day == 27
        assert next_run.weekday() == 0


class TestExportAll:
    def test_genera_los_tres_ficheros(self, tmp_path):
        storage = Storage(db_path=tmp_path / "seen.db")
        _seed(storage, [_item("x")])
        result = dashboard.export_all(storage, tmp_path / "out")
        storage.close()

        assert result["items"].exists()
        assert result["sources"].exists()
        assert result["meta"].exists()

    def test_crea_directorio_destino_si_no_existe(self, tmp_path):
        storage = Storage(db_path=tmp_path / "seen.db")
        out = tmp_path / "no" / "existe" / "todavia"
        dashboard.export_all(storage, out)
        storage.close()
        assert out.exists()
        assert (out / "items.json").exists()

    def test_json_es_utf8_con_acentos(self, tmp_path):
        """Los títulos llevan acentos; el JSON debe preservarlos legibles."""
        storage = Storage(db_path=tmp_path / "seen.db")
        _seed(storage, [_item("Convocatoria Enfermería del Trabajo")])
        dashboard.export_all(storage, tmp_path / "out")
        storage.close()

        raw = (tmp_path / "out" / "items.json").read_text(encoding="utf-8")
        assert "Enfermería del Trabajo" in raw  # no escapado a \u00...
