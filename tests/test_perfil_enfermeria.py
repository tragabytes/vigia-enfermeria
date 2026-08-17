"""
Smoke del perfil Enfermería del Trabajo contra el core pineado.

Los tests del pipeline (fuentes, storage, enricher, notifier…) viven en
vigia-core y corren en SU CI al taggear cada release: este repo no los
vendoriza (se desincronizaban con cada bump, PR #30). Aquí solo se valida el
COMPORTAMIENTO del perfil — que el extractor del core, con DEFAULT activo
(lo fija tests/conftest.py), sigue matcheando/descartando los casos canónicos
del bot. Sin aserciones sobre URLs ni constantes internas del core.

La integración real contra el core instalado la da el paso --dry-run de ci.yml.

Casos portados de los históricos validados del antiguo tests/test_extractor.py.
"""
from datetime import date

from vigia.extractor import extract
from vigia.sources.base import RawItem


def _raw(title: str, text: str = "", source: str = "test") -> RawItem:
    return RawItem(source=source, url="http://example.com", title=title,
                   date=date(2026, 4, 1), text=text)


# ---------------------------------------------------------------------------
# Matches fuertes (casos históricos reales)
# ---------------------------------------------------------------------------

def test_oposicion_bocm_orden_1074_2025():
    """BOCM 2025-05-08: 9 plazas Enfermero/a Especialista en Enfermería del Trabajo."""
    item = extract(_raw(
        "Orden 1074/2025, de la Consejería de Sanidad, por la que se convoca proceso "
        "selectivo para cubrir 9 plazas de Enfermero/a Especialista en Enfermería del Trabajo."
    ))
    assert item is not None
    assert item.categoria == "oposicion"


def test_variante_sin_articulo_boe_ayto_madrid():
    """BOE usa 'Enfermería de Trabajo' (sin 'del')."""
    item = extract(_raw(
        "Resolución de 28 de abril de 2023, del Ayuntamiento de Madrid, por la que se "
        "convoca proceso selectivo para cubrir 5 plazas de Enfermero/a (Enfermería de Trabajo)."
    ))
    assert item is not None
    assert item.categoria == "oposicion"


def test_match_via_body_text():
    """Título genérico, especialidad solo en el cuerpo (típico PDF de boletín)."""
    item = extract(_raw(
        "Resolución por la que se convocan pruebas selectivas para personal sanitario.",
        text="El proceso selectivo convoca plazas de Enfermería del Trabajo en el SERMAS.",
    ))
    assert item is not None


def test_match_debil_salud_laboral_con_enfermera():
    """Match débil: 'salud laboral' + 'enfermer' en ventana de contexto."""
    item = extract(_raw(
        "Servicio de Salud Laboral — plaza de enfermera en empresa pública."
    ))
    assert item is not None


# ---------------------------------------------------------------------------
# Falsos positivos (otras especialidades / ruido)
# ---------------------------------------------------------------------------

def test_tcae_descartado():
    """TCAE no es Enfermería del Trabajo."""
    item = extract(_raw(
        "Convocatoria para cubrir plazas de Técnico en Cuidados Auxiliares de Enfermería (TCAE)."
    ))
    assert item is None


def test_otra_especialidad_descartada():
    item = extract(_raw(
        "Oposición plaza Enfermería de Salud Mental, Hospital Gregorio Marañón."
    ))
    assert item is None


def test_salud_laboral_sin_enfermeria_descartado():
    """'Salud laboral' sin 'enfermer' cerca no hace match."""
    item = extract(_raw(
        "Plan de salud laboral para el personal de la Comunidad de Madrid, ejercicio 2025."
    ))
    assert item is None


def test_texto_irrelevante_descartado():
    item = extract(_raw("Convocatoria de becas de investigación en física de partículas."))
    assert item is None


# ---------------------------------------------------------------------------
# Clasificación por categoría
# ---------------------------------------------------------------------------

def test_categoria_bolsa():
    item = extract(_raw("Bolsa de trabajo Enfermería del Trabajo SERMAS 2025."))
    assert item is not None
    assert item.categoria == "bolsa"


def test_categoria_traslado():
    item = extract(_raw("Concurso de traslados de Enfermería del Trabajo, SERMAS 2025."))
    assert item is not None
    assert item.categoria == "traslado"


def test_categoria_oep():
    item = extract(_raw("OEP 2025 incluye plazas de enfermería del trabajo."))
    assert item is not None
    assert item.categoria == "oep"
