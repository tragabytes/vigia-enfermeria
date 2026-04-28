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

PROCESS_TYPE_LABEL = {
    "oposicion":          "Oposición",
    "bolsa":              "Bolsa",
    "concurso_traslados": "Concurso traslados",
    "interinaje":         "Interinaje",
    "temporal":           "Contrato temporal",
    "otro":               "Otro",
}

FASE_LABEL = {
    "convocatoria":           "Convocatoria",
    "admitidos_provisional":  "Admitidos provisional",
    "admitidos_definitivo":   "Admitidos definitivo",
    "examen":                 "Fechas de examen",
    "calificacion":           "Calificación",
    "propuesta_nombramiento": "Propuesta de nombramiento",
    "otro":                   "Actualización",
}

import requests

from vigia.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, USER_AGENT
from vigia.storage import Item

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
MAX_MESSAGE_LEN = 4096  # límite de Telegram

# URL pública del dashboard (rama gh-pages). Se incluye al final de cada
# notificación para que el destinatario pueda inspeccionar el histórico,
# las estadísticas y el estado de las fuentes desde un sitio estable.
DASHBOARD_URL = "https://tragabytes.github.io/vigia-enfermeria/"


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
    lines: list[str] = [f"🔔 <b>Vigilancia Enfermería del Trabajo — {fecha_str}</b>\n"]

    if items:
        for item in items:
            lines.extend(_format_item(item, today))
            lines.append("")
    else:
        lines.append("Sin novedades hoy.\n")

    for source_name, err_msg in errors:
        lines.append(
            f"⚠️ Fuente <b>{_escape(source_name)}</b> no respondió: {_escape(err_msg)}"
        )

    lines.append("")
    lines.append(f"🛰️ Panel completo: {DASHBOARD_URL}")

    return "\n".join(lines)


def _format_item(item: Item, today: date) -> list[str]:
    """Bloque por convocatoria, aprovechando los campos del enricher v2.

    Si el enricher v2 no ha corrido (sin API key, fallo, item legacy), las
    líneas de plazas/cierre/tasa/bases simplemente se omiten — el formato
    degrada al del enricher v1 (header + título + categoría + summary + url).
    """
    block: list[str] = []
    header = f"🟢 <b>NUEVO en {_escape(item.source.upper())}</b>"
    if item.organismo:
        header += f" — {_escape(item.organismo)}"
    block.append(header)
    block.append(f"<b>{_escape(item.titulo)}</b>")

    # Línea de proceso: tipo · plazas · tasa
    proc_bits: list[str] = []
    if item.process_type:
        proc_bits.append(PROCESS_TYPE_LABEL.get(item.process_type, item.process_type))
    if item.plazas:
        proc_bits.append(f"{item.plazas} plazas")
    if item.tasas_eur is not None:
        proc_bits.append(_format_eur(item.tasas_eur) + " tasa")
    if proc_bits:
        block.append("📊 " + " · ".join(_escape(b) for b in proc_bits))

    # Cierre con countdown
    if item.deadline_inscripcion:
        countdown = _format_countdown(item.deadline_inscripcion, today)
        if countdown:
            block.append(f"⏰ {_escape(countdown)}")

    # Fase del proceso si no es la inicial (evita ruido en convocatorias nuevas)
    if item.fase and item.fase not in ("convocatoria", "otro"):
        fase_label = FASE_LABEL.get(item.fase, item.fase)
        block.append(f"🪪 Fase: {_escape(fase_label)}")

    # Acción inmediata
    if item.next_action:
        block.append(f"🎯 {_escape(item.next_action)}")

    # Summary (si existe; solo cuando aporta más allá del título)
    if item.summary:
        block.append(f"<i>{_escape(item.summary)}</i>")

    # Enlaces — anuncio principal siempre; bases si difieren del anuncio.
    # Telegram autodetecta URLs crudas en HTML mode, pero los caracteres
    # especiales del HTML (& < >) deben escaparse en el atributo y el texto.
    block.append(f"🔗 {_escape(item.url)}")
    if item.url_bases and item.url_bases != item.url:
        block.append(f"📎 Bases: {_escape(item.url_bases)}")

    # Categoría legacy al final como tag (consume poco y mantiene continuidad
    # con el layout previo)
    block.append(f"📌 {_escape(item.categoria)}")
    return block


def _format_countdown(deadline_iso: str, today: date) -> Optional[str]:
    """Devuelve 'Cierre: DD/MM/YYYY (en N días)' o variantes según signo."""
    try:
        dl = date.fromisoformat(deadline_iso)
    except ValueError:
        return None
    days = (dl - today).days
    fecha_es = dl.strftime("%d/%m/%Y")
    if days < 0:
        return f"Cierre: {fecha_es} (cerrado hace {-days} días)"
    if days == 0:
        return f"Cierre: {fecha_es} (HOY)"
    if days == 1:
        return f"Cierre: {fecha_es} (mañana)"
    return f"Cierre: {fecha_es} (en {days} días)"


def _format_eur(amount: float) -> str:
    """Formatea importes con separador decimal de coma. 30.0 → '30€', 30.5 → '30,50€'."""
    if abs(amount - round(amount)) < 0.005:
        return f"{int(round(amount))}€"
    return f"{amount:.2f}€".replace(".", ",")


def _escape(text: str) -> str:
    """Escapa caracteres especiales para parse_mode HTML de Telegram.

    Telegram HTML reconoce solo `< > &` como caracteres reservados; el
    resto (incluido `_` que rompía Markdown v1 cuando aparecía en URLs
    de PDFs anexos) pasa intacto y no dispara `can't parse entities`.
    """
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )


def _split(text: str) -> list[str]:
    """Divide el mensaje en trozos que no superen el límite de Telegram."""
    if len(text) <= MAX_MESSAGE_LEN:
        return [text]
    chunks = []
    while text:
        chunks.append(text[:MAX_MESSAGE_LEN])
        text = text[MAX_MESSAGE_LEN:]
    return chunks


def _chat_ids() -> list[str]:
    """Lista de chat IDs destinatarios. Acepta TELEGRAM_CHAT_ID con un solo
    ID o varios separados por comas (p. ej. "123,456,-1001234")."""
    return [c.strip() for c in TELEGRAM_CHAT_ID.split(",") if c.strip()]


def _send_chunk(text: str) -> None:
    url = TELEGRAM_API.format(token=TELEGRAM_BOT_TOKEN)
    for chat_id in _chat_ids():
        resp = requests.post(
            url,
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        if not resp.ok:
            logger.error(
                "Telegram error chat_id=%s status=%s body=%s",
                chat_id, resp.status_code, resp.text[:200],
            )
            # No lanzamos la excepción para que un destinatario fallido
            # no impida la entrega al resto.
