"""Diff summarizer — qué ha cambiado entre dos snapshots de la misma URL.

Las fuentes hash-watcher (`cm_ficha_enfermeria`, `isciii`,
`canal_isabel_ii_calendario`) y el DetailWatcher genérico emiten un
`RawItem` cada vez que el body de su URL cambia (sha1 distinto). Pero
"el body cambió" incluye ruido cosmético: el campo `Última actualización`
del propio CMS sube cada vez que el administrador toca la página, aunque
no añada contenido nuevo. Resultado: alertas Telegram por cambios sin
información útil (caso real: cm_ficha snapshot 02336ae581→67324b71b7 del
2026-05-25, fue sólo el timestamp).

Este módulo determina si el diff entre dos versiones es:
  - **sustantivo**: información nueva relevante para el opositor
    (nueva fase, plazo, lista de admitidos, examen, resolución…). Se
    notifica con un resumen del cambio en lugar de "🟢 NUEVO".
  - **cosmético**: ruido administrativo. Se marca `is_relevant=False` y
    el notifier filtra la alerta (igual mecanismo que filtra los FP del
    enricher).

Estrategia en dos pasos:

1. **Pre-filtro local** (`_classify_locally`): difflib + regex de
   patrones volátiles conocidos. Si todas las líneas que cambian
   matchean (`Última actualización`, timestamps), decisión sin red ni
   coste.

2. **Llamada a Sonnet** (`_classify_via_llm`): si el pre-filtro no
   decide, se manda el unified diff al modelo con un prompt minimalista
   que pide JSON `{"sustantivo": bool, "resumen": "..."}`. Sin tool use,
   sin fetch web — sólo el texto del diff. Coste ~$0.0005 por llamada.

Comportamiento ante errores (sin API key, sin SDK, error de red, JSON
inválido): devuelve `(True, None)` — fail-open, la alerta llega como
"nuevo snapshot" sin resumen. Esto preserva el comportamiento anterior
(no perdemos alertas) cuando el sumarizador no puede operar.
"""
from __future__ import annotations

import difflib
import json
import logging
import os
import re
from typing import Optional

from vigia.profile import get_active_profile

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pre-filtro local — patrones de líneas volátiles del CMS
# ---------------------------------------------------------------------------

# Cualquier línea que cambie y matchee uno de estos patrones cuenta como
# "ruido administrativo". Si TODAS las líneas que cambian son volátiles,
# el diff se clasifica como cosmético sin llamar al LLM.
VOLATILE_PATTERNS: list[re.Pattern] = [
    # "Última actualización: 25 mayo 2026" — campo estándar de Drupal y
    # otros CMS, sube cada vez que un editor toca la página.
    re.compile(r"[Úú]ltima\s+actualizaci[oó]n", re.IGNORECASE),
    # Timestamps tipo "DD/MM/YYYY HH:MM" o "DD-MM-YYYY HH:MM:SS".
    re.compile(r"\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}\s+\d{1,2}:\d{2}"),
    # Widget "Compartir: X Facebook correo" — UI noise común.
    re.compile(r"^Compartir:", re.IGNORECASE),
]


# ---------------------------------------------------------------------------
# Configuración del LLM
# ---------------------------------------------------------------------------

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 256
MAX_DIFF_CHARS = 8000  # truncamos antes de mandar para acotar coste

SYSTEM_PROMPT = get_active_profile().diff_system_prompt

USER_TEMPLATE = (
    "Analiza este diff:\n\n```\n{diff}\n```\n\nResponde sólo el JSON."
)


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def summarize_diff(text_old: str, text_new: str) -> tuple[bool, Optional[str]]:
    """Decide si el cambio entre `text_old` y `text_new` es sustantivo y,
    si lo es, devuelve una frase resumen.

    Returns:
        `(substantive, summary)`:
          - `substantive=False, summary=None`: cosmético — el notifier
            debe SUPRIMIR la alerta marcando `is_relevant=False`.
          - `substantive=True, summary="..."`: cambio real con resumen.
          - `substantive=True, summary=None`: cambio real pero no se
            pudo generar resumen (fail-open: notifica sin resumen).

    Casos especiales:
      - `text_old == text_new`: devuelve `(False, None)` directamente.
      - `text_old` o `text_new` vacío: devuelve `(True, None)` — sin
        base para diff, dejamos pasar la alerta.
    """
    if not text_old or not text_new:
        return (True, None)
    if text_old == text_new:
        return (False, None)

    # 1. Pre-filtro local — sin API.
    local_decision = _classify_locally(text_old, text_new)
    if local_decision is not None:
        return local_decision

    # 2. Pasa al LLM. Manejo de errores: fail-open.
    try:
        return _classify_via_llm(text_old, text_new)
    except Exception as exc:
        logger.warning("diff_summarizer: error inesperado, fail-open: %s", exc)
        return (True, None)


# ---------------------------------------------------------------------------
# Pre-filtro local
# ---------------------------------------------------------------------------

def _classify_locally(
    text_old: str, text_new: str
) -> Optional[tuple[bool, Optional[str]]]:
    """Si todas las líneas que cambian son volátiles → cosmético. Si no,
    devuelve `None` para que decida el LLM."""
    diff_lines = list(difflib.unified_diff(
        text_old.splitlines(),
        text_new.splitlines(),
        n=0,
        lineterm="",
    ))
    # Líneas reales de cambio (excluyendo cabeceras +++ --- y @@).
    changes = [
        ln[1:].strip()
        for ln in diff_lines
        if ln and ln[0] in "+-"
        and not ln.startswith(("+++", "---"))
    ]
    # Filtramos líneas vacías que aparezcan tras strip (mero whitespace).
    changes = [c for c in changes if c]
    if not changes:
        # Diff sólo de whitespace.
        return (False, None)

    all_volatile = all(
        any(p.search(line) for p in VOLATILE_PATTERNS)
        for line in changes
    )
    if all_volatile:
        return (False, None)
    return None


# ---------------------------------------------------------------------------
# Llamada al LLM
# ---------------------------------------------------------------------------

def _classify_via_llm(
    text_old: str, text_new: str
) -> tuple[bool, Optional[str]]:
    """Pasa el unified diff a Sonnet y parsea su JSON. Errores burbujean
    al caller (que hace fail-open)."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        logger.info(
            "diff_summarizer: ANTHROPIC_API_KEY no configurada — fail-open"
        )
        return (True, None)
    try:
        import anthropic as _anthropic
    except ImportError:
        logger.warning(
            "diff_summarizer: paquete anthropic no instalado — fail-open"
        )
        return (True, None)

    diff_text = _make_diff_text(text_old, text_new)
    client = _anthropic.Anthropic()
    msg = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": USER_TEMPLATE.format(diff=diff_text),
        }],
    )
    raw = "".join(
        block.text for block in msg.content
        if getattr(block, "type", None) == "text"
    )
    return _parse_llm_response(raw)


def _make_diff_text(text_old: str, text_new: str) -> str:
    """Genera unified diff con contexto mínimo y capea a MAX_DIFF_CHARS."""
    diff_lines = difflib.unified_diff(
        text_old.splitlines(),
        text_new.splitlines(),
        n=2,
        lineterm="",
    )
    diff_text = "\n".join(diff_lines)
    if len(diff_text) > MAX_DIFF_CHARS:
        diff_text = diff_text[:MAX_DIFF_CHARS] + "\n…[diff truncado]"
    return diff_text


def _parse_llm_response(raw: str) -> tuple[bool, Optional[str]]:
    """Extrae el primer JSON `{...}` del output del LLM. Tolerante a
    markdown ``` o texto extra antes/después."""
    # Buscamos el primer { ... } razonable. No anidado — el prompt pide
    # JSON plano con dos claves.
    match = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
    if not match:
        logger.warning(
            "diff_summarizer: respuesta sin JSON identificable: %s",
            raw[:200],
        )
        return (True, None)
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        logger.warning(
            "diff_summarizer: JSON inválido en respuesta: %s",
            match.group(0)[:200],
        )
        return (True, None)
    substantive = bool(data.get("sustantivo", True))
    if not substantive:
        return (False, None)
    summary = data.get("resumen")
    summary = summary.strip() if isinstance(summary, str) else None
    return (True, summary or None)
