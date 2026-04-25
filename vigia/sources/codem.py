"""
Fuente CODEM: RSS del Colegio Oficial de Enfermería de Madrid (empleo público).

Feed RSS (validado 25/04/2026):
  - URL: https://www.codem.es/RssHyperLink.ashx?Idioma=...&Menu=e0fed1d6...
  - RSS 2.0 estándar, <item> con <title>, <pubDate>, <link>, <description> (HTML)
  - Incluye tanto oposiciones como concursos de traslado y bolsas
  - Los títulos son descriptivos: "Publicado el Concurso de Traslados 2025..."
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

CODEM_RSS_URL = (
    "https://www.codem.es/RssHyperLink.ashx"
    "?Idioma=940267a2-4160-4ee0-a17a-a3cc00a7c64c"
    "&Web=e8d948e0-b75e-4537-8e16-687622b6b7ce"
    "&Menu=e0fed1d6-aff3-4b0d-be4d-7a276dea3867"
    "&Canal=d8b9b124-8147-4727-a7a7-2d1b9184ea01"
)

FAST_KEYWORDS = ["enfermer", "salud laboral", "prevencion de riesgos"]


class CODEMSource(Source):
    name = "codem"

    def fetch(self, since_date: date) -> list[RawItem]:
        try:
            resp = requests.get(
                CODEM_RSS_URL, headers=self._default_headers(), timeout=20
            )
            resp.raise_for_status()
        except Exception as exc:
            logger.warning("CODEM RSS error: %s", exc)
            self.last_errors.append(str(exc))
            return []

        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError as exc:
            logger.error("CODEM: error parseando RSS: %s", exc)
            self.last_errors.append(f"parse error: {exc}")
            return []

        items: list[RawItem] = []
        for rss_item in root.iter("item"):
            title_el = rss_item.find("title")
            link_el = rss_item.find("link")
            pub_date_el = rss_item.find("pubDate")
            desc_el = rss_item.find("description")

            title = (title_el.text or "").strip() if title_el is not None else ""
            url = (link_el.text or "").strip() if link_el is not None else ""
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
                    url=url,
                    title=title,
                    date=pub_date,
                    text=desc_text,
                )
            )

        logger.info("CODEM: %d items relevantes encontrados", len(items))
        return items

    def _strip_html(self, html: str) -> str:
        from bs4 import BeautifulSoup

        if not html:
            return ""
        try:
            return BeautifulSoup(html, "lxml").get_text(" ", strip=True)
        except Exception:
            return html
