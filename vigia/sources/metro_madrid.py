"""
Fuente Metro de Madrid.

El sitio web de Metro de Madrid (metromadrid.es/trabaja-con-nosotros) devuelve
"Request Rejected" para cualquier cliente HTTP automatizado (WAF).

Las convocatorias de Metro de Madrid se publican en BOE (sección 2B, departamento
"Metro de Madrid") y en BOCM (sección B, organismo "Metro de Madrid"), que ya son
monitorizados por las fuentes boe.py y bocm.py respectivamente.

Esta fuente es un stub que delega esa cobertura y devuelve lista vacía.
"""
from __future__ import annotations

import logging
from datetime import date

from vigia.sources.base import RawItem, Source

logger = logging.getLogger(__name__)


class MetroMadridSource(Source):
    name = "metro_madrid"

    def fetch(self, since_date: date) -> list[RawItem]:
        logger.info(
            "Metro Madrid: sitio bloqueado por WAF; "
            "cobertura delegada a fuentes BOE y BOCM"
        )
        return []
