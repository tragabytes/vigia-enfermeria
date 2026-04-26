"""
Tests del enricher v2 (capa de IA con tool use + output estructurado).

Mockea el cliente Anthropic para no hacer llamadas reales en CI.

Cobertura:
  - Sin API key → no-op (graceful degradation).
  - Lista vacía → [].
  - JSON directo (sin tool use): el item recibe todos los campos validados.
  - Loop con tool use: el modelo llama fetch_url, le devolvemos contenido,
    responde con JSON. Verifica que el contenido del fetch llega al modelo.
  - JSON envuelto en fence ```json … ```.
  - Validación de enums (process_type, fase) y tipos (plazas int, tasas float).
  - is_relevant aceptado como bool o string ("true"/"false").
  - Fallo en un item no afecta al resto.
  - Loop runaway: si stop_reason siempre = "tool_use", aborta limpio.
  - Sanidad de _run_fetch_url: whitelist, scheme, redirect.
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from vigia import enricher
from vigia.storage import ENRICHMENT_VERSION, Item


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _block(type_: str, **kw):
    """Bloque mock con shape compatible con el SDK Anthropic."""
    return SimpleNamespace(type=type_, **kw)


def _resp(stop_reason: str, blocks: list):
    return SimpleNamespace(stop_reason=stop_reason, content=blocks)


def _make_item(titulo: str = "Convocatoria de prueba", **kw) -> Item:
    return Item(
        source=kw.get("source", "boe"),
        url=kw.get("url", "https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-1234"),
        titulo=titulo,
        fecha=kw.get("fecha", date(2026, 4, 25)),
        categoria=kw.get("categoria", "oposicion"),
    )


_FULL_JSON = """{
  "is_relevant": true,
  "relevance_reason": "Sí, oposición Enfermería del Trabajo en SERMAS",
  "process_type": "oposicion",
  "summary": "12 plazas Enfermero/a del Trabajo · SERMAS · OEP 2025 · Inscripción hasta 15/05/2026.",
  "organismo": "SERMAS",
  "centro": null,
  "plazas": 12,
  "deadline_inscripcion": "2026-05-15",
  "fecha_publicacion_oficial": "2026-04-25",
  "tasas_eur": 30.5,
  "url_bases": "https://www.boe.es/boe/dias/2026/04/25/pdfs/BOE-A-2026-1234.pdf",
  "url_inscripcion": "https://sede.comunidad.madrid/x",
  "requisitos_clave": ["Título de Enfermería del Trabajo", "Experiencia 1 año"],
  "fase": "convocatoria",
  "next_action": "Presentar instancia online antes del 15/05/2026",
  "confidence": 0.92
}"""


# ---------------------------------------------------------------------------
# Graceful degradation
# ---------------------------------------------------------------------------

class TestGracefulDegradation:
    def test_sin_api_key_devuelve_items_intactos(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        items = [_make_item("A"), _make_item("B")]
        result = enricher.enrich(items)
        assert len(result) == 2
        assert all(it.enriched_version is None for it in result)
        assert all(it.summary is None for it in result)

    def test_lista_vacia_no_llama_al_sdk(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        # Si llamáramos al SDK, importaríamos `anthropic` y fallaría con un
        # mock implícito. Verificar que no salimos del primer return.
        result = enricher.enrich([])
        assert result == []


# ---------------------------------------------------------------------------
# Caso feliz: JSON directo sin tool use
# ---------------------------------------------------------------------------

class TestJSONDirecto:
    def test_aplica_todos_los_campos_estructurados(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

        fake_client = MagicMock()
        fake_client.messages.create.return_value = _resp(
            "end_turn", [_block("text", text=_FULL_JSON)]
        )
        import anthropic
        monkeypatch.setattr(anthropic, "Anthropic", lambda: fake_client)

        item = _make_item("OEP 2025 SERMAS")
        result = enricher.enrich([item])

        it = result[0]
        assert it.is_relevant is True
        assert it.process_type == "oposicion"
        assert it.organismo == "SERMAS"
        assert it.plazas == 12
        assert it.deadline_inscripcion == "2026-05-15"
        assert it.tasas_eur == 30.5
        assert it.url_bases.startswith("https://www.boe.es/")
        assert it.requisitos_clave == [
            "Título de Enfermería del Trabajo", "Experiencia 1 año",
        ]
        assert it.fase == "convocatoria"
        assert it.next_action.startswith("Presentar instancia")
        assert 0.0 <= it.confidence <= 1.0
        assert it.enriched_version == ENRICHMENT_VERSION
        assert it.enriched_at is not None
        # El summary v1 también queda actualizado
        assert "12 plazas" in it.summary
        # Una sola llamada (sin tool use)
        assert fake_client.messages.create.call_count == 1

    def test_json_envuelto_en_fence_markdown(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        fenced = "Aquí tienes:\n```json\n" + _FULL_JSON + "\n```"
        fake_client = MagicMock()
        fake_client.messages.create.return_value = _resp(
            "end_turn", [_block("text", text=fenced)]
        )
        import anthropic
        monkeypatch.setattr(anthropic, "Anthropic", lambda: fake_client)

        result = enricher.enrich([_make_item()])
        assert result[0].is_relevant is True
        assert result[0].plazas == 12

    def test_is_relevant_false_se_persiste(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        json_fp = """{
          "is_relevant": false,
          "relevance_reason": "Es Enfermería de Salud Mental",
          "process_type": "oposicion",
          "summary": "Falso positivo",
          "organismo": null, "centro": null, "plazas": null,
          "deadline_inscripcion": null, "fecha_publicacion_oficial": null,
          "tasas_eur": null, "url_bases": null, "url_inscripcion": null,
          "requisitos_clave": [], "fase": "convocatoria",
          "next_action": null, "confidence": 0.95
        }"""
        fake_client = MagicMock()
        fake_client.messages.create.return_value = _resp(
            "end_turn", [_block("text", text=json_fp)]
        )
        import anthropic
        monkeypatch.setattr(anthropic, "Anthropic", lambda: fake_client)

        result = enricher.enrich([_make_item()])
        assert result[0].is_relevant is False
        assert result[0].relevance_reason.startswith("Es Enfermería de Salud Mental")
        assert result[0].enriched_version == ENRICHMENT_VERSION


# ---------------------------------------------------------------------------
# Caso con tool use (loop agentico de 1 turno extra)
# ---------------------------------------------------------------------------

class TestToolUseFlow:
    def test_modelo_llama_fetch_url_y_recibe_contenido(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

        # Simulamos: turno 1 → tool_use, turno 2 → end_turn con JSON.
        first = _resp("tool_use", [
            _block(
                "tool_use",
                id="toolu_1",
                name="fetch_url",
                input={"url": "https://www.boe.es/buscar/doc.php?id=BOE-A-2026-1234"},
            ),
        ])
        second = _resp("end_turn", [_block("text", text=_FULL_JSON)])

        fake_client = MagicMock()
        fake_client.messages.create.side_effect = [first, second]
        import anthropic
        monkeypatch.setattr(anthropic, "Anthropic", lambda: fake_client)

        # Mock del fetcher para que no haga red real
        with patch.object(enricher, "_run_fetch_url",
                          return_value="CUERPO BOE EXTRAÍDO: 12 plazas, plazo 15/05/2026") as fake_fetch:
            result = enricher.enrich([_make_item()])

        assert result[0].plazas == 12
        # Llamó a fetch_url una vez con la URL correcta
        fake_fetch.assert_called_once_with(
            "https://www.boe.es/buscar/doc.php?id=BOE-A-2026-1234"
        )
        # Hizo 2 llamadas al modelo (turno inicial + tras tool_result)
        assert fake_client.messages.create.call_count == 2

        # En el segundo turno, el mensaje user debe contener el tool_result.
        second_call_kwargs = fake_client.messages.create.call_args_list[1].kwargs
        msgs = second_call_kwargs["messages"]
        last_user = next(m for m in reversed(msgs) if m["role"] == "user")
        assert isinstance(last_user["content"], list)
        result_block = last_user["content"][0]
        assert result_block["type"] == "tool_result"
        assert result_block["tool_use_id"] == "toolu_1"
        assert "CUERPO BOE EXTRAÍDO" in result_block["content"]

    def test_loop_runaway_aborta(self, monkeypatch):
        """Si el modelo siempre responde tool_use sin acabar, abortar limpio."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

        looping = _resp("tool_use", [
            _block("tool_use", id="toolu_x", name="fetch_url",
                   input={"url": "https://www.boe.es/x"}),
        ])
        fake_client = MagicMock()
        fake_client.messages.create.return_value = looping
        import anthropic
        monkeypatch.setattr(anthropic, "Anthropic", lambda: fake_client)

        with patch.object(enricher, "_run_fetch_url", return_value="ok"):
            items = [_make_item()]
            result = enricher.enrich(items)

        # Item sigue sin enriquecer (excepción capturada por enrich())
        assert result[0].enriched_version is None
        # Se agotaron las MAX_TOOL_ITERATIONS
        assert fake_client.messages.create.call_count == enricher.MAX_TOOL_ITERATIONS


# ---------------------------------------------------------------------------
# Validación / sanitización de enums y tipos
# ---------------------------------------------------------------------------

class TestSanitizacion:
    def _enrich_with_json(self, monkeypatch, json_str: str) -> Item:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        fake_client = MagicMock()
        fake_client.messages.create.return_value = _resp(
            "end_turn", [_block("text", text=json_str)]
        )
        import anthropic
        monkeypatch.setattr(anthropic, "Anthropic", lambda: fake_client)
        return enricher.enrich([_make_item()])[0]

    def test_process_type_invalido_cae_a_otro(self, monkeypatch):
        item = self._enrich_with_json(monkeypatch, """{
          "is_relevant": true, "process_type": "invento_raro",
          "summary": "x", "fase": "convocatoria"
        }""")
        assert item.process_type == "otro"

    def test_fase_invalida_cae_a_otro(self, monkeypatch):
        item = self._enrich_with_json(monkeypatch, """{
          "is_relevant": true, "process_type": "oposicion",
          "summary": "x", "fase": "fase_inexistente"
        }""")
        assert item.fase == "otro"

    def test_deadline_con_formato_malo_se_descarta(self, monkeypatch):
        item = self._enrich_with_json(monkeypatch, """{
          "is_relevant": true, "process_type": "oposicion",
          "summary": "x", "fase": "convocatoria",
          "deadline_inscripcion": "15 de mayo de 2026"
        }""")
        assert item.deadline_inscripcion is None

    def test_plazas_string_se_coacciona_a_int(self, monkeypatch):
        item = self._enrich_with_json(monkeypatch, """{
          "is_relevant": true, "process_type": "oposicion",
          "summary": "x", "fase": "convocatoria",
          "plazas": "12"
        }""")
        assert item.plazas == 12

    def test_tasas_con_coma_decimal(self, monkeypatch):
        item = self._enrich_with_json(monkeypatch, """{
          "is_relevant": true, "process_type": "oposicion",
          "summary": "x", "fase": "convocatoria",
          "tasas_eur": "30,50"
        }""")
        assert item.tasas_eur == 30.5

    def test_is_relevant_string_si_se_acepta(self, monkeypatch):
        item = self._enrich_with_json(monkeypatch, """{
          "is_relevant": "true", "process_type": "oposicion",
          "summary": "x", "fase": "convocatoria"
        }""")
        assert item.is_relevant is True

    def test_requisitos_no_lista_se_descarta(self, monkeypatch):
        item = self._enrich_with_json(monkeypatch, """{
          "is_relevant": true, "process_type": "oposicion",
          "summary": "x", "fase": "convocatoria",
          "requisitos_clave": "no es una lista"
        }""")
        assert item.requisitos_clave is None


# ---------------------------------------------------------------------------
# Aislamiento de fallos: un item roto no tumba al resto
# ---------------------------------------------------------------------------

class TestFailureIsolation:
    def test_un_item_que_falla_no_corta_los_demas(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

        ok = _resp("end_turn", [_block("text", text=_FULL_JSON)])
        fake_client = MagicMock()
        fake_client.messages.create.side_effect = [
            ConnectionError("simulated"),  # primer item
            ok,                            # segundo item
        ]
        import anthropic
        monkeypatch.setattr(anthropic, "Anthropic", lambda: fake_client)

        items = [_make_item("A"), _make_item("B", url="https://www.boe.es/y")]
        result = enricher.enrich(items)
        assert result[0].enriched_version is None
        assert result[1].enriched_version == ENRICHMENT_VERSION

    def test_respuesta_sin_json_no_tumba_el_pipeline(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        fake_client = MagicMock()
        fake_client.messages.create.return_value = _resp(
            "end_turn", [_block("text", text="Lo siento, no puedo extraer datos.")]
        )
        import anthropic
        monkeypatch.setattr(anthropic, "Anthropic", lambda: fake_client)

        result = enricher.enrich([_make_item()])
        assert result[0].enriched_version is None  # no rompe — solo no enriquece


# ---------------------------------------------------------------------------
# fetch_url: whitelist y validaciones (sin red real)
# ---------------------------------------------------------------------------

class TestFetchUrl:
    def test_dominio_fuera_de_whitelist_devuelve_error(self):
        result = enricher._run_fetch_url("https://attacker.example.com/secret")
        assert result.startswith("ERROR: dominio")

    def test_scheme_no_http_se_rechaza(self):
        result = enricher._run_fetch_url("file:///etc/passwd")
        assert result.startswith("ERROR: scheme")

    def test_url_vacia_se_rechaza(self):
        assert enricher._run_fetch_url("").startswith("ERROR")
        assert enricher._run_fetch_url(None).startswith("ERROR")  # type: ignore[arg-type]

    def test_dominio_permitido_intenta_request(self, monkeypatch):
        """Mock requests.get para verificar que sí llama si el dominio es OK."""
        called = {}

        def fake_get(url, **kwargs):
            called["url"] = url
            resp = MagicMock()
            resp.status_code = 200
            resp.url = url
            resp.headers = {"content-type": "text/html; charset=utf-8"}
            resp.iter_content = lambda chunk_size: [
                b"<html><body><p>12 plazas Enfermero del Trabajo</p></body></html>"
            ]
            resp.close = lambda: None
            return resp

        monkeypatch.setattr(enricher.requests, "get", fake_get)
        result = enricher._run_fetch_url("https://www.boe.es/buscar/x")
        assert "ERROR" not in result
        assert "12 plazas" in result
        assert called["url"] == "https://www.boe.es/buscar/x"

    def test_redirect_a_dominio_no_permitido_se_bloquea(self, monkeypatch):
        def fake_get(url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            resp.url = "https://attacker.example.com/leaked"  # final URL tras redirect
            resp.headers = {"content-type": "text/html"}
            resp.iter_content = lambda chunk_size: [b"hi"]
            resp.close = lambda: None
            return resp

        monkeypatch.setattr(enricher.requests, "get", fake_get)
        result = enricher._run_fetch_url("https://www.boe.es/buscar/x")
        assert result.startswith("ERROR: redirect")

    def test_status_distinto_de_200(self, monkeypatch):
        def fake_get(url, **kwargs):
            resp = MagicMock()
            resp.status_code = 404
            resp.url = url
            resp.headers = {}
            resp.iter_content = lambda chunk_size: []
            resp.close = lambda: None
            return resp

        monkeypatch.setattr(enricher.requests, "get", fake_get)
        result = enricher._run_fetch_url("https://www.boe.es/buscar/x")
        assert result == "ERROR: HTTP 404"


# ---------------------------------------------------------------------------
# Backfill: enrich_pending sigue funcionando contra el storage real
# ---------------------------------------------------------------------------

class TestEnrichPending:
    def test_backfill_v2_actualiza_items_legacy(self, tmp_path, monkeypatch):
        from vigia.storage import Storage

        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        fake_client = MagicMock()
        fake_client.messages.create.return_value = _resp(
            "end_turn", [_block("text", text=_FULL_JSON)]
        )
        import anthropic
        monkeypatch.setattr(anthropic, "Anthropic", lambda: fake_client)

        s = Storage(db_path=tmp_path / "seen.db")
        legacy = _make_item("Item legacy")
        s.save(legacy)
        # Simulamos que el item tiene summary v1 pero enriched_version sigue null
        s._conn.execute(
            "UPDATE items SET summary=?, enriched_version=? WHERE id_hash=?",
            ("summary v1 antiguo", None, legacy.id_hash),
        )
        s._conn.commit()

        n = enricher.enrich_pending(s)
        assert n == 1

        row = s._conn.execute(
            "SELECT enriched_version, plazas, deadline_inscripcion "
            "FROM items WHERE id_hash=?", (legacy.id_hash,),
        ).fetchone()
        s.close()
        assert row[0] == ENRICHMENT_VERSION
        assert row[1] == 12
        assert row[2] == "2026-05-15"

    def test_backfill_sin_pendientes_no_llama_al_sdk(self, tmp_path, monkeypatch):
        from vigia.storage import Storage
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        fake_client = MagicMock()
        import anthropic
        monkeypatch.setattr(anthropic, "Anthropic", lambda: fake_client)

        s = Storage(db_path=tmp_path / "seen.db")
        # BD vacía
        n = enricher.enrich_pending(s)
        s.close()
        assert n == 0
        fake_client.messages.create.assert_not_called()
