"""
Fuente "Calendario Convocatoria 245 (Canal de Isabel II)" — hash-watcher
de https://www.convocatoriascanaldeisabelsegunda.es/calendario-245

Por qué fuente dedicada:
`canal_isabel_ii.py` sólo vigila el listado `/puestos` y detecta nuevas
filas. La convocatoria 245 (Enfermero/a Especialista en Enfermería del
Trabajo) ya está registrada en BD desde su alta (10/04/2026), así que ese
parser no vuelve a emitir nada para ella. Los hitos posteriores del
proceso — apertura de plicas, publicación de la lista provisional de
admitidos, examen, calificaciones — se publican en sub-páginas
(`/calendario-245`, `/convocatoria-245`) que el listing parser no mira.

Esta fuente es un cabo suelto deshechable: cuando el `DetailWatcher`
genérico esté implementado (ver BACKLOG / plan análisis A), todos los
procesos vivos se vigilarán automáticamente. Hasta entonces, parche
puntual para no perdernos los hitos de la convocatoria 245.

Estrategia: hash-watcher (ver `_hash_watcher.HashWatcherSource`). El
título incluye literalmente "Enfermería del Trabajo" para que el extractor
matchee siempre vía STRONG_PATTERNS — la tabla del calendario sólo
lleva nombres de fases ("Admisión de solicitudes", "Listado provisional…")
y no contendría la keyword por sí sola.

Fecha de publicación: máximo `dd/mm/yyyy` <= today() encontrado en el
cuerpo (la fase más reciente que ya ha empezado). Fallback a today().

Coste por run: 1 GET ~37KB. Sin paginación, sin PDFs anexos.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Optional

import requests

from vigia.sources._hash_watcher import HashWatcherSource
from vigia.sources.base import RawItem

logger = logging.getLogger(__name__)

CALENDARIO_URL = "https://www.convocatoriascanaldeisabelsegunda.es/calendario-245"
FETCH_TIMEOUT = 20

# Fechas dd/mm/yyyy en el cuerpo (las celdas FECHA INICIO / FECHA FIN).
DATE_RE = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b")


class CanalIsabelIICalendarioSource(HashWatcherSource):
    name = "canal_isabel_ii_calendario"
    url = CALENDARIO_URL
    title_template = (
        "Canal Isabel II — Calendario Enfermero/a Especialista en "
        "Enfermería del Trabajo (convocatoria 245) [snapshot {hash}]"
    )
    error_label = "Canal Isabel II calendario-245"
    # La tabla concreta del calendario es el contenido útil; `div#main-content`
    # es el contenedor Liferay; `body` es el último recurso. La marketing
    # landing del portal está fuera de `table.table`.
    body_selectors = ("table.table", "div#main-content", "body")

    def fetch(self, since_date: date) -> list[RawItem]:
        try:
            resp = requests.get(
                self.url,
                headers=self._default_headers(),
                timeout=FETCH_TIMEOUT,
            )
            resp.raise_for_status()
        except Exception as exc:
            msg = f"{self.error_label}: {exc}"
            self.logger.warning(msg)
            self.last_errors.append(msg)
            return []

        raw = self._build_snapshot_raw_item(resp.text)
        return [raw] if raw is not None else []

    def extract_pub_date(self, html: str, body_text: str) -> date:
        return _latest_started_phase_date(body_text) or date.today()

    # Compat: tests existentes invocan src._extract_body_text(html).
    def _extract_body_text(self, html: str) -> str:
        from vigia.sources._html import extract_clean_text
        return extract_clean_text(html, target_selectors=self.body_selectors)


def _latest_started_phase_date(text: str) -> Optional[date]:
    """Máxima fecha dd/mm/yyyy del cuerpo que ya ha pasado (<= today())."""
    today = date.today()
    candidates = []
    for d_str, m_str, y_str in DATE_RE.findall(text):
        try:
            d = datetime(int(y_str), int(m_str), int(d_str)).date()
        except ValueError:
            continue
        if d <= today:
            candidates.append(d)
    return max(candidates) if candidates else None
