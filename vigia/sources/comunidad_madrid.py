"""
Fuente Comunidad de Madrid: buscador de empleo público en sede.comunidad.madrid.

Estructura (validada 25/04/2026):
  - URL: https://sede.comunidad.madrid/buscador?t=KEYWORD&tipo=7&...&items_per_page=50
  - Drupal 8/9 con listado en div.pane-adel ul li
  - Cada item: título en div.titulo h3 a, URL relativa, estado en div.estado
  - Paginación: ?page=N (0-indexado), total en div.summary span

Estrategia:
  - Buscar con t=enfermeria (≈90 resultados) y t=salud+laboral
  - Filtrar títulos con keywords rápidos
  - Extraer fecha de "Apertura de plazo: DD/MM/YYYY" en el bloque de estado
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime

import requests

from vigia.config import normalize
from vigia.sources.base import RawItem, Source

logger = logging.getLogger(__name__)

SEDE_BASE = "https://sede.comunidad.madrid"
BUSCADOR_URL = (
    "https://sede.comunidad.madrid/buscador"
    "?tipo=7"
    "&native_string_nombre_consejeria=All"
    "&estado_pendiente%5B1%5D=1"
    "&estado_plazo%5B1%5D=1"
    "&estado_tramitacion%5B1%5D=1"
    "&items_per_page=50"
)

FAST_KEYWORDS = ["enfermer", "salud laboral", "prevencion de riesgos"]
SEARCH_TERMS = ["enfermeria", "salud laboral"]


class ComunidadMadridSource(Source):
    name = "comunidad_madrid"

    def fetch(self, since_date: date) -> list[RawItem]:
        all_items: list[RawItem] = []
        seen_urls: set[str] = set()
        for term in SEARCH_TERMS:
            items = self._fetch_term(term, since_date, seen_urls)
            all_items.extend(items)
        logger.info(
            "Comunidad Madrid: %d items relevantes encontrados", len(all_items)
        )
        return all_items

    def _fetch_term(
        self, term: str, since_date: date, seen_urls: set[str]
    ) -> list[RawItem]:
        from bs4 import BeautifulSoup

        items: list[RawItem] = []
        page = 0

        while True:
            url = f"{BUSCADOR_URL}&t={term}&page={page}"
            try:
                resp = requests.get(
                    url, headers=self._default_headers(), timeout=20
                )
                resp.raise_for_status()
            except Exception as exc:
                logger.warning("Comunidad Madrid error (term=%s page=%d): %s", term, page, exc)
                break

            soup = BeautifulSoup(resp.text, "lxml")
            pane = soup.find("div", class_="pane-adel")
            if not pane:
                break

            rows = pane.select("ul li")
            if not rows:
                break

            found_any = False
            for li in rows:
                item = self._parse_item(li, since_date, seen_urls)
                if item is not None:
                    items.append(item)
                found_any = True

            # Si la última página tiene items o pager no tiene "siguiente", parar
            pager_last = soup.find("li", class_="pager__item--last")
            pager_next = soup.find("li", class_="pager__item--next")
            if not found_any or not pager_next:
                break
            page += 1

        return items

    def _parse_item(
        self, li, since_date: date, seen_urls: set[str]
    ) -> RawItem | None:
        titulo_el = li.select_one("div.titulo h3 a")
        if not titulo_el:
            return None

        title = (titulo_el.get("title") or titulo_el.get_text(" ", strip=True)).strip()
        href = titulo_el.get("href", "")
        item_url = href if href.startswith("http") else SEDE_BASE + href

        if item_url in seen_urls:
            return None

        if not any(kw in normalize(title) for kw in FAST_KEYWORDS):
            return None

        # Extraer fecha de apertura del bloque de estado
        pub_date = date.today()
        estado_el = li.select_one("div.estado")
        if estado_el:
            text = estado_el.get_text(" ", strip=True)
            m = re.search(r"Apertura.*?(\d{2}/\d{2}/\d{4})", text)
            if m:
                try:
                    pub_date = datetime.strptime(m.group(1), "%d/%m/%Y").date()
                except ValueError:
                    pass

        if pub_date < since_date:
            return None

        seen_urls.add(item_url)
        return RawItem(
            source=self.name,
            url=item_url,
            title=title,
            date=pub_date,
            text="",
        )
