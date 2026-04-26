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
        # v1 (siempre presentes) + v2 (rellenos cuando el enricher haya
        # corrido; null mientras tanto)
        assert set(item.keys()) == {
            "id_hash", "source", "url", "titulo", "fecha",
            "categoria", "first_seen_at", "summary",
            "is_relevant", "relevance_reason", "process_type", "organismo",
            "centro", "plazas", "deadline_inscripcion",
            "fecha_publicacion_oficial", "tasas_eur", "url_bases",
            "url_inscripcion", "requisitos_clave", "fase", "next_action",
            "confidence", "enriched_at", "enriched_version",
        }
        # Item recién insertado (sin enricher v2) → todos los campos v2
        # son null/None.
        assert item["is_relevant"] is None
        assert item["enriched_version"] is None
        assert item["plazas"] is None

    def test_items_incluyen_campos_v2_si_estan_persistidos(self, tmp_path):
        from vigia.storage import ENRICHMENT_VERSION
        storage = Storage(db_path=tmp_path / "seen.db")
        it = _item("Convocatoria con datos v2")
        storage.save(it)
        # Simulamos enriquecimiento v2 directo en BD
        it.is_relevant = True
        it.process_type = "oposicion"
        it.organismo = "SERMAS"
        it.plazas = 12
        it.deadline_inscripcion = "2026-05-15"
        it.tasas_eur = 30.5
        it.requisitos_clave = ["Título de Enfermería del Trabajo"]
        it.fase = "convocatoria"
        it.next_action = "Presentar instancia online"
        it.confidence = 0.9
        it.enriched_at = "2026-04-26T12:00:00+00:00"
        it.enriched_version = ENRICHMENT_VERSION
        storage.update_enrichment(it)

        dashboard.export_all(storage, tmp_path / "out")
        storage.close()

        item = json.loads(
            (tmp_path / "out" / "items.json").read_text(encoding="utf-8")
        )[0]
        assert item["is_relevant"] is True
        assert item["plazas"] == 12
        assert item["deadline_inscripcion"] == "2026-05-15"
        assert item["tasas_eur"] == 30.5
        assert item["requisitos_clave"] == ["Título de Enfermería del Trabajo"]
        assert item["fase"] == "convocatoria"
        assert item["enriched_version"] == ENRICHMENT_VERSION


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

    def test_sin_probe_y_sin_snapshot_previo_no_escribe_degradado(self, tmp_path):
        """Regresión del bug null/unknown en SOURCES (2026-04-26):
        si el caller no pasa probe_results y NO existe sources_status.json
        en disco (caso típico en CI con checkout fresco), `export_all` debe
        ABSTENERSE de escribir el fichero — un payload de `unknown/null`
        pisaría al bueno publicado en gh-pages cuando el siguiente push
        haga `rm -rf data/* && cp docs/data/* data/`.

        El fix correcto exige que el workflow CI traiga el JSON desde
        gh-pages a `docs/data/` antes del export. Si no lo hace, mejor
        dejar la sección transitoriamente vacía que mostrar todas las
        fuentes como caídas.
        """
        storage = Storage(db_path=tmp_path / "seen.db")
        _seed(storage, [_item("a", source="boe"), _item("b", source="bocm")])
        out = tmp_path / "out"
        dashboard.export_all(storage, out)
        storage.close()

        # El fichero NO debe haberse creado.
        assert not (out / "sources_status.json").exists(), \
            "export_all no debe escribir sources_status.json degradado"

        # meta.json sí se escribe (con sources_online=0 — honesto: no hay
        # probe data) y el resto de salidas tampoco se ven afectadas.
        assert (out / "meta.json").exists()
        meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
        # No mentimos: sin probe, ninguna fuente cuenta como online.
        assert meta["sources_online"] == 0

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
    def test_genera_items_y_meta_sin_probe(self, tmp_path):
        """Sin probe_results y sin snapshot previo, items.json y meta.json
        se generan; sources_status.json NO (defensa contra el degradado)."""
        storage = Storage(db_path=tmp_path / "seen.db")
        _seed(storage, [_item("x")])
        result = dashboard.export_all(storage, tmp_path / "out")
        storage.close()

        assert result["items"].exists()
        assert result["meta"].exists()
        # sources_status.json no se crea cuando no hay probe ni snapshot.
        assert not result["sources"].exists()

    def test_genera_sources_si_hay_probe(self, tmp_path):
        storage = Storage(db_path=tmp_path / "seen.db")
        _seed(storage, [_item("x", source="boe")])
        probe = [{"name": "boe", "url": "https://boe.es", "status": "ok",
                  "code": 200, "detail": ""}]
        result = dashboard.export_all(storage, tmp_path / "out", probe_results=probe)
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

    def test_sin_probe_no_pisa_sources_status_existente(self, tmp_path):
        """Si llamamos export_all sin probe_results pero ya existía un
        sources_status.json (escrito por un --probe anterior), debe
        respetarse — esto evita que --maintenance degrade la pantalla
        SOURCES del dashboard."""
        storage = Storage(db_path=tmp_path / "seen.db")
        out = tmp_path / "out"

        # Primer export: con probe_results completos (simula --probe).
        full_probe = [
            {"name": "boe", "url": "https://boe.es", "status": "ok",
             "code": 200, "detail": ""},
            {"name": "bocm", "url": "https://bocm.es", "status": "ok",
             "code": 200, "detail": ""},
            {"name": "boam", "url": "https://madrid.es/boam", "status": "error",
             "code": 403, "detail": "geo"},
        ]
        dashboard.export_all(storage, out, probe_results=full_probe)

        # Segundo export: sin probe (simula --maintenance). Debe respetar
        # el sources_status.json del primer export.
        dashboard.export_all(storage, out)
        storage.close()

        data = json.loads((out / "sources_status.json").read_text(encoding="utf-8"))
        names = {r["name"] for r in data}
        assert names == {"boe", "bocm", "boam"}
        # Y los códigos HTTP siguen siendo los del probe original
        by_name = {r["name"]: r for r in data}
        assert by_name["boam"]["code"] == 403

    def test_sin_probe_refresca_total_hits(self, tmp_path):
        """Aunque reutilicemos el sources_status.json del último --probe,
        los `total_hits` por fuente sí deben refrescarse contra la BD: el
        conteo crece cada día y queremos que el dashboard lo refleje.
        Los campos del último probe (url, code, status) siguen congelados."""
        storage = Storage(db_path=tmp_path / "seen.db")
        out = tmp_path / "out"

        # Probe inicial con BD vacía (sin items todavía).
        full_probe = [
            {"name": "boe", "url": "https://boe.es", "status": "ok",
             "code": 200, "detail": ""},
            {"name": "bocm", "url": "https://bocm.es", "status": "ok",
             "code": 200, "detail": ""},
        ]
        dashboard.export_all(storage, out, probe_results=full_probe)
        first = json.loads((out / "sources_status.json").read_text(encoding="utf-8"))
        assert all(r["total_hits"] == 0 for r in first)

        # Llegan items nuevos a la BD entre runs.
        _seed(storage, [
            _item("a", source="boe"),
            _item("b", source="boe"),
            _item("c", source="bocm"),
        ])

        # Segundo export sin probe (pipeline diario): los hits se actualizan,
        # pero los códigos HTTP del probe anterior se conservan.
        dashboard.export_all(storage, out)
        storage.close()
        second = json.loads((out / "sources_status.json").read_text(encoding="utf-8"))
        by_name = {r["name"]: r for r in second}
        assert by_name["boe"]["total_hits"] == 2
        assert by_name["bocm"]["total_hits"] == 1
        assert by_name["boe"]["code"] == 200
        assert by_name["boe"]["url"] == "https://boe.es"
        assert by_name["boe"]["status"] == "ok"

    def test_sin_probe_anade_fuentes_nuevas_en_bd(self, tmp_path):
        """Si entre el último --probe y el run actual la BD ha estrenado
        una fuente nueva (ej. se acaba de añadir un parser), debe aparecer
        en sources_status.json marcada como `unknown` con sus total_hits."""
        storage = Storage(db_path=tmp_path / "seen.db")
        out = tmp_path / "out"

        full_probe = [
            {"name": "boe", "url": "https://boe.es", "status": "ok",
             "code": 200, "detail": ""},
        ]
        dashboard.export_all(storage, out, probe_results=full_probe)

        # Items de una fuente que no estaba en el probe original.
        _seed(storage, [_item("nuevo", source="codem")])

        dashboard.export_all(storage, out)
        storage.close()
        data = json.loads((out / "sources_status.json").read_text(encoding="utf-8"))
        by_name = {r["name"]: r for r in data}
        assert "codem" in by_name
        assert by_name["codem"]["status"] == "unknown"
        assert by_name["codem"]["total_hits"] == 1

    def test_genera_targets_json(self, tmp_path):
        """export_all debe escribir targets.json con la lista de 22 organismos."""
        storage = Storage(db_path=tmp_path / "seen.db")
        dashboard.export_all(storage, tmp_path / "out")
        storage.close()

        path = tmp_path / "out" / "targets.json"
        assert path.exists()
        targets = json.loads(path.read_text(encoding="utf-8"))
        assert len(targets) == 22
        ids = {t["id"] for t in targets}
        assert "T-01" in ids and "T-22" in ids


class TestTargetsPayload:
    def _save(self, storage, titulo, fecha=date(2026, 4, 25), summary=None,
              source="bocm", categoria="oposicion"):
        storage.save(Item(
            source=source,
            url=f"https://example.com/{abs(hash(titulo))}",
            titulo=titulo,
            fecha=fecha,
            categoria=categoria,
            summary=summary,
        ))

    def test_match_por_titulo(self, tmp_path):
        storage = Storage(db_path=tmp_path / "seen.db")
        self._save(storage, "Convocatoria SERMAS Enfermería del Trabajo")
        dashboard.export_all(storage, tmp_path / "out")
        storage.close()

        targets = json.loads(
            (tmp_path / "out" / "targets.json").read_text(encoding="utf-8")
        )
        sermas = next(t for t in targets if t["id"] == "T-01")
        assert sermas["hits"] == 1

    def test_match_por_summary_tambien(self, tmp_path):
        """Si el organismo solo aparece en el summary del enricher, debe contar."""
        storage = Storage(db_path=tmp_path / "seen.db")
        self._save(
            storage,
            titulo="Bolsa única de Enfermería del Trabajo (Subsanación)",
            summary="Hospital Universitario La Paz convoca 4 plazas.",
        )
        dashboard.export_all(storage, tmp_path / "out")
        storage.close()

        targets = json.loads(
            (tmp_path / "out" / "targets.json").read_text(encoding="utf-8")
        )
        la_paz = next(t for t in targets if t["id"] == "T-02")
        assert la_paz["hits"] == 1

    def test_active_si_publicacion_reciente(self, tmp_path):
        """ACTIVE = al menos un item con fecha < 90 días."""
        from datetime import timedelta
        now = datetime(2026, 4, 25, 12, 0, 0, tzinfo=timezone.utc)
        storage = Storage(db_path=tmp_path / "seen.db")
        self._save(storage, "FNMT convoca proceso", fecha=date(2026, 4, 1))
        dashboard.export_all(storage, tmp_path / "out", last_run_at=now)
        storage.close()

        targets = json.loads(
            (tmp_path / "out" / "targets.json").read_text(encoding="utf-8")
        )
        fnmt = next(t for t in targets if t["id"] == "T-07")
        assert fnmt["hits"] == 1
        assert fnmt["active"] is True

    def test_cold_si_publicacion_antigua(self, tmp_path):
        """Hit de hace más de 90 días → organismo aparece como COLD."""
        now = datetime(2026, 4, 25, 12, 0, 0, tzinfo=timezone.utc)
        storage = Storage(db_path=tmp_path / "seen.db")
        # Publicación de hace ~6 meses
        self._save(storage, "FNMT convocó proceso", fecha=date(2025, 10, 1))
        dashboard.export_all(storage, tmp_path / "out", last_run_at=now)
        storage.close()

        targets = json.loads(
            (tmp_path / "out" / "targets.json").read_text(encoding="utf-8")
        )
        fnmt = next(t for t in targets if t["id"] == "T-07")
        assert fnmt["hits"] == 1
        assert fnmt["active"] is False

    def test_sin_items_todos_en_cold_y_cero_hits(self, tmp_path):
        storage = Storage(db_path=tmp_path / "seen.db")
        dashboard.export_all(storage, tmp_path / "out")
        storage.close()

        targets = json.loads(
            (tmp_path / "out" / "targets.json").read_text(encoding="utf-8")
        )
        assert all(t["hits"] == 0 for t in targets)
        assert all(t["active"] is False for t in targets)

    def test_meta_incluye_targets_active_y_total(self, tmp_path):
        storage = Storage(db_path=tmp_path / "seen.db")
        self._save(storage, "SERMAS Enfermería del Trabajo", fecha=date(2026, 4, 1))
        dashboard.export_all(
            storage, tmp_path / "out",
            last_run_at=datetime(2026, 4, 25, tzinfo=timezone.utc),
        )
        storage.close()

        meta = json.loads(
            (tmp_path / "out" / "meta.json").read_text(encoding="utf-8")
        )
        assert meta["targets_total"] == 22
        assert meta["targets_active"] == 1

    def test_active_por_deadline_real_supera_heuristica_de_fecha(self, tmp_path):
        """Si el enricher v2 marcó deadline_inscripcion en el futuro, el
        organismo debe aparecer ACTIVE aunque la fecha de publicación sea
        antigua."""
        from vigia.storage import ENRICHMENT_VERSION
        from datetime import datetime, timezone, date

        now = datetime(2026, 4, 25, 12, 0, 0, tzinfo=timezone.utc)
        storage = Storage(db_path=tmp_path / "seen.db")

        # Publicación de hace 6 meses (heurística: cold), pero deadline
        # extraído por el enricher dice que cierra el 15/05/2026 (futuro).
        it = Item(
            source="bocm",
            url="https://example.com/sermas-1",
            titulo="SERMAS Enfermería del Trabajo (publicado hace 6m)",
            fecha=date(2025, 10, 1),
            categoria="oposicion",
        )
        storage.save(it)
        it.is_relevant = True
        it.deadline_inscripcion = "2026-05-15"
        it.fase = "convocatoria"
        it.enriched_version = ENRICHMENT_VERSION
        storage.update_enrichment(it)

        dashboard.export_all(storage, tmp_path / "out", last_run_at=now)
        storage.close()

        targets = json.loads(
            (tmp_path / "out" / "targets.json").read_text(encoding="utf-8")
        )
        sermas = next(t for t in targets if t["id"] == "T-01")
        assert sermas["active"] is True
        assert sermas["nearest_deadline"] == "2026-05-15"
        assert sermas["days_until"] == 20
        assert sermas["urgent"] is False  # >7 días
        assert sermas["latest_phase"] == "convocatoria"

    def test_urgent_si_deadline_a_menos_de_7_dias(self, tmp_path):
        from vigia.storage import ENRICHMENT_VERSION
        from datetime import datetime, timezone, date

        now = datetime(2026, 4, 25, 12, 0, 0, tzinfo=timezone.utc)
        storage = Storage(db_path=tmp_path / "seen.db")

        it = Item(
            source="bocm",
            url="https://example.com/sermas-urgent",
            titulo="SERMAS Enfermería del Trabajo cierra en 3 días",
            fecha=date(2026, 4, 1),
            categoria="oposicion",
        )
        storage.save(it)
        it.is_relevant = True
        it.deadline_inscripcion = "2026-04-28"  # 3 días después de now
        it.enriched_version = ENRICHMENT_VERSION
        storage.update_enrichment(it)

        dashboard.export_all(storage, tmp_path / "out", last_run_at=now)
        storage.close()

        targets = json.loads(
            (tmp_path / "out" / "targets.json").read_text(encoding="utf-8")
        )
        sermas = next(t for t in targets if t["id"] == "T-01")
        assert sermas["urgent"] is True
        assert sermas["days_until"] == 3

    def test_irrelevant_no_cuenta_para_watchlist(self, tmp_path):
        """Items con is_relevant=false (falsos positivos) no deben aparecer
        como hits del organismo, aunque coincidan con el patrón."""
        from vigia.storage import ENRICHMENT_VERSION
        from datetime import datetime, timezone, date

        now = datetime(2026, 4, 25, 12, 0, 0, tzinfo=timezone.utc)
        storage = Storage(db_path=tmp_path / "seen.db")

        it = Item(
            source="boe",
            url="https://example.com/sermas-fp",
            titulo="SERMAS plazas Enfermería de Salud Mental",
            fecha=date(2026, 4, 1),
            categoria="oposicion",
        )
        storage.save(it)
        it.is_relevant = False  # ← descartado por el enricher
        it.relevance_reason = "Es Salud Mental, no Trabajo"
        it.enriched_version = ENRICHMENT_VERSION
        storage.update_enrichment(it)

        dashboard.export_all(storage, tmp_path / "out", last_run_at=now)
        storage.close()

        targets = json.loads(
            (tmp_path / "out" / "targets.json").read_text(encoding="utf-8")
        )
        sermas = next(t for t in targets if t["id"] == "T-01")
        assert sermas["hits"] == 0
        assert sermas["active"] is False


class TestChangelog:
    """Tests del extractor de FIELD NOTES desde `git log`.

    Creamos un repo git efímero en tmp_path con commits sintéticos de
    distintas formas (conventional + scope, sin scope, prefijos a filtrar)
    y verificamos qué se queda en el payload.
    """

    @staticmethod
    def _init_repo(tmp_path):
        import subprocess
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.test"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=tmp_path, check=True)
        return tmp_path

    _commit_counter = 0

    @classmethod
    def _commit(cls, repo, subject, body=""):
        import subprocess
        # Contador monotónico para evitar colisiones de nombre de fichero.
        cls._commit_counter += 1
        f = repo / f"file_{cls._commit_counter}.txt"
        f.write_text(f"content {cls._commit_counter}", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        msg = subject + ("\n\n" + body if body else "")
        subprocess.run(["git", "commit", "-q", "-m", msg], cwd=repo, check=True)

    def test_filtra_solo_conventional_commits_relevantes(self, tmp_path):
        repo = self._init_repo(tmp_path)
        self._commit(repo, "feat(api): nuevo endpoint", "Body con detalles")
        self._commit(repo, "fix(parser): corrige edge case")
        self._commit(repo, "chore: bump deps")           # filtrado
        self._commit(repo, "Update README")              # filtrado (sin prefijo)
        self._commit(repo, "ci(gh-pages): publica")
        self._commit(repo, "refactor(core): extrae módulo")
        self._commit(repo, "test: añade fixture")        # filtrado

        entries = dashboard._changelog_payload(repo_dir=repo, max_entries=10)
        kinds = [e["kind"] for e in entries]
        # 4 deberían pasar: feat, fix, ci, refactor
        assert sorted(kinds) == ["ci", "feat", "fix", "refactor"]

    def test_extrae_scope_y_titulo(self, tmp_path):
        repo = self._init_repo(tmp_path)
        self._commit(repo, "feat(dashboard): export JSON")

        entries = dashboard._changelog_payload(repo_dir=repo)
        assert len(entries) == 1
        e = entries[0]
        assert e["kind"] == "feat"
        assert e["scope"] == "dashboard"
        assert e["title"] == "export JSON"
        assert len(e["commit"]) == 7  # SHA corto

    def test_body_descarta_co_authored_y_lineas_vacias(self, tmp_path):
        repo = self._init_repo(tmp_path)
        body = "\n\nLínea útil que describe el cambio.\n\nCo-Authored-By: Claude <x@x.com>\n"
        self._commit(repo, "feat(x): foo", body)

        entries = dashboard._changelog_payload(repo_dir=repo)
        assert entries[0]["body"] == "Línea útil que describe el cambio."

    def test_max_entries_respetado(self, tmp_path):
        repo = self._init_repo(tmp_path)
        for i in range(6):
            self._commit(repo, f"feat(x): cambio {i}")

        entries = dashboard._changelog_payload(repo_dir=repo, max_entries=3)
        assert len(entries) == 3

    def test_orden_descendente_por_fecha(self, tmp_path):
        repo = self._init_repo(tmp_path)
        self._commit(repo, "feat(x): primero")
        self._commit(repo, "feat(x): segundo")
        self._commit(repo, "feat(x): tercero")

        entries = dashboard._changelog_payload(repo_dir=repo)
        # `git log` devuelve más reciente primero por defecto.
        assert entries[0]["title"] == "tercero"
        assert entries[-1]["title"] == "primero"

    def test_directorio_sin_git_devuelve_lista_vacia(self, tmp_path):
        # tmp_path está vacío, no es un repo git
        empty = tmp_path / "empty"
        empty.mkdir()
        entries = dashboard._changelog_payload(repo_dir=empty)
        assert entries == []

    def test_export_all_genera_changelog_json(self, tmp_path):
        """Smoke test del integrador: export_all escribe data/changelog.json
        aunque sea con array vacío en un dir sin git."""
        empty = tmp_path / "empty"
        empty.mkdir()
        storage = Storage(db_path=tmp_path / "seen.db")
        # Cambiamos cwd a un dir sin git para forzar payload vacío
        import os
        cwd = os.getcwd()
        try:
            os.chdir(empty)
            dashboard.export_all(storage, tmp_path / "out")
        finally:
            os.chdir(cwd)
        storage.close()

        path = tmp_path / "out" / "changelog.json"
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data == []


class TestExportAllExtras:
    def test_json_es_utf8_con_acentos(self, tmp_path):
        """Los títulos llevan acentos; el JSON debe preservarlos legibles."""
        storage = Storage(db_path=tmp_path / "seen.db")
        _seed(storage, [_item("Convocatoria Enfermería del Trabajo")])
        dashboard.export_all(storage, tmp_path / "out")
        storage.close()

        raw = (tmp_path / "out" / "items.json").read_text(encoding="utf-8")
        assert "Enfermería del Trabajo" in raw  # no escapado a \u00...
