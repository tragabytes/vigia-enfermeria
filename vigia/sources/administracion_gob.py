"""
Fuente administracion.gob.es: buscador de empleo público.

El portal https://administracion.gob.es/pagFront/empleoBecas/empleo/buscadorEmpleo.htm
utiliza JavaScript para cargar los resultados (no hay HTML de convocatorias en la respuesta
del servidor) y no expone API pública ni feed RSS.

Las convocatorias que aparecen en este portal son publicadas por organismos de la AGE
que a su vez las publican en BOE (fuente boe.py) y BOCM (fuente bocm.py), que ya las
monitoriza este sistema.

Esta fuente es un stub que devuelve lista vacía.
"""
from __future__ import annotations

import logging
from datetime import date

from vigia.sources.base import RawItem, Source

logger = logging.getLogger(__name__)


class AdministracionGobSource(Source):
    name = "administracion_gob"

    def fetch(self, since_date: date) -> list[RawItem]:
        logger.info(
            "administracion.gob.es: portal JS-only sin API pública; "
            "cobertura delegada a fuentes BOE y BOCM"
        )
        return []
