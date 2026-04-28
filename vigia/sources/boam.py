"""
Fuente BOAM (Boletín Oficial del Ayuntamiento de Madrid).

`https://www.madrid.es/boam` está protegido por **Akamai Bot Manager**
(header `Server-Timing: ak_p`, error reference `errors.edgesuite.net`),
no por un filtro IP geo simple. Verificado experimentalmente el
2026-04-28 desde IP residencial española (Orange, AS12479) con UA
Firefox 121: HTTP 403 igual que desde los runners de GitHub Actions.
Akamai inspecciona TLS fingerprint, HTTP/2 frame ordering y posibles
challenges JS — superarlo requiere `curl-impersonate` o navegador real
headless (Playwright), con runtime caro y sin garantía.

Cobertura indirecta vigente (suficiente):
- **BOE sección 2B** (Administración Local) — `"administracion local"` ya
  está en `DEPT_KEYWORDS_FOR_BODY` de `boe.py`, lo que dispara la
  descarga del cuerpo HTML cuando el organismo emisor es del Ayto.
- **datos.madrid.es** (API CKAN) — la fuente `datos_madrid.py` recoge
  OEPs y procesos selectivos de estabilización del Ayuntamiento sin
  pasar por Akamai.

Esta fuente es un stub: devuelve lista vacía sin hacer requests, evitando
generar errores HTTP 403 recurrentes en la notificación diaria de
Telegram. Ver el research completo en `BACKLOG.md` (sección
"Investigación profunda del problema de IP geo-bloqueada").
"""
from __future__ import annotations

import logging
from datetime import date

from vigia.sources.base import RawItem, Source

logger = logging.getLogger(__name__)


class BOAMSource(Source):
    name = "boam"

    def fetch(self, since_date: date) -> list[RawItem]:
        logger.info(
            "BOAM: madrid.es bloqueado por Akamai Bot Manager; "
            "cobertura delegada a BOE 2B + datos.madrid.es"
        )
        return []
