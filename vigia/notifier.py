"""
Notificador Telegram.

Recibe lista de Item (ya filtrados por el extractor y opcionalmente
enriquecidos por enricher.py) y envía un mensaje Markdown agrupado.

El flujo es:
    extractor.py → [enricher.py en el futuro] → notifier.py

Para interponer enricher.py bastará con:
    items = enricher.enrich(items)   # nueva línea en main.py
Sin tocar nada de este módulo.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

import requests

from vigia.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, USER_AGENT
from vigia.storage import Item

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
MAX_MESSAGE_LEN = 4096  # límite de Telegram


def send(
    items: list[Item],
    errors: list[tuple[str, str]],
    run_date: Optional[date] = None,
) -> None:
    """
    Envía el resumen del día a Telegram.

    :param items:    Hallazgos nuevos ya deduplicados.
    :param errors:   Lista de (nombre_fuente, mensaje_error) para fuentes que fallaron.
    :param run_date: Fecha de la ejecución; si None, usa hoy.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Credenciales Telegram no configuradas — notificación omitida")
        return

    today = run_date or date.today()
    message = _build_message(items, errors, today)

    for chunk in _split(message):
        _send_chunk(chunk)


def send_test(message: str = "✅ vigia-enfermeria: conexión OK") -> None:
    """Envía un mensaje de prueba para validar credenciales."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID deben estar en las variables de entorno"
        )
    _send_chunk(message)
    logger.info("Mensaje de prueba enviado correctamente")


# ---------------------------------------------------------------------------
# Funciones internas
# ---------------------------------------------------------------------------

def _build_message(items: list[Item], errors: list[tuple[str, str]], today: date) -> str:
    fecha_str = today.strftime("%d/%m/%Y")
    lines: list[str] = [f"🔔 *Vigilancia Enfermería del Trabajo — {fecha_str}*\n"]

    if items:
        for item in items:
            lines.append(f"🟢 *NUEVO en {item.source.upper()}*")
            lines.append(f"{_escape(item.titulo)}")
            lines.append(f"📌 {_escape(item.categoria)}")
            if item.summary:
                lines.append(f"_{_escape(item.summary)}_")
            lines.append(f"🔗 {item.url}")
            lines.append("")
    else:
        lines.append("Sin novedades hoy.\n")

    for source_name, err_msg in errors:
        lines.append(f"⚠️ Fuente *{_escape(source_name)}* no respondió: {_escape(err_msg)}")

    return "\n".join(lines)


def _escape(text: str) -> str:
    """Escapa caracteres especiales para Markdown v1 de Telegram."""
    for ch in ("_", "*", "`", "["):
        text = text.replace(ch, f"\\{ch}")
    return text


def _split(text: str) -> list[str]:
    """Divide el mensaje en trozos que no superen el límite de Telegram."""
    if len(text) <= MAX_MESSAGE_LEN:
        return [text]
    chunks = []
    while text:
        chunks.append(text[:MAX_MESSAGE_LEN])
        text = text[MAX_MESSAGE_LEN:]
    return chunks


def _send_chunk(text: str) -> None:
    url = TELEGRAM_API.format(token=TELEGRAM_BOT_TOKEN)
    resp = requests.post(
        url,
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        },
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    if not resp.ok:
        logger.error("Telegram error %s: %s", resp.status_code, resp.text[:200])
        resp.raise_for_status()
