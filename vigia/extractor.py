"""
Motor de extracción: aplica las reglas del plan (sección 3) sobre RawItem
y devuelve Item si hay match, None si no.

Es la única fuente de verdad de las reglas de matching y clasificación.
El flujo es:
    sources/*.py  →  extractor.py  →  [enricher.py futuro]  →  notifier.py

Para interponer enricher.py bastará con añadir en main.py:
    items = [enricher.enrich(i) for i in items]   # sin tocar este módulo
"""
from __future__ import annotations

import logging
import re
from datetime import date
from typing import Optional

from vigia.config import (
    CATEGORY_HINTS,
    FALSE_POSITIVE_PATTERNS,
    STRONG_PATTERNS,
    WEAK_CONTEXT_PATTERNS,
    normalize,
)
from vigia.sources.base import RawItem
from vigia.storage import Item

logger = logging.getLogger(__name__)

# Pre-compilar patrones para rendimiento
_STRONG_RE = [re.compile(p) for p in STRONG_PATTERNS]
_FP_RE = [re.compile(p) for p in FALSE_POSITIVE_PATTERNS]
_WEAK_RE = [(re.compile(a), re.compile(b)) for a, b in WEAK_CONTEXT_PATTERNS]


def extract(raw: RawItem) -> Optional[Item]:
    """
    Aplica las reglas sobre un RawItem.

    1. Normaliza título + texto
    2. Descarta falsos positivos
    3. Comprueba match fuerte
    4. Comprueba match débil (requiere contexto)
    5. Clasifica y devuelve Item, o None si no hay match
    """
    combined = normalize(f"{raw.title} {raw.text}")

    # 1. Falsos positivos → descartar antes de cualquier check
    for fp_re in _FP_RE:
        if fp_re.search(combined):
            logger.debug("FP descartado: [%s] %s", raw.source, raw.title[:60])
            return None

    matched = False

    # 2. Match fuerte
    for strong_re in _STRONG_RE:
        if strong_re.search(combined):
            matched = True
            logger.info("Match fuerte [%s]: %s", raw.source, raw.title[:80])
            break

    # 3. Match débil: par (contexto, confirmador)
    if not matched:
        for ctx_re, conf_re in _WEAK_RE:
            ctx_match = ctx_re.search(combined)
            if ctx_match:
                # Comprobar que el confirmador ('enfermer') aparece en una ventana de 100 chars
                start = max(0, ctx_match.start() - 100)
                end = min(len(combined), ctx_match.end() + 100)
                window = combined[start:end]
                if conf_re.search(window):
                    matched = True
                    logger.info("Match débil [%s]: %s", raw.source, raw.title[:80])
                    break

    if not matched:
        return None

    categoria = _classify(combined)

    # Pasamos el texto del RawItem (truncado) al Item.extra para que el
    # enricher (vigia/enricher.py) tenga contexto adicional sin necesidad
    # de re-descargar el cuerpo. No se persiste en SQL — solo vive durante
    # el run.
    extra: dict = {}
    if raw.text:
        extra["raw_text"] = raw.text[:2000]

    return Item(
        source=raw.source,
        url=raw.url,
        titulo=raw.title,
        fecha=raw.date,
        categoria=categoria,
        extra=extra,
    )


def _classify(text: str) -> str:
    """Infiere categoría a partir del texto normalizado."""
    for cat_key, hints in CATEGORY_HINTS.items():
        for hint in hints:
            if hint in text:
                return cat_key
    return "otro"
