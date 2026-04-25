"""
Fuente Ayuntamiento de Madrid: portal de oposiciones y bolsas de trabajo.

Estructura (validada 25/04/2026):
  - Hub: https://www.madrid.es/portales/munimadrid/oposiciones.html
    → redirige a URL VgnVCM con contenido principal
  - Contenido en <main id="readspeaker">:
    - Carrusel <ul class="mw-content"> > <li> > <a class="mw-item"> (bolsas activas)
    - Secciones <div class="news-item"> > <ul class="news-list"> > <li> > <a class="news-link">

Limitación: el buscador de sede.madrid.es requiere JS (devuelve 403).
Las convocatorias diarias del Ayuntamiento aparecen en BOAM (fuente boam.py);
esta fuente captura ítems visibles en el portal estático como cobertura adicional.
"""
from __future__ import annotations

import logging
from datetime import date

import requests

from vigia.config import normalize
from vigia.sources.base import RawItem, Source

logger = logging.getLogger(__name__)

AYTO_HUB_URL = "https://www.madrid.es/portales/munimadrid/oposiciones.html"
MADRID_BASE = "https://www.madrid.es"

FAST_KEYWORDS = ["enfermer", "salud laboral", "prevencion de riesgos"]


class AyuntamientoMadridSource(Source):
    name = "ayuntamiento_madrid"

    def fetch(self, since_date: date) -> list[RawItem]:
        from bs4 import BeautifulSoup

        try:
            resp = requests.get(
                AYTO_HUB_URL,
                headers=self._default_headers(),
                timeout=20,
                allow_redirects=True,
            )
            resp.raise_for_status()
        except Exception as exc:
            logger.warning("Ayuntamiento Madrid error: %s", exc)
            self.last_errors.append(str(exc))
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        main = soup.find(id="readspeaker") or soup.body
        if not main:
            return []

        items: list[RawItem] = []
        seen_urls: set[str] = set()

        # Buscar en carrusel de bolsas activas y secciones de noticias
        for a in main.find_all("a", href=True):
            text = a.get_text(" ", strip=True)
            if len(text) < 15:
                continue
            if not any(kw in normalize(text) for kw in FAST_KEYWORDS):
                continue

            href = a["href"]
            url = href if href.startswith("http") else MADRID_BASE + href
            if url in seen_urls:
                continue
            seen_urls.add(url)

            items.append(
                RawItem(
                    source=self.name,
                    url=url,
                    title=text,
                    date=date.today(),
                    text="",
                )
            )

        logger.info(
            "Ayuntamiento Madrid: %d items relevantes encontrados", len(items)
        )
        return items
