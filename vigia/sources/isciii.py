"""
Fuente ISCIII (Instituto de Salud Carlos III) — hash-watcher de la página
de proceso selectivo de bolsa de empleo.

Por qué hash-watcher en vez de listado→item:
research del 2026-04-28 confirmó que el portal isciii.es NO expone un
listado dinámico de convocatorias. Las únicas vías de empleo son tres
páginas estáticas bajo `/bolsa-empleo/`:

  - `/bolsa-empleo/proceso-selectivo` ← describe la convocatoria viva
    (publicada 19/07/2023). Cuando el ISCIII abra una convocatoria nueva
    o cambie de fase la sustancial de la bolsa, esta página se actualiza.
  - `/bolsa-empleo/listado-valoracion-meritos` ← fase 1 administrativa,
    ~27 PDFs con códigos opacos. Cambia cada quincena.
  - `/bolsa-empleo/valoracion-tecnica` ← fase 2 administrativa,
    ~64 PDFs con códigos opacos. Cambia cada quincena.

Este parser monitoriza SOLO `proceso-selectivo` (la más estable y donde
aparecería una convocatoria nueva relevante). Las dos páginas de fases
activas son demasiado ruidosas: docenas de PDFs nuevos al mes, todos
con códigos `SGPY-XXX-26-M3-DDCP` que no revelan perfil profesional
sin abrir el documento — ROI negativo para enricher v2.

Estrategia: hash-watcher (ver `_hash_watcher.HashWatcherSource`).

Coste: 1 GET por run, ~225KB. Sin paginación, sin PDFs anexos.
Cobertura indirecta complementaria vía BOE/BOCM ya cerrada (keywords
"isciii" / "instituto de salud carlos iii" en `DEPT_KEYWORDS_FOR_BODY`
y `HEALTH_ORGS`).
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

ISCIII_PROCESO_URL = "https://www.isciii.es/bolsa-empleo/proceso-selectivo"
FETCH_TIMEOUT = 20

# "fecha publicación 19/07/23" o "fecha de publicación 19/07/2023".
PUB_DATE_RE = re.compile(
    r"fecha\s+(?:de\s+)?publicaci[oó]n\s+(\d{1,2}/\d{1,2}/\d{2,4})",
    re.IGNORECASE,
)

# Selectores adicionales (más allá de los nav/header/footer/script/style/
# noscript que el helper ya descompone) que ensucian el hash con cambios
# de render sin variar el contenido sustancial.
EXTRA_NOISE_SELECTORS = (".lfr-nav-item", ".lfr-nav-child-toggle")


class ISCIIISource(HashWatcherSource):
    name = "isciii"
    url = ISCIII_PROCESO_URL
    title_template = "ISCIII Bolsa de empleo — Proceso Selectivo [snapshot {hash}]"
    error_label = "ISCIII proceso-selectivo"
    body_selectors = ("main", "#main-content", "body")
    noise_selectors = EXTRA_NOISE_SELECTORS

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
        return _extract_pub_date(body_text) or date.today()

    # Compat: tests existentes invocan src._extract_body_text(html).
    def _extract_body_text(self, html: str) -> str:
        from vigia.sources._html import extract_clean_text
        return extract_clean_text(
            html,
            target_selectors=self.body_selectors,
            extra_decompose=self.noise_selectors,
        )


def _extract_pub_date(text: str) -> Optional[date]:
    m = PUB_DATE_RE.search(text)
    if not m:
        return None
    raw = m.group(1)
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None
