"""
Tests de cobertura de organismos en BOCM y BOE.

Garantiza que organismos clave (FNMT, EMT, ayuntamientos grandes de Madrid)
están en las listas de palabras clave que disparan la descarga del PDF/body
correspondiente. Si alguien borra accidentalmente uno de la lista, este
test salta.
"""
from __future__ import annotations

import pytest

from vigia.config import normalize
from vigia.sources.bocm import HEALTH_ORGS
from vigia.sources.boe import DEPT_KEYWORDS_FOR_BODY


@pytest.mark.parametrize(
    "organismo_real",
    [
        # Sanitarios / SERMAS
        "Consejería de Sanidad",
        "SERMAS",
        "Servicio Madrileño de Salud",
        "Hospital Universitario La Paz",
        "Gerencia de Atención Primaria",
        # Empresas públicas
        "Canal de Isabel II",
        "Metro de Madrid",
        "Casa de la Moneda — FNMT-RCM",
        "Fábrica Nacional de Moneda y Timbre",
        "EMT Madrid",
        "Empresa Municipal de Transportes",
        # Grandes ayuntamientos
        "Ayuntamiento de Móstoles",
        "Ayuntamiento de Alcalá de Henares",
        "Ayuntamiento de Fuenlabrada",
        "Ayuntamiento de Leganés",
        "Ayuntamiento de Getafe",
        "Ayuntamiento de Alcorcón",
        "Ayuntamiento de Torrejón de Ardoz",
        "Ayuntamiento de Parla",
        "Ayuntamiento de Alcobendas",
    ],
)
def test_organismo_dispara_descarga_bocm(organismo_real: str) -> None:
    """En BOCM, este organismo (normalizado) hace match con HEALTH_ORGS."""
    org_norm = normalize(organismo_real)
    assert any(kw in org_norm for kw in HEALTH_ORGS), (
        f"El organismo '{organismo_real}' (normalizado: '{org_norm}') no "
        f"dispara la descarga de PDF en BOCM. Revisa HEALTH_ORGS."
    )


@pytest.mark.parametrize(
    "departamento_real",
    [
        # Cubiertos por "administracion local"
        "Administración Local — Ayuntamiento de Madrid",
        "Administración Local — Ayuntamiento de Móstoles",
        # Cubiertos explícitamente
        "FNMT-RCM",
        "Fábrica Nacional de Moneda y Timbre",
        "Casa de la Moneda",
        "EMT Madrid",
        "Empresa Municipal de Transportes",
        "Comunidades Autónomas — Madrid",
        "Consejería de Sanidad",
        "SERMAS",
        "CIEMAT",
        "Canal de Isabel II",
        "Metro de Madrid",
    ],
)
def test_departamento_dispara_descarga_boe(departamento_real: str) -> None:
    """En BOE, este departamento (normalizado) hace match con DEPT_KEYWORDS_FOR_BODY."""
    dept_norm = normalize(departamento_real)
    assert any(kw in dept_norm for kw in DEPT_KEYWORDS_FOR_BODY), (
        f"El departamento '{departamento_real}' (normalizado: '{dept_norm}') "
        f"no dispara la descarga de body en BOE. Revisa DEPT_KEYWORDS_FOR_BODY."
    )


def test_health_orgs_normalizados() -> None:
    """Sanity: todas las entradas de HEALTH_ORGS están en minúsculas, sin tildes."""
    for kw in HEALTH_ORGS:
        assert kw == normalize(kw), (
            f"'{kw}' no está normalizado. Debería ser: '{normalize(kw)}'"
        )


def test_dept_keywords_normalizados() -> None:
    """Sanity: todas las entradas de DEPT_KEYWORDS_FOR_BODY están en minúsculas, sin tildes."""
    for kw in DEPT_KEYWORDS_FOR_BODY:
        assert kw == normalize(kw), (
            f"'{kw}' no está normalizado. Debería ser: '{normalize(kw)}'"
        )
