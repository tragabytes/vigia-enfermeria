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

Estrategia: misma técnica que el parser ISCIII. Descarga la página,
selecciona el `<article class="node--type-main-information">` (cuerpo
limpio sin nav/menú), calcula `sha1(body)[:10]` e incorpora el hash al
título del RawItem como `[snapshot <hash>]`. Como `id_hash =
sha256(source|url|titulo)`, snapshots distintos generan items distintos
en BD; idénticos los descarta `filter_new`. El cuerpo menciona
"Enfermería del Trabajo" varias veces, así que el extractor matcheará
siempre que el snapshot exista — cada cambio sustantivo de la ficha
genera una alerta real al usuario.

Fecha de publicación: extraída de la última fecha presente en los paths
`/docs/assets/YYYY/MM/DD/...` del HTML (señal real de la última
actualización de los documentos enlazados, más precisa que parsear el
texto). Fallback al texto "Última actualización: DD mes YYYY", luego a
`today()` con warning.

Coste por run: 1 GET ~125KB. Sin paginación, sin PDFs anexos.
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

FICHA_URL = "https://www.comunidad.madrid/empleo/diplomado-enfermeria-trabajo"
FETCH_TIMEOUT = 20

# Selector del cuerpo principal de la ficha. La página usa Drupal con un
# layout estable de varios años. Si Drupal cambia el theme y el selector
# deja de matchear, _extract_body_text cae a `<main id="main-content">`
# y luego a `<body>`.
ARTICLE_SELECTOR = "article.node--type-main-information"

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


class ComunidadMadridFichaEnfermeriaSource(Source):
    name = "cm_ficha_enfermeria"
    probe_url = FICHA_URL

    def fetch(self, since_date: date) -> list[RawItem]:
        try:
            resp = requests.get(
                FICHA_URL,
                headers=self._default_headers(),
                timeout=FETCH_TIMEOUT,
            )
            resp.raise_for_status()
        except Exception as exc:
            msg = f"CM ficha Enfermería del Trabajo: {exc}"
            self.logger.warning(msg)
            self.last_errors.append(msg)
            return []

        html = resp.text
        body_text = self._extract_body_text(html)
        if not body_text.strip():
            msg = "CM ficha Enfermería del Trabajo: cuerpo principal vacío tras limpieza"
            self.logger.warning(msg)
            self.last_errors.append(msg)
            return []

        snapshot_hash = hashlib.sha1(body_text.encode("utf-8")).hexdigest()[:10]
        title = (
            f"Comunidad de Madrid — Ficha Diplomado en Enfermería del Trabajo "
            f"[snapshot {snapshot_hash}]"
        )
        pub_date = (
            _date_from_assets(html)
            or _date_from_last_update_text(body_text)
            or date.today()
        )

        return [
            RawItem(
                source=self.name,
                url=FICHA_URL,
                title=title,
                date=pub_date,
                text=body_text,
            )
        ]

    @staticmethod
    def _extract_body_text(html: str) -> str:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        target = (
            soup.select_one(ARTICLE_SELECTOR)
            or soup.find("main", id="main-content")
            or soup.body
            or soup
        )
        # Defensivo: aún quitamos ruido predecible que podría ensuciar el hash.
        for sel in ["nav", "header", "footer", "script", "style"]:
            for el in target.select(sel):
                el.decompose()
        return target.get_text(" ", strip=True)


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
