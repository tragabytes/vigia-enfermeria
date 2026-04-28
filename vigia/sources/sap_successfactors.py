"""
Fuente común para portales de empleo basados en SAP SuccessFactors
Career Site Builder (CSB).

Varias empresas públicas estatales usan este ATS y exponen un endpoint
`/search/` que devuelve HTML server-side completo del listado de ofertas
activas — sin JavaScript, sin WAF intermedio, sin login. Detectado en el
research del 2026-04-28 al inspeccionar `/platform/js/search/search.js`
en sus respuestas.

Empresas cubiertas hoy:
- **RENFE** (`empleo.renfe.com`)
- **Correos** (`empleo.correos.com`)
- **Navantia** (`empleo.navantia.es`)

Estructura HTML compartida:
- Cada item del listado: `<tr class="data-row">` (Correos) o
  `<div class="job">` (RENFE). Aceptamos ambos selectores.
- Link: `<a class="jobTitle-link" href="/job/<slug>/<id>/">TITLE</a>`.
- Fecha (cuando aparece): `<span class="jobDate">DD mes YYYY</span>` en
  formato español ("22 abr 2026").
- Localización opcional: `<span class="jobFacility">` o
  `<div class="location">`.

**Por qué el listado completo y no `?q=enfermería`:** SAP SuccessFactors
hace búsqueda OR amplia — `?q=prevención` devuelve TODAS las ofertas del
portal aunque ninguna mencione "prevención" en el título. Validado el
2026-04-28 con RENFE: 6 puestos no relacionados con PRL devueltos. Por
eso descargamos el listado completo (~6-15 items por portal en momentos
típicos) y filtramos nosotros con `FAST_KEYWORDS`.

**Paginación:** SAP usa `?startrow=N&num=10`. Se itera hasta que la
página no devuelve items, hasta un tope de 10 páginas por seguridad
(volumen real esperado: 1 página).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date
from typing import Optional

import requests

from vigia.config import normalize
from vigia.sources.base import RawItem, Source

logger = logging.getLogger(__name__)

FAST_KEYWORDS = ["enfermer", "salud laboral", "prevencion de riesgos"]

# Meses en español abreviados (formato del listado: "22 abr 2026") y largos.
_MESES_ES = {
    "ene": 1, "enero": 1,
    "feb": 2, "febrero": 2,
    "mar": 3, "marzo": 3,
    "abr": 4, "abril": 4,
    "may": 5, "mayo": 5,
    "jun": 6, "junio": 6,
    "jul": 7, "julio": 7,
    "ago": 8, "agosto": 8,
    "sep": 9, "sept": 9, "septiembre": 9, "setiembre": 9,
    "oct": 10, "octubre": 10,
    "nov": 11, "noviembre": 11,
    "dic": 12, "diciembre": 12,
}

# "22 abr 2026" o "22 abril 2026", con punto opcional tras el mes.
_DATE_ES = re.compile(
    r"\b(\d{1,2})\s+([a-záéíóúñ\.]+)\s+(\d{4})\b",
    re.IGNORECASE,
)

# Tope de paginación defensivo: hoy ningún portal tiene >50 items. 5 páginas
# de 10 cubren el volumen esperado con margen.
_MAX_PAGES = 5
_PAGE_SIZE = 10


@dataclass
class SapEmpresa:
    code: str            # "RENFE"
    nombre: str          # "Renfe Operadora"
    search_url: str      # "https://empleo.renfe.com/search/"


SAP_EMPRESAS: list[SapEmpresa] = [
    SapEmpresa(
        code="RENFE",
        nombre="Renfe Operadora",
        search_url="https://empleo.renfe.com/search/",
    ),
    SapEmpresa(
        code="CORREOS",
        nombre="Sociedad Estatal Correos y Telégrafos",
        search_url="https://empleo.correos.com/search/",
    ),
    SapEmpresa(
        code="NAVANTIA",
        nombre="Navantia",
        search_url="https://empleo.navantia.es/search/",
    ),
]


class SapSuccessfactorsSource(Source):
    name = "sap_successfactors"
    probe_url = "https://empleo.renfe.com/search/"

    def fetch(self, since_date: date) -> list[RawItem]:
        all_items: list[RawItem] = []
        for emp in SAP_EMPRESAS:
            items = self._fetch_empresa(emp, since_date)
            all_items.extend(items)
        logger.info(
            "SAP SuccessFactors: %d items relevantes (%d empresas)",
            len(all_items), len(SAP_EMPRESAS),
        )
        return all_items

    def _fetch_empresa(self, emp: SapEmpresa, since_date: date) -> list[RawItem]:
        from bs4 import BeautifulSoup

        items: list[RawItem] = []
        seen_urls: set[str] = set()

        for page in range(_MAX_PAGES):
            startrow = page * _PAGE_SIZE
            url = f"{emp.search_url}?startrow={startrow}&num={_PAGE_SIZE}"
            try:
                resp = requests.get(
                    url, headers=self._default_headers(), timeout=20
                )
                resp.raise_for_status()
            except Exception as exc:
                logger.warning("%s search error (startrow=%d): %s", emp.code, startrow, exc)
                self.last_errors.append(f"{emp.code} startrow={startrow}: {exc}")
                break

            soup = BeautifulSoup(resp.text, "lxml")
            page_items = soup.select("tr.data-row, div.job")
            if not page_items:
                # Página vacía → no hay más resultados.
                break

            for container in page_items:
                item = self._parse_card(container, emp, since_date, seen_urls)
                if item is not None:
                    items.append(item)
                    logger.info("%s match: %s", emp.code, item.title[:90])

        return items

    def _parse_card(
        self, container, emp: SapEmpresa, since_date: date, seen_urls: set[str]
    ) -> Optional[RawItem]:
        anchor = container.select_one("a.jobTitle-link") or container.find("a", href=True)
        if not anchor or not anchor.get("href"):
            return None

        title = anchor.get_text(" ", strip=True)
        if not title:
            return None
        if not _matches_fast_keywords(title):
            return None

        item_url = _resolve_url(anchor["href"], emp.search_url)
        if item_url in seen_urls:
            return None

        date_el = container.select_one(".jobDate") or container.select_one("[class*=jobDate]")
        date_text = date_el.get_text(" ", strip=True) if date_el else ""
        pub_date = _parse_es_date(date_text) or date.today()
        if pub_date < since_date:
            return None

        seen_urls.add(item_url)
        return RawItem(
            source=self.name,
            url=item_url,
            title=title,
            date=pub_date,
            text="",
            extra={"empresa": emp.code, "empresa_nombre": emp.nombre},
        )


# ---------------------------------------------------------------------------
# Helpers puros (sin red).
# ---------------------------------------------------------------------------

def _matches_fast_keywords(text: str) -> bool:
    norm = normalize(text)
    return any(kw in norm for kw in FAST_KEYWORDS)


def _resolve_url(href: str, base_url: str) -> str:
    """Resuelve href relativo contra el origen del search_url. Asumimos que
    `base_url` es del tipo `https://empleo.renfe.com/search/` y que href
    relativo arranca con `/job/...`."""
    if href.startswith(("http://", "https://")):
        return href
    # Origen: https://empleo.renfe.com (sin path)
    m = re.match(r"^(https?://[^/]+)", base_url)
    if not m:
        return href
    origin = m.group(1)
    if href.startswith("/"):
        return origin + href
    return origin + "/" + href


def _parse_es_date(text: str) -> Optional[date]:
    """Parsea fechas españolas tipo '22 abr 2026' o '15 abril 2025'."""
    if not text:
        return None
    m = _DATE_ES.search(text)
    if not m:
        return None
    mes_token = m.group(2).lower().rstrip(".")
    mes = _MESES_ES.get(mes_token)
    if mes is None:
        return None
    try:
        return date(int(m.group(3)), mes, int(m.group(1)))
    except ValueError:
        return None
