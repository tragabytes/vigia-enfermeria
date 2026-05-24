"""
Tests del parser CSIC sede electrónica.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from vigia.sources import csic_sede
from vigia.sources.csic_sede import CSICSedeSource


def _resp(text: str, status: int = 200):
    r = MagicMock()
    r.status_code = status
    r.text = text
    r.raise_for_status = lambda: None
    return r


# HTML representativo de sede.csic.gob.es. 3 convocatorias: dos del
# listado real (libre designación, ayudas PIF) y una añadida ad-hoc
# con "Servicio de Prevención" para validar el camino del matching.
CSIC_SEDE_HTML = """
<html><body>
  <div class="views-row col-md-3">
    <div class="views-field views-field-field-fecha-publicacion">
      <div class="field-content">28/04/2026</div>
    </div>
    <div class="views-field views-field-title">
      <span class="field-content">
        <a href="/tramites/convocatorias-de-personal/convocatoria/38205">
          Provisión de puestos de trabajo por libre designación (Ref.38205)
        </a>
      </span>
    </div>
  </div>
  <div class="views-row col-md-3">
    <div class="views-field views-field-field-fecha-publicacion">
      <div class="field-content">15/04/2026</div>
    </div>
    <div class="views-field views-field-title">
      <span class="field-content">
        <a href="/tramites/convocatorias-de-personal/convocatoria/38199">
          Concurso de méritos plaza Enfermería del Trabajo Servicio Prevención (Ref.38199)
        </a>
      </span>
    </div>
  </div>
  <div class="views-row col-md-3">
    <div class="views-field views-field-field-fecha-publicacion">
      <div class="field-content">10/04/2026</div>
    </div>
    <div class="views-field views-field-title">
      <span class="field-content">
        <a href="/tramites/convocatorias-de-personal/convocatoria/38206">
          Ayudas PIF2025 tesis doctoral - Convocatoria extraordinaria (Ref.38206)
        </a>
      </span>
    </div>
  </div>
</body></html>
"""


class TestCSICSedeSource:
    def test_extrae_solo_convocatoria_con_keyword(self):
        source = CSICSedeSource()
        with patch.object(
            csic_sede.requests, "get", return_value=_resp(CSIC_SEDE_HTML),
        ):
            items = source.fetch(since_date=date(2000, 1, 1))

        assert len(items) == 1
        assert "Enfermería del Trabajo" in items[0].title

    def test_extrae_fecha_del_field_drupal(self):
        source = CSICSedeSource()
        with patch.object(
            csic_sede.requests, "get", return_value=_resp(CSIC_SEDE_HTML),
        ):
            items = source.fetch(since_date=date(2000, 1, 1))

        assert items[0].date == date(2026, 4, 15)

    def test_url_absoluta_construida_correctamente(self):
        source = CSICSedeSource()
        with patch.object(
            csic_sede.requests, "get", return_value=_resp(CSIC_SEDE_HTML),
        ):
            items = source.fetch(since_date=date(2000, 1, 1))

        assert items[0].url == \
            "https://sede.csic.gob.es/tramites/convocatorias-de-personal/convocatoria/38199"

    def test_descarta_convocatorias_sin_keyword(self):
        source = CSICSedeSource()
        with patch.object(
            csic_sede.requests, "get", return_value=_resp(CSIC_SEDE_HTML),
        ):
            items = source.fetch(since_date=date(2000, 1, 1))

        titles_upper = " ".join(it.title.upper() for it in items)
        assert "LIBRE DESIGNACIÓN" not in titles_upper
        assert "PIF2025" not in titles_upper

    def test_filtra_por_since_date(self):
        source = CSICSedeSource()
        with patch.object(
            csic_sede.requests, "get", return_value=_resp(CSIC_SEDE_HTML),
        ):
            items = source.fetch(since_date=date(2026, 5, 1))

        # Enfermería se publicó 15/04/2026 → fuera del rango.
        assert items == []

    def test_fecha_invalida_cae_a_today(self):
        """Si .views-field-field-fecha-publicacion no parsea, fallback today."""
        html = """
        <html><body>
          <div class="views-row">
            <div class="views-field views-field-field-fecha-publicacion">
              <div class="field-content">fecha inválida</div>
            </div>
            <div class="views-field views-field-title">
              <span class="field-content">
                <a href="/tramites/convocatorias-de-personal/convocatoria/999">
                  Plaza Enfermería del Trabajo (Ref.999)
                </a>
              </span>
            </div>
          </div>
        </body></html>
        """
        source = CSICSedeSource()
        with patch.object(
            csic_sede.requests, "get", return_value=_resp(html),
        ):
            items = source.fetch(since_date=date(2000, 1, 1))

        assert len(items) == 1
        assert items[0].date == date.today()

    def test_listado_caido_devuelve_lista_vacia_con_error(self):
        source = CSICSedeSource()
        with patch.object(
            csic_sede.requests, "get",
            side_effect=Exception("connection reset"),
        ):
            items = source.fetch(since_date=date(2000, 1, 1))

        assert items == []
        assert source.last_errors and "connection reset" in source.last_errors[0]

    def test_probe_url_es_listado(self):
        source = CSICSedeSource()
        assert source.probe_url == \
            "https://sede.csic.gob.es/tramites/convocatorias-de-personal"
