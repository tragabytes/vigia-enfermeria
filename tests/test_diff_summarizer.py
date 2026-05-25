"""
Tests del diff_summarizer (Análisis B).

Cubre:
  1. Textos idénticos / vacíos: comportamiento determinista sin LLM.
  2. Pre-filtro local: cambio sólo en "Última actualización" o widgets
     volátiles → cosmético sin llamar a LLM.
  3. Cambio mixto: pasa al LLM (que mockeamos).
  4. Parsing del JSON del LLM: válido, malformado, fuera del JSON.
  5. Fail-open: sin API key o anthropic no instalado, devuelve
     (True, None) sin levantar.
  6. unified_diff: cap a MAX_DIFF_CHARS.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from vigia.diff_summarizer import (
    _classify_locally,
    _make_diff_text,
    _parse_llm_response,
    summarize_diff,
    MAX_DIFF_CHARS,
)


# --------------------------------------------------------------------------
# Casos triviales
# --------------------------------------------------------------------------

class TestTriviales:
    def test_textos_identicos_devuelve_cosmetico(self):
        assert summarize_diff("abc", "abc") == (False, None)

    def test_texto_vacio_devuelve_substantive_fail_open(self):
        """Sin base de comparación → fail-open: notifica sin resumen."""
        assert summarize_diff("", "algo") == (True, None)
        assert summarize_diff("algo", "") == (True, None)


# --------------------------------------------------------------------------
# Pre-filtro local
# --------------------------------------------------------------------------

class TestPreFiltro:
    def test_solo_ultima_actualizacion_es_cosmetico(self):
        old = "Cuerpo del proceso\nÚltima actualización: 20 mayo 2026\nMás contenido"
        new = "Cuerpo del proceso\nÚltima actualización: 25 mayo 2026\nMás contenido"
        assert _classify_locally(old, new) == (False, None)

    def test_solo_timestamp_es_cosmetico(self):
        old = "Fecha cuestionario 21/03/2026 10:00"
        new = "Fecha cuestionario 21/03/2026 12:30"
        assert _classify_locally(old, new) == (False, None)

    def test_cambio_sustantivo_no_decide_localmente(self):
        old = "Listado provisional pendiente"
        new = "Listado provisional publicado el 25/05/2026"
        assert _classify_locally(old, new) is None

    def test_mezcla_volatil_y_sustantivo_pasa_al_llm(self):
        """Si hay AL MENOS una línea no volátil, el pre-filtro NO decide
        (delega al LLM)."""
        old = "Última actualización: 20 mayo 2026\nApertura plicas: pendiente"
        new = "Última actualización: 25 mayo 2026\nApertura plicas: 22/05/2026"
        # La segunda línea no matchea VOLATILE_PATTERNS → pasa al LLM
        assert _classify_locally(old, new) is None

    def test_lineas_anadidas_no_volatiles_pasa_al_llm(self):
        old = "linea1"
        new = "linea1\nlinea2 nueva"
        # La línea nueva no es volátil → pre-filtro no decide.
        assert _classify_locally(old, new) is None


# --------------------------------------------------------------------------
# Parsing del JSON del LLM
# --------------------------------------------------------------------------

class TestParsingLlm:
    def test_json_valido_sustantivo(self):
        raw = '{"sustantivo": true, "resumen": "Publicada la lista provisional"}'
        assert _parse_llm_response(raw) == (True, "Publicada la lista provisional")

    def test_json_valido_cosmetico(self):
        raw = '{"sustantivo": false, "resumen": ""}'
        assert _parse_llm_response(raw) == (False, None)

    def test_json_con_texto_envolvente(self):
        """A veces el LLM añade preamble pese al prompt."""
        raw = (
            "Aquí está el análisis:\n"
            '{"sustantivo": true, "resumen": "Nueva fase de admitidos"}\n'
            "Fin."
        )
        assert _parse_llm_response(raw) == (True, "Nueva fase de admitidos")

    def test_json_invalido_fail_open(self):
        raw = '{"sustantivo": yes, "resumen":}'  # malformado
        assert _parse_llm_response(raw) == (True, None)

    def test_sin_json_fail_open(self):
        raw = "No sé qué decir"
        assert _parse_llm_response(raw) == (True, None)

    def test_resumen_vacio_se_normaliza_a_none(self):
        raw = '{"sustantivo": true, "resumen": "  "}'
        assert _parse_llm_response(raw) == (True, None)

    def test_resumen_ausente_devuelve_none(self):
        raw = '{"sustantivo": true}'
        assert _parse_llm_response(raw) == (True, None)


# --------------------------------------------------------------------------
# Integración fin a fin con mock del LLM
# --------------------------------------------------------------------------

def _mock_anthropic_response(text: str):
    """Construye un MagicMock que imita el shape de `messages.create`."""
    block = MagicMock()
    block.type = "text"
    block.text = text
    msg = MagicMock()
    msg.content = [block]
    return msg


class TestSummarizeDiffE2E:
    def test_pre_filtro_corta_sin_llm(self, monkeypatch):
        """Caso real cm_ficha: sólo cambia 'Última actualización' → no
        debe haber llamada al LLM."""
        old = (
            "Proceso selectivo Enfermería del Trabajo\n"
            "Última actualización: 20 mayo 2026\n"
            "Plazas: 9\n"
        )
        new = (
            "Proceso selectivo Enfermería del Trabajo\n"
            "Última actualización: 25 mayo 2026\n"
            "Plazas: 9\n"
        )
        # Patcheamos anthropic para detectar si se llama
        with patch("vigia.diff_summarizer._classify_via_llm") as mock_llm:
            result = summarize_diff(old, new)
        assert result == (False, None)
        assert mock_llm.call_count == 0

    def test_cambio_sustantivo_llama_al_llm(self, monkeypatch):
        old = "Listado provisional pendiente"
        new = "Listado provisional publicado el 25/05/2026"
        with patch(
            "vigia.diff_summarizer._classify_via_llm",
            return_value=(True, "Lista provisional publicada"),
        ) as mock_llm:
            result = summarize_diff(old, new)
        assert result == (True, "Lista provisional publicada")
        assert mock_llm.call_count == 1

    def test_sin_api_key_fail_open(self, monkeypatch):
        """Sin ANTHROPIC_API_KEY: pasa el pre-filtro pero el LLM se salta
        y devuelve (True, None)."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        old = "Listado pendiente"
        new = "Listado publicado el 25/05/2026"
        assert summarize_diff(old, new) == (True, None)

    def test_excepcion_en_llm_fail_open(self, monkeypatch):
        old = "Listado pendiente"
        new = "Listado publicado el 25/05/2026"
        with patch(
            "vigia.diff_summarizer._classify_via_llm",
            side_effect=RuntimeError("API down"),
        ):
            assert summarize_diff(old, new) == (True, None)


# --------------------------------------------------------------------------
# Diff text generation
# --------------------------------------------------------------------------

class TestMakeDiffText:
    def test_cap_a_max_diff_chars(self):
        old = "X" * 100_000
        new = "Y" * 100_000
        diff = _make_diff_text(old, new)
        assert len(diff) <= MAX_DIFF_CHARS + 50  # margen para sufijo "…[diff truncado]"
        assert "[diff truncado]" in diff

    def test_diff_pequenio_no_se_trunca(self):
        diff = _make_diff_text("hola mundo", "hola mundo nuevo")
        assert "[diff truncado]" not in diff
        assert "-hola mundo" in diff or "+hola mundo nuevo" in diff
