"""
Fuente "Ficha proceso Enfermería del Trabajo (Comunidad de Madrid)" —
hash-watcher de https://www.comunidad.madrid/empleo/diplomado-enfermeria-trabajo

Por qué fuente dedicada:
el portal `www.comunidad.madrid` (distinto de `sede.comunidad.madrid` que
ya monitorizamos vía `comunidad_madrid.py`) publica una "ficha de proceso"
estable por categoría profesional. La ficha de Diplomado en Enfermería del
Trabajo concentra: convocatoria viva, número de plazas, plazos, links a
BOCM, listas de admitidos/excluidos provisionales y definitivas,
calendario de actuaciones, plantilla correctora, etc. El usuario la sigue
manualmente porque es el sitio donde aparecen las novedades antes de que
se publiquen como item específico en el buscador `sede.comunidad.madrid`
(pueden pasar días entre que se actualiza la ficha y que sale la
resolución concreta).

Estrategia: hash-watcher (ver `_hash_watcher.HashWatcherSource`). El
cuerpo sí menciona "Enfermería del Trabajo", así que el extractor
matcheará cada snapshot que se emita → cada cambio sustantivo de la
ficha genera una alerta real al usuario.

Fecha de publicación: extraída de la última fecha presente en los paths
`/docs/assets/YYYY/MM/DD/...` del HTML (señal real de la última
actualización de los documentos enlazados). Fallback al texto
"Última actualización: DD mes YYYY", luego a `today()` con warning.

Coste por run: 1 GET ~125KB. Sin paginación, sin PDFs anexos.
"""
from __future__ import annotations

import logging
import re
from datetime import date
from typing import Optional

import requests

from vigia.sources._hash_watcher import HashWatcherSource
from vigia.sources.base import RawItem

logger = logging.getLogger(__name__)

FICHA_URL = "https://www.comunidad.madrid/empleo/diplomado-enfermeria-trabajo"
FETCH_TIMEOUT = 20

# Fecha en path de assets enlazados desde la ficha. Cuando el tribunal
# publica un PDF nuevo, queda con esta forma.
ASSET_DATE_RE = re.compile(r"/docs/assets/(\d{4})/(\d{2})/(\d{2})/")

# Texto "Última actualización: 25 marzo 2026" en la cabecera de la ficha.
SPANISH_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}
LAST_UPDATE_RE = re.compile(
    r"[uú]ltima\s+actualizaci[oó]n[:\s]+(\d{1,2})\s+([a-záéíóú]+)\s+(\d{4})",
    re.IGNORECASE,
)


class ComunidadMadridFichaEnfermeriaSource(HashWatcherSource):
    name = "cm_ficha_enfermeria"
    url = FICHA_URL
    title_template = (
        "Comunidad de Madrid — Ficha Diplomado en Enfermería del Trabajo "
        "[snapshot {hash}]"
    )
    error_label = "CM ficha Enfermería del Trabajo"
    # Selector preciso de la ficha (Drupal). Si el theme cambia, cae a
    # `<main id="main-content">` y luego a `<body>`.
    body_selectors = (
        "article.node--type-main-information",
        "main#main-content",
        "body",
    )

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
        return (
            _date_from_assets(html)
            or _date_from_last_update_text(body_text)
            or date.today()
        )

    # Compat: tests existentes invocan src._extract_body_text(html).
    # Mantenemos el método como wrapper sobre la base.
    def _extract_body_text(self, html: str) -> str:
        from vigia.sources._html import extract_clean_text
        return extract_clean_text(html, target_selectors=self.body_selectors)


def _date_from_assets(html: str) -> Optional[date]:
    matches = ASSET_DATE_RE.findall(html)
    if not matches:
        return None
    try:
        return max(date(int(y), int(m), int(d)) for y, m, d in matches)
    except (TypeError, ValueError):
        return None


def _date_from_last_update_text(text: str) -> Optional[date]:
    m = LAST_UPDATE_RE.search(text)
    if not m:
        return None
    day, month_name, year = m.group(1), m.group(2).lower(), m.group(3)
    month = SPANISH_MONTHS.get(month_name)
    if month is None:
        return None
    try:
        return date(int(year), month, int(day))
    except ValueError:
        return None
