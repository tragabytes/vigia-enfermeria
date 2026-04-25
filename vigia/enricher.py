"""
Capa de enriquecimiento con IA — añade un resumen breve a cada Item antes
de notificar.

Encaja como punto de extensión entre el extractor y el notifier:

    sources/*.py → extractor.py → enricher.py → notifier.py

El enricher es opcional: si la variable de entorno `ANTHROPIC_API_KEY` no
está definida, devuelve los items sin tocar y el cron sigue funcionando
exactamente como antes (graceful degradation).

Para minimizar coste y no re-procesar items ya vistos, se llama tras la
deduplicación en main.py — solo enriquecemos los items nuevos que se van
a notificar.

Modelo: Claude Haiku 4.5. Tarea acotada (resumir 2 líneas), no necesita
razonamiento extendido. Coste estimado: ~$0.001 por item.
"""
from __future__ import annotations

import logging
import os

from vigia.storage import Item, Storage

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5"
MAX_TOKENS = 250
MAX_TEXT_CHARS = 1500  # del raw_text que viene del extractor

PROMPT_TEMPLATE = """Eres un asistente que resume convocatorias de empleo público en español, en estilo telegrama.

Convocatoria detectada:
- Fuente: {source}
- Categoría detectada: {categoria}
- Título: {titulo}
- URL: {url}
- Texto adicional disponible: {text}

Genera un resumen breve (máximo 2 líneas, ~200 caracteres) que destaque:
- Nº de plazas (si se menciona)
- Especialidad exacta (Enfermería del Trabajo, salud laboral...)
- Organismo convocante
- Fecha límite de inscripción o de inicio (si aparece)

Sé conciso. Si falta un dato, omítelo — no inventes nada. Responde SOLO con el resumen, sin frases introductorias del tipo "Aquí tienes el resumen" ni explicaciones."""


def enrich(items: list[Item]) -> list[Item]:
    """
    Enriquece cada Item con `summary` generado por Claude.

    Si `ANTHROPIC_API_KEY` no está definida, devuelve la lista sin tocar.
    Si una llamada concreta falla, ese item queda sin summary y los demás
    siguen procesándose. La firma se mantiene compatible para que el flujo
    de main.py no necesite cambios condicionales.
    """
    if not items:
        return items

    if not os.environ.get("ANTHROPIC_API_KEY"):
        logger.info(
            "Enricher: ANTHROPIC_API_KEY no configurada — saltando enriquecimiento"
        )
        return items

    try:
        import anthropic
    except ImportError:
        logger.warning(
            "Enricher: paquete 'anthropic' no instalado — saltando enriquecimiento"
        )
        return items

    client = anthropic.Anthropic()
    enriched = 0
    failed = 0

    for item in items:
        try:
            item.summary = _summarize(client, item)
            enriched += 1
        except Exception as exc:
            failed += 1
            logger.warning(
                "Enricher: fallo al resumir [%s] %s: %s",
                item.source, item.titulo[:60], exc,
            )
            # Item se devuelve sin summary; el notifier lo gestiona como antes.

    logger.info(
        "Enricher: %d/%d items enriquecidos (%d fallidos)",
        enriched, len(items), failed,
    )
    return items


def enrich_pending(storage: Storage) -> int:
    """Enriquece los items en BD que aún no tienen summary y persiste el
    resultado. Devuelve el nº de items efectivamente enriquecidos.

    Útil como tarea de mantenimiento: cuando se incorporó la persistencia
    del summary, los hallazgos previos quedaron sin él; este método los
    completa de forma idempotente (los runs sucesivos solo enriquecen los
    que sigan sin summary).

    Como `raw_text` no se persiste, el LLM solo verá título + categoría +
    fuente + URL — suficiente para un resumen sintético en la mayoría de
    casos.
    """
    pending = storage.iter_items_without_summary()
    if not pending:
        logger.info("Enricher: no hay items pendientes de summary")
        return 0

    logger.info("Enricher: enriqueciendo %d items pendientes", len(pending))
    enriched = enrich(pending)
    n = 0
    for item in enriched:
        if item.summary:
            storage.update_summary(item)
            n += 1
    logger.info("Enricher: %d/%d items recibieron summary", n, len(pending))
    return n


def _summarize(client, item: Item) -> str:
    """Llama a Claude Haiku con el prompt y devuelve el resumen como string."""
    raw_text = ""
    if isinstance(item.extra, dict):
        raw_text = item.extra.get("raw_text", "") or ""
    text_section = raw_text[:MAX_TEXT_CHARS] if raw_text else "(no disponible)"

    prompt = PROMPT_TEMPLATE.format(
        source=item.source,
        categoria=item.categoria,
        titulo=item.titulo[:300],
        url=item.url,
        text=text_section,
    )

    resp = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )

    summary = next(
        (b.text for b in resp.content if getattr(b, "type", None) == "text"),
        "",
    ).strip()

    if not summary:
        raise ValueError("respuesta vacía del LLM")

    return summary
