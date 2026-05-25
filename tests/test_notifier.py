"""
Tests del notifier: cubre el header ACTUALIZACIÓN vs NUEVO según los
campos `change_substantive` y `change_summary` (Análisis B).
"""
from __future__ import annotations

from datetime import date

from vigia.notifier import _format_item
from vigia.storage import Item


def _make_item(**kw) -> Item:
    return Item(
        source=kw.get("source", "cm_ficha_enfermeria"),
        url=kw.get("url", "https://example.com/x"),
        titulo=kw.get(
            "titulo",
            "CM Ficha Enfermería del Trabajo [snapshot abc1234567]",
        ),
        fecha=kw.get("fecha", date(2026, 5, 25)),
        categoria=kw.get("categoria", "oposicion"),
        organismo=kw.get("organismo"),
        change_substantive=kw.get("change_substantive"),
        change_summary=kw.get("change_summary"),
    )


def test_item_normal_sin_diff_muestra_nuevo():
    """Item de listado o primer snapshot: header con 🟢 NUEVO."""
    item = _make_item(change_substantive=None, change_summary=None)
    lines = _format_item(item, date(2026, 5, 25))
    header = lines[0]
    assert "🟢" in header
    assert "NUEVO" in header
    assert "ACTUALIZACIÓN" not in header


def test_item_con_cambio_sustantivo_muestra_actualizacion():
    """change_substantive=True: header con 🟡 ACTUALIZACIÓN."""
    item = _make_item(
        change_substantive=True,
        change_summary="Publicada lista provisional de admitidos",
    )
    lines = _format_item(item, date(2026, 5, 25))
    header = lines[0]
    assert "🟡" in header
    assert "ACTUALIZACIÓN" in header
    assert "Publicada lista provisional de admitidos" in header


def test_item_actualizacion_sin_summary_muestra_header_basico():
    """Si fail-open del diff_summarizer no produjo resumen pero
    sí marcó como sustantivo, header sin frase añadida."""
    item = _make_item(
        change_substantive=True,
        change_summary=None,
    )
    lines = _format_item(item, date(2026, 5, 25))
    header = lines[0]
    assert "ACTUALIZACIÓN" in header
    # No hay frase añadida tras "ACTUALIZACIÓN en ..."
    assert ":" not in header.split("ACTUALIZACIÓN")[1].split("</b>")[0]


def test_item_organismo_se_concatena_en_actualizacion():
    item = _make_item(
        change_substantive=True,
        change_summary="Nueva fase",
        organismo="Comunidad de Madrid",
    )
    lines = _format_item(item, date(2026, 5, 25))
    header = lines[0]
    assert "Comunidad de Madrid" in header
    assert "Nueva fase" in header


def test_summary_se_escapa_html_correctamente():
    """change_summary con caracteres especiales debe escaparse."""
    item = _make_item(
        change_substantive=True,
        change_summary="<script>alert(1)</script>",
    )
    lines = _format_item(item, date(2026, 5, 25))
    header = lines[0]
    assert "<script>" not in header
    assert "&lt;script&gt;" in header
