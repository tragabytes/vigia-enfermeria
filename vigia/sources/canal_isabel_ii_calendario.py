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

Estrategia: misma técnica que `cm_ficha_enfermeria.py` e `isciii.py`.
Descarga la página, extrae el cuerpo limpio (sólo la `<table class="table">`
con el calendario, ignorando el banner de marketing del portal Liferay),
calcula `sha1(body)[:10]` y lo incorpora al título como `[snapshot <hash>]`.

El título incluye literalmente "Enfermero/a Especialista en Enfermería del
Trabajo" para que el extractor matchee siempre vía STRONG_PATTERNS — la
tabla del calendario no contiene "enfermería" por sí sola, sólo nombres
de fases ("Admisión de solicitudes", "Listado provisional...").

Fecha de publicación: máximo `dd/mm/yyyy` <= today() encontrado en el
cuerpo (la fase más reciente que ya ha empezado). Fallback a today().

Coste por run: 1 GET ~37KB. Sin paginación, sin PDFs anexos.
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import date, datetime
from typing import Optional

import requests

from vigia.sources._html import extract_clean_text
from vigia.sources.base import RawItem, Source

logger = logging.getLogger(__name__)

CALENDARIO_URL = "https://www.convocatoriascanaldeisabelsegunda.es/calendario-245"
FETCH_TIMEOUT = 20

# Cascada de selectores: la tabla concreta del calendario es el contenido
# útil; `div#main-content` es el contenedor Liferay; `body` es el último
# recurso. La marketing landing del portal está fuera de `table.table`.
BODY_SELECTORS = ("table.table", "div#main-content", "body")

# Fechas dd/mm/yyyy en el cuerpo (las celdas FECHA INICIO / FECHA FIN).
DATE_RE = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b")


class CanalIsabelIICalendarioSource(Source):
    name = "canal_isabel_ii_calendario"
    probe_url = CALENDARIO_URL

    def fetch(self, since_date: date) -> list[RawItem]:
        try:
            resp = requests.get(
                CALENDARIO_URL,
                headers=self._default_headers(),
                timeout=FETCH_TIMEOUT,
            )
            resp.raise_for_status()
        except Exception as exc:
            msg = f"Canal Isabel II calendario-245: {exc}"
            self.logger.warning(msg)
            self.last_errors.append(msg)
            return []

        body_text = self._extract_body_text(resp.text)
        if not body_text.strip():
            msg = "Canal Isabel II calendario-245: cuerpo principal vacío tras limpieza"
            self.logger.warning(msg)
            self.last_errors.append(msg)
            return []

        snapshot_hash = hashlib.sha1(body_text.encode("utf-8")).hexdigest()[:10]
        title = (
            f"Canal Isabel II — Calendario Enfermero/a Especialista en "
            f"Enfermería del Trabajo (convocatoria 245) "
            f"[snapshot {snapshot_hash}]"
        )
        pub_date = _latest_started_phase_date(body_text) or date.today()

        return [
            RawItem(
                source=self.name,
                url=CALENDARIO_URL,
                title=title,
                date=pub_date,
                text=body_text,
            )
        ]

    @staticmethod
    def _extract_body_text(html: str) -> str:
        return extract_clean_text(html, target_selectors=BODY_SELECTORS)


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
