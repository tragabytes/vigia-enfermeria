"""
Clase abstracta base para todas las fuentes.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class RawItem:
    """
    Resultado crudo devuelto por una fuente antes de pasar por el extractor.

    El campo `text` contiene todo el texto relevante para aplicar las reglas
    de matching (título + descripción + cuerpo si está disponible).

    El flujo previsto es:
        sources/*.py  →  extractor.py  →  [future enricher.py]  →  notifier.py

    El extractor recibe RawItem y devuelve Item (o None si no hay match).
    El enricher, cuando exista, recibirá Item y devolverá Item enriquecido.
    """
    source: str
    url: str
    title: str
    date: date
    text: str = ""                   # texto adicional para matching (resumen, cuerpo…)
    extra: dict = field(default_factory=dict)  # metadatos opcionales por fuente


class Source(ABC):
    """
    Interfaz común para todas las fuentes de datos.

    Subclases deben implementar únicamente `fetch`.
    """

    name: str = ""  # identificador corto, p.ej. "boe", "bocm"

    def __init__(self) -> None:
        self.logger = logging.getLogger(f"vigia.sources.{self.name}")
        # Errores no bloqueantes detectados durante fetch() (HTTP 4xx/5xx,
        # parsing fallido, etc.). main.py los recoge tras la ejecución y los
        # incluye en la notificación de Telegram para que las caídas de
        # fuentes sean visibles sin tener que mirar los logs de Actions.
        self.last_errors: list[str] = []

    @abstractmethod
    def fetch(self, since_date: date) -> list[RawItem]:
        """
        Obtiene ítems publicados a partir de `since_date`.

        Debe ser tolerante a fallos: si una operación parcial falla, capturarla
        con `try/except`, hacer `logger.warning(...)` Y añadir un mensaje a
        `self.last_errors` para que sea reportado en la notificación. Solo
        levantar la excepción si el fallo impide cualquier extracción útil.
        """

    def _default_headers(self) -> dict[str, str]:
        from vigia.config import USER_AGENT
        return {"User-Agent": USER_AGENT}
