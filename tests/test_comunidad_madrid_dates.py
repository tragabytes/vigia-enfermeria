"""
Tests del parser Comunidad de Madrid centrados en la resolución de fechas.

Bug original (BACKLOG #1, observado 26/04/2026): cuando el listado del
buscador no exponía "Apertura: DD/MM/YYYY" (caso "En tramitación", "Plazo
indefinido", "Finalizado") la fuente caía a `date.today()` y todos los items
acababan etiquetados con la fecha del run del cron, falseando la métrica
`published` en el dashboard.

Estos tests fijan la cascada de fallbacks:
  1. Listado: "Apertura/Inicio: DD/MM/YYYY".
  2. Detalle: `.fecha-actualizacion` → último `.hito-fecha`.
  3. Título: año `(YYYY)` → `date(YYYY, 1, 1)`.
  4. `date.today()` con warning como red de seguridad final.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from vigia.sources import comunidad_madrid
from vigia.sources.comunidad_madrid import (
    ComunidadMadridSource,
    _date_from_detail_html,
    _date_from_listing,
    _year_from_title,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resp(text: str, status: int = 200):
    r = MagicMock()
    r.status_code = status
    r.text = text
    r.raise_for_status = lambda: None
    return r


def _listing_li(estado_text: str, title: str = "Bolsa de Enfermería del Trabajo (2024)"):
    """HTML mínimo de un `<li>` del buscador con el `div.estado` indicado."""
    return f"""
    <li>
      <div class="titulo"><h3><a href="/oferta-empleo/foo" title="{title}">{title}</a></h3></div>
      <div class="estado">{estado_text}</div>
    </li>
    """


# ---------------------------------------------------------------------------
# Listado
# ---------------------------------------------------------------------------


class TestListingDate:
    def test_apertura_legacy_extrae_fecha(self):
        """El patrón histórico 'Apertura de plazo: DD/MM/YYYY' sigue funcionando."""
        assert _date_from_listing("Apertura de plazo: 15/03/2026") == date(2026, 3, 15)

    def test_inicio_estado_en_plazo(self):
        """Caso real 'En plazo': 'Inicio: 21/04/2026 | Fin: 12/05/2026'."""
        text = "En plazo Inicio: 21/04/2026 Fin: 12/05/2026"
        assert _date_from_listing(text) == date(2026, 4, 21)

    def test_inicio_sin_dos_puntos(self):
        """Robusto a separadores: 'Inicio 21/04/2026' (sin colon)."""
        assert _date_from_listing("Inicio 21/04/2026") == date(2026, 4, 21)

    def test_estado_sin_fecha_devuelve_none(self):
        """'En tramitación' / 'Plazo indefinido' / 'Finalizado' no traen fecha."""
        for text in ("En tramitación", "Plazo indefinido", "Finalizado", ""):
            assert _date_from_listing(text) is None

    def test_fecha_invalida_devuelve_none(self):
        assert _date_from_listing("Apertura: 99/99/9999") is None


# ---------------------------------------------------------------------------
# Detalle
# ---------------------------------------------------------------------------


class TestDetailDate:
    def test_fecha_actualizacion_es_la_preferida(self):
        """`.fecha-actualizacion` gana al `.hito-fecha` cuando ambos existen."""
        html = """
        <html><body>
          <div class="fecha-actualizacion">Última actualización: 18/03/2026</div>
          <div class="hito-fecha">25/03/2026</div>
          <div class="hito-fecha">14/03/2022</div>
        </body></html>
        """
        assert _date_from_detail_html(html) == date(2026, 3, 18)

    def test_hito_fecha_mas_antiguo_si_no_hay_actualizacion(self):
        """Sin `.fecha-actualizacion` se coge el ÚLTIMO `.hito-fecha` (más antiguo)."""
        html = """
        <html><body>
          <div class="hito-fecha">14/03/2022</div>
          <div class="hito-fecha">14/03/2022</div>
          <div class="hito-fecha">27/12/2021</div>
        </body></html>
        """
        assert _date_from_detail_html(html) == date(2021, 12, 27)

    def test_html_sin_fechas_devuelve_none(self):
        assert _date_from_detail_html("<html><body><p>nada</p></body></html>") is None

    def test_fecha_actualizacion_malformada_cae_a_hito(self):
        """Si la actualización no parseable, sigue intentando con hitos."""
        html = """
        <html><body>
          <div class="fecha-actualizacion">Última actualización: pendiente</div>
          <div class="hito-fecha">15/01/2025</div>
        </body></html>
        """
        assert _date_from_detail_html(html) == date(2025, 1, 15)


# ---------------------------------------------------------------------------
# Título
# ---------------------------------------------------------------------------


class TestYearFromTitle:
    def test_anio_entre_parentesis(self):
        assert _year_from_title("Bolsa única (2024). Subsanación") == date(2024, 1, 1)

    def test_anio_fuera_de_rango_se_descarta(self):
        """Años absurdos (1999, 2099) se ignoran para evitar falsos positivos
        con cualquier número entre paréntesis."""
        assert _year_from_title("Algo (1999)") is None
        assert _year_from_title("Algo (2099)") is None

    def test_sin_anio_devuelve_none(self):
        assert _year_from_title("Bolsa única de Enfermería del Trabajo") is None

    def test_numero_no_anio_se_ignora(self):
        """`(123)` no es un año de 4 dígitos."""
        assert _year_from_title("Plaza (123)") is None


# ---------------------------------------------------------------------------
# Cascada completa via _parse_item
# ---------------------------------------------------------------------------


class TestCascada:
    def _parse(self, source, li_html):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(li_html, "lxml")
        li = soup.find("li")
        return source._parse_item(li, since_date=date(2000, 1, 1), seen_urls=set())

    def test_listing_da_la_fecha_sin_tocar_red(self):
        """Si el listado ya trae 'Inicio: ...', no se hace request al detalle."""
        source = ComunidadMadridSource()
        with patch.object(source, "_fetch_detail_date") as mock_detail:
            item = self._parse(
                source,
                _listing_li("En plazo Inicio: 21/04/2026 Fin: 12/05/2026"),
            )
        assert item.date == date(2026, 4, 21)
        mock_detail.assert_not_called()

    def test_sin_listing_baja_al_detalle(self):
        """'En tramitación' sin fecha → fetch del detalle con fecha-actualizacion."""
        source = ComunidadMadridSource()
        detail_html = (
            "<html><body><div class='fecha-actualizacion'>"
            "Última actualización: 18/03/2026</div></body></html>"
        )
        with patch.object(comunidad_madrid.requests, "get", return_value=_resp(detail_html)):
            item = self._parse(source, _listing_li("En tramitación"))
        assert item.date == date(2026, 3, 18)

    def test_detalle_404_cae_al_titulo(self):
        """Si el detalle falla (404, timeout), año del título salva el item."""
        source = ComunidadMadridSource()
        with patch.object(comunidad_madrid.requests, "get", side_effect=Exception("boom")):
            item = self._parse(
                source,
                _listing_li(
                    "En tramitación",
                    title="Bolsa única de Enfermería del Trabajo (2024). Subsanación",
                ),
            )
        assert item.date == date(2024, 1, 1)

    def test_todo_falla_cae_a_today_con_warning(self, caplog):
        """Sin listado, sin detalle parseable, sin año en título → today() + warning."""
        source = ComunidadMadridSource()
        empty_detail = "<html><body><p>nada</p></body></html>"
        with patch.object(
            comunidad_madrid.requests, "get", return_value=_resp(empty_detail)
        ):
            with caplog.at_level("WARNING", logger="vigia.sources.comunidad_madrid"):
                item = self._parse(
                    source,
                    _listing_li(
                        "En tramitación",
                        title="Bolsa de Enfermería del Trabajo sin año explícito",
                    ),
                )
        assert item.date == date.today()
        assert any("sin fecha resoluble" in rec.message for rec in caplog.records)
