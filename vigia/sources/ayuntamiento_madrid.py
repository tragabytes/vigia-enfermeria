"""
Fuente Ayuntamiento de Madrid (`madrid.es/portales/munimadrid/oposiciones`).

El portal está protegido por **Akamai Bot Manager** (mismo Akamai que
sirve el BOAM — ver `boam.py` para el research completo). Verificado el
2026-04-28: HTTP 403 desde IP residencial española con UA Firefox real.

Cobertura indirecta vigente (suficiente):
- **BOE sección 2B** (Administración Local) — convocatorias del
  Ayuntamiento de Madrid pasan obligatoriamente por aquí.
- **datos.madrid.es** (API CKAN) — OEPs y procesos selectivos de
  estabilización del Ayto, sin Akamai.

Esta fuente es un stub: devuelve lista vacía sin hacer requests, evitando
generar errores HTTP 403 recurrentes en la notificación diaria de
Telegram.
"""
from __future__ import annotations

import logging
from datetime import date

from vigia.sources.base import RawItem, Source

logger = logging.getLogger(__name__)


class AyuntamientoMadridSource(Source):
    name = "ayuntamiento_madrid"

    def fetch(self, since_date: date) -> list[RawItem]:
        logger.info(
            "Ayuntamiento Madrid: madrid.es bloqueado por Akamai Bot Manager; "
            "cobertura delegada a BOE 2B + datos.madrid.es"
        )
        return []
