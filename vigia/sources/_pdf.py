"""Helpers de extracción de texto desde PDFs.

Antes la lógica vivía replicada en cuatro sitios (boe, bocm, ciemat,
enricher) con tres implementaciones que hacían streaming + cap por
tamaño y una sin streaming (BOCM). Centralizado aquí para que un
cambio en pdfplumber o en las constantes (5 MB, 30 págs, chunk de
8 KB) se aplique en un solo punto.

`download_and_extract_pdf` siempre hace streaming con tope de bytes —
cubre el caso BOCM antiguo (que descargaba `resp.content` directo)
añadiendo defensa en profundidad sin romper el caso de uso real
(PDFs BOCM típicos < 500 KB).
"""
from __future__ import annotations

import io
import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)

DEFAULT_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_MAX_PAGES = 30
_CHUNK_SIZE = 8192


def extract_pdf_text(
    data: bytes, max_pages: Optional[int] = DEFAULT_MAX_PAGES
) -> str:
    """Extrae texto plano de un PDF en memoria.

    `max_pages=None` recorre todas las páginas — BOCM lo usa porque
    el keyword ha aparecido en la página 19 de 26 en casos históricos.

    Devuelve string vacío si pdfplumber no está instalado o el PDF
    está corrupto / cifrado. El caller trata "sin texto" como "anexo
    no útil"; no lanza excepciones para no abortar el run completo.
    """
    try:
        import pdfplumber
    except ImportError:
        logger.debug("pdfplumber no instalado — texto vacío")
        return ""

    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            pages = pdf.pages if max_pages is None else pdf.pages[:max_pages]
            chunks = [t for page in pages if (t := page.extract_text())]
            return "\n\n".join(chunks)
    except Exception as exc:
        logger.debug("PDF parse error: %s", exc)
        return ""


def download_and_extract_pdf(
    url: str,
    *,
    headers: dict[str, str],
    timeout: int,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_pages: Optional[int] = DEFAULT_MAX_PAGES,
    verify: bool = True,
) -> str:
    """Descarga un PDF (streaming, capado) y devuelve su texto plano.

    `verify=False` solo se justifica con CIEMAT, cuyo certificado no
    envía el intermedio y rompe en setups Python sin la cadena de CAs.
    """
    resp = requests.get(
        url,
        headers=headers,
        timeout=timeout,
        stream=True,
        verify=verify,
    )
    resp.raise_for_status()

    body = bytearray()
    for chunk in resp.iter_content(chunk_size=_CHUNK_SIZE):
        if not chunk:
            continue
        body.extend(chunk)
        if len(body) >= max_bytes:
            body = body[:max_bytes]
            break
    resp.close()

    return extract_pdf_text(bytes(body), max_pages=max_pages)
