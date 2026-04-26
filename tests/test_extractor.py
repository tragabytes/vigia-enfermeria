"""
Tests unitarios del extractor: cubren todos los casos históricos validados
y los falsos positivos más importantes.
"""
from __future__ import annotations

from datetime import date

import pytest

from vigia.extractor import extract
from vigia.sources.base import RawItem


def _raw(title: str, text: str = "", source: str = "test") -> RawItem:
    return RawItem(source=source, url="http://example.com", title=title, date=date.today(), text=text)


# ---------------------------------------------------------------------------
# Casos históricos validados (DEBEN ser detectados)
# ---------------------------------------------------------------------------

class TestCasosHistoricos:
    def test_boe_ayto_madrid_2023_05_08(self):
        """BOE 2023-05-08: Ayuntamiento de Madrid 5 plazas Enfermero/a (Enfermería de Trabajo)."""
        item = extract(_raw(
            "Resolución de 28 de abril de 2023, del Ayuntamiento de Madrid, por la que se "
            "convoca proceso selectivo para cubrir 5 plazas de Enfermero/a (Enfermería de Trabajo)."
        ))
        assert item is not None
        assert item.categoria == "oposicion"

    def test_boe_variante_sin_articulo(self):
        """BOE usa 'Enfermería de Trabajo' sin 'del'."""
        item = extract(_raw(
            "Convocatoria para proveer plazas de Enfermero/a (Enfermería de Trabajo) "
            "en el Servicio de Salud Laboral."
        ))
        assert item is not None

    def test_bocm_sermas_concurso_meritos_2024(self):
        """BOCM 2024-03-18: SERMAS Concurso Méritos Enfermero/a Especialista (Enfermería del Trabajo)."""
        item = extract(_raw(
            "Resolución 1234/2024 del SERMAS por la que se convoca concurso de méritos "
            "para la provisión de plazas de Enfermero/a Especialista (Enfermería del Trabajo).",
            source="bocm",
        ))
        assert item is not None
        assert item.categoria == "traslado"

    def test_bocm_orden_1074_2025(self):
        """BOCM 2025-05-08: Orden 1074/2025 9 plazas Enfermero/a Especialista."""
        item = extract(_raw(
            "Orden 1074/2025, de la Consejería de Sanidad, por la que se convoca proceso "
            "selectivo para cubrir 9 plazas de Enfermero/a Especialista en Enfermería del Trabajo."
        ))
        assert item is not None
        assert item.categoria == "oposicion"

    def test_bocm_en_pdf(self):
        """Keyword en cuerpo del PDF (título genérico, texto con especialidad)."""
        item = extract(_raw(
            "Resolución por la que se convocan pruebas selectivas para personal sanitario.",
            text="El proceso selectivo convoca plazas de Enfermería del Trabajo en el SERMAS.",
        ))
        assert item is not None

    def test_boam_titulo_con_especialidad(self):
        """BOAM incluye la especialidad directamente en el título del sumario."""
        item = extract(_raw(
            "Resolución por la que se convoca proceso selectivo para Enfermero/a "
            "(Enfermería de Trabajo) del Servicio de Salud Laboral del Ayuntamiento de Madrid."
        ))
        assert item is not None
        assert item.categoria == "oposicion"

    def test_canal_isabel_ii_puestos(self):
        """Canal Isabel II: tabla /puestos con título exacto."""
        item = extract(_raw(
            "Enfermero/a especialista en enfermería del trabajo",
            source="canal_isabel_ii",
        ))
        assert item is not None

    def test_enfermera_salud_laboral(self):
        """Variante 'enfermera de salud laboral'."""
        item = extract(_raw("Convocatoria plaza Enfermera de Salud Laboral, Ayuntamiento de Leganés."))
        assert item is not None

    def test_match_debil_salud_laboral_con_enfermera(self):
        """Match débil: 'salud laboral' + 'enfermer' en ventana de 100 chars."""
        item = extract(_raw(
            "Servicio de Salud Laboral — plaza de enfermera en empresa pública."
        ))
        assert item is not None

    def test_bolsa_empleo(self):
        item = extract(_raw("Apertura de bolsa de empleo para Enfermería del Trabajo, SERMAS."))
        assert item is not None
        assert item.categoria == "bolsa"

    def test_bolsa_unica_empleo_temporal(self):
        """CODEM publica 'Bolsa única de empleo temporal de Especialista en
        Enfermería del Trabajo'. Antes caía en 'otro' porque el hint era
        'bolsa de empleo' (no admitía 'única' entre medio)."""
        item = extract(_raw(
            "Bolsa única de empleo temporal de Especialista en Enfermería del Trabajo (2024). Subsanación."
        ))
        assert item is not None
        assert item.categoria == "bolsa"

    def test_proceso_estabilizacion_es_oposicion(self):
        """SERMAS publica 'Proceso de estabilización en SERMAS de la categoría
        de Enfermero/a Especialista en Enfermería del Trabajo'. Es un proceso
        selectivo y debe clasificarse como oposicion (antes caía en otro)."""
        item = extract(_raw(
            "Proceso de estabilización en SERMAS de la categoría de Enfermero/a Especialista en Enfermería del Trabajo."
        ))
        assert item is not None
        assert item.categoria == "oposicion"

    def test_proceso_acceso_libre_es_oposicion(self):
        """'Proceso de acceso libre para Diplomado en Enfermería Especialista
        en Enfermería del Trabajo' también es un proceso selectivo."""
        item = extract(_raw(
            "Proceso de acceso libre para Diplomado en Enfermería Especialista en Enfermería del Trabajo."
        ))
        assert item is not None
        assert item.categoria == "oposicion"

    def test_oep(self):
        item = extract(_raw("Oferta de Empleo Público OEP 2025, plazas de Enfermería del Trabajo."))
        assert item is not None
        assert item.categoria == "oep"

    def test_enfermeria_de_empresa_rtve(self):
        """Variante histórica 'Enfermería de Empresa' (RTVE y otras empresas
        públicas estatales). Es sinónimo formativo de Enfermería del Trabajo."""
        item = extract(_raw(
            "Convocatoria de la Corporación RTVE para plazas de Enfermería de Empresa."
        ))
        assert item is not None
        assert item.categoria == "oposicion"

    def test_enfermero_a_de_empresa(self):
        """Variante 'Enfermero/a de Empresa' — tras normalize la '/' se vuelve espacio."""
        item = extract(_raw(
            "Proceso selectivo para Enfermero/a de Empresa, RENFE Operadora."
        ))
        assert item is not None
        assert item.categoria == "oposicion"


# ---------------------------------------------------------------------------
# Falsos positivos (NO deben ser detectados)
# ---------------------------------------------------------------------------

class TestFalsosPositivos:
    def test_tcae(self):
        """Técnico en Cuidados Auxiliares de Enfermería — no es Enfermería del Trabajo."""
        item = extract(_raw(
            "Convocatoria para cubrir plazas de Técnico en Cuidados Auxiliares de Enfermería (TCAE)."
        ))
        assert item is None

    def test_auxiliar_enfermeria(self):
        item = extract(_raw("Proceso selectivo para Auxiliar de Enfermería, Consejería de Sanidad."))
        assert item is None

    def test_enfermeria_salud_mental(self):
        item = extract(_raw("Oposición plaza Enfermería de Salud Mental, Hospital Gregorio Marañón."))
        assert item is None

    def test_enfermeria_pediatrica(self):
        item = extract(_raw("Bolsa de empleo Enfermería Pediátrica, Hospital La Paz."))
        assert item is None

    def test_matrona(self):
        item = extract(_raw("Concurso de traslados para Matrona, SERMAS 2025."))
        assert item is None

    def test_enfermedades_no_match(self):
        """'Enfermedades' no debe activar el fast-keyword."""
        item = extract(_raw(
            "Resolución sobre enfermedades de declaración obligatoria en el ámbito laboral."
        ))
        assert item is None

    def test_sin_contexto_salud_laboral(self):
        """'Salud laboral' sin 'enfermer' cerca no hace match."""
        item = extract(_raw(
            "Plan de salud laboral para el personal de la Comunidad de Madrid, ejercicio 2025."
        ))
        assert item is None

    def test_texto_irrelevante(self):
        item = extract(_raw("Convocatoria de becas de investigación en física de partículas."))
        assert item is None


# ---------------------------------------------------------------------------
# Clasificación
# ---------------------------------------------------------------------------

class TestClasificacion:
    def test_bolsa(self):
        item = extract(_raw("Bolsa de trabajo Enfermería del Trabajo SERMAS 2025."))
        assert item is not None
        assert item.categoria == "bolsa"

    def test_traslado(self):
        item = extract(_raw("Concurso de traslados de Enfermería del Trabajo, SERMAS 2025."))
        assert item is not None
        assert item.categoria == "traslado"

    def test_oposicion(self):
        item = extract(_raw("Convocatoria oposición 10 plazas Enfermería del Trabajo."))
        assert item is not None
        assert item.categoria == "oposicion"

    def test_oep(self):
        item = extract(_raw("OEP 2025 incluye plazas de enfermería del trabajo."))
        assert item is not None
        assert item.categoria == "oep"

    def test_otro(self):
        item = extract(_raw("Enfermería del Trabajo: lista definitiva de admitidos."))
        assert item is not None
        assert item.categoria == "otro"
