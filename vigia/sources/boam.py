"""
Fuente BOAM: PDF del sumario diario del Boletín Oficial del Ayuntamiento de Madrid.

Estrategia (validada con datos reales el 25/04/2026):
  1. Scrape https://www.madrid.es/boam → obtener la URL del PDF del día
  2. Descargar el PDF completo (~6-15 MB, no hay descarga parcial)
  3. Extraer texto de las primeras 8 páginas (contienen el SUMARIO)
  4. Parsear el sumario para identificar ítems con keywords relevantes

Estructura del sumario BOAM:
  - Páginas 1: portada
  - Página 2: SUMARIO con secciones A) Sesiones, B) Disposiciones y Actos, C) Personal...
  - Páginas 3-8: continuación del sumario con Convocatorias, Nombramientos, etc.

Hallazgo: Los títulos del SUMARIO incluyen la especialidad ("Enfermero/a (Enfermería de
Trabajo)"), a diferencia del BOE/BOCM donde la especialidad solo aparece en el cuerpo.
"""
from __future__ import annotations

import io
import logging
import re
from datetime import date, timedelta

import requests

from vigia.config import normalize
from vigia.sources.base import RawItem, Source

logger = logging.getLogger(__name__)

BOAM_HOME = "https://www.madrid.es/boam"
BOAM_BASE_URL = "https://sede.madrid.es"
SUMARIO_PAGES = 10  # páginas iniciales donde está el sumario


class BOAMSource(Source):
    name = "boam"

    def fetch(self, since_date: date) -> list[RawItem]:
        items: list[RawItem] = []
        for delta in range((date.today() - since_date).days + 1):
            target = since_date + timedelta(days=delta)
            if target.weekday() >= 5:
                continue
            try:
                items.extend(self._fetch_day(target))
            except Exception as exc:
                logger.warning("BOAM %s error: %s", target, exc)
        return items

    def _fetch_day(self, target: date) -> list[RawItem]:
        pdf_url, boam_num = self._find_pdf_url(target)
        if not pdf_url:
            logger.info("BOAM: sin edición para %s", target)
            return []

        logger.info("BOAM: descargando PDF %s (%s)", boam_num, pdf_url[:80])
        sumario_text = self._download_and_extract_sumario(pdf_url)
        if not sumario_text:
            logger.warning("BOAM: no se pudo extraer texto del sumario %s", boam_num)
            return []

        return self._parse_sumario(sumario_text, target, boam_num, pdf_url)

    def _find_pdf_url(self, target: date) -> tuple[str, str]:
        """
        Scrapea la página principal del BOAM para encontrar el PDF de la fecha dada.
        Devuelve (url_pdf, numero_boam).
        """
        from bs4 import BeautifulSoup

        resp = requests.get(
            BOAM_HOME,
            headers=self._default_headers(),
            timeout=20,
            allow_redirects=True,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        target_str = target.strftime("%-d/%m/%Y")  # "24/04/2026"
        # En Windows strftime %-d no existe; normalizar
        target_str_alt = target.strftime("%d/%m/%Y")

        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(" ", strip=True)
            # Buscar el enlace del BOAM con la fecha correcta
            if "BOAM" in text and any(
                t in text for t in [target_str, target_str_alt, target.strftime("%d/%m/%Y")]
            ):
                # Buscar el PDF de descarga en los hermanos del enlace
                parent = a.find_parent()
                if parent:
                    for sibling_a in parent.find_all("a", href=True):
                        sibling_href = sibling_a["href"]
                        if ".pdf" in sibling_href.lower() or ".PDF" in sibling_href:
                            pdf_url = (
                                sibling_href
                                if sibling_href.startswith("http")
                                else BOAM_BASE_URL + sibling_href
                            )
                            # Extraer número de BOAM del texto
                            m = re.search(r"BOAM n[º.°]?\s*(\d[\d.]*)", text, re.IGNORECASE)
                            boam_num = m.group(1).replace(".", "") if m else "?"
                            return pdf_url, boam_num

        # Si no encontró la fecha exacta en la página (puede estar desfasada), usar el más reciente
        # que coincida con la fecha objetivo
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if ".pdf" in href.lower() and target.strftime("%d%m%Y") in href:
                pdf_url = href if href.startswith("http") else BOAM_BASE_URL + href
                m = re.search(r"BOAM_(\d+)_", href)
                boam_num = m.group(1) if m else "?"
                return pdf_url, boam_num

        # Último recurso: usar el primer PDF de la página
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text_near = a.get_text(" ", strip=True)
            if ".pdf" in href.lower() and "BOAM_" in href:
                # Solo si la fecha está en el href
                date_str_in_href = target.strftime("%d%m%Y")
                if date_str_in_href in href:
                    pdf_url = href if href.startswith("http") else BOAM_BASE_URL + href
                    m = re.search(r"BOAM_(\d+)_", href)
                    boam_num = m.group(1) if m else "?"
                    return pdf_url, boam_num

        return "", ""

    def _download_and_extract_sumario(self, pdf_url: str) -> str:
        """Descarga el PDF y extrae el texto de las primeras SUMARIO_PAGES páginas."""
        import pdfplumber

        resp = requests.get(pdf_url, headers=self._default_headers(), timeout=120)
        resp.raise_for_status()
        with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
            parts = []
            for page in pdf.pages[:SUMARIO_PAGES]:
                t = page.extract_text()
                if t:
                    parts.append(t)
        return "\n".join(parts)

    def _parse_sumario(
        self, sumario_text: str, target: date, boam_num: str, pdf_url: str
    ) -> list[RawItem]:
        """
        Extrae los ítems del sumario que contienen keywords relevantes.
        El sumario tiene líneas como:
          "Resolución de ... por la que se aprueban las bases específicas ... Enfermero/a
           (Enfermería de Trabajo) ...\n  pág. 42"
        Agrupa líneas en ítems usando el marcador "pág." como delimitador.
        """
        items: list[RawItem] = []
        # Dividir el sumario en bloques separados por "pág. N"
        # Los ítems acaban con "pág. NNN"
        blocks = re.split(r"\n(?=.*pág\.?\s*\d)", sumario_text, flags=re.IGNORECASE)

        for block in blocks:
            block = block.strip()
            if len(block) < 20:
                continue
            block_norm = normalize(block)
            # Comprobar si contiene algún keyword rápido
            if not any(
                kw in block_norm
                for kw in ["enfermer", "salud laboral", "prevencion de riesgos"]
            ):
                continue

            # Extraer número de página para construir url aproximada
            page_match = re.search(r"pág\.?\s*(\d+)", block, re.IGNORECASE)
            page_num = int(page_match.group(1)) if page_match else 0

            # Limpiar el bloque: quitar "pág. N" al final
            title = re.sub(r"\s*pág\.?\s*\d+\s*$", "", block, flags=re.IGNORECASE).strip()
            # Eliminar saltos de línea internos
            title = re.sub(r"\s+", " ", title)

            items.append(
                RawItem(
                    source=self.name,
                    url=pdf_url,
                    title=title,
                    date=target,
                    text="",
                    extra={"boam_num": boam_num, "pagina": page_num},
                )
            )

        return items
