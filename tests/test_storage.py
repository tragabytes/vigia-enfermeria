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
