"""
Tests del parser AENA (portal de convocatorias PFSrv server-rendered).

Estructura confirmada vía WebFetch 2026-05-24:
  <h3>{título}</h3>
  Fecha inicio inscripción: DD/MM/YYYY
  Fecha fin inscripción: DD/MM/YYYY
  [Bases / Doc] [Ver proceso] [Reclamaciones]

Cada convocatoria empieza con un <h3>; el bloque del item se extiende
hasta el siguiente <h3>. Hoy (2026-05-24) AENA tiene 10 convocatorias
listadas pero ninguna es de Enfermería; los tests reproducen la
estructura con un item de Enfermería añadido para validar el matching.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from vigia.sources import aena
from vigia.sources.aena import AENASource


def _resp(text: str, status: int = 200):
    r = MagicMock()
    r.status_code = status
    r.text = text
    r.raise_for_status = lambda: None
    return r


# HTML representativo recortado del portal real. 3 convocatorias: dos
# realistas (Selección Externa Nivel D — la real de hoy, y una de Técnico
# Mantenimiento) y una de Enfermería del Trabajo para validar el matching.
AENA_HTML = """
<html><body>
  <div class="contenido">
    <h3>CONVOCATORIA SELECCION EXTERNA (NIVEL D) 29/04/2026</h3>
    <p>Fecha inicio inscripción: 29/04/2026</p>
    <p>Fecha fin inscripción: 10/05/2026</p>
    <a href="/empleo/PFSrv?accion=basesNivelD">Bases / Doc</a>
    <a href="/empleo/PFSrv?accion=verProcesoNivelD">Ver proceso</a>

    <h3>CONVOCATORIA SELECCION ENFERMERO/A DEL TRABAJO 15/04/2026</h3>
    <p>Fecha inicio inscripción: 15/04/2026</p>
    <p>Fecha fin inscripción: 30/04/2026</p>
    <a href="/empleo/PFSrv?accion=basesEnfermeria">Bases / Doc</a>
    <a href="/empleo/PFSrv?accion=verProcesoEnfermeria">Ver proceso</a>

    <h3>CONVOCATORIA TECNICO MANTENIMIENTO 02/04/2026</h3>
    <p>Fecha inicio inscripción: 02/04/2026</p>
    <p>Fecha fin inscripción: 16/04/2026</p>
    <a href="/empleo/PFSrv?accion=basesTecnico">Bases / Doc</a>
  </div>
</body></html>
"""


class TestAENASource:
    def test_extrae_convocatoria_de_enfermeria(self):
        source = AENASource()
        with patch.object(
            aena.requests, "get", return_value=_resp(AENA_HTML),
        ):
            items = source.fetch(since_date=date(2000, 1, 1))

        assert len(items) == 1
        assert "ENFERMERO/A DEL TRABAJO" in items[0].title.upper()

    def test_descarta_convocatorias_sin_keyword(self):
        source = AENASource()
        with patch.object(
            aena.requests, "get", return_value=_resp(AENA_HTML),
        ):
            items = source.fetch(since_date=date(2000, 1, 1))

        titles_upper = " ".join(it.title.upper() for it in items)
        assert "NIVEL D" not in titles_upper
        assert "TECNICO MANTENIMIENTO" not in titles_upper

    def test_extrae_url_y_fecha_inicio_correctas(self):
        source = AENASource()
        with patch.object(
            aena.requests, "get", return_value=_resp(AENA_HTML),
        ):
            items = source.fetch(since_date=date(2000, 1, 1))

        item = items[0]
        assert item.url == \
            "https://empleo.aena.es/empleo/PFSrv?accion=basesEnfermeria"
        assert item.date == date(2026, 4, 15)

    def test_filtra_por_since_date(self):
        source = AENASource()
        with patch.object(
            aena.requests, "get", return_value=_resp(AENA_HTML),
        ):
            items = source.fetch(since_date=date(2026, 5, 1))

        # Enfermería abrió 15/04/2026 → fuera del rango.
        assert items == []

    def test_h3_sin_bloque_de_fechas_cae_a_today(self):
        """Si el bloque no tiene 'Fecha inicio inscripción', la fecha cae
        a today() (red de seguridad) — no se descarta el item."""
        html = """
        <html><body>
          <h3>Convocatoria Enfermería del Trabajo sin fechas explícitas</h3>
          <p>Más información próximamente</p>
        </body></html>
        """
        source = AENASource()
        with patch.object(
            aena.requests, "get", return_value=_resp(html),
        ):
            items = source.fetch(since_date=date(2000, 1, 1))

        assert len(items) == 1
        assert items[0].date == date.today()

    def test_url_sintetica_si_h3_sin_anchor_en_bloque(self):
        """Si el bloque del item no tiene <a> alguno, generamos URL
        sintética con fragment determinista."""
        html = """
        <html><body>
          <h3>Convocatoria Enfermería del Trabajo</h3>
          <p>Fecha inicio inscripción: 01/05/2026</p>
          <p>Fecha fin inscripción: 31/05/2026</p>
        </body></html>
        """
        source = AENASource()
        with patch.object(
            aena.requests, "get", return_value=_resp(html),
        ):
            items = source.fetch(since_date=date(2000, 1, 1))

        assert len(items) == 1
        assert items[0].url.startswith(
            "https://empleo.aena.es/empleo/PFSrv?accion=inicio#"
        )

    def test_listado_caido_devuelve_lista_vacia_con_error(self):
        source = AENASource()
        with patch.object(
            aena.requests, "get",
            side_effect=Exception("connection reset"),
        ):
            items = source.fetch(since_date=date(2000, 1, 1))

        assert items == []
        assert source.last_errors and "connection reset" in source.last_errors[0]

    def test_probe_url_es_listado(self):
        source = AENASource()
        assert source.probe_url == \
            "https://empleo.aena.es/empleo/PFSrv?accion=inicio"
