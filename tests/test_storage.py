"""
Tests del módulo storage: migración idempotente del esquema y persistencia
del summary que añade el enricher.

La columna `summary` se añadió cuando expusimos la BD en el dashboard web.
Las BDs creadas antes de ese cambio (las que viven en la rama `state` del
repo) deben recibir la columna sin perder datos previos.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime

from vigia.storage import Item, Storage


def _make_item(**kw) -> Item:
    return Item(
        source=kw.get("source", "boe"),
        url=kw.get("url", "https://boe.es/x"),
        titulo=kw.get("titulo", "Convocatoria de prueba"),
        fecha=kw.get("fecha", date(2026, 4, 25)),
        categoria=kw.get("categoria", "oposicion"),
        summary=kw.get("summary", None),
    )


class TestMigracionIdempotente:
    def test_bd_nueva_tiene_columna_summary(self, tmp_path):
        s = Storage(db_path=tmp_path / "seen.db")
        cols = {row[1] for row in s._conn.execute("PRAGMA table_info(items)")}
        s.close()
        assert "summary" in cols

    def test_bd_legacy_sin_summary_se_migra_sin_perder_datos(self, tmp_path):
        """
        Simula una BD pre-migración: tabla `items` sin columna summary, con
        un registro ya guardado. Tras abrir con Storage(), la columna debe
        existir y el registro previo debe seguir intacto.
        """
        legacy_path = tmp_path / "legacy.db"
        conn = sqlite3.connect(str(legacy_path))
        conn.execute("""
            CREATE TABLE items (
                id_hash       TEXT PRIMARY KEY,
                source        TEXT NOT NULL,
                url           TEXT NOT NULL,
                titulo        TEXT NOT NULL,
                fecha         TEXT NOT NULL,
                categoria     TEXT NOT NULL,
                first_seen_at TEXT NOT NULL
            )
        """)
        conn.execute(
            "INSERT INTO items VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("hash1", "boe", "https://boe.es/x", "Item legacy",
             "2026-04-20", "oposicion", "2026-04-20T08:00:00"),
        )
        conn.commit()
        conn.close()

        s = Storage(db_path=legacy_path)
        cols = {row[1] for row in s._conn.execute("PRAGMA table_info(items)")}
        assert "summary" in cols

        rows = list(s._conn.execute("SELECT id_hash, titulo, summary FROM items"))
        s.close()
        assert len(rows) == 1
        assert rows[0][0] == "hash1"
        assert rows[0][1] == "Item legacy"
        assert rows[0][2] is None  # summary aún sin rellenar

    def test_migracion_es_idempotente(self, tmp_path):
        """Abrir Storage dos veces sobre la misma BD no debe fallar."""
        path = tmp_path / "seen.db"
        Storage(db_path=path).close()
        # Segunda apertura: la columna ya existe, ALTER TABLE NO debe ejecutarse.
        s = Storage(db_path=path)
        cols = {row[1] for row in s._conn.execute("PRAGMA table_info(items)")}
        s.close()
        assert "summary" in cols


class TestUpdateSummary:
    def test_update_summary_persiste_el_resumen(self, tmp_path):
        s = Storage(db_path=tmp_path / "seen.db")
        item = _make_item()
        s.save(item)

        item.summary = "6 plazas Enfermero/a del Trabajo · SERMAS · OEP 2025"
        s.update_summary(item)

        row = s._conn.execute(
            "SELECT summary FROM items WHERE id_hash = ?", (item.id_hash,)
        ).fetchone()
        s.close()
        assert row[0] == "6 plazas Enfermero/a del Trabajo · SERMAS · OEP 2025"

    def test_update_summary_sin_summary_no_hace_nada(self, tmp_path):
        """Si el enricher no rellenó summary, no debemos sobrescribir con NULL."""
        s = Storage(db_path=tmp_path / "seen.db")
        item = _make_item(summary="resumen original")
        s.save(item)

        item.summary = None
        s.update_summary(item)  # no debe pisar el valor previo

        row = s._conn.execute(
            "SELECT summary FROM items WHERE id_hash = ?", (item.id_hash,)
        ).fetchone()
        s.close()
        assert row[0] == "resumen original"

    def test_save_persiste_summary_si_viene_relleno(self, tmp_path):
        """Caso menos habitual: si el item ya trae summary, save() lo guarda."""
        s = Storage(db_path=tmp_path / "seen.db")
        item = _make_item(summary="resumen pre-existente")
        s.save(item)

        row = s._conn.execute(
            "SELECT summary FROM items WHERE id_hash = ?", (item.id_hash,)
        ).fetchone()
        s.close()
        assert row[0] == "resumen pre-existente"

    def test_filter_new_guarda_sin_summary_y_update_lo_añade(self, tmp_path):
        """Flujo realista: filter_new persiste sin summary, luego enricher
        rellena `item.summary` y llamamos update_summary."""
        s = Storage(db_path=tmp_path / "seen.db")
        items = [_make_item(titulo="A"), _make_item(titulo="B")]
        new = s.filter_new(items)
        assert len(new) == 2

        # Simulamos que el enricher rellenó summary solo en uno
        new[0].summary = "Resumen A"
        for it in new:
            s.update_summary(it)

        rows = dict(s._conn.execute("SELECT titulo, summary FROM items"))
        s.close()
        assert rows["A"] == "Resumen A"
        assert rows["B"] is None


class TestDiffSummarizerSupport:
    """Soporte de Storage para el diff_summarizer (Análisis B):
    persistencia de raw_text + change_summary y query del snapshot anterior."""

    def test_bd_nueva_tiene_columnas_diff(self, tmp_path):
        s = Storage(db_path=tmp_path / "seen.db")
        cols = {row[1] for row in s._conn.execute("PRAGMA table_info(items)")}
        s.close()
        assert "raw_text" in cols
        assert "change_summary" in cols
        assert "change_substantive" in cols

    def test_save_persiste_raw_text_si_viene_relleno(self, tmp_path):
        s = Storage(db_path=tmp_path / "seen.db")
        item = _make_item(titulo="Foo [snapshot abcdef0123]")
        item.raw_text = "Cuerpo limpio del snapshot"
        s.save(item)
        row = s._conn.execute(
            "SELECT raw_text FROM items WHERE id_hash = ?", (item.id_hash,)
        ).fetchone()
        s.close()
        assert row[0] == "Cuerpo limpio del snapshot"

    def test_save_persiste_raw_text_null_para_items_no_snapshot(self, tmp_path):
        s = Storage(db_path=tmp_path / "seen.db")
        item = _make_item()  # raw_text por defecto = None
        s.save(item)
        row = s._conn.execute(
            "SELECT raw_text FROM items WHERE id_hash = ?", (item.id_hash,)
        ).fetchone()
        s.close()
        assert row[0] is None

    def test_update_change_summary_persiste(self, tmp_path):
        s = Storage(db_path=tmp_path / "seen.db")
        item = _make_item()
        s.save(item)
        item.change_summary = "Publicada lista provisional de admitidos"
        item.change_substantive = True
        s.update_change_summary(item)
        row = s._conn.execute(
            "SELECT change_summary, change_substantive FROM items "
            "WHERE id_hash = ?", (item.id_hash,)
        ).fetchone()
        s.close()
        assert row[0] == "Publicada lista provisional de admitidos"
        assert row[1] == 1

    def test_update_change_substantive_false_se_persiste_como_cero(self, tmp_path):
        s = Storage(db_path=tmp_path / "seen.db")
        item = _make_item()
        s.save(item)
        item.change_substantive = False
        s.update_change_summary(item)
        row = s._conn.execute(
            "SELECT change_substantive FROM items WHERE id_hash = ?",
            (item.id_hash,)
        ).fetchone()
        s.close()
        assert row[0] == 0

    def test_get_previous_snapshot_raw_text_devuelve_anterior(self, tmp_path):
        s = Storage(db_path=tmp_path / "seen.db")
        # Snapshot antiguo, persistido primero
        old = _make_item(titulo="Foo [snapshot oldhash1234]")
        old.raw_text = "cuerpo viejo"
        old.first_seen_at = datetime(2026, 5, 20, 10, 0)
        s.save(old)
        # Snapshot nuevo
        new = _make_item(titulo="Foo [snapshot newhash5678]")
        new.raw_text = "cuerpo nuevo"
        new.first_seen_at = datetime(2026, 5, 25, 10, 0)
        s.save(new)
        prev = s.get_previous_snapshot_raw_text(
            source=new.source, url=new.url, exclude_id_hash=new.id_hash,
        )
        s.close()
        assert prev == "cuerpo viejo"

    def test_get_previous_snapshot_raw_text_sin_anterior_devuelve_none(self, tmp_path):
        s = Storage(db_path=tmp_path / "seen.db")
        item = _make_item(titulo="Foo [snapshot newhash5678]")
        item.raw_text = "cuerpo nuevo"
        s.save(item)
        prev = s.get_previous_snapshot_raw_text(
            source=item.source, url=item.url, exclude_id_hash=item.id_hash,
        )
        s.close()
        assert prev is None

    def test_get_previous_snapshot_raw_text_pre_migracion_devuelve_none(self, tmp_path):
        """Snapshot anterior pre-feature B: raw_text es NULL. La query
        debe devolver None (no podemos diffear contra NULL)."""
        s = Storage(db_path=tmp_path / "seen.db")
        old = _make_item(titulo="Foo [snapshot oldhash1234]")
        # raw_text deliberadamente None
        old.first_seen_at = datetime(2026, 5, 20, 10, 0)
        s.save(old)
        new = _make_item(titulo="Foo [snapshot newhash5678]")
        new.raw_text = "cuerpo nuevo"
        new.first_seen_at = datetime(2026, 5, 25, 10, 0)
        s.save(new)
        prev = s.get_previous_snapshot_raw_text(
            source=new.source, url=new.url, exclude_id_hash=new.id_hash,
        )
        s.close()
        assert prev is None


class TestDetailSnapshots:
    """Tabla auxiliar `detail_snapshots` — estado del DetailWatcher."""

    def test_bd_nueva_tiene_tabla_detail_snapshots(self, tmp_path):
        s = Storage(db_path=tmp_path / "seen.db")
        tables = {
            row[0] for row in s._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        s.close()
        assert "detail_snapshots" in tables

    def test_get_devuelve_none_cuando_no_hay_snapshot(self, tmp_path):
        s = Storage(db_path=tmp_path / "seen.db")
        assert s.get_detail_snapshot("https://example.com/a") is None
        s.close()

    def test_upsert_inserta_y_get_lo_devuelve(self, tmp_path):
        s = Storage(db_path=tmp_path / "seen.db")
        s.upsert_detail_snapshot(
            url="https://example.com/a",
            last_hash="abc123",
            last_body="cuerpo limpio",
            last_checked_at="2026-05-25T12:00:00",
        )
        snap = s.get_detail_snapshot("https://example.com/a")
        s.close()
        assert snap == ("abc123", "cuerpo limpio", "2026-05-25T12:00:00")

    def test_upsert_reescribe_si_url_existe(self, tmp_path):
        s = Storage(db_path=tmp_path / "seen.db")
        s.upsert_detail_snapshot(
            "https://example.com/a", "hash_v1", "body_v1", "2026-05-25T08:00:00"
        )
        s.upsert_detail_snapshot(
            "https://example.com/a", "hash_v2", "body_v2", "2026-05-26T08:00:00"
        )
        snap = s.get_detail_snapshot("https://example.com/a")
        s.close()
        assert snap == ("hash_v2", "body_v2", "2026-05-26T08:00:00")

    def test_migracion_idempotente_no_borra_snapshots(self, tmp_path):
        """Abrir Storage dos veces preserva los snapshots ya guardados."""
        path = tmp_path / "seen.db"
        s1 = Storage(db_path=path)
        s1.upsert_detail_snapshot(
            "https://example.com/x", "h1", "b1", "2026-05-25T08:00:00"
        )
        s1.close()

        s2 = Storage(db_path=path)
        snap = s2.get_detail_snapshot("https://example.com/x")
        s2.close()
        assert snap == ("h1", "b1", "2026-05-25T08:00:00")

    def test_legacy_db_sin_tabla_se_crea_sin_perder_items(self, tmp_path):
        """BD pre-A: tabla items pero no detail_snapshots. Al abrir,
        la tabla nueva se crea sin tocar la existente."""
        legacy_path = tmp_path / "legacy.db"
        conn = sqlite3.connect(str(legacy_path))
        conn.execute("""
            CREATE TABLE items (
                id_hash TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                url TEXT NOT NULL,
                titulo TEXT NOT NULL,
                fecha TEXT NOT NULL,
                categoria TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                summary TEXT
            )
        """)
        conn.execute(
            "INSERT INTO items VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("h", "boe", "u", "t", "2026-04-20", "oposicion",
             "2026-04-20T08:00:00", None),
        )
        conn.commit()
        conn.close()

        s = Storage(db_path=legacy_path)
        tables = {
            row[0] for row in s._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert "detail_snapshots" in tables
        # Item legacy intacto
        rows = list(s._conn.execute("SELECT id_hash, titulo FROM items"))
        s.close()
        assert rows == [("h", "t")]
