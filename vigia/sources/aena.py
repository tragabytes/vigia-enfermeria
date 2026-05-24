"""
Fuente AENA — portal de empleo PFSrv (Procesos Funcionarios / públicos).

URL: https://empleo.aena.es/empleo/PFSrv?accion=inicio
HTTP 200, server-side rendered. Sistema custom de servlets Java.

Lección de research (2026-05-24): el research previo del 2026-04-28 había
descartado AENA porque miraba `https://empleo.aena.es/empleo/` (la
landing/home), que sí es una SPA con body_text=929. Pero el endpoint REAL
de convocatorias `PFSrv?accion=inicio` devuelve HTML server-rendered
completo con la lista de procesos vivos.

Estructura HTML:

  <h3>{título de la convocatoria}</h3>
  Fecha inicio inscripción: DD/MM/YYYY
  Fecha fin inscripción: DD/MM/YYYY
  [Bases / Doc] [Ver proceso] [Reclamaciones]

Cada convocatoria está marcada por un `<h3>` con su título; las fechas y
enlaces aparecen como hermanos en el mismo bloque hasta el siguiente
`<h3>`. No hay clase CSS distintiva, así que usamos el propio `<h3>` como
ancla del item.
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import date
from urllib.parse import urljoin

import requests

from vigia.config import FAST_KEYWORDS, normalize
from vigia.sources.base import RawItem, Source

logger = logging.getLogger(__name__)

AENA_LISTADO_URL = "https://empleo.aena.es/empleo/PFSrv?accion=inicio"
FETCH_TIMEOUT = 30

# "Fecha inicio inscripción: DD/MM/YYYY" en el bloque del item.
_FECHA_INICIO_RE = re.compile(
    r"fecha\s+inicio\s+inscripci[oó]n[^\d]*(\d{1,2})/(\d{1,2})/(\d{4})",
    re.IGNORECASE,
)


class AENASource(Source):
    name = "aena"
    probe_url = AENA_LISTADO_URL

    def fetch(self, since_date: date) -> list[RawItem]:
        from bs4 import BeautifulSoup

        try:
            resp = requests.get(
                AENA_LISTADO_URL,
                headers=self._default_headers(),
                timeout=FETCH_TIMEOUT,
            )
            resp.raise_for_status()
        except Exception as exc:
            logger.warning("AENA listado error: %s", exc)
            self.last_errors.append(str(exc))
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        items: list[RawItem] = []
        seen_urls: set[str] = set()

        for h3 in soup.find_all("h3"):
            title = h3.get_text(" ", strip=True)
            if not title:
                continue

            # Bloque del item = el h3 + sus hermanos hasta el siguiente h3.
            # Necesitamos ese rango para que el filtro fast-keyword y el
            # regex de fecha vean las fechas y enlaces del bloque, no solo
            # el título.
            block_parts: list[str] = [title]
            block_anchor = None
            for sibling in h3.find_next_siblings():
                if sibling.name == "h3":
                    break
                block_parts.append(sibling.get_text(" ", strip=True))
                if block_anchor is None:
                    # El <a> puede ser sibling directo del <h3> o vivir
                    # anidado dentro de un <p>/<div>. Cubrimos ambos casos.
                    if sibling.name == "a" and sibling.get("href"):
                        block_anchor = sibling
                    elif hasattr(sibling, "find"):
                        cand = sibling.find("a", href=True)
                        if cand:
                            block_anchor = cand
            block_text = " ".join(block_parts).strip()

            if not any(kw in normalize(block_text) for kw in FAST_KEYWORDS):
                continue

            if block_anchor is not None:
                url = urljoin(AENA_LISTADO_URL, block_anchor["href"])
            else:
                digest = hashlib.sha1(title.encode("utf-8")).hexdigest()[:12]
                url = f"{AENA_LISTADO_URL}#{digest}"

            if url in seen_urls:
                continue
            seen_urls.add(url)

            m = _FECHA_INICIO_RE.search(block_text)
            if m:
                try:
                    pub_date = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
                except ValueError:
                    pub_date = date.today()
            else:
                pub_date = date.today()

            if pub_date < since_date:
                continue

            items.append(RawItem(
                source=self.name,
                url=url,
                title=title,
                date=pub_date,
                text=block_text,
            ))
            logger.info("AENA match: %s", title[:90])

        logger.info("AENA: %d items relevantes", len(items))
        return items
