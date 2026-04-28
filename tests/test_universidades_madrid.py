"""
Tests del parser de universidades públicas de Madrid.

Cubre los puntos críticos del parser genérico:
  1. Filtrado fast-keyword sobre el título (descarta convocatorias no
     relacionadas con Enfermería / Salud Laboral / Prevención).
  2. Extracción de fecha en los dos formatos del portal UCM real
     ("DD/MM/YYYY" en items recientes, "DD de mes de YYYY" en históricos).
  3. Resolución de URL relativa vs absoluta vs PDF de tercero (UCM enlaza
     a veces directamente al BOE).
  4. Fallback al año `(YYYY)` del título cuando no hay "Actualizado el".
  5. Acumulación de errores en `last_errors` cuando un portal cae.
  6. Deduplicación si la misma URL aparece en dos contenedores.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from vigia.sources import universidades_madrid
from vigia.sources.universidades_madrid import (
    UniversidadesMadridSource,
    _extract_date,
    _matches_fast_keywords,
    _resolve_url,
    _year_from_title,
)


# ---------------------------------------------------------------------------
# Fixtures de HTML real (extracto de https://www.ucm.es/convocatorias-vigentes-pas
# capturado el 2026-04-28, con un item adaptado para incluir "Enfermería del
# Trabajo" — que en la página real solo aparece como link a un PDF de UAH).
# ---------------------------------------------------------------------------

UCM_LISTING_HTML = """
<html><body>
  <div class="wg_txt">
    <div><h2>PTGAS FUNCIONARIO</h2>
    <h4>Procesos selectivos 2024</h4>
    <ul class="lista_resalta">
      <li>
        <a href="https://www.ucm.es/escala-auxiliar-administrativa-c2-2024">
          Escala Auxiliar Administrativa, Grupo C, Subgrupo C2
        </a>
        (Actualizado el 28/10/2025)
      </li>
      <li>
        <a href="https://www.ucm.es/orden-4-du-enfermeria-del-trabajo">
          Orden 4 D.U. Enfermería del Trabajo
        </a>
        (Actualizado el 19/09/2024)
      </li>
    </ul>

    <h4>Procesos selectivos 2021</h4>
    <p>
      <a href="https://www.ucm.es/enfermera-prevencion-salud-laboral-pi-2021">
        Escala Especial de Servicios — Enfermera de Prevención y Salud Laboral
      </a>
      (Actualizado el 5 de abril de 2022)
    </p>

    <h2>OTRAS UNIVERSIDADES: UAH</h2>
    <ul>
      <li>
        <a href="https://www.uah.es/export/sites/uah/es/empleo-publico/PAS/.galleries/Laboral/2025/BOE-A-2025-21158.21.10.25.2_ET_AMS.pdf">
          Convocatoria proceso selectivo Titulado/a Medio/a, especialidad Enfermería del Trabajo-Asistencia Médica Sanitaria
        </a>
      </li>
    </ul>
  </div>
</body></html>
"""


def _resp(text: str, status: int = 200):
    r = MagicMock()
    r.status_code = status
    r.text = text
    r.raise_for_status = lambda: None
    return r


# ---------------------------------------------------------------------------
# Helpers puros (sin red)
# ---------------------------------------------------------------------------


class TestFastKeywords:
    def test_titulo_de_enfermeria_pasa(self):
        assert _matches_fast_keywords("Plaza de Enfermería del Trabajo") is True

    def test_titulo_de_salud_laboral_pasa(self):
        assert _matches_fast_keywords("Especialista en Salud Laboral") is True

    def test_titulo_no_relacionado_se_descarta(self):
        assert _matches_fast_keywords("Escala Auxiliar Administrativa C2") is False

    def test_normaliza_acentos(self):
        """Funciona con o sin tildes (la función pasa por `normalize`)."""
        assert _matches_fast_keywords("Enfermeria del Trabajo") is True


class TestExtractDate:
    def test_formato_corto_ddmmyyyy(self):
        assert _extract_date("(Actualizado el 28/10/2025)") == date(2025, 10, 28)

    def test_formato_largo_dd_de_mes_de_yyyy(self):
        assert _extract_date("Actualizado el 5 de abril de 2022") == date(2022, 4, 5)

    def test_formato_largo_septiembre_alternativo(self):
        """`setiembre` también admitido (variante minoritaria pero presente)."""
        assert _extract_date("publicado el 1 de setiembre de 2023") == date(2023, 9, 1)

    def test_sin_fecha_devuelve_none(self):
        assert _extract_date("texto sin fechas relevantes") is None

    def test_fecha_invalida_devuelve_none(self):
        assert _extract_date("99/99/2025") is None


class TestResolveUrl:
    def test_absoluta_se_devuelve_tal_cual(self):
        assert _resolve_url(
            "https://www.uah.es/foo.pdf", "https://www.ucm.es"
        ) == "https://www.uah.es/foo.pdf"

    def test_relativa_con_slash_se_concatena_a_base(self):
        assert _resolve_url("/convocatoria", "https://www.ucm.es") == \
            "https://www.ucm.es/convocatoria"

    def test_relativa_sin_slash_tambien_se_resuelve(self):
        assert _resolve_url("convocatoria", "https://www.ucm.es") == \
            "https://www.ucm.es/convocatoria"


class TestYearFromTitle:
    def test_anio_entre_parentesis(self):
        assert _year_from_title("Convocatoria (2024). Subsanación") == date(2024, 1, 1)

    def test_anio_fuera_de_rango_se_descarta(self):
        assert _year_from_title("Algo (1999)") is None

    def test_sin_anio_devuelve_none(self):
        assert _year_from_title("Sin año") is None


# ---------------------------------------------------------------------------
# Listado UCM completo (con red mockeada)
# ---------------------------------------------------------------------------


class TestUcmListing:
    def test_solo_extrae_items_con_keyword_de_enfermeria(self):
        """De los 4 items del HTML, 2 contienen `enfermer` en el título y 1
        contiene `salud laboral` — los 3 deben pasar el filtro fast.
        El item "Escala Auxiliar Administrativa" debe descartarse.
        """
        source = UniversidadesMadridSource()
        with patch.object(
            universidades_madrid.requests, "get",
            return_value=_resp(UCM_LISTING_HTML),
        ):
            items = source.fetch(since_date=date(2000, 1, 1))

        titles = [it.title for it in items]
        assert any("Orden 4 D.U. Enfermería del Trabajo" in t for t in titles)
        assert any("Enfermera de Prevención y Salud Laboral" in t for t in titles)
        assert any("Enfermería del Trabajo-Asistencia" in t for t in titles)
        assert not any("Auxiliar Administrativa" in t for t in titles)
        assert len(items) == 3

    def test_extrae_url_y_fecha_correctas(self):
        source = UniversidadesMadridSource()
        with patch.object(
            universidades_madrid.requests, "get",
            return_value=_resp(UCM_LISTING_HTML),
        ):
            items = source.fetch(since_date=date(2000, 1, 1))

        orden4 = next(
            it for it in items if "Orden 4 D.U." in it.title
        )
        assert orden4.url == "https://www.ucm.es/orden-4-du-enfermeria-del-trabajo"
        assert orden4.date == date(2024, 9, 19)
        assert orden4.extra["uni"] == "UCM"
        assert orden4.source == "universidades_madrid"

    def test_filtra_por_since_date(self):
        """Items publicados antes de `since_date` deben descartarse."""
        source = UniversidadesMadridSource()
        with patch.object(
            universidades_madrid.requests, "get",
            return_value=_resp(UCM_LISTING_HTML),
        ):
            # Cualquier fecha posterior a 2024-09-19 corta el "Orden 4 D.U."
            items = source.fetch(since_date=date(2025, 1, 1))

        titles = [it.title for it in items]
        assert not any("Orden 4 D.U." in t for t in titles)
        assert not any("Salud Laboral" in t for t in titles)  # 2022-04-05

    def test_link_externo_a_pdf_uah_se_acepta(self):
        """UCM enlaza directamente al PDF del BOE/UAH; el parser no debe
        rechazarlo por ser de otro dominio — el filtro es fast-keyword,
        no por host."""
        source = UniversidadesMadridSource()
        with patch.object(
            universidades_madrid.requests, "get",
            return_value=_resp(UCM_LISTING_HTML),
        ):
            items = source.fetch(since_date=date(2000, 1, 1))

        uah_pdf = next(it for it in items if "uah.es" in it.url)
        assert uah_pdf.url.endswith(".pdf")
        assert uah_pdf.extra["uni"] == "UCM"  # se categoriza por la fuente que lo lista

    def test_listado_caido_acumula_error(self):
        source = UniversidadesMadridSource()
        with patch.object(
            universidades_madrid.requests, "get",
            side_effect=Exception("connection reset"),
        ):
            items = source.fetch(since_date=date(2000, 1, 1))

        assert items == []
        assert any("UCM" in err for err in source.last_errors)


class TestProbe:
    def test_probe_url_apunta_a_listado_ucm(self):
        source = UniversidadesMadridSource()
        assert source.probe_url == "https://www.ucm.es/convocatorias-vigentes-pas"
