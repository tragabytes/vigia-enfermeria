"""
Tests del parser CM Ficha Enfermería del Trabajo (hash-watcher).

Cubre:
  1. Selector preciso del cuerpo (`article.node--type-main-information`)
     limpia ruido pero conserva contenido sustantivo.
  2. Extracción de fecha por cascada: `/docs/assets/YYYY/MM/DD/` →
     "Última actualización: DD mes YYYY" → today().
  3. Emisión de un único RawItem con `[snapshot <hash>]` en el título.
  4. Idempotencia: mismo cuerpo → mismo título → mismo id_hash.
  5. Cambio sustantivo del cuerpo → snapshot distinto → id_hash distinto.
  6. El extractor matchea el RawItem (la ficha menciona Enfermería del
     Trabajo en el cuerpo).
  7. Tolerancia a fallos: HTTP error / red / body vacío.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from vigia.extractor import extract
from vigia.sources.cm_ficha_enfermeria import (
    ComunidadMadridFichaEnfermeriaSource,
    _date_from_assets,
    _date_from_last_update_text,
)
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
<header>Cabecera del portal</header>
<nav><a>Inicio</a><a>Empleo</a></nav>
<main id="main-content">
  <article class="node node--type-main-information">
    <h1>Diplomado en Enfermería del Trabajo</h1>
    <p>Última actualización: 25 marzo 2026</p>
    <p>Proceso selectivo para el acceso a plazas de carácter laboral de la
       categoría profesional de Diplomado en Enfermería Especialista,
       Especialidad Enfermería del Trabajo (Grupo II, Nivel 8 Área D).</p>
    <p>Convocatoria: Orden 1074/2025, de 24 de abril (BOCM del 8 de mayo).
       Número de plazas: 9.</p>
    <a href="https://www.comunidad.madrid/docs/assets/2025/10/21/admitidos.pdf">Admitidos</a>
    <a href="https://www.comunidad.madrid/docs/assets/2026/03/25/cuestionario.pdf">Cuestionario</a>
  </article>
</main>
<footer>Pie de página</footer>
</body></html>
"""

HTML_MODIFIED = """
<html><body>
<main id="main-content">
  <article class="node node--type-main-information">
    <h1>Diplomado en Enfermería del Trabajo</h1>
    <p>Última actualización: 1 mayo 2026</p>
    <p>NUEVA FASE: publicada plantilla correctora definitiva del primer ejercicio.</p>
    <p>Convocatoria Enfermería del Trabajo: Orden 1074/2025.</p>
    <a href="https://www.comunidad.madrid/docs/assets/2026/05/01/plantilla.pdf">Plantilla</a>
  </article>
</main>
</body></html>
"""

HTML_VACIO = "<html><body></body></html>"


def test_extract_body_text_selecciona_solo_article_y_quita_nav_header_footer():
    src = ComunidadMadridFichaEnfermeriaSource()
    text = src._extract_body_text(HTML_BASE)
    assert "Diplomado en Enfermería del Trabajo" in text
    assert "Proceso selectivo" in text
    assert "Cabecera del portal" not in text
    assert "Pie de página" not in text
    assert "Inicio" not in text
    assert "Empleo" not in text


def test_date_from_assets_devuelve_la_maxima():
    html = ('<a href="/docs/assets/2025/10/21/x.pdf">a</a>'
            '<a href="/docs/assets/2026/03/25/y.pdf">b</a>'
            '<a href="/docs/assets/2026/01/12/z.pdf">c</a>')
    assert _date_from_assets(html) == date(2026, 3, 25)


def test_date_from_assets_sin_links_devuelve_none():
    assert _date_from_assets("<html>nada</html>") is None


def test_date_from_last_update_text_castellano():
    assert _date_from_last_update_text("Última actualización: 25 marzo 2026") == date(2026, 3, 25)


def test_date_from_last_update_text_mes_invalido_devuelve_none():
    assert _date_from_last_update_text("Última actualización: 25 brumario 2026") is None


def test_date_from_last_update_text_sin_match():
    assert _date_from_last_update_text("Documento sin marca de actualización") is None


def test_fetch_emite_un_raw_item_con_snapshot_y_fecha_de_assets():
    src = ComunidadMadridFichaEnfermeriaSource()
    with patch("vigia.sources.cm_ficha_enfermeria.requests.get",
               return_value=_resp(HTML_BASE)):
        items = src.fetch(date(2026, 1, 1))

    assert len(items) == 1
    raw = items[0]
    assert raw.source == "cm_ficha_enfermeria"
    assert raw.url == "https://www.comunidad.madrid/empleo/diplomado-enfermeria-trabajo"
    assert "snapshot" in raw.title
    # Prefiere la fecha de assets (más fiable) sobre la de "Última actualización".
    assert raw.date == date(2026, 3, 25)
    assert "Diplomado en Enfermería del Trabajo" in raw.text
    assert src.last_errors == []


def test_fetch_idempotente_mismo_contenido_mismo_titulo():
    src = ComunidadMadridFichaEnfermeriaSource()
    with patch("vigia.sources.cm_ficha_enfermeria.requests.get",
               return_value=_resp(HTML_BASE)):
        a = src.fetch(date(2026, 1, 1))[0]
        b = src.fetch(date(2026, 1, 1))[0]
    assert a.title == b.title


def test_fetch_cambio_de_contenido_genera_snapshot_distinto():
    src = ComunidadMadridFichaEnfermeriaSource()
    with patch("vigia.sources.cm_ficha_enfermeria.requests.get",
               return_value=_resp(HTML_BASE)):
        a = src.fetch(date(2026, 1, 1))[0]
    with patch("vigia.sources.cm_ficha_enfermeria.requests.get",
               return_value=_resp(HTML_MODIFIED)):
        b = src.fetch(date(2026, 1, 1))[0]
    assert a.title != b.title
    assert b.date == date(2026, 5, 1)


def test_id_hash_distinto_entre_snapshots():
    src = ComunidadMadridFichaEnfermeriaSource()
    with patch("vigia.sources.cm_ficha_enfermeria.requests.get",
               return_value=_resp(HTML_BASE)):
        raw_a = src.fetch(date(2026, 1, 1))[0]
    with patch("vigia.sources.cm_ficha_enfermeria.requests.get",
               return_value=_resp(HTML_MODIFIED)):
        raw_b = src.fetch(date(2026, 1, 1))[0]
    item_a = Item(source=raw_a.source, url=raw_a.url, titulo=raw_a.title,
                  fecha=raw_a.date, categoria="otro")
    item_b = Item(source=raw_b.source, url=raw_b.url, titulo=raw_b.title,
                  fecha=raw_b.date, categoria="otro")
    assert item_a.id_hash != item_b.id_hash


def test_extractor_matchea_el_snapshot_porque_el_cuerpo_menciona_enfermeria():
    """A diferencia del ISCIII, esta ficha SÍ menciona "Enfermería del
    Trabajo" en el cuerpo, así que cada snapshot pasará el matcher y
    generará una alerta real al usuario."""
    src = ComunidadMadridFichaEnfermeriaSource()
    with patch("vigia.sources.cm_ficha_enfermeria.requests.get",
               return_value=_resp(HTML_BASE)):
        raw = src.fetch(date(2026, 1, 1))[0]
    item = extract(raw)
    assert item is not None
    assert item.categoria == "oposicion"


def test_fetch_http_error_no_levanta_y_registra_last_errors():
    src = ComunidadMadridFichaEnfermeriaSource()
    with patch("vigia.sources.cm_ficha_enfermeria.requests.get",
               return_value=_resp("", status=500)):
        items = src.fetch(date(2026, 1, 1))
    assert items == []
    assert len(src.last_errors) == 1
    assert "ficha" in src.last_errors[0].lower()


def test_fetch_excepcion_de_red_no_levanta_y_registra_last_errors():
    src = ComunidadMadridFichaEnfermeriaSource()
    with patch("vigia.sources.cm_ficha_enfermeria.requests.get",
               side_effect=Exception("connection reset")):
        items = src.fetch(date(2026, 1, 1))
    assert items == []
    assert "connection reset" in src.last_errors[0]


def test_fetch_body_vacio_no_emite_y_registra_last_errors():
    src = ComunidadMadridFichaEnfermeriaSource()
    with patch("vigia.sources.cm_ficha_enfermeria.requests.get",
               return_value=_resp(HTML_VACIO)):
        items = src.fetch(date(2026, 1, 1))
    assert items == []
    assert "vacío" in src.last_errors[0]


def test_fetch_sin_fecha_extraible_cae_a_today(monkeypatch):
    """Sin assets ni 'Última actualización', fallback a today()."""
    from datetime import date as _date

    class FixedDate(_date):
        @classmethod
        def today(cls):
            return cls(2026, 4, 28)

    monkeypatch.setattr("vigia.sources.cm_ficha_enfermeria.date", FixedDate)
    html = """
    <html><body><main>
      <article class="node node--type-main-information">
        <h1>Diplomado en Enfermería del Trabajo</h1>
        <p>Cuerpo sin fechas resolubles.</p>
      </article>
    </main></body></html>
    """
    src = ComunidadMadridFichaEnfermeriaSource()
    with patch("vigia.sources.cm_ficha_enfermeria.requests.get",
               return_value=_resp(html)):
        items = src.fetch(_date(2026, 1, 1))
    assert items[0].date == _date(2026, 4, 28)
