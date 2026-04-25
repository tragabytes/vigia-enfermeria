"""
Fuente Canal de Isabel II: tabla de convocatorias en /puestos.

Estructura (validada 25/04/2026):
  - URL: https://convocatoriascanaldeisabelsegunda.es/puestos
  - <table class="table"> con <tr class="body-table"> — 116 filas ordenadas por fecha desc
  - Columnas: fecha (dd/mm/yyyy) | código | nombre | convocatoria | calendario | inscripción | -
  - Todas las convocatorias históricas y activas en una sola página
"""
from __future__ import annotations

import logging
from datetime import date, datetime

import requests

from vigia.config import normalize
from vigia.sources.base import RawItem, Source

logger = logging.getLogger(__name__)

CANAL_PUESTOS_URL = "https://convocatoriascanaldeisabelsegunda.es/puestos"
CANAL_BASE_URL = "https://convocatoriascanaldeisabelsegunda.es"

FAST_KEYWORDS = ["enfermer", "salud laboral", "prevencion de riesgos"]


class CanalIsabelIISource(Source):
    name = "canal_isabel_ii"

    def fetch(self, since_date: date) -> list[RawItem]:
        from bs4 import BeautifulSoup

        try:
            resp = requests.get(
                CANAL_PUESTOS_URL,
                headers=self._default_headers(),
                timeout=30,
            )
            resp.raise_for_status()
        except Exception as exc:
            logger.warning("Canal Isabel II error: %s", exc)
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        items: list[RawItem] = []

        for row in soup.find_all("tr", class_="body-table"):
            tds = row.find_all("td")
            if len(tds) < 3:
                continue

            date_str = tds[0].get_text(strip=True)
            title = tds[2].get_text(strip=True)

            try:
                pub_date = datetime.strptime(date_str, "%d/%m/%Y").date()
            except ValueError:
                pub_date = date.today()

            if pub_date < since_date:
                continue

            if not any(kw in normalize(title) for kw in FAST_KEYWORDS):
                continue

            # URL de la convocatoria (4ª columna, si existe)
            conv_url = ""
            if len(tds) > 3:
                link = tds[3].find("a", href=True)
                if link:
                    href = link["href"]
                    conv_url = href if href.startswith("http") else CANAL_BASE_URL + href

            items.append(
                RawItem(
                    source=self.name,
                    url=conv_url or CANAL_PUESTOS_URL,
                    title=title,
                    date=pub_date,
                    text="",
                )
            )

        logger.info("Canal Isabel II: %d items relevantes encontrados", len(items))
        return items
