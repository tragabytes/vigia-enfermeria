"""
Fuente Comunidad de Madrid: buscador de empleo público en sede.comunidad.madrid.

Estructura (validada 25/04/2026, fechas reauditadas 28/04/2026):
  - URL: https://sede.comunidad.madrid/buscador?t=KEYWORD&tipo=7&...&items_per_page=50
  - Drupal 8/9 con listado en div.pane-adel ul li
  - Cada item: título en div.titulo h3 a, URL relativa, estado en div.estado
  - Paginación: ?page=N (0-indexado), total en div.summary span

Estados observados en `div.estado` y su impacto sobre la fecha de publicación:
  - "En plazo" → muestra `Inicio: DD/MM/YYYY | Fin: DD/MM/YYYY`. Inicio es la
    aproximación más fiel a la publicación.
  - "En tramitación", "Plazo indefinido", "Finalizado" → no exponen fecha en el
    listado. Hay que bajar al detalle del item:
      · `.fecha-actualizacion` (Última actualización: DD/MM/YYYY) si existe.
      · Último `.hito-fecha` (el más antiguo del calendario de actuaciones) si no.
      · Año `(YYYY)` del título como heurística final.
      · `date.today()` con warning si todo falla — preserva el comportamiento
        previo de "no perder items" pero ahora deja rastro en el log.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Optional

import requests

from vigia.config import normalize
from vigia.sources.base import RawItem, Source

logger = logging.getLogger(__name__)

SEDE_BASE = "https://sede.comunidad.madrid"
BUSCADOR_URL = (
    "https://sede.comunidad.madrid/buscador"
    "?tipo=7"
    "&native_string_nombre_consejeria=All"
    "&estado_pendiente%5B1%5D=1"
    "&estado_plazo%5B1%5D=1"
    "&estado_tramitacion%5B1%5D=1"
    "&items_per_page=50"
)

FAST_KEYWORDS = ["enfermer", "salud laboral", "prevencion de riesgos"]
SEARCH_TERMS = ["enfermeria", "salud laboral"]

# El listado expone la fecha como "Apertura..." (estado abierto histórico) o
# "Inicio: DD/MM/YYYY" (estado "En plazo" actual). Ambas señalan publicación.
LISTING_DATE_RE = re.compile(r"(?:Apertura|Inicio)\D*?(\d{2}/\d{2}/\d{4})")

# Año entre paréntesis al final del título: "Bolsa única (2024). Subsanación".
TITLE_YEAR_RE = re.compile(r"\((\d{4})\)")

DATE_FROM_TEXT_RE = re.compile(r"(\d{2}/\d{2}/\d{4})")

DETAIL_TIMEOUT = 15


class ComunidadMadridSource(Source):
    name = "comunidad_madrid"
    probe_url = SEDE_BASE  # https://sede.comunidad.madrid

    def fetch(self, since_date: date) -> list[RawItem]:
        all_items: list[RawItem] = []
        seen_urls: set[str] = set()
        for term in SEARCH_TERMS:
            items = self._fetch_term(term, since_date, seen_urls)
            all_items.extend(items)
        logger.info(
            "Comunidad Madrid: %d items relevantes encontrados", len(all_items)
        )
        return all_items

    def _fetch_term(
        self, term: str, since_date: date, seen_urls: set[str]
    ) -> list[RawItem]:
        from bs4 import BeautifulSoup

        items: list[RawItem] = []
        page = 0

        while True:
            url = f"{BUSCADOR_URL}&t={term}&page={page}"
            try:
                resp = requests.get(
                    url, headers=self._default_headers(), timeout=20
                )
                resp.raise_for_status()
            except Exception as exc:
                logger.warning("Comunidad Madrid error (term=%s page=%d): %s", term, page, exc)
                self.last_errors.append(f"term={term} page={page}: {exc}")
                break

            soup = BeautifulSoup(resp.text, "lxml")
            pane = soup.find("div", class_="pane-adel")
            if not pane:
                break

            rows = pane.select("ul li")
            if not rows:
                break

            found_any = False
            for li in rows:
                item = self._parse_item(li, since_date, seen_urls)
                if item is not None:
                    items.append(item)
                found_any = True

            # Si la última página tiene items o pager no tiene "siguiente", parar
            pager_last = soup.find("li", class_="pager__item--last")
            pager_next = soup.find("li", class_="pager__item--next")
            if not found_any or not pager_next:
                break
            page += 1

        return items

    def _parse_item(
        self, li, since_date: date, seen_urls: set[str]
    ) -> RawItem | None:
        titulo_el = li.select_one("div.titulo h3 a")
        if not titulo_el:
            return None

        title = (titulo_el.get("title") or titulo_el.get_text(" ", strip=True)).strip()
        href = titulo_el.get("href", "")
        item_url = href if href.startswith("http") else SEDE_BASE + href

        if item_url in seen_urls:
            return None

        if not any(kw in normalize(title) for kw in FAST_KEYWORDS):
            return None

        estado_el = li.select_one("div.estado")
        estado_text = estado_el.get_text(" ", strip=True) if estado_el else ""
        pub_date = self._resolve_pub_date(estado_text, item_url, title)

        if pub_date < since_date:
            return None

        seen_urls.add(item_url)
        return RawItem(
            source=self.name,
            url=item_url,
            title=title,
            date=pub_date,
            text="",
        )

    def _resolve_pub_date(
        self, estado_text: str, item_url: str, title: str
    ) -> date:
        """Cascada de fallbacks ordenada por fiabilidad descendente.

        1. Listado: "Apertura/Inicio: DD/MM/YYYY".
        2. Detalle: `.fecha-actualizacion` → último `.hito-fecha`.
        3. Título: año `(YYYY)`.
        4. `date.today()` con warning — solo si las tres anteriores fallan.
        """
        d = _date_from_listing(estado_text)
        if d is not None:
            return d
        return self.resolve_pub_date_from_detail(item_url, title)

    def resolve_pub_date_from_detail(self, item_url: str, title: str) -> date:
        """Cascada sin paso de listado, expuesta para `maintenance.py`.

        Cuando el item ya está en BD y solo tenemos url + título (no hay
        `div.estado` que rescatar del listado), aplicamos directamente:
        detalle → título → today() con warning.
        """
        d = self._fetch_detail_date(item_url)
        if d is not None:
            return d

        d = _year_from_title(title)
        if d is not None:
            return d

        logger.warning(
            "Comunidad Madrid: sin fecha resoluble para %s — fallback a today()",
            item_url[:120],
        )
        return date.today()

    def _fetch_detail_date(self, item_url: str) -> Optional[date]:
        from bs4 import BeautifulSoup

        try:
            resp = requests.get(
                item_url, headers=self._default_headers(), timeout=DETAIL_TIMEOUT
            )
            resp.raise_for_status()
        except Exception as exc:
            logger.warning(
                "Comunidad Madrid detalle (%s): %s", item_url[:80], exc
            )
            return None

        return _date_from_detail_html(resp.text)


def _date_from_listing(estado_text: str) -> Optional[date]:
    if not estado_text:
        return None
    m = LISTING_DATE_RE.search(estado_text)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%d/%m/%Y").date()
    except ValueError:
        return None


def _date_from_detail_html(html: str) -> Optional[date]:
    """Extrae la mejor fecha disponible del HTML de la página de detalle.

    Preferencia: `.fecha-actualizacion` (Última actualización) > último
    `.hito-fecha` (el más antiguo del calendario de actuaciones, que es la
    primera publicación).
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")

    fecha_act = soup.select_one(".fecha-actualizacion")
    if fecha_act:
        m = DATE_FROM_TEXT_RE.search(fecha_act.get_text(" ", strip=True))
        if m:
            try:
                return datetime.strptime(m.group(1), "%d/%m/%Y").date()
            except ValueError:
                pass

    hitos = soup.select(".hito-fecha")
    if hitos:
        # El listado de hitos viene en orden cronológico inverso (más reciente
        # arriba). El último es el hito más antiguo — la publicación original.
        oldest_text = hitos[-1].get_text(" ", strip=True)
        m = DATE_FROM_TEXT_RE.search(oldest_text)
        if m:
            try:
                return datetime.strptime(m.group(1), "%d/%m/%Y").date()
            except ValueError:
                pass

    return None


def _year_from_title(title: str) -> Optional[date]:
    """Devuelve `date(YYYY, 1, 1)` si el título incluye `(YYYY)` con un año
    dentro de un rango razonable. Si no, None."""
    m = TITLE_YEAR_RE.search(title)
    if not m:
        return None
    year = int(m.group(1))
    today = date.today()
    if year < 2000 or year > today.year + 1:
        return None
    return date(year, 1, 1)
