"""
Fuente CODEM: feeds RSS del Colegio Oficial de Enfermería de Madrid.

Feeds monitorizados (validados 25/04/2026):
  1. Empleo público (~246 items): convocatorias, concursos, bolsas. Sección
     "/empleo-publico" del portal del colegio.
  2. Actualidad (~2400 items, 8MB): noticias generales del colegio. A veces
     adelanta convocatorias (ej. "Canal de Isabel II convoca una plaza de
     enfermera especialista en Enfermería del Trabajo").

Ambos siguen el patrón estándar `RssHyperLink.ashx?Idioma=...&Menu=X&Canal=Y`,
RSS 2.0 con <item><title><pubDate><link><description> (HTML embebido).

Los items se filtran primero por fecha (since_date) y luego por fast keyword
en el texto combinado de title + description plain. La deduplicación
posterior en storage.py (por hash de source+url+titulo) cubre el caso
improbable de que un item aparezca en los dos feeds.
"""
from __future__ import annotations

import logging
from datetime import date
from email.utils import parsedate
from xml.etree import ElementTree as ET

import requests

from vigia.config import normalize
from vigia.sources.base import RawItem, Source

logger = logging.getLogger(__name__)

# Lista de feeds RSS a consultar. Cada entrada es (etiqueta, url). La
# etiqueta solo se usa internamente para logs y para `RawItem.extra` —
# la notificación a Telegram solo muestra "CODEM" sin distinguir feed.
_BASE = (
    "https://www.codem.es/RssHyperLink.ashx"
    "?Idioma=940267a2-4160-4ee0-a17a-a3cc00a7c64c"
    "&Web=e8d948e0-b75e-4537-8e16-687622b6b7ce"
)
CODEM_RSS_FEEDS: list[tuple[str, str]] = [
    (
        "empleo",
        f"{_BASE}&Menu=e0fed1d6-aff3-4b0d-be4d-7a276dea3867"
        f"&Canal=d8b9b124-8147-4727-a7a7-2d1b9184ea01",
    ),
    (
        "actualidad",
        f"{_BASE}&Menu=8babeabd-7261-4fab-9bf1-7858b1ebbfb9"
        f"&Canal=0c5726d8-34d8-4116-bb82-1f75d36b307b",
    ),
]

FAST_KEYWORDS = ["enfermer", "salud laboral", "prevencion de riesgos"]

# El feed "actualidad" pesa ~8MB; subimos timeout para no fallar por red lenta.
HTTP_TIMEOUT = 60


class CODEMSource(Source):
    name = "codem"

    def fetch(self, since_date: date) -> list[RawItem]:
        all_items: list[RawItem] = []
        for label, url in CODEM_RSS_FEEDS:
            all_items.extend(self._fetch_feed(label, url, since_date))
        logger.info("CODEM: %d items relevantes encontrados (todos los feeds)", len(all_items))
        return all_items

    def _fetch_feed(self, label: str, url: str, since_date: date) -> list[RawItem]:
        try:
            resp = requests.get(url, headers=self._default_headers(), timeout=HTTP_TIMEOUT)
            resp.raise_for_status()
        except Exception as exc:
            logger.warning("CODEM RSS [%s] error: %s", label, exc)
            self.last_errors.append(f"{label}: {exc}")
            return []

        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError as exc:
            logger.error("CODEM [%s]: error parseando RSS: %s", label, exc)
            self.last_errors.append(f"{label} parse error: {exc}")
            return []

        items: list[RawItem] = []
        for rss_item in root.iter("item"):
            title_el = rss_item.find("title")
            link_el = rss_item.find("link")
            pub_date_el = rss_item.find("pubDate")
            desc_el = rss_item.find("description")

            title = (title_el.text or "").strip() if title_el is not None else ""
            item_url = (link_el.text or "").strip() if link_el is not None else ""
            desc_raw = (desc_el.text or "") if desc_el is not None else ""

            desc_text = self._strip_html(desc_raw)

            pub_date = date.today()
            if pub_date_el is not None and pub_date_el.text:
                parsed = parsedate(pub_date_el.text)
                if parsed:
                    try:
                        pub_date = date(parsed[0], parsed[1], parsed[2])
                    except ValueError:
                        pass

            if pub_date < since_date:
                continue

            combined = f"{title} {desc_text}"
            if not any(kw in normalize(combined) for kw in FAST_KEYWORDS):
                continue

            items.append(
                RawItem(
                    source=self.name,
                    url=item_url,
                    title=title,
                    date=pub_date,
                    text=desc_text,
                    extra={"feed": label},
                )
            )

        logger.info("CODEM [%s]: %d items relevantes", label, len(items))
        return items

    def _strip_html(self, html: str) -> str:
        from bs4 import BeautifulSoup

        if not html:
            return ""
        try:
            return BeautifulSoup(html, "lxml").get_text(" ", strip=True)
        except Exception:
            return html
