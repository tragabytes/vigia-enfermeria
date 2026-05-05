"""Helper de extracción de texto plano desde HTML.

Las fuentes hash-watcher (isciii, cm_ficha_enfermeria) y el enricher
hacen casi exactamente lo mismo: descomponen scripts/styles/nav/
header/footer, opcionalmente seleccionan un contenedor concreto, y
extraen texto. Antes había tres implementaciones; ahora vive aquí.
"""
from __future__ import annotations

import logging
from typing import Iterable

logger = logging.getLogger(__name__)

# Tags que casi nunca aportan al texto útil — siempre se descomponen.
_DEFAULT_DECOMPOSE = ("script", "style", "noscript", "header", "footer", "nav")


def extract_clean_text(
    html: str | bytes,
    *,
    target_selectors: Iterable[str] = ("body",),
    extra_decompose: Iterable[str] = (),
    separator: str = " ",
    collapse_lines: bool = False,
) -> str:
    """Limpia un HTML y devuelve texto plano legible.

    `target_selectors`: lista en orden de preferencia. Se usa el primero
    que matchee como raíz; si ninguno encaja, recurre al `<body>` y, si
    tampoco lo hay, al documento entero.

    `extra_decompose`: selectores adicionales a borrar antes del
    `get_text` (p. ej. `.lfr-nav-item` en ISCIII, que no es nav puro).

    `separator` + `collapse_lines`: el enricher quiere "\\n" + colapso
    por línea (preserva pistas visuales para el LLM); las fuentes
    hash-watcher usan " " + strip=True (output va a hash y a matcher,
    no necesita estructura).
    """
    if isinstance(html, bytes):
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            return html.decode("utf-8", errors="replace")
    else:
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            return html

    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")

    target = None
    for sel in target_selectors:
        target = soup.select_one(sel)
        if target is not None:
            break
    if target is None:
        target = soup.body or soup

    decompose_all = list(_DEFAULT_DECOMPOSE) + list(extra_decompose)
    for sel in decompose_all:
        for el in target.select(sel):
            el.decompose()

    text = target.get_text(separator=separator, strip=(not collapse_lines))
    if collapse_lines:
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        text = "\n".join(lines)
    return text
