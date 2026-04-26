"""
Fuente CIEMAT (Centro de Investigaciones Energéticas, Medioambientales y
Tecnológicas) — portal propio en `ciemat.es/ofertas-de-empleo`.

Por qué fuente dedicada (en vez de delegar al BOE/Ministerio de Ciencia):
las convocatorias OPIs publicadas en BOE listan los organismos juntos
con titulares genéricos ("Escala Técnicos Especializados de OPIs"). Las
plazas concretas viven en un PDF anexo enlazado solo desde la oferta
del portal CIEMAT, no desde el HTML del item BOE. Verificado contra la
oferta 2380 (Concurso Específico I 2026): el PDF
`2380CIEMATPerfiles_formativos_2025*.pdf` lista literalmente
"Especialidad de Enfermería del trabajo" y "SALUD LABORAL Y PREVENCIÓN".

Estructura del portal:

  Listado: GET https://www.ciemat.es/ofertas-de-empleo
    - HTML server-side, sin JS-only.
    - Cada oferta es un `<a>` con href tipo
      `/ofertas-de-empleo/-/ofertas/oferta/<id>?...` y la fecha en el
      bloque padre como `dd/mm/aaaa`.

  Detalle: GET https://www.ciemat.es/ofertas-de-empleo/-/ofertas/oferta/<id>
    - El HTML del detalle es ligero (~3KB de texto plano).
    - Bajo "Descargas" lleva uno o varios `<a href="...pdf">` al PDF de
      perfiles / bases / anexos en el propio dominio ciemat.es.

Cobertura: descargamos hasta 3 PDFs por oferta (mismo límite que el
plan B del BOE), 30 páginas por PDF. El extractor + enricher v2 se
encargan del matching y enriquecimiento.

NOTA SSL: el certificado de www.ciemat.es no envía el intermediate y
algunas instalaciones de Python no lo validan. Usamos `verify=False` con
warning silenciado — riesgo aceptable para una web institucional pública
de la AGE.
"""
from __future__ import annotations

import io
import logging
import re
from datetime import date, datetime
from urllib.parse import urljoin, urlparse

import requests
import urllib3

from vigia.config import normalize
from vigia.sources.base import RawItem, Source

# Silencia el warning del verify=False (cert intermedio de ciemat.es).
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

CIEMAT_LISTADO_URL = "https://www.ciemat.es/ofertas-de-empleo"

# Whitelist anti-SSRF para los PDFs anexos. Solo dominio ciemat.es: si
# CIEMAT linka a un PDF en otro dominio (raro), lo ignoramos.
CIEMAT_PDF_HOSTS: set[str] = {
    "www.ciemat.es", "ciemat.es", "rdgroups.ciemat.es",
}
MAX_PDFS_PER_OFFER = 3
MAX_PDF_PAGES = 30
MAX_PDF_BYTES = 5 * 1024 * 1024
PDF_FETCH_TIMEOUT = 25
LIST_FETCH_TIMEOUT = 30
DETAIL_FETCH_TIMEOUT = 20

OFFER_LINK_RE = re.compile(r"/ofertas-de-empleo/-/ofertas/oferta/(\d+)")
DATE_RE = re.compile(r"\b(\d{2}/\d{2}/\d{4})\b")

# Filtro grueso aplicado al texto agregado (HTML detalle + PDFs) para
# decidir si vale la pena materializar el RawItem. El extractor real
# aplica reglas mucho más estrictas; aquí solo evitamos enviar al
# extractor cosas claramente irrelevantes (oferta de informática, etc).
FAST_KEYWORDS = ["enfermer", "salud laboral", "prevencion de riesgos"]


class CIEMATSource(Source):
    name = "ciemat"
    probe_url = CIEMAT_LISTADO_URL

    def fetch(self, since_date: date) -> list[RawItem]:
        from bs4 import BeautifulSoup

        try:
            resp = requests.get(
                CIEMAT_LISTADO_URL,
                headers=self._default_headers(),
                timeout=LIST_FETCH_TIMEOUT,
                verify=False,
            )
            resp.raise_for_status()
        except Exception as exc:
            logger.warning("CIEMAT listado error: %s", exc)
            self.last_errors.append(str(exc))
            return []

        soup = BeautifulSoup(resp.text, "lxml")

        # Cada oferta es un <a> que lleva al detalle. Saltamos los enlaces
        # del paginador iterando sólo los que tengan href con id de oferta.
        offers: list[tuple[str, str, date]] = []  # (id, title, pub_date)
        seen_ids: set[str] = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            m = OFFER_LINK_RE.search(href)
            if not m:
                continue
            offer_id = m.group(1)
            if offer_id in seen_ids:
                continue
            seen_ids.add(offer_id)

            title = a.get_text(" ", strip=True)
            if not title:
                continue

            # La fecha vive en el bloque padre del enlace, separada por
            # espacios o pipes. La extraemos buscando un patrón dd/mm/yyyy
            # en el texto del contenedor más cercano.
            container = a.find_parent(["li", "tr", "div", "article"]) or a.parent
            container_text = container.get_text(" ", strip=True) if container else title
            mm = DATE_RE.search(container_text)
            if mm:
                try:
                    pub_date = datetime.strptime(mm.group(1), "%d/%m/%Y").date()
                except ValueError:
                    pub_date = date.today()
            else:
                pub_date = date.today()

            if pub_date < since_date:
                continue

            offers.append((offer_id, title, pub_date))

        logger.info("CIEMAT listado: %d ofertas en rango", len(offers))

        items: list[RawItem] = []
        for offer_id, title, pub_date in offers:
            url = urljoin(CIEMAT_LISTADO_URL + "/", f"-/ofertas/oferta/{offer_id}")
            try:
                detail_text, pdf_links = self._fetch_offer_detail(url)
            except Exception as exc:
                logger.warning("CIEMAT detalle %s error: %s", offer_id, exc)
                self.last_errors.append(f"oferta-{offer_id}: {exc}")
                continue

            # Concatenamos detalle HTML + textos de PDFs anexos (max 3).
            # Solo descargamos PDFs hasta encontrar match — ahorra tokens.
            combined = detail_text
            for pdf_url in pdf_links[:MAX_PDFS_PER_OFFER]:
                try:
                    chunk = self._fetch_pdf_text(pdf_url)
                except Exception as exc:
                    logger.debug("CIEMAT PDF %s error: %s", pdf_url, exc)
                    chunk = ""
                if chunk:
                    combined += "\n\n[ANEXO PDF " + pdf_url + "]\n" + chunk
                    if any(kw in normalize(combined) for kw in FAST_KEYWORDS):
                        logger.info(
                            "CIEMAT [%s]: match en %s", offer_id, pdf_url,
                        )
                        break

            # Filtro grueso: si tras detalle + PDFs no hay match siquiera
            # de "enfermer"/"salud laboral", saltamos. El extractor real
            # aplicaría las reglas STRONG/WEAK después.
            if not any(kw in normalize(combined) for kw in FAST_KEYWORDS):
                continue

            items.append(
                RawItem(
                    source=self.name,
                    url=url,
                    title=title,
                    date=pub_date,
                    text=combined,
                )
            )

        logger.info("CIEMAT: %d items relevantes encontrados", len(items))
        return items

    def _fetch_offer_detail(self, url: str) -> tuple[str, list[str]]:
        """GET al detalle de una oferta. Devuelve (texto_plano, lista_pdf_urls).

        Los PDFs se filtran por whitelist `CIEMAT_PDF_HOSTS` (anti-SSRF) y
        deduplican. No priorizamos por nombre porque las ofertas CIEMAT
        suelen tener un único PDF principal — si hay varios (raro), los
        recorremos en orden de aparición.
        """
        from bs4 import BeautifulSoup

        resp = requests.get(
            url,
            headers=self._default_headers(),
            timeout=DETAIL_FETCH_TIMEOUT,
            verify=False,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        body = soup.body
        text = body.get_text(" ", strip=True) if body else ""

        pdf_links: list[str] = []
        seen: set[str] = set()
        if body:
            for a in body.find_all("a", href=True):
                full = urljoin(url, a["href"])
                if full in seen:
                    continue
                if not full.lower().endswith(".pdf"):
                    continue
                host = (urlparse(full).hostname or "").lower()
                if host not in CIEMAT_PDF_HOSTS:
                    continue
                seen.add(full)
                pdf_links.append(full)

        return text, pdf_links

    def _fetch_pdf_text(self, url: str) -> str:
        """Descarga un PDF anexo y devuelve su texto plano (max 30 págs)."""
        import pdfplumber

        resp = requests.get(
            url,
            headers=self._default_headers(),
            timeout=PDF_FETCH_TIMEOUT,
            stream=True,
            verify=False,
        )
        resp.raise_for_status()
        body = bytearray()
        for chunk in resp.iter_content(chunk_size=8192):
            if not chunk:
                continue
            body.extend(chunk)
            if len(body) >= MAX_PDF_BYTES:
                body = body[:MAX_PDF_BYTES]
                break
        resp.close()

        try:
            with pdfplumber.open(io.BytesIO(bytes(body))) as pdf:
                pieces = []
                for page in pdf.pages[:MAX_PDF_PAGES]:
                    t = page.extract_text() or ""
                    if t:
                        pieces.append(t)
                return "\n\n".join(pieces)
        except Exception as exc:
            logger.debug("CIEMAT PDF parse error %s: %s", url, exc)
            return ""
