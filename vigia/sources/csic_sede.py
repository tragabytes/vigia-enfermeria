"""
Fuente CSIC — sede electrónica `tramites/convocatorias-de-personal`.

URL: https://sede.csic.gob.es/tramites/convocatorias-de-personal
HTTP 200, server-rendered (Drupal Views). Sin WAF.

El portal www.csic.es/es/formacion-y-empleo/convocatorias es solo una
landing que enlaza a `sede.csic.gob.es`. La sede es la fuente real de
convocatorias de personal del CSIC: oposiciones, libre designación,
concursos de méritos, ayudas predoctorales y postdoctorales.

Estructura HTML por convocatoria:

  <div class="views-row col-md-3">
    <div class="views-field views-field-field-fecha-publicacion">
      <div class="field-content">DD/MM/YYYY</div>
    </div>
    <div class="views-field views-field-title">
      <span class="field-content">
        <a href="/tramites/convocatorias-de-personal/convocatoria/NNNNN">
          Título de la convocatoria (Ref.NNNNN)
        </a>
      </span>
    </div>
  </div>

`sede.csic.gob.es` paginará probablemente para listar todas las
convocatorias vivas; el listado base muestra 8 a la vez. Si se necesita
paginación, mejora futura.
"""
from __future__ import annotations

import logging
import re
from datetime import date
from urllib.parse import urljoin

import requests

from vigia.config import FAST_KEYWORDS, normalize
from vigia.sources.base import RawItem, Source

logger = logging.getLogger(__name__)

CSIC_SEDE_LISTADO_URL = "https://sede.csic.gob.es/tramites/convocatorias-de-personal"
FETCH_TIMEOUT = 30

_DATE_DDMMYYYY = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")


class CSICSedeSource(Source):
    name = "csic_sede"
    probe_url = CSIC_SEDE_LISTADO_URL

    def fetch(self, since_date: date) -> list[RawItem]:
        from bs4 import BeautifulSoup

        try:
            resp = requests.get(
                CSIC_SEDE_LISTADO_URL,
                headers=self._default_headers(),
                timeout=FETCH_TIMEOUT,
            )
            resp.raise_for_status()
        except Exception as exc:
            logger.warning("CSIC sede listado error: %s", exc)
            self.last_errors.append(str(exc))
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        items: list[RawItem] = []
        seen_urls: set[str] = set()

        for row in soup.select(".views-row"):
            anchor = row.select_one(".views-field-title a")
            if not anchor:
                continue
            title = anchor.get_text(" ", strip=True)
            if not title:
                continue

            if not any(kw in normalize(title) for kw in FAST_KEYWORDS):
                continue

            url = urljoin(CSIC_SEDE_LISTADO_URL, anchor["href"])
            if url in seen_urls:
                continue
            seen_urls.add(url)

            pub_date = date.today()
            fecha_node = row.select_one(
                ".views-field-field-fecha-publicacion .field-content"
            )
            if fecha_node:
                m = _DATE_DDMMYYYY.search(fecha_node.get_text(strip=True))
                if m:
                    try:
                        pub_date = date(
                            int(m.group(3)), int(m.group(2)), int(m.group(1)),
                        )
                    except ValueError:
                        pass

            if pub_date < since_date:
                continue

            items.append(RawItem(
                source=self.name,
                url=url,
                title=title,
                date=pub_date,
                text=title,
            ))
            logger.info("CSIC sede match: %s", title[:90])

        logger.info("CSIC sede: %d items relevantes", len(items))
        return items
