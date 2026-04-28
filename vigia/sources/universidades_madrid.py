"""
Fuente Universidades Públicas de Madrid: vigilancia de los portales de PTGAS
(Personal Técnico, de Gestión y de Administración y Servicios) de las
universidades públicas de la Comunidad de Madrid.

Las universidades convocan plazas para sus servicios de prevención y unidades
sanitarias propias. Caso real motivador (UAM, nov 2024 → res. enero 2026):
"Pruebas selectivas Escala Especial Superior — Enfermero/a, Servicio de
Prevención y Salud" que no se detectó porque BOE/BOCM no siempre repiten
estas convocatorias cuando la universidad publica vía BOUC u otro boletín
propio.

Estado de la implementación (2026-04-28, segunda iteración):

- **UCM** (commit `da6f243`): listado `convocatorias-vigentes-pas`,
  estructura `<ul class="lista_resalta"><li>` y `<p>` dentro de `div.wg_txt`,
  fecha "(Actualizado el DD/MM/YYYY)" o "(Actualizado el DD de mes de YYYY)".
- **UAH**: 3 listados (`/PAS/funcionario/`, `/PAS/laboral/`,
  `/PAS/bolsa-de-empleo/`). Estructura `ul.main-ul article h4 a` con `<p>`
  hermano "Resolución DD de mes de YYYY" en el contenedor padre. Match real
  confirmado: B1 Titulado/a Medio "ENFERMERÍA DEL TRABAJO-ASISTENCIA MÉDICA
  SANITARIA" en `/laboral/`.
- **UAM**: 2 listados (`personal-funcionario`, `personal-laboral`).
  Estructura `<div class="uam-card">` con `<span class="uam-becas-status">`
  + `<span class="uam-becas-date">` + `<p>` con título. **Sin enlace `<a>`
  por convocatoria** — UAM no expone URL de detalle individual. Generamos
  URL sintética con fragment determinista (sha1 del título). Match real
  confirmado: dos resoluciones de Enfermero/a (Servicio de Prevención y
  Salud) en `personal-funcionario` y una bolsa de Titulado Medio Enfermería
  del Trabajo en `personal-laboral`.

**Universidades NO implementadas, motivo técnico:**

- **UC3M** (`https://www.uc3m.es/empleo/pas/novedades_empleo_publico`): el
  listado es una tabla `<tr>` con columnas (CUERPO, GRUPO, ESPECIALIDAD,
  PLAZAS, FECHA PREVISTA). **Las celdas no contienen `<a>` por fila**, así
  que cada item carecería de URL específica como en UAM. Pero además, hoy
  no hay procesos de "Enfermería" en la columna ESPECIALIDAD (todas son
  ADMINISTRACIÓN, BIBLIOTECA, INFORMÁTICA). Implementable a futuro con la
  misma estrategia de URL sintética; para esta iteración queda fuera por
  ROI bajo.
- **URJC** (`https://www.urjc.es/empleo-publico`): Joomla (`com_k2`) con
  HTML pesado (>1MB). Las plazas se publican en bloques `<p>` con enlaces a
  `sede.urjc.es/tablon-oficial/anexo/<id>/` — anexos individuales del
  expediente (notas, plantillas, resoluciones), no la convocatoria inicial.
  En el momento del research había una convocatoria de Enfermería en curso
  con 7 anexos publicados, pero ninguno apuntaba al texto de la
  convocatoria original. Parser sería ruidoso; mejor delegar a la cobertura
  indirecta vía BOE 2A (las pruebas selectivas de URJC sí pasan por BOE).
- **UPM** (`https://www.upm.es/...`): no se localizó portal público de
  convocatorias PTGAS. Las URLs candidatas devuelven 404 o redirigen a
  páginas genéricas. Probablemente UPM publica todo vía BOE / BOUPM (su
  boletín interno) y no expone listado HTTP libre. Fuera de scope.

La fuente publica un único `name = "universidades_madrid"` agregando todas
las universidades; cada `RawItem` lleva `extra["uni"]` para identificar el
origen concreto.
"""
from __future__ import annotations

import hashlib
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

# Meses en español para parsear "Actualizado el 15 de septiembre de 2024"
# y "Resolución 27 de octubre de 2025".
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
class UniListing:
    """Una URL concreta de listado dentro de una universidad.

    `item_css` selecciona el contenedor de cada item. Puede ser un selector
    compuesto (con coma) si el portal mezcla `<li>` y `<p>` (UCM).

    `item_exclude_classes` permite filtrar contenedores que coincidan con el
    selector pero no sean items reales (p.ej. en UAM, `<div class="uam-card
    uam-filters">` es un panel de filtros, no una convocatoria).
    """
    url: str
    item_css: str
    item_exclude_classes: tuple[str, ...] = ()


@dataclass
class UniConfig:
    """Configuración por universidad. Añadir una nueva = añadir entrada a
    `UNI_CONFIGS` con sus URLs y selectores reales — sin tocar la clase Source.
    """
    code: str       # código corto: "UCM", "UAM"...
    nombre: str     # nombre público completo
    base_url: str   # ej. "https://www.ucm.es"
    listings: list[UniListing] = field(default_factory=list)


UNI_CONFIGS: list[UniConfig] = [
    UniConfig(
        code="UCM",
        nombre="Universidad Complutense de Madrid",
        base_url="https://www.ucm.es",
        listings=[
            UniListing(
                url="https://www.ucm.es/convocatorias-vigentes-pas",
                item_css="div.wg_txt li, div.wg_txt p",
            ),
        ],
    ),
    UniConfig(
        code="UAH",
        nombre="Universidad de Alcalá",
        base_url="https://www.uah.es",
        listings=[
            UniListing(
                url="https://www.uah.es/es/empleo-publico/PAS/funcionario/",
                item_css="ul.main-ul article",
            ),
            UniListing(
                url="https://www.uah.es/es/empleo-publico/PAS/laboral/",
                item_css="ul.main-ul article",
            ),
            UniListing(
                url="https://www.uah.es/es/empleo-publico/PAS/bolsa-de-empleo/",
                item_css="ul.main-ul article",
            ),
        ],
    ),
    UniConfig(
        code="UAM",
        nombre="Universidad Autónoma de Madrid",
        base_url="https://www.uam.es",
        listings=[
            UniListing(
                url="https://www.uam.es/uam/ptgas/listado-concursos-oposiciones-bolsas-personal-funcionario",
                item_css="div.uam-card",
                # Excluir el panel de filtros (mismo selector compartido).
                item_exclude_classes=("uam-filters",),
            ),
            UniListing(
                url="https://www.uam.es/uam/ptgas/listado-concursos-oposiciones-bolsas-personal-laboral",
                item_css="div.uam-card",
                item_exclude_classes=("uam-filters",),
            ),
        ],
    ),
]


class UniversidadesMadridSource(Source):
    name = "universidades_madrid"
    probe_url = "https://www.ucm.es/convocatorias-vigentes-pas"

    def fetch(self, since_date: date) -> list[RawItem]:
        all_items: list[RawItem] = []
        for cfg in UNI_CONFIGS:
            for listing in cfg.listings:
                items = self._fetch_listing(cfg, listing, since_date)
                all_items.extend(items)
        logger.info(
            "Universidades Madrid: %d items relevantes (%d universidades, %d listados)",
            len(all_items),
            len(UNI_CONFIGS),
            sum(len(c.listings) for c in UNI_CONFIGS),
        )
        return all_items

    def _fetch_listing(
        self, cfg: UniConfig, listing: UniListing, since_date: date
    ) -> list[RawItem]:
        from bs4 import BeautifulSoup

        try:
            resp = requests.get(
                listing.url, headers=self._default_headers(), timeout=20
            )
            resp.raise_for_status()
        except Exception as exc:
            logger.warning("%s listado error (%s): %s", cfg.code, listing.url, exc)
            self.last_errors.append(f"{cfg.code} {listing.url}: {exc}")
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        items: list[RawItem] = []
        seen_urls: set[str] = set()

        for container in soup.select(listing.item_css):
            classes = set(container.get("class") or [])
            if classes & set(listing.item_exclude_classes):
                continue

            container_text = container.get_text(" ", strip=True)
            if not container_text:
                continue

            # Filtro fast-keyword sobre el texto COMPLETO del contenedor —
            # no solo el title del primer <a>. UAM mete el título de la
            # convocatoria en un `<p>` y en UAH puede aparecer "Enfermería"
            # más abajo en el cuerpo del item, no necesariamente en el `<a>`.
            if not _matches_fast_keywords(container_text):
                continue

            anchor = container.find("a", href=True)
            title, item_url = _resolve_title_and_url(
                container_text, anchor, listing.url, cfg.base_url
            )
            if title is None:
                continue
            if item_url in seen_urls:
                continue

            pub_date = (
                _extract_date(container_text)
                or _year_from_title(title)
            )
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
                text=container_text,
                extra={"uni": cfg.code, "uni_nombre": cfg.nombre},
            ))
            logger.info("%s match: %s", cfg.code, title[:90])

        return items


# ---------------------------------------------------------------------------
# Helpers puros (sin red, fácilmente testables).
# ---------------------------------------------------------------------------

def _matches_fast_keywords(text: str) -> bool:
    norm = normalize(text)
    return any(kw in norm for kw in FAST_KEYWORDS)


def _resolve_title_and_url(
    container_text: str,
    anchor,
    listing_url: str,
    base_url: str,
) -> tuple[Optional[str], Optional[str]]:
    """Devuelve `(title, url)` para un item del listado.

    Tres casos según lo que el container ofrezca:
    1. **Anchor con texto descriptivo**: `(<a> text, resolved url)`.
    2. **Anchor sin texto útil** (p.ej. solo "DESCARGAR PDF"): título =
       primeras palabras del container, url = href del anchor.
    3. **Sin anchor** (caso UAM): título = texto del container, url =
       `listing_url#sha1` para que cada item tenga URL única estable.
    """
    if anchor is not None:
        href = anchor.get("href", "").strip()
        if href and not href.startswith(("#", "javascript:")):
            anchor_text = anchor.get_text(" ", strip=True)
            url = _resolve_url(href, base_url)
            # Si el `<a>` lleva poco texto (caso UAM "DESCARGAR PDF" o un icon),
            # mejor usar el texto del container, que sí describe la plaza.
            if anchor_text and len(anchor_text) >= 25:
                return _trim_title(anchor_text), url
            return _trim_title(container_text), url

    title = _trim_title(container_text)
    if not title:
        return None, None
    digest = hashlib.sha1(title.encode("utf-8")).hexdigest()[:12]
    return title, f"{listing_url}#{digest}"


def _resolve_url(href: str, base_url: str) -> str:
    if href.startswith(("http://", "https://")):
        return href
    if href.startswith("/"):
        return base_url.rstrip("/") + href
    return base_url.rstrip("/") + "/" + href


def _trim_title(text: str, max_len: int = 280) -> str:
    """Recorta texto largo manteniendo la frase principal del título."""
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_len:
        return text
    cut = text[:max_len].rsplit(" ", 1)[0]
    return cut + "…"


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
