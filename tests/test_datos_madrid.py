"""
Tests de la fuente datos.madrid.es (CKAN API).

Mockea las dos llamadas HTTP que hace la fuente:
  1. GET package_show?id=... (devuelve metadata del dataset con la URL del CSV)
  2. GET <csv_url>          (devuelve el CSV)

Y verifica que detecta filas con keywords, ignora ruido, y que el title
y la URL quedan bien construidos para deduplicación.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest

from vigia.sources.datos_madrid import DatosMadridSource, DATASETS


# CSV mínimo simulando el dataset OEP. La columna "categoria" es la 5.
_CSV_OEP = b"""ano;turno;grupo;f_l;categoria;categoria_secundaria;turno_libre;turno_disc;promo_int;total
2025;tl;a2;f;Enfermero/a del Trabajo;;6;;;6
2025;tl;a2;f;Enfermero/a;;15;2;;17
2024;tl;a2;f;Auxiliar de Enfermeria;;10;;;10
2024;tl;a1;f;Tecnico Superior de Prevencion de Riesgos Laborales;;3;;;3
"""

_CSV_ESTAB = b"""clase;grupo;categoria;estado;observaciones;total
PF;A2;Enfermero (Trabajo);finalizado;ninguno;1
PF;A2;Enfermero (General);finalizado;pendiente;40
"""


def _meta_response(csv_url: str) -> MagicMock:
    """Simula la respuesta de la API CKAN package_show."""
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value={
        "result": {
            "metadata_modified": "2025-01-02T10:00:00",
            "resources": [
                {"format": "PDF", "url": "https://example.com/doc.pdf"},
                {"format": "CSV", "url": csv_url},
                {"format": "XLSX", "url": "https://example.com/data.xlsx"},
            ],
        },
    })
    return resp


def _csv_response(content: bytes) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.content = content
    return resp


def _make_get_mock():
    """
    Helper: crea un mock de requests.get que enruta según la URL pedida.
    Retorna metadata para `package_show`, contenido CSV para las URLs CSV.
    """
    def fake_get(url, *args, **kwargs):
        if "package_show?id=300701" in url:
            return _meta_response("https://datos.madrid.es/oep.csv")
        if "package_show?id=300687" in url:
            return _meta_response("https://datos.madrid.es/estab.csv")
        if url.endswith("/oep.csv"):
            return _csv_response(_CSV_OEP)
        if url.endswith("/estab.csv"):
            return _csv_response(_CSV_ESTAB)
        raise AssertionError(f"URL inesperada en mock: {url}")
    return fake_get


# ---------------------------------------------------------------------------

class TestDatosMadrid:
    def test_fetch_consume_los_dos_datasets(self, monkeypatch):
        monkeypatch.setattr(
            "vigia.sources.datos_madrid.requests.get", _make_get_mock()
        )
        source = DatosMadridSource()
        items = source.fetch(date(2026, 1, 1))
        # Deben aparecer items del OEP y de la Estabilización
        labels = {item.extra["dataset"] for item in items}
        assert "OEP" in labels
        assert "Estabilización" in labels

    def test_detecta_enfermero_trabajo_oep(self, monkeypatch):
        monkeypatch.setattr(
            "vigia.sources.datos_madrid.requests.get", _make_get_mock()
        )
        source = DatosMadridSource()
        items = source.fetch(date(2026, 1, 1))
        titles = [it.title for it in items]
        assert any(
            "OEP" in t and "Enfermero/a del Trabajo" in t for t in titles
        ), f"No se detectó la línea de Enfermero/a del Trabajo. Titles: {titles}"

    def test_detecta_estabilizacion_enfermero_trabajo(self, monkeypatch):
        monkeypatch.setattr(
            "vigia.sources.datos_madrid.requests.get", _make_get_mock()
        )
        source = DatosMadridSource()
        items = source.fetch(date(2026, 1, 1))
        titles = [it.title for it in items]
        assert any(
            "Estabilización" in t and "Enfermero (Trabajo)" in t for t in titles
        )

    def test_filtra_filas_sin_keyword(self, monkeypatch):
        """Filas sin "enfermer"/"salud laboral"/"prevenc" deben descartarse."""
        monkeypatch.setattr(
            "vigia.sources.datos_madrid.requests.get", _make_get_mock()
        )
        source = DatosMadridSource()
        items = source.fetch(date(2026, 1, 1))
        # No debe haber items con categorías irrelevantes (técnico contable, etc.)
        for it in items:
            assert any(
                kw in it.title.lower()
                for kw in ("enfermer", "salud laboral", "prevenc")
            ), f"Item irrelevante coló: {it.title}"

    def test_extra_contiene_dataset_label(self, monkeypatch):
        monkeypatch.setattr(
            "vigia.sources.datos_madrid.requests.get", _make_get_mock()
        )
        source = DatosMadridSource()
        items = source.fetch(date(2026, 1, 1))
        for it in items:
            assert "dataset" in it.extra
            assert it.extra["dataset"] in {"OEP", "Estabilización"}

    def test_fallo_metadata_no_corta_otros_datasets(self, monkeypatch):
        """Si la API CKAN cae para un dataset, los demás siguen procesándose."""
        def fake_get(url, *args, **kwargs):
            if "package_show?id=300701" in url:
                # Simulamos que el OEP da error
                raise ConnectionError("simulated 503")
            if "package_show?id=300687" in url:
                return _meta_response("https://datos.madrid.es/estab.csv")
            if url.endswith("/estab.csv"):
                return _csv_response(_CSV_ESTAB)
            raise AssertionError(f"URL inesperada: {url}")

        monkeypatch.setattr("vigia.sources.datos_madrid.requests.get", fake_get)
        source = DatosMadridSource()
        items = source.fetch(date(2026, 1, 1))

        # Estabilización SÍ debe haberse procesado
        assert any(it.extra["dataset"] == "Estabilización" for it in items)
        # Y el error de OEP debe estar registrado en last_errors
        assert any("OEP" in err for err in source.last_errors)

    def test_dataset_sin_csv_genera_error(self, monkeypatch):
        """Si un dataset no tiene recurso CSV, last_errors lo registra."""
        def fake_get(url, *args, **kwargs):
            if "package_show?id=300701" in url:
                resp = MagicMock()
                resp.status_code = 200
                resp.raise_for_status = MagicMock()
                resp.json = MagicMock(return_value={
                    "result": {
                        "metadata_modified": "2025-01-02",
                        "resources": [{"format": "PDF", "url": "x.pdf"}],
                    },
                })
                return resp
            if "package_show?id=300687" in url:
                return _meta_response("https://datos.madrid.es/estab.csv")
            if url.endswith("/estab.csv"):
                return _csv_response(_CSV_ESTAB)
            raise AssertionError(f"URL inesperada: {url}")

        monkeypatch.setattr("vigia.sources.datos_madrid.requests.get", fake_get)
        source = DatosMadridSource()
        source.fetch(date(2026, 1, 1))

        assert any("sin CSV" in err for err in source.last_errors)


class TestDatasetsConfiguration:
    def test_no_se_incluye_rpt_por_defecto(self):
        """La RPT (906052) genera ruido y se excluye intencionalmente."""
        ids = [ds_id for ds_id, _ in DATASETS]
        assert not any("906052" in i for i in ids), (
            "La RPT no debería estar en los datasets por defecto"
        )

    def test_oep_y_estabilizacion_si_estan(self):
        ids = [ds_id for ds_id, _ in DATASETS]
        assert "300701-0-empleo-oep" in ids
        assert "300687-0-plantilla-estabilizacion" in ids
