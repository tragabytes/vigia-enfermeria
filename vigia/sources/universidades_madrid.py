"""
Fuente Universidades Públicas de Madrid: vigilancia de los portales de PTGAS
(Personal Técnico, de Gestión y de Administración y Servicios) de las seis
universidades públicas de la Comunidad de Madrid.

Las universidades convocan plazas para sus servicios de prevención y unidades
sanitarias propias. Caso real motivador (UAM, noviembre 2024): "Pruebas
selectivas ingreso Escala Especial Superior de Servicios — Enfermero", que
no se detectó porque BOE/BOCM no siempre repiten estas convocatorias en sus
ediciones cuando la universidad publica vía BOUC u otro boletín propio.

Estado de la implementación (2026-04-28):
- **UCM**: implementada. URL `convocatorias-vigentes-pas` con estructura
  HTML estable, listado agrupado por sección (`PTGAS FUNCIONARIO`, `Procesos
  selectivos 202X`) con `<ul class="lista_resalta">` y `<p>` que contienen
  `<a>` + texto "(Actualizado el DD/MM/YYYY)".
- **UAM, UCM, UPM, URJC, UC3M, UAH**: pendientes. Ver BACKLOG. La
  arquitectura de configs en `UNI_CONFIGS` permite añadirlas sin tocar la
  clase Source — basta con la URL del listado y los selectores reales.

La fuente publica un único `name = "universidades_madrid"` agregando todas
las universidades; cada `RawItem` lleva `extra["uni"]` para identificar el
origen concreto y poder filtrar / agrupar después.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

import requests

from vigia.config import normalize
from vigia.sources.base import RawItem, Source

logger = logging.getLogger(__name__)

# Keywords rápidas para descartar ruido del listado antes de cualquier fetch
# adicional. Coinciden con las del resto de fuentes (FAST_KEYWORDS).
FAST_KEYWORDS = ["enfermer", "salud laboral", "prevencion de riesgos"]

# Meses en español para parsear "Actualizado el 15 de septiembre de 2024".
_MESES_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}

# Regex de fecha en formato corto DD/MM/YYYY.
_DATE_DDMMYYYY = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
# Regex de fecha en formato largo "DD de mes de YYYY".
_DATE_LITERAL = re.compile(
    r"\b(\d{1,2})\s+de\s+([a-záéíóú]+)\s+de\s+(\d{4})\b",
    re.IGNORECASE,
)


@dataclass
class UniConfig:
    """Configuración por universidad. Añadir una nueva = añadir entrada a `UNI_CONFIGS`.

    La estrategia de extracción es siempre la misma: GET del `listing_url`,
    BeautifulSoup, iterar contenedores que coincidan con `item_css`, sacar
    el primer `<a>` como título+url y buscar fecha de "Actualizado/publicado"
    en el texto del contenedor padre.
    """
    code: str           # código corto: "UCM", "UAM"...
    nombre: str         # nombre público: "Universidad Complutense de Madrid"
    base_url: str       # "https://www.ucm.es"
    listing_url: str    # URL del listado público de convocatorias activas
    # Selector CSS del contenedor por item del listado. Cada elemento
    # devolverá su primer `<a>` como título + url y su texto plano como
    # fuente de la fecha "(Actualizado el ...)".
    item_css: str = "div.wg_txt li, div.wg_txt p"


UNI_CONFIGS: list[UniConfig] = [
    UniConfig(
        code="UCM",
        nombre="Universidad Complutense de Madrid",
        base_url="https://www.ucm.es",
        listing_url="https://www.ucm.es/convocatorias-vigentes-pas",
        item_css="div.wg_txt li, div.wg_txt p",
    ),
]


class UniversidadesMadridSource(Source):
    name = "universidades_madrid"
    probe_url = "https://www.ucm.es/convocatorias-vigentes-pas"

    def fetch(self, since_date: date) -> list[RawItem]:
        all_items: list[RawItem] = []
        for cfg in UNI_CONFIGS:
            uni_items = self._fetch_uni(cfg, since_date)
            all_items.extend(uni_items)
        logger.info(
            "Universidades Madrid: %d items relevantes (%d universidades configuradas)",
            len(all_items), len(UNI_CONFIGS),
        )
        return all_items

    def _fetch_uni(self, cfg: UniConfig, since_date: date) -> list[RawItem]:
        from bs4 import BeautifulSoup

        try:
            resp = requests.get(
                cfg.listing_url, headers=self._default_headers(), timeout=20
            )
            resp.raise_for_status()
        except Exception as exc:
            logger.warning("%s listado error: %s", cfg.code, exc)
            self.last_errors.append(f"{cfg.code}: {exc}")
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        items: list[RawItem] = []
        seen_urls: set[str] = set()

        for container in soup.select(cfg.item_css):
            anchor = container.find("a", href=True)
            if not anchor:
                continue

            title = anchor.get_text(" ", strip=True)
            if not title:
                continue
            if not _matches_fast_keywords(title):
                continue

            href = anchor["href"].strip()
            if not href or href.startswith("#") or href.startswith("javascript:"):
                continue
            item_url = _resolve_url(href, cfg.base_url)
            if item_url in seen_urls:
                continue

            container_text = container.get_text(" ", strip=True)
            pub_date = _extract_date(container_text) or _year_from_title(title)
            if pub_date is None:
                logger.warning(
                    "%s: sin fecha resoluble para '%s' — fallback a today()",
                    cfg.code, title[:80],
                )
                pub_date = date.today()
            if pub_date < since_date:
                continue

            seen_urls.add(item_url)
            items.append(RawItem(
                source=self.name,
                url=item_url,
                title=title,
                date=pub_date,
                text="",
                extra={"uni": cfg.code, "uni_nombre": cfg.nombre},
            ))
            logger.info("%s match: %s", cfg.code, title[:90])

        return items


def _matches_fast_keywords(title: str) -> bool:
    norm = normalize(title)
    return any(kw in norm for kw in FAST_KEYWORDS)


def _resolve_url(href: str, base_url: str) -> str:
    if href.startswith(("http://", "https://")):
        return href
    if href.startswith("/"):
        return base_url.rstrip("/") + href
    return base_url.rstrip("/") + "/" + href


def _extract_date(text: str) -> Optional[date]:
    """Busca primero "DD/MM/YYYY" y, si no hay, "DD de mes de YYYY"."""
    if not text:
        return None

    m = _DATE_DDMMYYYY.search(text)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass

    m = _DATE_LITERAL.search(text)
    if m:
        mes = _MESES_ES.get(m.group(2).lower())
        if mes:
            try:
                return date(int(m.group(3)), mes, int(m.group(1)))
            except ValueError:
                pass

    return None


def _year_from_title(title: str) -> Optional[date]:
    """`(YYYY)` → date(YYYY, 1, 1) si está en rango razonable."""
    m = re.search(r"\((\d{4})\)", title)
    if not m:
        return None
    year = int(m.group(1))
    today = date.today()
    if year < 2000 or year > today.year + 1:
        return None
    return date(year, 1, 1)
