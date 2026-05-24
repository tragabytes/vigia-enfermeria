"""
Tests del parser IAC (Instituto de Astrofísica de Canarias).
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from vigia.sources import iac
from vigia.sources.iac import IACSource


def _resp(text: str, status: int = 200):
    r = MagicMock()
    r.status_code = status
    r.text = text
    r.raise_for_status = lambda: None
    return r


# HTML representativo del portal IAC (Drupal). 3 ofertas: dos realistas
# del listado actual (predoctorales, sin keyword) y una añadida ad-hoc
# con "Enfermería" para validar el camino del matching.
IAC_LISTING_HTML = """
<html><body>
  <div class="view-content">
    <div class="views-row">
      <div class="field field--name-title">
        <a href="/es/ofertas-de-trabajo/un-contrato-predoctoral-en-el-iac-ps-2026-060">
          Un Contrato Predoctoral en el IAC ASTRI Mini Array PS-2026-060
        </a>
      </div>
      <ul class="links inline">
        <li class="node-readmore">
          <a href="/es/ofertas-de-trabajo/un-contrato-predoctoral-en-el-iac-ps-2026-060">
            Leer más
          </a>
        </li>
      </ul>
    </div>
    <div class="views-row">
      <div class="field field--name-title">
        <a href="/es/ofertas-de-trabajo/enfermero-a-servicio-prevencion-ps-2026-099">
          Enfermero/a del Servicio de Prevención y Salud Laboral PS-2026-099
        </a>
      </div>
      <ul class="links inline">
        <li class="node-readmore">
          <a href="/es/ofertas-de-trabajo/enfermero-a-servicio-prevencion-ps-2026-099">
            Leer más
          </a>
        </li>
      </ul>
    </div>
    <div class="views-row">
      <div class="field field--name-title">
        <a href="/es/ofertas-de-trabajo/seis-contratos-predoctorales-ars-ps-2026-064">
          Seis Contratos Predoctorales (ARs) en el IAC PS-2026-064
        </a>
      </div>
    </div>
  </div>
</body></html>
"""


class TestIACSource:
    def test_extrae_solo_oferta_con_keyword(self):
        source = IACSource()
        with patch.object(
            iac.requests, "get", return_value=_resp(IAC_LISTING_HTML),
        ):
            items = source.fetch(since_date=date(2000, 1, 1))

        assert len(items) == 1
        assert "Enfermero/a del Servicio de Prevenci" in items[0].title

    def test_url_absoluta_y_dedupe_de_anchor_leer_mas(self):
        """La oferta de Enfermería aparece dos veces (título + 'Leer más').
        Solo debe generar 1 item, con la URL del título (no la del botón)."""
        source = IACSource()
        with patch.object(
            iac.requests, "get", return_value=_resp(IAC_LISTING_HTML),
        ):
            items = source.fetch(since_date=date(2000, 1, 1))

        assert len(items) == 1
        assert items[0].url == \
            "https://www.iac.es/es/ofertas-de-trabajo/enfermero-a-servicio-prevencion-ps-2026-099"

    def test_descarta_predoctorales_sin_keyword(self):
        source = IACSource()
        with patch.object(
            iac.requests, "get", return_value=_resp(IAC_LISTING_HTML),
        ):
            items = source.fetch(since_date=date(2000, 1, 1))

        titles_upper = " ".join(it.title.upper() for it in items)
        assert "PREDOCTORAL" not in titles_upper
        assert "ARS" not in titles_upper

    def test_fecha_cae_a_today_porque_listado_no_la_expone(self):
        source = IACSource()
        with patch.object(
            iac.requests, "get", return_value=_resp(IAC_LISTING_HTML),
        ):
            items = source.fetch(since_date=date(2000, 1, 1))

        assert items[0].date == date.today()

    def test_listado_caido_devuelve_lista_vacia_con_error(self):
        source = IACSource()
        with patch.object(
            iac.requests, "get",
            side_effect=Exception("connection reset"),
        ):
            items = source.fetch(since_date=date(2000, 1, 1))

        assert items == []
        assert source.last_errors and "connection reset" in source.last_errors[0]

    def test_probe_url_es_listado(self):
        source = IACSource()
        assert source.probe_url == "https://www.iac.es/es/empleo"
