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

Estrategia: descarga la página, extrae el cuerpo principal limpio
(quitando navegación), calcula un hash corto del texto, y lo incorpora
al título del RawItem como `[snapshot <hash>]`. Como
`id_hash = sha256(source|url|titulo)`, cada snapshot distinto es un
item nuevo en BD; snapshots repetidos los descarta `filter_new`. El
extractor decide si el contenido menciona Enfermería del Trabajo: si
lo hace, entra al pipeline normal (matcher + enricher v2). Si no, se
descarta como cualquier otro item irrelevante.

Coste: 1 GET por run, ~225KB. Sin paginación, sin PDFs anexos.
Cobertura indirecta complementaria vía BOE/BOCM ya cerrada (keywords
"isciii" / "instituto de salud carlos iii" en `DEPT_KEYWORDS_FOR_BODY`
y `HEALTH_ORGS`).
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import date, datetime
from typing import Optional

import requests

from vigia.sources.base import RawItem, Source

logger = logging.getLogger(__name__)

ISCIII_PROCESO_URL = "https://www.isciii.es/bolsa-empleo/proceso-selectivo"
FETCH_TIMEOUT = 20

# "fecha publicación 19/07/23" o "fecha de publicación 19/07/2023".
PUB_DATE_RE = re.compile(
    r"fecha\s+(?:de\s+)?publicaci[oó]n\s+(\d{1,2}/\d{1,2}/\d{2,4})",
    re.IGNORECASE,
)

# Selectores que ensucian el hash (cambian con el render aunque el
# contenido sustancial no varíe).
NOISE_SELECTORS = [
    "nav", "header", "footer", "script", "style",
    ".lfr-nav-item", ".lfr-nav-child-toggle",
]


class ISCIIISource(Source):
    name = "isciii"
    probe_url = ISCIII_PROCESO_URL

    def fetch(self, since_date: date) -> list[RawItem]:
        try:
            resp = requests.get(
                ISCIII_PROCESO_URL,
                headers=self._default_headers(),
                timeout=FETCH_TIMEOUT,
            )
            resp.raise_for_status()
        except Exception as exc:
            msg = f"ISCIII proceso-selectivo: {exc}"
            self.logger.warning(msg)
            self.last_errors.append(msg)
            return []

        body_text = self._extract_body_text(resp.text)
        if not body_text.strip():
            msg = "ISCIII proceso-selectivo: cuerpo principal vacío tras limpieza"
            self.logger.warning(msg)
            self.last_errors.append(msg)
            return []

        snapshot_hash = hashlib.sha1(body_text.encode("utf-8")).hexdigest()[:10]
        title = (
            f"ISCIII Bolsa de empleo — Proceso Selectivo "
            f"[snapshot {snapshot_hash}]"
        )
        pub_date = _extract_pub_date(body_text) or date.today()

        return [
            RawItem(
                source=self.name,
                url=ISCIII_PROCESO_URL,
                title=title,
                date=pub_date,
                text=body_text,
            )
        ]

    @staticmethod
    def _extract_body_text(html: str) -> str:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        for sel in NOISE_SELECTORS:
            for el in soup.select(sel):
                el.decompose()
        main = (
            soup.find("main")
            or soup.find(id="main-content")
            or soup.body
            or soup
        )
        return main.get_text(" ", strip=True)


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
