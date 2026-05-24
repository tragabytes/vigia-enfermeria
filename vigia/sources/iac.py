"""
Fuente IAC (Instituto de Astrofísica de Canarias) — portal ofertas de trabajo.

URL: https://www.iac.es/es/empleo
HTTP 200, server-rendered (Drupal). Sin WAF.

Las convocatorias del IAC son mayoritariamente contratos predoctorales y
postdoctorales de investigación, no plazas estructurales del Servicio de
Prevención. Implementamos el parser sobre el listado para cazar cualquier
oferta que aparezca con "enfermer" / "salud laboral" / "prevencion de
riesgos" en el título; si aparece, el extractor + enricher v2 deciden.

Estructura HTML del listado:

  <a href="/es/ofertas-de-trabajo/<slug>">Título de la oferta PS-AAAA-NNN</a>

Los items aparecen duplicados (el `<a>` del título del card y un `<a>`
"Leer más" en `<li class="node-readmore">`). Deduplicamos por URL y
saltamos los anchors cuyo texto sea "Leer más".

Limitación: el listado expone solo títulos; la fecha de publicación
solo aparece en la página de detalle. No bajamos al detalle para
evitar N+1 fetches en cada cron — la fecha cae a `today()` y el item
queda con la fecha del descubrimiento, suficiente para deduplicación
y orden cronológico aproximado. Si se necesita fecha real algún día,
mejora futura estilo CIEMAT (1 GET extra por oferta).
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

IAC_LISTADO_URL = "https://www.iac.es/es/empleo"
FETCH_TIMEOUT = 30

_OFFER_HREF_RE = re.compile(r"^/es/ofertas-de-trabajo/")


class IACSource(Source):
    name = "iac"
    probe_url = IAC_LISTADO_URL

    def fetch(self, since_date: date) -> list[RawItem]:
        from bs4 import BeautifulSoup

        try:
            resp = requests.get(
                IAC_LISTADO_URL,
                headers=self._default_headers(),
                timeout=FETCH_TIMEOUT,
            )
            resp.raise_for_status()
        except Exception as exc:
            logger.warning("IAC listado error: %s", exc)
            self.last_errors.append(str(exc))
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        items: list[RawItem] = []
        seen_urls: set[str] = set()

        for a in soup.find_all("a", href=_OFFER_HREF_RE):
            title = a.get_text(" ", strip=True)
            if not title:
                continue
            # El `<a>` "Leer más" duplica el del título — saltamos.
            if title.lower() in ("leer más", "leer mas"):
                continue

            if not any(kw in normalize(title) for kw in FAST_KEYWORDS):
                continue

            url = urljoin(IAC_LISTADO_URL, a["href"])
            if url in seen_urls:
                continue
            seen_urls.add(url)

            # Sin GET de detalle: fecha = today() en el primer descubrimiento.
            # Suficiente para deduplicación; el orden cronológico es aproximado.
            pub_date = date.today()
            if pub_date < since_date:
                continue

            items.append(RawItem(
                source=self.name,
                url=url,
                title=title,
                date=pub_date,
                text=title,
            ))
            logger.info("IAC match: %s", title[:90])

        logger.info("IAC: %d items relevantes", len(items))
        return items
