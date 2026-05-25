"""
Tests del parser Canal Isabel II Calendario-245 (hash-watcher).

Cubre:
  1. Selector `table.table` aísla el calendario y descarta el banner de
     marketing del portal Liferay.
  2. Extracción de fecha: máxima `dd/mm/yyyy` <= today() del cuerpo
     (la fase más reciente que ya ha empezado).
  3. Emisión de un único RawItem con `[snapshot <hash>]` en el título.
  4. Idempotencia: mismo cuerpo → mismo título → mismo id_hash.
  5. Cambio del calendario → snapshot distinto → id_hash distinto.
  6. El extractor matchea el RawItem porque el TÍTULO contiene
     "Enfermería del Trabajo" (la tabla no lo menciona).
  7. Tolerancia a fallos: HTTP error / red / body vacío.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from vigia.extractor import extract
from vigia.sources.canal_isabel_ii_calendario import (
    CanalIsabelIICalendarioSource,
    _latest_started_phase_date,
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


# Fragmento real del portal: el wrapper de marketing del portal Liferay
# (banner "Cuidar el agua...") + el contenedor `div#main-content` con la
# tabla del calendario dentro.
HTML_BASE = """
<html><body>
<header><nav>menú</nav></header>
<section id="content">
  <div class="marketing-banner">
    <h2>CUIDAR EL AGUA ES UNA LABOR DE TODOS</h2>
    <p>Banner de marketing que no debe ensuciar el hash.</p>
  </div>
  <div id="main-content">
    <h2>Calendario para Enfermero/a especialista en enfermería del trabajo</h2>
    <table class="table">
      <thead>
        <tr><th>FASE</th><th>FECHA INICIO</th><th>FECHA FIN</th><th>LISTADO</th></tr>
      </thead>
      <tbody>
        <tr><td>Admisión de solicitudes</td><td>10/04/2026</td><td>28/04/2026</td><td>—</td></tr>
        <tr><td>Listado provisional de admisión</td><td>25/05/2026</td><td>30/06/2026</td><td><a href="/listados/x.pdf">Ver</a></td></tr>
      </tbody>
    </table>
  </div>
</section>
<footer>pie</footer>
</body></html>
"""

# Nueva fase añadida: el portal publica el examen.
HTML_FASE_NUEVA = """
<html><body>
<div id="main-content">
  <table class="table">
    <thead>
      <tr><th>FASE</th><th>FECHA INICIO</th><th>FECHA FIN</th><th>LISTADO</th></tr>
    </thead>
    <tbody>
      <tr><td>Admisión de solicitudes</td><td>10/04/2026</td><td>28/04/2026</td><td>—</td></tr>
      <tr><td>Listado provisional de admisión</td><td>25/05/2026</td><td>30/06/2026</td><td><a href="/listados/x.pdf">Ver</a></td></tr>
      <tr><td>Listado definitivo de admitidos</td><td>15/07/2026</td><td>15/07/2026</td><td><a href="/listados/y.pdf">Ver</a></td></tr>
    </tbody>
  </table>
</div>
</body></html>
"""

HTML_SIN_TABLA = "<html><body><header>solo header</header></body></html>"


def test_extract_body_text_aisla_calendario_y_descarta_banner_marketing():
    src = CanalIsabelIICalendarioSource()
    text = src._extract_body_text(HTML_BASE)
    assert "Admisión de solicitudes" in text
    assert "10/04/2026" in text
    assert "Listado provisional de admisión" in text
    # El banner de marketing NO debe filtrarse al hash
    assert "CUIDAR EL AGUA" not in text
    assert "Banner de marketing" not in text
    # Tampoco el H2 del título de la página (vive fuera de table.table)
    assert "Calendario para Enfermero" not in text


def test_latest_started_phase_date_devuelve_max_pasada(monkeypatch):
    from datetime import date as _date

    class FixedDate(_date):
        @classmethod
        def today(cls):
            return cls(2026, 5, 25)

    monkeypatch.setattr(
        "vigia.sources.canal_isabel_ii_calendario.date", FixedDate
    )
    text = "Inicio 10/04/2026 Fin 28/04/2026 Provisional 25/05/2026 Final 30/06/2026"
    # 30/06 es futuro; 25/05 es la última fase iniciada
    assert _latest_started_phase_date(text) == _date(2026, 5, 25)


def test_latest_started_phase_date_sin_fechas_pasadas_devuelve_none(monkeypatch):
    from datetime import date as _date

    class FixedDate(_date):
        @classmethod
        def today(cls):
            return cls(2026, 1, 1)

    monkeypatch.setattr(
        "vigia.sources.canal_isabel_ii_calendario.date", FixedDate
    )
    text = "Todas las fechas futuras: 10/04/2026 28/04/2026"
    assert _latest_started_phase_date(text) is None


def test_latest_started_phase_date_ignora_fechas_invalidas():
    # 99/99/9999 no es una fecha válida
    text = "99/99/9999 y la real 15/03/2020"
    # Sólo la válida y pasada cuenta
    assert _latest_started_phase_date(text) == date(2020, 3, 15)


def test_fetch_emite_un_raw_item_con_snapshot(monkeypatch):
    from datetime import date as _date

    class FixedDate(_date):
        @classmethod
        def today(cls):
            return cls(2026, 5, 25)

    monkeypatch.setattr(
        "vigia.sources.canal_isabel_ii_calendario.date", FixedDate
    )
    src = CanalIsabelIICalendarioSource()
    with patch(
        "vigia.sources.canal_isabel_ii_calendario.requests.get",
        return_value=_resp(HTML_BASE),
    ):
        items = src.fetch(_date(2026, 1, 1))

    assert len(items) == 1
    raw = items[0]
    assert raw.source == "canal_isabel_ii_calendario"
    assert raw.url == "https://www.convocatoriascanaldeisabelsegunda.es/calendario-245"
    assert "snapshot" in raw.title
    assert "Enfermería del Trabajo" in raw.title
    # Última fase iniciada (25/05) coincide con today
    assert raw.date == _date(2026, 5, 25)
    assert "Admisión de solicitudes" in raw.text
    assert src.last_errors == []


def test_fetch_idempotente_mismo_contenido_mismo_titulo():
    src = CanalIsabelIICalendarioSource()
    with patch(
        "vigia.sources.canal_isabel_ii_calendario.requests.get",
        return_value=_resp(HTML_BASE),
    ):
        a = src.fetch(date(2026, 1, 1))[0]
        b = src.fetch(date(2026, 1, 1))[0]
    assert a.title == b.title


def test_fetch_cambio_de_contenido_genera_snapshot_distinto():
    src = CanalIsabelIICalendarioSource()
    with patch(
        "vigia.sources.canal_isabel_ii_calendario.requests.get",
        return_value=_resp(HTML_BASE),
    ):
        a = src.fetch(date(2026, 1, 1))[0]
    with patch(
        "vigia.sources.canal_isabel_ii_calendario.requests.get",
        return_value=_resp(HTML_FASE_NUEVA),
    ):
        b = src.fetch(date(2026, 1, 1))[0]
    assert a.title != b.title


def test_id_hash_distinto_entre_snapshots():
    src = CanalIsabelIICalendarioSource()
    with patch(
        "vigia.sources.canal_isabel_ii_calendario.requests.get",
        return_value=_resp(HTML_BASE),
    ):
        raw_a = src.fetch(date(2026, 1, 1))[0]
    with patch(
        "vigia.sources.canal_isabel_ii_calendario.requests.get",
        return_value=_resp(HTML_FASE_NUEVA),
    ):
        raw_b = src.fetch(date(2026, 1, 1))[0]
    item_a = Item(
        source=raw_a.source, url=raw_a.url, titulo=raw_a.title,
        fecha=raw_a.date, categoria="otro",
    )
    item_b = Item(
        source=raw_b.source, url=raw_b.url, titulo=raw_b.title,
        fecha=raw_b.date, categoria="otro",
    )
    assert item_a.id_hash != item_b.id_hash


def test_extractor_matchea_porque_titulo_contiene_enfermeria_del_trabajo():
    """La tabla sólo lleva nombres de fases — sin la keyword. El matcher
    pasa porque el título de RawItem incluye "Enfermería del Trabajo"."""
    src = CanalIsabelIICalendarioSource()
    with patch(
        "vigia.sources.canal_isabel_ii_calendario.requests.get",
        return_value=_resp(HTML_BASE),
    ):
        raw = src.fetch(date(2026, 1, 1))[0]
    item = extract(raw)
    assert item is not None
    assert item.source == "canal_isabel_ii_calendario"


def test_fetch_http_error_no_levanta_y_registra_last_errors():
    src = CanalIsabelIICalendarioSource()
    with patch(
        "vigia.sources.canal_isabel_ii_calendario.requests.get",
        return_value=_resp("", status=500),
    ):
        items = src.fetch(date(2026, 1, 1))
    assert items == []
    assert len(src.last_errors) == 1
    assert "calendario-245" in src.last_errors[0]


def test_fetch_excepcion_de_red_no_levanta_y_registra_last_errors():
    src = CanalIsabelIICalendarioSource()
    with patch(
        "vigia.sources.canal_isabel_ii_calendario.requests.get",
        side_effect=Exception("connection reset"),
    ):
        items = src.fetch(date(2026, 1, 1))
    assert items == []
    assert "connection reset" in src.last_errors[0]


def test_fetch_sin_tabla_cae_a_body_pero_si_quedara_vacio_registra_error():
    """Sin `table.table` ni `div#main-content`, cae a `body`. Si el body
    no contuviera texto útil, registra last_errors."""
    src = CanalIsabelIICalendarioSource()
    with patch(
        "vigia.sources.canal_isabel_ii_calendario.requests.get",
        return_value=_resp("<html><body></body></html>"),
    ):
        items = src.fetch(date(2026, 1, 1))
    assert items == []
    assert "vacío" in src.last_errors[0]
