"""
Tests del parser SAP SuccessFactors compartido (RENFE, Correos, Navantia).

Cubre los puntos críticos:
  1. Estructura HTML compartida con dos variantes: `<tr class="data-row">`
     (Correos) y `<div class="job">` (RENFE). El selector debe aceptar
     ambas en la misma pasada.
  2. Filtro fast-keyword sobre el title del `<a class="jobTitle-link">`
     (descarta jefaturas, becas, etc.).
  3. Parseo de fecha en formato español "DD mes YYYY" y "DD mes. YYYY"
     (con punto opcional tras el mes abreviado).
  4. URL absoluta resuelta contra el origen del search_url.
  5. Iteración por paginación `?startrow=N` hasta agotar items.
  6. Acumulación de errores en `last_errors` cuando un portal cae.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from vigia.sources import sap_successfactors
from vigia.sources.sap_successfactors import (
    SapEmpresa,
    SapSuccessfactorsSource,
    _matches_fast_keywords,
    _parse_es_date,
    _resolve_url,
)


# ---------------------------------------------------------------------------
# HTML real recortado de las páginas /search/ capturadas el 2026-04-28.
# ---------------------------------------------------------------------------

# RENFE usa `<div class="job">` con paginación de 6 items.
RENFE_PAGE_1_HTML = """
<html><body>
  <div class="row job">
    <div class="tiletitle">
      <a class="jobTitle-link" href="/job/Enfermero-Servicio-Prevencion-Madrid/1234567890/">
        EDE26-04/9999 Enfermera/o del Trabajo - Servicio de Prevención
      </a>
    </div>
    <div class="section-field">
      <span class="jobDate">15 abr 2026</span>
    </div>
  </div>
  <div class="row job">
    <div class="tiletitle">
      <a class="jobTitle-link" href="/job/Jefatura-Mantenimiento/1359228157/">
        EDE26-04/3001 Jefatura de Base de Mantenimiento
      </a>
    </div>
    <div class="section-field">
      <span class="jobDate">10 mar 2026</span>
    </div>
  </div>
</body></html>
"""

# Correos usa `<tr class="data-row">`.
CORREOS_PAGE_1_HTML = """
<html><body>
  <table>
    <tr class="data-row">
      <td>
        <span class="jobTitle"><a class="jobTitle-link"
          href="/job/Madrid-Tecnico-Salud-Laboral/9876543210/">
          Técnico Especialista en Salud Laboral - Servicio de Prevención
        </a></span>
        <span class="jobDate">22 abr 2026</span>
      </td>
    </tr>
    <tr class="data-row">
      <td>
        <span class="jobTitle"><a class="jobTitle-link"
          href="/job/Becas-Madrid/1376845233/">
          Jóvenes Talentos 2026 - Beca Recursos Humanos Madrid
        </a></span>
        <span class="jobDate">22 abr 2026</span>
      </td>
    </tr>
  </table>
</body></html>
"""

# Página vacía (sin items) — devuelta cuando se pasa de la última página.
EMPTY_HTML = "<html><body><table></table></body></html>"


def _resp(text: str, status: int = 200):
    r = MagicMock()
    r.status_code = status
    r.text = text
    r.raise_for_status = lambda: None
    return r


# ---------------------------------------------------------------------------
# Helpers puros
# ---------------------------------------------------------------------------


class TestParseEsDate:
    def test_formato_corto_22_abr_2026(self):
        assert _parse_es_date("22 abr 2026") == date(2026, 4, 22)

    def test_formato_largo_15_abril_2025(self):
        assert _parse_es_date("15 abril 2025") == date(2025, 4, 15)

    def test_punto_tras_mes_abreviado(self):
        assert _parse_es_date("3 oct. 2024") == date(2024, 10, 3)

    def test_septiembre_alternativo(self):
        assert _parse_es_date("1 sep 2026") == date(2026, 9, 1)
        assert _parse_es_date("1 sept 2026") == date(2026, 9, 1)
        assert _parse_es_date("1 setiembre 2026") == date(2026, 9, 1)

    def test_mes_invalido_devuelve_none(self):
        assert _parse_es_date("22 xxx 2026") is None

    def test_texto_sin_fecha(self):
        assert _parse_es_date("Sin fecha aquí") is None


class TestResolveUrl:
    def test_relativa_se_concatena_al_origen(self):
        assert _resolve_url("/job/foo/123/", "https://empleo.renfe.com/search/") == \
            "https://empleo.renfe.com/job/foo/123/"

    def test_absoluta_se_devuelve_tal_cual(self):
        assert _resolve_url(
            "https://other.example.com/job/x", "https://empleo.renfe.com/search/"
        ) == "https://other.example.com/job/x"


class TestFastKeywords:
    def test_titulo_de_enfermeria_pasa(self):
        assert _matches_fast_keywords("Enfermera/o del Trabajo - Servicio de Prevención") is True

    def test_titulo_de_salud_laboral_pasa(self):
        assert _matches_fast_keywords("Técnico en Salud Laboral") is True

    def test_jefatura_se_descarta(self):
        assert _matches_fast_keywords("Jefatura de Base de Mantenimiento") is False

    def test_becas_se_descartan(self):
        assert _matches_fast_keywords("Jóvenes Talentos 2026 - Beca RR.HH.") is False


# ---------------------------------------------------------------------------
# RENFE listing (con `<div class="job">`)
# ---------------------------------------------------------------------------


class TestRenfeListing:
    def _patch_get_renfe_only(self, html: str):
        empty = _resp(EMPTY_HTML)
        renfe_resp = _resp(html)

        def side_effect(url, *args, **kwargs):
            return renfe_resp if "renfe.com" in url else empty

        return patch.object(
            sap_successfactors.requests, "get", side_effect=side_effect
        )

    def test_solo_extrae_item_de_enfermeria(self):
        source = SapSuccessfactorsSource()
        with self._patch_get_renfe_only(RENFE_PAGE_1_HTML):
            items = source.fetch(since_date=date(2000, 1, 1))

        renfe_items = [it for it in items if it.extra.get("empresa") == "RENFE"]
        # Solo 1 item con keyword (Enfermera) — el de Jefatura se descarta
        assert len(renfe_items) == 1
        assert "Enfermera/o del Trabajo" in renfe_items[0].title

    def test_url_absoluta_resuelta_contra_origen(self):
        source = SapSuccessfactorsSource()
        with self._patch_get_renfe_only(RENFE_PAGE_1_HTML):
            items = source.fetch(since_date=date(2000, 1, 1))

        item = next(it for it in items if it.extra.get("empresa") == "RENFE")
        assert item.url == \
            "https://empleo.renfe.com/job/Enfermero-Servicio-Prevencion-Madrid/1234567890/"

    def test_extrae_fecha_jobdate(self):
        source = SapSuccessfactorsSource()
        with self._patch_get_renfe_only(RENFE_PAGE_1_HTML):
            items = source.fetch(since_date=date(2000, 1, 1))

        item = next(it for it in items if it.extra.get("empresa") == "RENFE")
        assert item.date == date(2026, 4, 15)

    def test_extras_llevan_codigo_empresa(self):
        source = SapSuccessfactorsSource()
        with self._patch_get_renfe_only(RENFE_PAGE_1_HTML):
            items = source.fetch(since_date=date(2000, 1, 1))

        item = next(it for it in items if it.extra.get("empresa") == "RENFE")
        assert item.extra["empresa"] == "RENFE"
        assert item.extra["empresa_nombre"] == "Renfe Operadora"
        assert item.source == "sap_successfactors"


# ---------------------------------------------------------------------------
# Correos listing (con `<tr class="data-row">`)
# ---------------------------------------------------------------------------


class TestCorreosListing:
    def _patch_get_correos_only(self, html: str):
        empty = _resp(EMPTY_HTML)
        correos_resp = _resp(html)

        def side_effect(url, *args, **kwargs):
            return correos_resp if "correos.com" in url else empty

        return patch.object(
            sap_successfactors.requests, "get", side_effect=side_effect
        )

    def test_extrae_item_salud_laboral(self):
        source = SapSuccessfactorsSource()
        with self._patch_get_correos_only(CORREOS_PAGE_1_HTML):
            items = source.fetch(since_date=date(2000, 1, 1))

        correos_items = [it for it in items if it.extra.get("empresa") == "CORREOS"]
        assert len(correos_items) == 1
        assert "Salud Laboral" in correos_items[0].title

    def test_acepta_tr_data_row_estructura(self):
        """El selector debe matchear `<tr class="data-row">` usado por Correos."""
        source = SapSuccessfactorsSource()
        with self._patch_get_correos_only(CORREOS_PAGE_1_HTML):
            items = source.fetch(since_date=date(2000, 1, 1))

        correos_items = [it for it in items if it.extra.get("empresa") == "CORREOS"]
        # Si el selector solo cogiera div.job, no encontraría nada
        assert len(correos_items) >= 1


# ---------------------------------------------------------------------------
# Paginación
# ---------------------------------------------------------------------------


class TestPagination:
    def test_para_cuando_pagina_devuelve_vacio(self):
        """`?startrow=10` con 0 items debe terminar la iteración."""
        source = SapSuccessfactorsSource()
        call_log = []

        def side_effect(url, *args, **kwargs):
            call_log.append(url)
            if "renfe.com" in url:
                # Solo página 1 tiene contenido; siguientes vacías
                if "startrow=0" in url:
                    return _resp(RENFE_PAGE_1_HTML)
                return _resp(EMPTY_HTML)
            return _resp(EMPTY_HTML)

        with patch.object(
            sap_successfactors.requests, "get", side_effect=side_effect
        ):
            source.fetch(since_date=date(2000, 1, 1))

        # Por cada empresa: page 0 (no vacía si tiene resultados) + page 1 (vacía → break).
        # Para RENFE: page 0 con datos + page 1 vacía → 2 calls.
        # Correos y Navantia: page 0 vacía → 1 call cada una.
        # Total mínimo esperable a `renfe.com`: 2 (page 0 + page 1).
        renfe_calls = [u for u in call_log if "renfe.com" in u]
        assert len(renfe_calls) == 2
        assert "startrow=0" in renfe_calls[0]
        assert "startrow=10" in renfe_calls[1]


# ---------------------------------------------------------------------------
# Errores de red
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_portal_caido_acumula_error_y_continua_otros(self):
        """Si Correos cae, RENFE y Navantia siguen procesándose."""
        source = SapSuccessfactorsSource()

        def side_effect(url, *args, **kwargs):
            if "correos.com" in url:
                raise Exception("connection reset")
            if "renfe.com" in url and "startrow=0" in url:
                return _resp(RENFE_PAGE_1_HTML)
            return _resp(EMPTY_HTML)

        with patch.object(
            sap_successfactors.requests, "get", side_effect=side_effect
        ):
            items = source.fetch(since_date=date(2000, 1, 1))

        # Tenemos el match de RENFE (Enfermera del Trabajo)
        renfe_items = [it for it in items if it.extra.get("empresa") == "RENFE"]
        assert len(renfe_items) == 1
        # Y se acumuló el error de Correos
        assert any("CORREOS" in err for err in source.last_errors)


class TestProbe:
    def test_probe_url_apunta_a_renfe_search(self):
        source = SapSuccessfactorsSource()
        assert source.probe_url == "https://empleo.renfe.com/search/"
