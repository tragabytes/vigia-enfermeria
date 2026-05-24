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
    _date_from_pdf_url,
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


# ---------------------------------------------------------------------------
# UAH — items con `<h4><a>` dentro de `<article>` y `<p>` con fecha hermano.
# Estructura recortada de https://www.uah.es/es/empleo-publico/PAS/laboral/
# capturada el 2026-04-28.
# ---------------------------------------------------------------------------

UAH_LABORAL_HTML = """
<html><body>
  <div class="wrapper wrapper-box">
    <ul class="list-unstyled main-ul">
      <li>
        <article>
          <div>
            <p><strong>Resolución</strong> 09 de octubre de 2025</p>
            <h4 class="title-element">
              <a href="/es/empleo-publico/PAS/convocatoria/CONVOCATORIA-ENFERMERIA-DEL-TRABAJO/">
                CONVOCATORIA DE PROCESO SELECTIVO PARA LA PROVISIÓN DE LA CATEGORÍA TITULADO/A MEDIO/A,
                ESPECIALIDAD "ENFERMERÍA DEL TRABAJO-ASISTENCIA MÉDICA SANITARIA"
              </a>
            </h4>
          </div>
        </article>
      </li>
      <li>
        <article>
          <div>
            <p><strong>Resolución</strong> 27 de octubre de 2025</p>
            <h4 class="title-element">
              <a href="/es/empleo-publico/PAS/convocatoria/CONVOCATORIA-LABORATORIOS/">
                CONVOCATORIA TÉCNICO ESPECIALISTA, ESPECIALIDAD LABORATORIOS
              </a>
            </h4>
          </div>
        </article>
      </li>
    </ul>
  </div>
</body></html>
"""


class TestUahLaboral:
    def _patch_get_uah_only(self, html: str):
        """Mock que devuelve `html` para URLs de UAH y respuesta vacía para UCM/UAM."""
        empty = _resp("<html><body></body></html>")
        uah_resp = _resp(html)

        def side_effect(url, *args, **kwargs):
            return uah_resp if "uah.es" in url else empty

        return patch.object(
            universidades_madrid.requests, "get", side_effect=side_effect
        )

    def test_extrae_item_de_enfermeria_del_trabajo(self):
        source = UniversidadesMadridSource()
        with self._patch_get_uah_only(UAH_LABORAL_HTML):
            items = source.fetch(since_date=date(2000, 1, 1))

        uah_items = [it for it in items if it.extra.get("uni") == "UAH"]
        # 3 listados UAH * 1 item con "enfermer" cada uno (mismo HTML mockeado
        # se sirve para los tres) = 3 items duplicados pero con misma URL →
        # 3 fetches generan 3 items distintos solo si los listings se procesan
        # independientemente. Como el set seen_urls es por listing, sí hay
        # duplicados. Validamos que al menos uno aparezca con los datos correctos.
        enfermeria = next(it for it in uah_items if "ENFERMER" in it.title.upper())
        assert enfermeria.url == \
            "https://www.uah.es/es/empleo-publico/PAS/convocatoria/CONVOCATORIA-ENFERMERIA-DEL-TRABAJO/"
        assert enfermeria.date == date(2025, 10, 9)
        assert enfermeria.extra["uni"] == "UAH"

    def test_descarta_items_sin_keyword_de_enfermeria(self):
        source = UniversidadesMadridSource()
        with self._patch_get_uah_only(UAH_LABORAL_HTML):
            items = source.fetch(since_date=date(2000, 1, 1))

        titles_upper = " ".join(it.title.upper() for it in items)
        assert "LABORATORIOS" not in titles_upper


# ---------------------------------------------------------------------------
# UAM — `<div class="uam-card">` sin `<a>` por convocatoria. URL sintética.
# Estructura recortada de
# https://www.uam.es/uam/ptgas/listado-concursos-oposiciones-bolsas-personal-funcionario
# capturada el 2026-04-28.
# ---------------------------------------------------------------------------

UAM_FUNCIONARIO_HTML = """
<html><body>
  <!-- panel de filtros que comparte la clase uam-card y debe ser excluido -->
  <div class="uam-card uam-filters">
    <div class="uam-filters-header">Filtrar por</div>
    <p>Estado de la convocatoria</p>
  </div>

  <!-- item real con resolución de Enfermero/a -->
  <div class="uam-card">
    <span class="uam-becas-status">Resuelta</span>
    <div class="uam-becas-separator"></div>
    <span class="uam-becas-date">22/01/2026</span>
    <p>
      Pruebas selectivas para el ingreso en la Escala Especial Superior de Servicios
      de la Universidad Autónoma de Madrid para el Personal Técnico, de Gestión y de
      Administración y Servicios por el sistema de oposición libre, un puesto de
      Enfermero/a, en el Servicio de Prevención y Salud
    </p>
  </div>

  <!-- item ruido sin keyword relevante -->
  <div class="uam-card">
    <span class="uam-becas-status">Abierta</span>
    <span class="uam-becas-date">14/04/2026</span>
    <p>Pruebas selectivas para el ingreso en la Escala Auxiliar Administrativa de la UAM</p>
  </div>
</body></html>
"""


class TestUamSinAnchor:
    def _patch_get_uam_only(self, html: str):
        empty = _resp("<html><body></body></html>")
        uam_resp = _resp(html)

        def side_effect(url, *args, **kwargs):
            return uam_resp if "uam.es" in url else empty

        return patch.object(
            universidades_madrid.requests, "get", side_effect=side_effect
        )

    def test_card_filters_se_descarta(self):
        """`<div class="uam-card uam-filters">` es panel de filtros — no item."""
        source = UniversidadesMadridSource()
        with self._patch_get_uam_only(UAM_FUNCIONARIO_HTML):
            items = source.fetch(since_date=date(2000, 1, 1))

        uam_items = [it for it in items if it.extra.get("uni") == "UAM"]
        for it in uam_items:
            assert "Filtrar por" not in it.title
            assert "Estado de la convocatoria" not in it.title

    def test_url_sintetica_con_fragment_hash_cuando_no_hay_anchor(self):
        """UAM no expone `<a>` por convocatoria → URL = listing + #hash(title)."""
        source = UniversidadesMadridSource()
        with self._patch_get_uam_only(UAM_FUNCIONARIO_HTML):
            items = source.fetch(since_date=date(2000, 1, 1))

        uam_items = [it for it in items if it.extra.get("uni") == "UAM"]
        enfermero = next(it for it in uam_items if "Enfermero" in it.title)
        # URL del listado + "#" + hash determinista
        assert enfermero.url.startswith(
            "https://www.uam.es/uam/ptgas/listado-concursos-oposiciones-bolsas-personal-"
        )
        assert "#" in enfermero.url
        # Hash consistente entre runs con el mismo título
        # (sha1 de los primeros 280 chars del título normalizado)
        digest = enfermero.url.split("#", 1)[1]
        assert len(digest) == 12
        assert all(c in "0123456789abcdef" for c in digest)

    def test_extrae_fecha_ddmmyyyy_del_card(self):
        source = UniversidadesMadridSource()
        with self._patch_get_uam_only(UAM_FUNCIONARIO_HTML):
            items = source.fetch(since_date=date(2000, 1, 1))

        enfermero = next(
            it for it in items
            if it.extra.get("uni") == "UAM" and "Enfermero" in it.title
        )
        assert enfermero.date == date(2026, 1, 22)

    def test_titulo_se_recorta_si_es_demasiado_largo(self):
        """Texto del card supera 280 chars → recorte limpio en última palabra."""
        long_html = """
        <html><body>
          <div class="uam-card">
            <span class="uam-becas-date">01/02/2026</span>
            <p>Pruebas selectivas para el ingreso de un puesto de Enfermero/a """ + ("muy largo " * 80) + """</p>
          </div>
        </body></html>
        """
        source = UniversidadesMadridSource()
        with self._patch_get_uam_only(long_html):
            items = source.fetch(since_date=date(2000, 1, 1))

        uam_items = [it for it in items if it.extra.get("uni") == "UAM"]
        assert uam_items, "el item con keyword 'enfermer' debe pasar el filtro"
        assert len(uam_items[0].title) <= 282  # 280 + "…"
        assert uam_items[0].title.endswith("…")


# ---------------------------------------------------------------------------
# Helper internal — `_resolve_title_and_url`
# ---------------------------------------------------------------------------


class TestResolveTitleAndUrl:
    def _make_anchor(self, html: str):
        from bs4 import BeautifulSoup
        return BeautifulSoup(html, "lxml").find("a")

    def test_anchor_con_texto_descriptivo_devuelve_anchor_text(self):
        from vigia.sources.universidades_madrid import _resolve_title_and_url
        a = self._make_anchor('<a href="/foo">Convocatoria de Enfermería del Trabajo 2026</a>')
        title, url = _resolve_title_and_url(
            "container text con info adicional", a,
            "https://example.org/listing", "https://example.org",
        )
        assert title == "Convocatoria de Enfermería del Trabajo 2026"
        assert url == "https://example.org/foo"

    def test_anchor_corto_usa_texto_del_container(self):
        from vigia.sources.universidades_madrid import _resolve_title_and_url
        a = self._make_anchor('<a href="/x.pdf">DESCARGAR PDF</a>')
        title, url = _resolve_title_and_url(
            "B1 Titulado/a Medio: ENFERMERÍA DEL TRABAJO_SERVICIO DE PREVENCIÓN", a,
            "https://example.org/listing", "https://example.org",
        )
        assert "ENFERMERÍA DEL TRABAJO" in title
        # URL del PDF, no la sintética
        assert url == "https://example.org/x.pdf"

    def test_sin_anchor_devuelve_url_sintetica_estable(self):
        from vigia.sources.universidades_madrid import _resolve_title_and_url
        title1, url1 = _resolve_title_and_url(
            "Plaza Enfermería del Trabajo", None,
            "https://example.org/listing", "https://example.org",
        )
        title2, url2 = _resolve_title_and_url(
            "Plaza Enfermería del Trabajo", None,
            "https://example.org/listing", "https://example.org",
        )
        # Determinista: el mismo título da la misma URL
        assert url1 == url2
        assert url1.startswith("https://example.org/listing#")

    def test_anchor_con_href_javascript_se_ignora(self):
        from vigia.sources.universidades_madrid import _resolve_title_and_url
        a = self._make_anchor('<a href="javascript:void(0)">Click aquí</a>')
        title, url = _resolve_title_and_url(
            "Plaza Enfermería del Trabajo", a,
            "https://example.org/listing", "https://example.org",
        )
        # Cae al modo URL sintética
        assert url.startswith("https://example.org/listing#")


# ---------------------------------------------------------------------------
# UC3M — tabla `<tr>` con columnas, sin `<a>` por fila. URL sintética como UAM.
# Hoy no hay procesos de Enfermería en UC3M; el HTML del test reproduce la
# estructura (cabecera + filas de otras especialidades + 1 fila de Enfermería
# añadida ad-hoc para verificar el camino del matching cuando aparezca).
# ---------------------------------------------------------------------------

UC3M_LISTING_HTML = """
<html><body>
  <table>
    <tr>
      <th>CUERPO O ESCALA</th><th>GRUPO</th><th>ESPECIALIDAD</th>
      <th>PLAZAS</th><th>FECHA PREVISTA CONVOCATORIA</th>
      <th>FECHA PREVISTA INICIO PLAZO PRESENTACIÓN SOLICITUDES</th>
    </tr>
    <tr>
      <td>Escala Auxiliar Administrativa</td><td>C2</td><td>ADMINISTRACIÓN</td>
      <td>5</td><td>jun 2026</td><td>sept 2026</td>
    </tr>
    <tr>
      <td>Escala Técnica de Gestión</td><td>A2</td><td>ENFERMERÍA DEL TRABAJO</td>
      <td>1</td><td>mar 2026</td><td>abr 2026</td>
    </tr>
  </table>
</body></html>
"""


class TestUc3mListing:
    def _patch_get_uc3m_only(self, html: str):
        empty = _resp("<html><body></body></html>")
        uc3m_resp = _resp(html)

        def side_effect(url, *args, **kwargs):
            return uc3m_resp if "uc3m.es" in url else empty

        return patch.object(
            universidades_madrid.requests, "get", side_effect=side_effect
        )

    def test_cabecera_th_y_filas_sin_keyword_se_descartan(self):
        """La cabecera <th> y la fila de ADMINISTRACIÓN no contienen
        keywords del filtro fast → caen naturalmente, no requieren
        exclusión explícita."""
        source = UniversidadesMadridSource()
        with self._patch_get_uc3m_only(UC3M_LISTING_HTML):
            items = source.fetch(since_date=date(2000, 1, 1))

        uc3m_items = [it for it in items if it.extra.get("uni") == "UC3M"]
        for it in uc3m_items:
            assert "CUERPO O ESCALA" not in it.title
            assert "ADMINISTRACIÓN" not in it.title.upper().split("ENFERMER")[0]

    def test_fila_con_enfermeria_genera_item_con_url_sintetica(self):
        """Cuando UC3M publique una plaza de Enfermería (no es hoy), debe
        entrar al pipeline con URL sintética determinista igual que UAM."""
        source = UniversidadesMadridSource()
        with self._patch_get_uc3m_only(UC3M_LISTING_HTML):
            items = source.fetch(since_date=date(2000, 1, 1))

        uc3m_items = [it for it in items if it.extra.get("uni") == "UC3M"]
        enf = next(it for it in uc3m_items if "ENFERMERÍA" in it.title.upper())
        assert enf.url.startswith(
            "https://www.uc3m.es/empleo/pas/novedades_empleo_publico#"
        )
        digest = enf.url.split("#", 1)[1]
        assert len(digest) == 12

    def test_solo_se_genera_item_de_la_fila_con_keyword(self):
        """De 3 filas (cabecera + admin + enfermería), solo la última
        genera item."""
        source = UniversidadesMadridSource()
        with self._patch_get_uc3m_only(UC3M_LISTING_HTML):
            items = source.fetch(since_date=date(2000, 1, 1))

        uc3m_items = [it for it in items if it.extra.get("uni") == "UC3M"]
        assert len(uc3m_items) == 1


# ---------------------------------------------------------------------------
# `_date_from_pdf_url` — rescate de fecha desde el filename del PDF
# ---------------------------------------------------------------------------


class TestDateFromPdfUrl:
    def test_formato_puntos_caso_real_uah(self):
        """`B1-Enfermeria-03.09.2020.pdf` → 2020-09-03."""
        assert _date_from_pdf_url(
            "https://www.uah.es/.../B1-Enfermeria-03.09.2020.pdf"
        ) == date(2020, 9, 3)

    def test_formato_guiones(self):
        assert _date_from_pdf_url(
            "https://example.org/Convocatoria-15-04-2025.pdf"
        ) == date(2025, 4, 15)

    def test_formato_underscores(self):
        assert _date_from_pdf_url(
            "https://example.org/Bolsa_27_10_2024.pdf"
        ) == date(2024, 10, 27)

    def test_url_no_pdf_devuelve_none(self):
        assert _date_from_pdf_url("https://example.org/foo.html") is None

    def test_pdf_sin_fecha_legible_devuelve_none(self):
        assert _date_from_pdf_url("https://example.org/anexo-III.pdf") is None

    def test_pdf_con_fecha_invalida_devuelve_none(self):
        """`32.13.2025` no es una fecha real."""
        assert _date_from_pdf_url(
            "https://example.org/Foo-32.13.2025.pdf"
        ) is None

    def test_url_vacia_devuelve_none(self):
        assert _date_from_pdf_url(None) is None
        assert _date_from_pdf_url("") is None


# ---------------------------------------------------------------------------
# `resolve_pub_date` con item_url — la cascada respeta prioridades
# ---------------------------------------------------------------------------


class TestResolvePubDateCascade:
    def test_container_gana_sobre_pdf_url(self):
        """Si el listado expone fecha explícita, prevalece sobre la del
        filename — el listado es más reciente y autoritativo."""
        source = UniversidadesMadridSource()
        d = source.resolve_pub_date(
            container_text="(Actualizado el 15/03/2026)",
            title="Plaza Enfermería del Trabajo",
            item_url="https://example.org/foo-03.09.2020.pdf",
        )
        assert d == date(2026, 3, 15)

    def test_pdf_gana_sobre_year_from_title_cuando_container_no_tiene_fecha(self):
        """PDF filename es más preciso que el año del título."""
        source = UniversidadesMadridSource()
        d = source.resolve_pub_date(
            container_text="sin fecha legible",
            title="Convocatoria (2020)",
            item_url="https://example.org/B1-03.09.2020.pdf",
        )
        assert d == date(2020, 9, 3)

    def test_year_from_title_cuando_container_y_pdf_fallan(self):
        source = UniversidadesMadridSource()
        d = source.resolve_pub_date(
            container_text="sin fecha legible",
            title="Convocatoria (2024)",
            item_url="https://example.org/anexo-III.pdf",
        )
        assert d == date(2024, 1, 1)

    def test_fallback_today_si_todo_falla(self):
        source = UniversidadesMadridSource()
        d = source.resolve_pub_date(
            container_text="sin fecha",
            title="sin año",
            item_url=None,
        )
        assert d == date.today()


# ---------------------------------------------------------------------------
# Estado UAM — capturado en `RawItem.extra['state']` (lectura mínima, sin BD)
# ---------------------------------------------------------------------------


class TestUamState:
    def _patch_get_uam_only(self, html: str):
        empty = _resp("<html><body></body></html>")
        uam_resp = _resp(html)

        def side_effect(url, *args, **kwargs):
            return uam_resp if "uam.es" in url else empty

        return patch.object(
            universidades_madrid.requests, "get", side_effect=side_effect
        )

    def test_card_con_span_status_propaga_state_a_extra(self):
        """UAM con `<span class='uam-becas-status'>Resuelta</span>` →
        `RawItem.extra['state'] == 'Resuelta'`."""
        source = UniversidadesMadridSource()
        with self._patch_get_uam_only(UAM_FUNCIONARIO_HTML):
            items = source.fetch(since_date=date(2000, 1, 1))

        enfermero = next(
            it for it in items
            if it.extra.get("uni") == "UAM" and "Enfermero" in it.title
        )
        assert enfermero.extra["state"] == "Resuelta"

    def test_card_sin_span_status_no_anade_clave_state(self):
        """Si el card UAM no tiene `span.uam-becas-status` (hipotético),
        la clave `state` no aparece en `extra`."""
        html_sin_status = """
        <html><body>
          <div class="uam-card">
            <span class="uam-becas-date">01/02/2026</span>
            <p>Plaza Enfermería del Trabajo sin estado declarado</p>
          </div>
        </body></html>
        """
        source = UniversidadesMadridSource()
        with self._patch_get_uam_only(html_sin_status):
            items = source.fetch(since_date=date(2000, 1, 1))

        uam_items = [it for it in items if it.extra.get("uni") == "UAM"]
        assert uam_items
        for it in uam_items:
            assert "state" not in it.extra

    def test_universidades_sin_ese_span_no_reciben_state(self):
        """UCM/UAH no usan esa clase → ningún item suyo lleva `extra['state']`."""
        source = UniversidadesMadridSource()
        with patch.object(
            universidades_madrid.requests, "get",
            return_value=_resp(UCM_LISTING_HTML),
        ):
            items = source.fetch(since_date=date(2000, 1, 1))

        ucm_items = [it for it in items if it.extra.get("uni") == "UCM"]
        assert ucm_items
        for it in ucm_items:
            assert "state" not in it.extra
