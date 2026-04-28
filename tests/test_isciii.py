"""
Tests del parser ISCIII (hash-watcher de proceso-selectivo).

Cubre:
  1. Limpieza del cuerpo (nav/header/footer descartados antes del hash).
  2. Extracción de fecha de publicación del cuerpo (formatos corto/largo).
  3. Emisión de un único RawItem con `[snapshot <hash>]` en el título.
  4. Idempotencia: mismo cuerpo → mismo título → mismo id_hash (filtrado
     por `filter_new` aguas abajo).
  5. Cambio sustantivo del cuerpo → snapshot distinto → id_hash distinto.
  6. Tolerancia a fallos: HTTP error y body vacío no levantan, registran
     en `last_errors` y devuelven lista vacía.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from vigia.sources.isciii import ISCIIISource, _extract_pub_date
from vigia.storage import Item


def _resp(html: str, status: int = 200):
    r = MagicMock()
    r.status_code = status
    r.text = html
    if status >= 400:
        r.raise_for_status = MagicMock(side_effect=Exception(f"HTTP {status}"))
    else:
        r.raise_for_status = lambda: None
    return r


HTML_BASE = """
<html><body>
<nav><a>Inicio</a><a>Bolsa</a></nav>
<header>Header del portal</header>
<main id="main-content">
  <h2>Bolsa de empleo</h2>
  <p>Convocatoria del proceso selectivo (fecha publicación 19/07/23).</p>
  <p>Documento de preguntas frecuentes y anexo III: Solicitud de participación.</p>
</main>
<footer>Footer del portal</footer>
</body></html>
"""

HTML_MODIFIED = """
<html><body>
<nav><a>Inicio</a></nav>
<main id="main-content">
  <h2>Bolsa de empleo</h2>
  <p>Convocatoria del proceso selectivo (fecha publicación 19/07/23).</p>
  <p>NUEVO ANEXO IV: Plaza de Enfermera Especialista en Enfermería del Trabajo.</p>
</main>
</body></html>
"""

HTML_VACIO = "<html><body></body></html>"


def test_extract_body_text_quita_nav_header_footer():
    src = ISCIIISource()
    text = src._extract_body_text(HTML_BASE)
    assert "Bolsa de empleo" in text
    assert "preguntas frecuentes" in text
    assert "Header del portal" not in text
    assert "Footer del portal" not in text
    assert "Inicio" not in text


def test_extract_pub_date_formato_corto():
    assert _extract_pub_date("fecha publicación 19/07/23") == date(2023, 7, 19)


def test_extract_pub_date_formato_largo():
    assert _extract_pub_date("Convocatoria fecha de publicación 19/07/2023.") == date(2023, 7, 19)


def test_extract_pub_date_sin_match_devuelve_none():
    assert _extract_pub_date("Documento sin fecha resoluble") is None


def test_fetch_emite_un_raw_item_con_snapshot_y_fecha_extraida():
    src = ISCIIISource()
    with patch("vigia.sources.isciii.requests.get", return_value=_resp(HTML_BASE)):
        items = src.fetch(date(2026, 1, 1))

    assert len(items) == 1
    raw = items[0]
    assert raw.source == "isciii"
    assert raw.url == "https://www.isciii.es/bolsa-empleo/proceso-selectivo"
    assert "snapshot" in raw.title
    assert raw.date == date(2023, 7, 19)
    assert "Bolsa de empleo" in raw.text
    assert src.last_errors == []


def test_fetch_idempotente_mismo_contenido_mismo_titulo():
    src = ISCIIISource()
    with patch("vigia.sources.isciii.requests.get", return_value=_resp(HTML_BASE)):
        a = src.fetch(date(2026, 1, 1))[0]
        b = src.fetch(date(2026, 1, 1))[0]
    assert a.title == b.title


def test_fetch_cambio_de_contenido_genera_snapshot_distinto():
    src = ISCIIISource()
    with patch("vigia.sources.isciii.requests.get", return_value=_resp(HTML_BASE)):
        a = src.fetch(date(2026, 1, 1))[0]
    with patch("vigia.sources.isciii.requests.get", return_value=_resp(HTML_MODIFIED)):
        b = src.fetch(date(2026, 1, 1))[0]
    assert a.title != b.title
    # El segundo snapshot incluye texto que matcheará el extractor.
    assert "Enfermería del Trabajo" in b.text


def test_id_hash_distinto_entre_snapshots():
    """El id_hash del Item se deriva de source|url|titulo. Snapshots
    distintos en title ⇒ id_hash distinto, así filter_new lo trata como
    item nuevo."""
    src = ISCIIISource()
    with patch("vigia.sources.isciii.requests.get", return_value=_resp(HTML_BASE)):
        raw_a = src.fetch(date(2026, 1, 1))[0]
    with patch("vigia.sources.isciii.requests.get", return_value=_resp(HTML_MODIFIED)):
        raw_b = src.fetch(date(2026, 1, 1))[0]
    item_a = Item(source=raw_a.source, url=raw_a.url, titulo=raw_a.title,
                  fecha=raw_a.date, categoria="otro")
    item_b = Item(source=raw_b.source, url=raw_b.url, titulo=raw_b.title,
                  fecha=raw_b.date, categoria="otro")
    assert item_a.id_hash != item_b.id_hash


def test_fetch_http_error_no_levanta_y_registra_last_errors():
    src = ISCIIISource()
    with patch("vigia.sources.isciii.requests.get", return_value=_resp("", status=500)):
        items = src.fetch(date(2026, 1, 1))
    assert items == []
    assert len(src.last_errors) == 1
    assert "ISCIII" in src.last_errors[0]


def test_fetch_excepcion_de_red_no_levanta_y_registra_last_errors():
    src = ISCIIISource()
    with patch("vigia.sources.isciii.requests.get",
               side_effect=Exception("connection reset")):
        items = src.fetch(date(2026, 1, 1))
    assert items == []
    assert len(src.last_errors) == 1
    assert "connection reset" in src.last_errors[0]


def test_fetch_body_vacio_no_emite_y_registra_last_errors():
    src = ISCIIISource()
    with patch("vigia.sources.isciii.requests.get", return_value=_resp(HTML_VACIO)):
        items = src.fetch(date(2026, 1, 1))
    assert items == []
    assert len(src.last_errors) == 1
    assert "vacío" in src.last_errors[0]


def test_fetch_sin_fecha_extraible_cae_a_today(monkeypatch):
    """Si la cascada no encuentra fecha en el cuerpo, fallback a today()."""
    from datetime import date as _date

    class FixedDate(_date):
        @classmethod
        def today(cls):
            return cls(2026, 4, 28)

    monkeypatch.setattr("vigia.sources.isciii.date", FixedDate)
    html = "<html><body><main>Cuerpo sin fecha de publicación válida</main></body></html>"
    src = ISCIIISource()
    with patch("vigia.sources.isciii.requests.get", return_value=_resp(html)):
        items = src.fetch(_date(2026, 1, 1))
    assert items[0].date == _date(2026, 4, 28)
