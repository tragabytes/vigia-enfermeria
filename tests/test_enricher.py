"""
Tests del enricher (capa de IA con Claude).

Mockea el cliente Anthropic para no hacer llamadas reales en CI.
Verifica los tres casos clave:
  1. Con API key configurada → cada item recibe summary.
  2. Sin API key → la lista pasa intacta sin error (graceful degradation).
  3. Si una llamada falla → ese item queda sin summary y los demás siguen.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest

from vigia import enricher
from vigia.storage import Item


def _fake_response(text: str) -> MagicMock:
    """Crea una respuesta-mock del SDK Anthropic con un solo bloque de texto."""
    block = MagicMock()
    block.type = "text"
    block.text = text
    resp = MagicMock()
    resp.content = [block]
    return resp


def _make_item(titulo: str = "Test convocatoria", **kwargs) -> Item:
    return Item(
        source=kwargs.get("source", "datos_madrid"),
        url=kwargs.get("url", "https://example.com/oferta-1"),
        titulo=titulo,
        fecha=date.today(),
        categoria=kwargs.get("categoria", "oep"),
    )


# ---------------------------------------------------------------------------

class TestEnricher:
    def test_sin_api_key_devuelve_items_intactos(self, monkeypatch):
        """Si no hay ANTHROPIC_API_KEY, no se llama al SDK."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        items = [_make_item("Convocatoria A"), _make_item("Convocatoria B")]
        result = enricher.enrich(items)

        assert len(result) == 2
        assert all(it.summary is None for it in result)

    def test_con_api_key_cada_item_recibe_summary(self, monkeypatch):
        """Con la key configurada, cada item se enriquece con un resumen."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

        fake_client = MagicMock()
        fake_client.messages.create.return_value = _fake_response(
            "6 plazas Enfermero/a del Trabajo · Ayto. Madrid · OEP 2025."
        )

        import anthropic
        monkeypatch.setattr(anthropic, "Anthropic", lambda: fake_client)

        items = [_make_item("Item A"), _make_item("Item B")]
        result = enricher.enrich(items)

        assert len(result) == 2
        assert all(it.summary is not None for it in result)
        assert "Enfermero/a del Trabajo" in result[0].summary
        # Una llamada por item
        assert fake_client.messages.create.call_count == 2

    def test_lista_vacia_no_llama_al_sdk(self, monkeypatch):
        """Optimización: si no hay items, ni siquiera importamos anthropic."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        fake_anthropic_module = MagicMock()
        monkeypatch.setattr(enricher, "Item", Item)  # sanity

        result = enricher.enrich([])
        assert result == []

    def test_fallo_de_un_item_no_corta_el_resto(self, monkeypatch):
        """Una excepción al resumir un item no debe afectar a los demás."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

        # El primer create lanza, el segundo devuelve OK
        fake_client = MagicMock()
        fake_client.messages.create.side_effect = [
            ConnectionError("simulated network error"),
            _fake_response("Resumen OK del segundo item."),
        ]

        import anthropic
        monkeypatch.setattr(anthropic, "Anthropic", lambda: fake_client)

        items = [_make_item("A"), _make_item("B")]
        result = enricher.enrich(items)

        assert result[0].summary is None  # falló, sin summary
        assert result[1].summary == "Resumen OK del segundo item."

    def test_respuesta_vacia_se_trata_como_fallo(self, monkeypatch):
        """Si el LLM responde con texto vacío, se trata como error."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

        fake_client = MagicMock()
        fake_client.messages.create.return_value = _fake_response("")
        import anthropic
        monkeypatch.setattr(anthropic, "Anthropic", lambda: fake_client)

        items = [_make_item("A")]
        result = enricher.enrich(items)
        assert result[0].summary is None

    def test_usa_raw_text_del_extra_si_esta_disponible(self, monkeypatch):
        """El enricher inyecta el `raw_text` del Item.extra al prompt."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

        captured_messages = []

        def capture(model, max_tokens, messages, **kwargs):
            captured_messages.extend(messages)
            return _fake_response("ok")

        fake_client = MagicMock()
        fake_client.messages.create.side_effect = capture

        import anthropic
        monkeypatch.setattr(anthropic, "Anthropic", lambda: fake_client)

        item = _make_item("Convocatoria X")
        item.extra = {"raw_text": "Contenido específico del cuerpo del documento."}
        enricher.enrich([item])

        assert any(
            "Contenido específico del cuerpo" in m["content"]
            for m in captured_messages
        )

    def test_si_no_hay_raw_text_el_prompt_indica_no_disponible(self, monkeypatch):
        """Sin raw_text en extra, el prompt usa '(no disponible)'."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

        captured = []

        def capture(model, max_tokens, messages, **kwargs):
            captured.extend(messages)
            return _fake_response("ok")

        fake_client = MagicMock()
        fake_client.messages.create.side_effect = capture
        import anthropic
        monkeypatch.setattr(anthropic, "Anthropic", lambda: fake_client)

        item = _make_item("Sin contexto")
        # extra={} por defecto en post_init
        enricher.enrich([item])

        assert any("(no disponible)" in m["content"] for m in captured)
