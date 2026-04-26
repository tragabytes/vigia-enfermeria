"""
Enriquecimiento estructurado con IA — Nivel 2.

Sustituye al enricher single-shot anterior. En lugar de generar un sumario
textual, lanza una conversación agentica corta con Claude Sonnet 4.6 que:

  1. Recibe los datos del Item (título, fuente, URL, categoría, raw_text).
  2. Puede invocar una tool `fetch_url(url)` para descargar el cuerpo de
     la convocatoria desde dominios oficiales.
  3. Devuelve un JSON estructurado con los campos clave: relevancia real
     (¿es Enfermería del Trabajo o un falso positivo?), tipo de proceso,
     plazas, deadline de inscripción, tasas, bases, fase del proceso y
     próxima acción.

El enricher es opcional: si `ANTHROPIC_API_KEY` no está definida, devuelve
los items intactos y el cron sigue funcionando (graceful degradation).

Encaja como punto de extensión entre extractor y notifier:

    sources/*.py → extractor.py → enricher.py → notifier.py

Para el backfill del histórico (items que entraron con la versión v1 o
sin enriquecer), usar `enrich_pending(storage)` desde el workflow de
mantenimiento.

Modelo: Claude Sonnet 4.6. Tool use con un único `fetch_url` whitelisted.
Coste estimado al volumen real (≤3 items/día): ~$3/año.
"""
from __future__ import annotations

import io
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlparse

import requests

from vigia.config import USER_AGENT
from vigia.storage import ENRICHMENT_VERSION, Item, Storage

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuración del modelo
# ---------------------------------------------------------------------------

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 2048
MAX_TOOL_ITERATIONS = 4   # tope de loops para evitar runaway costs
# Texto inyectado en el prompt inicial. 1500 chars era insuficiente para
# convocatorias BOE genéricas tipo "personal facultativo y técnico" donde
# las plazas concretas de Enfermería viven más allá del char 8000 (caso
# real: BOE-A-2026-795 Policía Nacional). 12k chars (~3k tokens input
# extra por item) cubre la mayoría de items BOE/BOCM sin saturar contexto.
MAX_TEXT_CHARS = 12000

# ---------------------------------------------------------------------------
# Configuración del fetcher (anti-SSRF + límites)
# ---------------------------------------------------------------------------

# Whitelist estricta de hostnames permitidos en `fetch_url`. Cualquier otro
# dominio devuelve error inmediato sin hacer la request — incluido tras
# seguir redirects.
ALLOWED_FETCH_HOSTS: set[str] = {
    # BOE
    "boe.es", "www.boe.es",
    # BOCM (sumario y descargas)
    "bocm.es", "www.bocm.es",
    # Comunidad de Madrid (sede y portales relacionados)
    "comunidad.madrid", "www.comunidad.madrid",
    "sede.comunidad.madrid", "transparencia.comunidad.madrid",
    # Ayuntamiento de Madrid (incluye sede que sirve BOAM)
    "madrid.es", "www.madrid.es", "sede.madrid.es",
    "transparencia.madrid.es",
    # Datos abiertos del Ayto.
    "datos.madrid.es",
    # Canal de Isabel II (web de convocatorias)
    "convocatoriascanaldeisabelsegunda.es",
    "www.convocatoriascanaldeisabelsegunda.es",
    # CODEM
    "codem.es", "www.codem.es",
}

MAX_FETCH_BYTES = 5 * 1024 * 1024     # 5 MB
FETCH_TIMEOUT_SECONDS = 15
MAX_FETCH_TEXT_CHARS = 30_000          # truncamos antes de devolverlo al LLM


# ---------------------------------------------------------------------------
# Definición de la tool registrada con el modelo
# ---------------------------------------------------------------------------

FETCH_URL_TOOL: dict[str, Any] = {
    "name": "fetch_url",
    "description": (
        "Descarga el contenido de una URL oficial (BOE, BOCM, BOAM, sede de "
        "la Comunidad de Madrid, Ayuntamiento de Madrid, Canal de Isabel II, "
        "CODEM, datos.madrid.es) y devuelve el texto extraído. Usar para "
        "consultar el cuerpo de una convocatoria, sus bases o un PDF anexo "
        "cuando el título no contiene los datos pedidos. Acepta HTML y PDF. "
        "Solo URLs https. Tamaño máximo 5MB. Resultado truncado a 30k caracteres."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "URL absoluta de la convocatoria, anexo o PDF de bases.",
            },
        },
        "required": ["url"],
    },
}


# ---------------------------------------------------------------------------
# Schema de salida esperada del modelo (JSON estructurado)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """Eres un asistente que extrae datos estructurados de convocatorias de empleo público en España, especializado en plazas para Enfermería del Trabajo (también llamada Enfermería de Empresa o Enfermería de Salud Laboral, sinónimos a efectos de catálogo del Ministerio de Sanidad).

Tu trabajo: recibir el dato bruto de una convocatoria y devolver un JSON con los campos clave. Puedes (y debes, cuando los datos no estén en el resumen recibido) usar la tool `fetch_url` para descargar el cuerpo del boletín o el PDF de bases.

CRITERIOS PARA `is_relevant`:
- TRUE → la convocatoria ofrece plazas, bolsa o concurso de traslados específicamente para la especialidad de Enfermería del Trabajo / Salud Laboral / Enfermería de Empresa, o es un servicio de prevención de riesgos laborales que requiere esa titulación.
- FALSE → falsos positivos típicos: Enfermería de Salud Mental, Pediátrica, Familiar y Comunitaria, Geriátrica, Obstétrico-Ginecológica (matronas), o Enfermería general sin especialidad. También FALSE si solo es un nombramiento/lista provisional/cese sin plazas nuevas para la especialidad.
- En la duda, prioriza FALSE — el sistema reduce ruido eliminando items con is_relevant=false.

CRITERIOS PARA `process_type`:
- "oposicion" → proceso selectivo / pruebas selectivas / concurso-oposición de acceso libre
- "bolsa" → bolsa de empleo, bolsa única, contratación temporal estructurada
- "concurso_traslados" → concurso de traslados / concurso de méritos entre estatutarios
- "interinaje" → nombramiento de interino / sustitución concreta
- "temporal" → contrato temporal puntual no incluido en bolsa
- "otro" → cualquier otro caso

CRITERIOS PARA `fase`:
- "convocatoria" → publicación inicial con plazo de inscripción abierto
- "admitidos_provisional" / "admitidos_definitivo" → listas de admitidos
- "examen" → fechas/sedes del ejercicio
- "calificacion" → resultados de un ejercicio o calificación final
- "propuesta_nombramiento" → resolución de adjudicación
- "otro" → cualquier otro estado intermedio

REGLAS DE EXTRACCIÓN:
- Fechas en formato `YYYY-MM-DD`. Si solo conoces el mes y año, deja `null`.
- `plazas`: solo el TOTAL de plazas convocadas; si no aparece, `null`.
- `tasas_eur`: tasa de inscripción base en euros (no descuentos ni reducciones).
- `url_bases`: URL al PDF/HTML con las bases completas (a veces es un anexo distinto del que recibes).
- `requisitos_clave`: lista corta (≤4) de requisitos imprescindibles (titulación específica, experiencia, etc.). No copies todo el listado del BOE — solo lo más diferenciador.
- `next_action`: una frase ≤140 chars con la acción inmediata que el usuario debe tomar (ej. "Presentar instancia online en sede.comunidad.madrid antes del 15/05/2026").
- `summary`: ~200 caracteres en estilo telegrama, factual, sin frases introductorias. Mismo formato que el enricher v1.
- `confidence`: 0..1 según lo seguro que estés del extracto general.
- Si un campo no es deducible con razonable certeza, devuélvelo como `null`. NO INVENTES NADA.

USO DE LA TOOL:
- Si el título y `raw_text` son suficientes para todos los campos pedidos, NO llames a la tool — responde directamente con el JSON.
- Si te falta algún dato clave (deadline, plazas, tasas, bases) y la URL principal está en dominio oficial, llámala una vez para inspeccionar el cuerpo.
- IMPORTANTE — falsos negativos a evitar: si el sistema te ha enviado este item es porque un matcher automático YA detectó "Enfermería del Trabajo", "Enfermería de Empresa", "Enfermería de Salud Laboral" o "salud laboral + enfermer" en el cuerpo descargado de la convocatoria. Si el `raw_text` que recibes no muestra esa evidencia, ES PORQUE LLEGA TRUNCADO — los listados de plazas suelen estar más adelante en el documento. En ese caso DEBES llamar a `fetch_url` para descargar el HTML/PDF completo antes de marcar `is_relevant=false`. Solo descarta si tras consultar la URL tampoco aparece la especialidad.
- Como mucho 2 llamadas a tool por item. Después responde con lo que tengas.

FORMATO DE SALIDA OBLIGATORIO:
Responde SOLO con un bloque JSON válido (puedes envolverlo en ```json … ``` si quieres). Sin texto antes ni después. El JSON debe seguir este schema (todos los campos opcionales pueden ser null):

{
  "is_relevant": true|false,
  "relevance_reason": "string",
  "process_type": "oposicion|bolsa|concurso_traslados|interinaje|temporal|otro",
  "summary": "string ~200 chars",
  "organismo": "string|null",
  "centro": "string|null",
  "plazas": int|null,
  "deadline_inscripcion": "YYYY-MM-DD|null",
  "fecha_publicacion_oficial": "YYYY-MM-DD|null",
  "tasas_eur": float|null,
  "url_bases": "string|null",
  "url_inscripcion": "string|null",
  "requisitos_clave": ["string", ...] | [],
  "fase": "convocatoria|admitidos_provisional|admitidos_definitivo|examen|calificacion|propuesta_nombramiento|otro",
  "next_action": "string|null",
  "confidence": 0.0..1.0
}"""


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def enrich(items: list[Item]) -> list[Item]:
    """Enriquece cada Item con la información estructurada del enricher v2.

    Si `ANTHROPIC_API_KEY` no está configurada, devuelve la lista sin tocar.
    Si una llamada concreta falla, ese item queda sin enriquecimiento y los
    demás siguen procesándose. La firma se mantiene compatible con el
    enricher v1 para que `main.py` no necesite cambios condicionales.
    """
    if not items:
        return items

    if not os.environ.get("ANTHROPIC_API_KEY"):
        logger.info(
            "Enricher: ANTHROPIC_API_KEY no configurada — saltando enriquecimiento"
        )
        return items

    try:
        import anthropic  # noqa: F401
    except ImportError:
        logger.warning(
            "Enricher: paquete 'anthropic' no instalado — saltando enriquecimiento"
        )
        return items

    import anthropic as _anthropic
    client = _anthropic.Anthropic()
    enriched = 0
    failed = 0

    for item in items:
        try:
            data = _enrich_one(client, item)
            _apply_enrichment(item, data)
            enriched += 1
        except Exception as exc:
            failed += 1
            logger.warning(
                "Enricher: fallo al enriquecer [%s] %s: %s",
                item.source, item.titulo[:60], exc,
            )

    logger.info(
        "Enricher v2: %d/%d items enriquecidos (%d fallidos)",
        enriched, len(items), failed,
    )
    return items


def enrich_pending(storage: Storage) -> int:
    """Enriquece los items de BD que aún no estén en `ENRICHMENT_VERSION`.

    Idempotente — recorre todos los items con `enriched_version IS NULL`
    o `< ENRICHMENT_VERSION` (es decir, sin enriquecer o con summary v1
    pendiente de actualizar a la estructura v2). Persiste el resultado en
    BD vía `update_enrichment` y devuelve el nº de items efectivamente
    enriquecidos.

    Pensado para correr desde el workflow `maintenance.yml` cuando se
    sube `ENRICHMENT_VERSION` o se incorporan los nuevos campos.
    """
    pending = storage.iter_items_for_enrichment()
    if not pending:
        logger.info("Enricher: no hay items pendientes de enriquecimiento")
        return 0

    logger.info(
        "Enricher: %d items pendientes (objetivo v%d)",
        len(pending), ENRICHMENT_VERSION,
    )
    enriched = enrich(pending)
    n = 0
    for item in enriched:
        if item.enriched_version is not None:
            storage.update_enrichment(item)
            n += 1
    logger.info(
        "Enricher: %d/%d items recibieron enriquecimiento v%d",
        n, len(pending), ENRICHMENT_VERSION,
    )
    return n


# ---------------------------------------------------------------------------
# Loop interno con tool use
# ---------------------------------------------------------------------------

def _enrich_one(client, item: Item) -> dict[str, Any]:
    """Lanza la conversación con Sonnet hasta obtener el JSON final.

    Limita a `MAX_TOOL_ITERATIONS` para que un item no dispare un loop
    runaway. Si el modelo se queda en stop_reason "tool_use" pasado el
    tope, se aborta con excepción y el item queda sin enriquecer (lo
    captura el `try/except` del caller).
    """
    user_content = _build_initial_user_content(item)
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": user_content},
    ]

    for iteration in range(MAX_TOOL_ITERATIONS):
        resp = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=[FETCH_URL_TOOL],
            messages=messages,
        )

        if resp.stop_reason == "tool_use":
            # Acumula la respuesta del modelo (incluye tool_use blocks) y
            # devuelve los tool_results en el siguiente turno user.
            messages.append({"role": "assistant", "content": resp.content})
            tool_results = []
            for block in resp.content:
                if getattr(block, "type", None) == "tool_use":
                    if block.name != "fetch_url":
                        result_text = (
                            f"ERROR: tool '{block.name}' no soportada"
                        )
                    else:
                        url = (block.input or {}).get("url", "")
                        result_text = _run_fetch_url(url)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_text,
                    })
            if not tool_results:
                # stop_reason era tool_use pero no había bloques tool_use →
                # estado inconsistente, abortamos.
                raise RuntimeError("tool_use sin bloques tool_use")
            messages.append({"role": "user", "content": tool_results})
            continue

        if resp.stop_reason in ("end_turn", "stop_sequence"):
            text = "".join(
                b.text for b in resp.content
                if getattr(b, "type", None) == "text"
            ).strip()
            if not text:
                raise ValueError("respuesta final vacía del LLM")
            return _parse_json_block(text)

        raise RuntimeError(
            f"stop_reason inesperado: {resp.stop_reason!r}"
        )

    raise RuntimeError(
        f"loop excedió {MAX_TOOL_ITERATIONS} iteraciones sin respuesta final"
    )


def _build_initial_user_content(item: Item) -> str:
    raw_text = ""
    if isinstance(item.extra, dict):
        raw_text = item.extra.get("raw_text", "") or ""

    # Construcción del bloque de texto auxiliar:
    # - Primeros ~4KB para contexto general (organismo, fechas iniciales).
    # - Snippets dirigidos con ventanas de 400 chars alrededor de cada
    #   palabra clave. Esto es decisivo para items BOE largos (>100KB)
    #   donde las plazas concretas viven más allá del char 80000 — un
    #   simple truncado al inicio nunca las ve.
    if raw_text:
        head = raw_text[:4000]
        snippets = _extract_relevant_snippets(raw_text, max_snippets=6)
        snippet_block = ""
        if snippets:
            snippet_block = (
                "\n\n[Fragmentos relevantes localizados por el matcher "
                "automático en el cuerpo descargado:]\n"
                + "\n---\n".join(snippets)
            )
        # Tope total para no saturar el prompt.
        body_section = (head + snippet_block)[:MAX_TEXT_CHARS]
    else:
        body_section = "(no disponible)"

    return (
        "Convocatoria detectada por el sistema:\n"
        f"- Fuente: {item.source}\n"
        f"- Categoría heurística: {item.categoria}\n"
        f"- Título: {item.titulo[:300]}\n"
        f"- URL: {item.url}\n"
        f"- Fecha de detección: {item.fecha}\n"
        f"- Texto adicional disponible:\n{body_section}\n\n"
        "Devuelve el JSON estructurado siguiendo el schema definido en las "
        "instrucciones del sistema. Llama a `fetch_url` solo si necesitas "
        "datos que no están arriba."
    )


# Keywords ordenadas por prioridad: las que confirman match positivo del
# extractor van primero (HIGH); las contextuales (WEAK / genéricas) detrás.
# Esto importa porque en items BOE largos las menciones genéricas de
# "Prevención de Riesgos Laborales" aparecen a lo largo del documento
# (lactancia, gestión, etc.) y saturarían el max_snippets antes de llegar
# a las menciones STRONG (que están en el listado de plazas, hacia el
# final). Procesamos HIGH primero para garantizar que llegan al prompt.
_SNIPPET_KEYWORDS_HIGH: list[str] = [
    # Strong matches del extractor — la propia especialidad
    "enfermería del trabajo", "enfermeria del trabajo",
    "enfermería de empresa", "enfermeria de empresa",
    "enfermería de salud laboral", "enfermeria de salud laboral",
    "enfermero del trabajo", "enfermera del trabajo",
    "enfermero de empresa", "enfermera de empresa",
    "enfermero/a del trabajo", "enfermero/a de empresa",
    "especialista en enfermería del trabajo",
    "especialidad enfermería del trabajo",
    # Categoría profesional convocada
    "especialidad enfermería", "especialidad enfermeria",
    "especialidad en enfermería", "especialidad en enfermeria",
    "especialista en enfermería", "especialista en enfermeria",
]
_SNIPPET_KEYWORDS_LOW: list[str] = [
    "enfermería (prevención", "enfermeria (prevencion",
    "(prevención riesgos", "(prevencion riesgos",
    "salud laboral",
    "servicio de prevención", "servicio de prevencion",
    "prevención de riesgos laborales", "prevencion de riesgos laborales",
    "(prl)", " prl ",
]


def _extract_relevant_snippets(
    text: str,
    window: int = 400,
    max_snippets: int = 6,
) -> list[str]:
    """Devuelve hasta `max_snippets` ventanas de ~`window` chars centradas
    en cada match de las keywords. Fusiona ventanas que se solapan para no
    duplicar contexto.

    Estrategia: procesa primero las keywords HIGH (prueba directa de la
    especialidad de Enfermería del Trabajo) hasta agotar `max_snippets`;
    si sobra cupo, rellena con keywords LOW (contexto de PRL/salud
    laboral). Sin esto, en items BOE largos los matches genéricos de
    "Prevención de Riesgos Laborales" en bloques tempranos del documento
    se comían todo el cupo antes de llegar a la sección de plazas.

    Pensado para inyectar al prompt del enricher cuando el cuerpo del
    item es demasiado largo para mandarlo entero (HTML BOE: 100-300KB).
    """
    if not text:
        return []

    text_lower = text.lower()
    half = window // 2

    def _find_spans(keywords: list[str]) -> list[tuple[int, int]]:
        spans: list[tuple[int, int]] = []
        for kw in keywords:
            start = 0
            while True:
                idx = text_lower.find(kw, start)
                if idx == -1:
                    break
                spans.append((idx, idx + len(kw)))
                start = idx + 1
                if len(spans) > 500:
                    break
            if len(spans) > 500:
                break
        return sorted(spans)

    def _spans_to_windows(
        spans: list[tuple[int, int]],
        existing: list[tuple[int, int]],
    ) -> list[tuple[int, int]]:
        out = list(existing)
        for s, e in spans:
            ws, we = max(0, s - half), min(len(text), e + half)
            # Fusionar con ventanas existentes que solapen (independiente
            # del orden de inserción HIGH/LOW).
            merged = False
            for i, (xs, xe) in enumerate(out):
                if ws <= xe and we >= xs:
                    out[i] = (min(xs, ws), max(xe, we))
                    merged = True
                    break
            if not merged:
                out.append((ws, we))
            if len(out) >= max_snippets:
                break
        return out

    # 1. Procesar HIGH primero (tomamos hasta max_snippets matches HIGH).
    high_windows = _spans_to_windows(_find_spans(_SNIPPET_KEYWORDS_HIGH), [])
    # 2. Si queda cupo, rellenar con LOW.
    final_windows = (
        high_windows
        if len(high_windows) >= max_snippets
        else _spans_to_windows(_find_spans(_SNIPPET_KEYWORDS_LOW), high_windows)
    )

    if not final_windows:
        return []

    # 3. Ordenar por offset y materializar el texto.
    final_windows.sort()
    snippets = []
    for ws, we in final_windows[:max_snippets]:
        snippet = text[ws:we].replace("\n", " ").strip()
        prefix = "…" if ws > 0 else ""
        suffix = "…" if we < len(text) else ""
        snippets.append(prefix + snippet + suffix)
    return snippets


# ---------------------------------------------------------------------------
# Tool runner — fetch_url con whitelist anti-SSRF
# ---------------------------------------------------------------------------

def _run_fetch_url(url: str) -> str:
    """Descarga la URL y devuelve texto extraído. Devuelve mensaje de error
    como string si algo falla (no lanza excepciones — el LLM debe poder
    seguir trabajando con el resto de información)."""
    if not url or not isinstance(url, str):
        return "ERROR: url ausente o no es string"

    try:
        parsed = urlparse(url)
    except Exception:
        return "ERROR: url malformada"

    if parsed.scheme not in ("http", "https"):
        return f"ERROR: scheme '{parsed.scheme}' no permitido (solo http/https)"

    host = (parsed.hostname or "").lower()
    if host not in ALLOWED_FETCH_HOSTS:
        return (
            f"ERROR: dominio '{host}' fuera de la whitelist. "
            f"Permitidos: {', '.join(sorted(ALLOWED_FETCH_HOSTS))}"
        )

    try:
        resp = requests.get(
            url,
            timeout=FETCH_TIMEOUT_SECONDS,
            stream=True,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/pdf,application/json,*/*",
            },
            allow_redirects=True,
        )
    except requests.RequestException as exc:
        return f"ERROR: request fallida ({exc.__class__.__name__}: {exc})"

    # Validar el host final tras redirects (defensa adicional anti-SSRF).
    final_host = (urlparse(resp.url).hostname or "").lower()
    if final_host not in ALLOWED_FETCH_HOSTS:
        resp.close()
        return f"ERROR: redirect a dominio no permitido ('{final_host}')"

    if resp.status_code != 200:
        resp.close()
        return f"ERROR: HTTP {resp.status_code}"

    body = bytearray()
    for chunk in resp.iter_content(chunk_size=8192):
        if not chunk:
            continue
        body.extend(chunk)
        if len(body) >= MAX_FETCH_BYTES:
            body = body[:MAX_FETCH_BYTES]
            break
    resp.close()

    content_type = (resp.headers.get("content-type") or "").lower()
    is_pdf = "pdf" in content_type or url.lower().endswith(".pdf")

    if is_pdf:
        text = _extract_pdf_text(bytes(body))
    else:
        text = _extract_html_text(bytes(body))

    if not text.strip():
        return "ERROR: contenido vacío tras extracción"

    if len(text) > MAX_FETCH_TEXT_CHARS:
        return text[:MAX_FETCH_TEXT_CHARS] + "\n[…texto truncado…]"
    return text


def _extract_pdf_text(data: bytes) -> str:
    """Extrae texto plano de un PDF. Usa pdfplumber (ya en requirements)."""
    try:
        import pdfplumber
    except ImportError:
        return "ERROR: pdfplumber no instalado"

    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            chunks = []
            for page in pdf.pages[:30]:   # cap a 30 páginas para acotar
                t = page.extract_text() or ""
                if t:
                    chunks.append(t)
            return "\n\n".join(chunks)
    except Exception as exc:
        return f"ERROR: parseo PDF falló ({exc})"


def _extract_html_text(data: bytes) -> str:
    """Extrae texto legible de HTML. Quita scripts/styles y colapsa blancos."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return data.decode("utf-8", errors="replace")

    try:
        soup = BeautifulSoup(data, "lxml")
    except Exception:
        soup = BeautifulSoup(data, "html.parser")

    for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    # colapsa blancos
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Parsing y aplicación del JSON al Item
# ---------------------------------------------------------------------------

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _parse_json_block(text: str) -> dict[str, Any]:
    """Intenta extraer el JSON del texto del LLM.

    Acepta tres formatos:
      1. JSON puro (todo el texto es el objeto).
      2. JSON envuelto en ```json … ``` (markdown fence).
      3. Cualquier objeto JSON encerrado en {} dentro del texto.
    """
    text = text.strip()
    # 1. JSON directo
    if text.startswith("{") and text.endswith("}"):
        return json.loads(text)
    # 2. Fence ```json ... ```
    m = _JSON_FENCE_RE.search(text)
    if m:
        return json.loads(m.group(1))
    # 3. Primer { ... último } por matching de llaves
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start:end + 1])
    raise ValueError("no se encontró bloque JSON en la respuesta del LLM")


# Conjuntos válidos para sanitizar valores enum del LLM.
_VALID_PROCESS_TYPES = {
    "oposicion", "bolsa", "concurso_traslados", "interinaje", "temporal", "otro",
}
_VALID_FASES = {
    "convocatoria", "admitidos_provisional", "admitidos_definitivo",
    "examen", "calificacion", "propuesta_nombramiento", "otro",
}
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _apply_enrichment(item: Item, data: dict[str, Any]) -> None:
    """Vuelca el dict del LLM en el `Item`, validando tipos y enums.

    Cualquier valor no reconocido se baja a `None` o al fallback "otro".
    Esto evita corromper la BD con strings que el frontend no sabría pintar.
    """
    item.is_relevant = _coerce_bool(data.get("is_relevant"))
    item.relevance_reason = _coerce_str(data.get("relevance_reason"))

    pt = _coerce_str(data.get("process_type"))
    item.process_type = pt if pt in _VALID_PROCESS_TYPES else (
        "otro" if pt else None
    )

    item.summary = _coerce_str(data.get("summary"))
    item.organismo = _coerce_str(data.get("organismo"))
    item.centro = _coerce_str(data.get("centro"))
    item.plazas = _coerce_int(data.get("plazas"))

    deadline = _coerce_str(data.get("deadline_inscripcion"))
    item.deadline_inscripcion = deadline if (deadline and _DATE_RE.match(deadline)) else None

    fpub = _coerce_str(data.get("fecha_publicacion_oficial"))
    item.fecha_publicacion_oficial = fpub if (fpub and _DATE_RE.match(fpub)) else None

    item.tasas_eur = _coerce_float(data.get("tasas_eur"))
    item.url_bases = _coerce_str(data.get("url_bases"))
    item.url_inscripcion = _coerce_str(data.get("url_inscripcion"))

    reqs = data.get("requisitos_clave")
    if isinstance(reqs, list):
        item.requisitos_clave = [str(x) for x in reqs if x is not None][:8]
    else:
        item.requisitos_clave = None

    fase = _coerce_str(data.get("fase"))
    item.fase = fase if fase in _VALID_FASES else (
        "otro" if fase else None
    )

    item.next_action = _coerce_str(data.get("next_action"))
    item.confidence = _coerce_float(data.get("confidence"))
    item.enriched_at = datetime.now(timezone.utc).isoformat()
    item.enriched_version = ENRICHMENT_VERSION


def _coerce_bool(v: Any) -> Optional[bool]:
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("true", "yes", "si", "sí", "1"):
            return True
        if s in ("false", "no", "0"):
            return False
    return None


def _coerce_str(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        return s or None
    return str(v)


def _coerce_int(v: Any) -> Optional[int]:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    if isinstance(v, str):
        s = v.strip()
        try:
            return int(s)
        except ValueError:
            try:
                return int(float(s))
            except ValueError:
                return None
    return None


def _coerce_float(v: Any) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.strip().replace(",", "."))
        except ValueError:
            return None
    return None
