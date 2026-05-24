"""
Tests del parser Ayuntamiento de Las Rozas (portal Convocatorias-en-plazo).

El listado contiene solo procesos con plazo abierto, así que es una
fuente de detección temprana respecto a BOCM. Hoy (2026-05-24) ningún
proceso vivo es de Enfermería; los tests reproducen la estructura HTML
real y añaden un item de Enfermería para validar el camino del matching.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from vigia.sources import las_rozas
from vigia.sources.las_rozas import LasRozasSource, _try_parse_pub_date


def _resp(text: str, status: int = 200):
    r = MagicMock()
    r.status_code = status
    r.text = text
    r.raise_for_status = lambda: None
    return r


# HTML representativo recortado del portal real (estructura validada vía
# WebFetch 2026-05-24). Una fila de Técnico de Emergencias Sanitarias
# (real, hoy) y una fila adicional de Enfermería del Trabajo añadida para
# probar el camino del matching.
LAS_ROZAS_HTML = """
<html><body>
  <table>
    <thead>
      <tr>
        <th>Expediente</th><th>Puesto</th><th>Plazo</th><th>Subgrupo</th>
        <th>Turno</th><th>Plazas</th><th>Tipo</th><th>Estado</th><th>Info</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td><a href="/expediente/PI-02-2025">PI-02/2025</a></td>
        <td>Técnico/a de Emergencias Sanitarias</td>
        <td>Desde el 23 de junio hasta el 18 de julio de 2025</td>
        <td>C1</td><td>Promoción Interna</td><td>21</td>
        <td>Laboral</td><td>Plazo abierto</td><td><a href="/bases/PI-02">Bases</a></td>
      </tr>
      <tr>
        <td><a href="/expediente/PE-05-2026">PE-05/2026</a></td>
        <td>Enfermero/a del Trabajo — Servicio de Prevención Municipal</td>
        <td>Desde el 12 de mayo hasta el 9 de junio de 2026</td>
        <td>A2</td><td>Libre</td><td>1</td>
        <td>Laboral</td><td>Plazo abierto</td><td><a href="/bases/PE-05">Bases</a></td>
      </tr>
      <tr>
        <td><a href="/expediente/PA-10-2026">PA-10/2026</a></td>
        <td>Auxiliar Administrativo</td>
        <td>Desde el 1 de abril hasta el 30 de abril de 2026</td>
        <td>C2</td><td>Libre</td><td>5</td>
        <td>Funcionario</td><td>Plazo abierto</td><td><a href="/bases/PA-10">Bases</a></td>
      </tr>
    </tbody>
  </table>
</body></html>
"""


class TestTryParsePubDate:
    def test_desde_el_dd_de_mes_hasta_el_dd_de_mes_de_yyyy(self):
        """Formato real del portal: año al final del 'hasta el ...'."""
        assert _try_parse_pub_date(
            "Desde el 23 de junio hasta el 18 de julio de 2025"
        ) == date(2025, 6, 23)

    def test_desde_el_dd_de_mes_de_yyyy_con_ano_explicito(self):
        """Formato alternativo con año en la apertura."""
        assert _try_parse_pub_date(
            "Desde el 26 de enero de 2026 hasta el 20 de febrero de 2026"
        ) == date(2026, 1, 26)

    def test_solo_hasta_el_se_usa_como_fallback(self):
        assert _try_parse_pub_date(
            "hasta el 30 de septiembre de 2025"
        ) == date(2025, 9, 30)

    def test_sin_fechas_devuelve_none(self):
        assert _try_parse_pub_date("texto sin fecha legible") is None

    def test_mes_invalido_devuelve_none(self):
        assert _try_parse_pub_date("Desde el 1 de undecimbre de 2025") is None


class TestLasRozasSource:
    def test_fila_con_enfermeria_genera_item(self):
        source = LasRozasSource()
        with patch.object(
            las_rozas.requests, "get", return_value=_resp(LAS_ROZAS_HTML),
        ):
            items = source.fetch(since_date=date(2000, 1, 1))

        titles = [it.title for it in items]
        assert any("Enfermero/a del Trabajo" in t for t in titles)

    def test_descarta_filas_sin_keyword(self):
        """Técnico de Emergencias Sanitarias y Auxiliar Administrativo
        no contienen `enfermer`/`salud laboral`/`prevencion de riesgos`."""
        source = LasRozasSource()
        with patch.object(
            las_rozas.requests, "get", return_value=_resp(LAS_ROZAS_HTML),
        ):
            items = source.fetch(since_date=date(2000, 1, 1))

        titles_upper = " ".join(it.title.upper() for it in items)
        assert "EMERGENCIAS" not in titles_upper
        assert "ADMINISTRATIVO" not in titles_upper

    def test_url_absoluta_desde_anchor(self):
        source = LasRozasSource()
        with patch.object(
            las_rozas.requests, "get", return_value=_resp(LAS_ROZAS_HTML),
        ):
            items = source.fetch(since_date=date(2000, 1, 1))

        enfermero = next(it for it in items if "Enfermero" in it.title)
        assert enfermero.url == \
            "https://www.lasrozas.es/expediente/PE-05-2026"

    def test_extrae_fecha_de_apertura(self):
        source = LasRozasSource()
        with patch.object(
            las_rozas.requests, "get", return_value=_resp(LAS_ROZAS_HTML),
        ):
            items = source.fetch(since_date=date(2000, 1, 1))

        enfermero = next(it for it in items if "Enfermero" in it.title)
        assert enfermero.date == date(2026, 5, 12)

    def test_filtra_por_since_date(self):
        source = LasRozasSource()
        with patch.object(
            las_rozas.requests, "get", return_value=_resp(LAS_ROZAS_HTML),
        ):
            items = source.fetch(since_date=date(2026, 6, 1))

        # Item de Enfermería abrió 12/05/2026 → fuera del rango.
        assert items == []

    def test_listado_caido_devuelve_lista_vacia_con_error(self):
        source = LasRozasSource()
        with patch.object(
            las_rozas.requests, "get",
            side_effect=Exception("connection reset"),
        ):
            items = source.fetch(since_date=date(2000, 1, 1))

        assert items == []
        assert source.last_errors and "connection reset" in source.last_errors[0]

    def test_fecha_fallback_a_row_text_si_celda_plazo_no_tiene_fechas(self):
        """Item en fase post-apertura: la celda 2 ya muestra el evento
        actual (no el plazo original). Caemos a buscar la fecha en el
        texto completo de la fila."""
        html_post_apertura = """
        <html><body><table><tbody>
          <tr>
            <td><a href="/expediente/PI-03/2024">PI-03/2024</a></td>
            <td>Diplomado Universitario de Enfermería (DUE)</td>
            <td>Publicación listado provisional de admitidos</td>
            <td>A2</td><td>Promoción interna</td><td>2</td>
            <td>Laboral fijo</td>
            <td>Alegaciones del 5 de mayo hasta el 19 de mayo de 2026</td>
            <td></td><td></td>
          </tr>
        </tbody></table></body></html>
        """
        source = LasRozasSource()
        with patch.object(
            las_rozas.requests, "get", return_value=_resp(html_post_apertura),
        ):
            items = source.fetch(since_date=date(2000, 1, 1))

        assert len(items) == 1
        # Fecha rescatada del texto de la celda 7. El texto dice "del 5 de
        # mayo hasta el 19 de mayo" — sin "Desde el", así que el regex de
        # apertura no matchea; cae al regex de "hasta el" → 19/5 (cierre).
        assert items[0].date == date(2026, 5, 19)

    def test_url_sintetica_si_no_hay_anchor(self):
        """Fila sin <a> en la primera celda → URL = listing + #hash(title)."""
        html_sin_anchor = """
        <html><body><table><tbody>
          <tr>
            <td>EXP-001</td>
            <td>Enfermería del Trabajo (sin enlace)</td>
            <td>Desde el 1 de mayo hasta el 30 de mayo de 2026</td>
          </tr>
        </tbody></table></body></html>
        """
        source = LasRozasSource()
        with patch.object(
            las_rozas.requests, "get", return_value=_resp(html_sin_anchor),
        ):
            items = source.fetch(since_date=date(2000, 1, 1))

        assert len(items) == 1
        assert items[0].url.startswith(
            "https://www.lasrozas.es/el-ayuntamiento/Convocatorias-en-plazo#"
        )

    def test_probe_url_es_listado(self):
        source = LasRozasSource()
        assert source.probe_url == \
            "https://www.lasrozas.es/el-ayuntamiento/Convocatorias-en-plazo"
