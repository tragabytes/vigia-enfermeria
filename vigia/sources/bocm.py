"""
Fuente BOCM: XML sumario diario + descarga selectiva de PDFs.

Estrategia (validada con datos reales el 25/04/2026):
  1. Scrape /ultimo-bocm para obtener la URL del XML del día
  2. Parsear el XML sumario (estructura: sumario/diario/secciones/seccion/apartado/organismo/disposicion)
  3. Comprobar títulos contra keywords
  4. Para disposiciones de la sección "B) Autoridades y Personal" de organismos
     sanitarios (SERMAS, Consejería de Sanidad) cuyo título NO hace match pero
     que contiene "concurso", "proceso selectivo" o "convocatoria" + "especialista" /
     "personal sanitario": descargar el PDF y extraer texto de las primeras 3 páginas

Hallazgo clave (18/03/2024, BOCM-20240318-17):
  El título del sumario dice "categorías de personal sanitario del Grupo A, Subgrupo A2"
  pero el PDF contiene "en Enfermería del Trabajo" en el cuerpo del documento.
"""
from __future__ import annotations

import io
import logging
from datetime import date, timedelta
from xml.etree import ElementTree as ET

import requests

from vigia.config import normalize
from vigia.sources.base import RawItem, Source

logger = logging.getLogger(__name__)

BOCM_HOME = "https://www.bocm.es"
BOCM_ULTIMO = "https://www.bocm.es/ultimo-bocm"
BOCM_XML_PATTERN = (
    "https://www.bocm.es/boletin/CM_Boletin_BOCM/{year}/{month:02d}/{day:02d}/"
    "BOCM-{year}{month:02d}{day:02d}{num:03d}.xml"
)

# Organismos relevantes que justifican descargar el PDF de la disposición
# para buscar la especialidad en el cuerpo del documento (minúsculas sin tildes).
# Ampliado para cubrir empresas públicas con servicio de prevención propio
# (FNMT, EMT, Canal de Isabel II, Metro Madrid) y ayuntamientos grandes de
# la Comunidad de Madrid donde puede haber Enfermería del Trabajo.
HEALTH_ORGS = [
    # Sanidad / SERMAS
    "consejeria de sanidad",
    "sermas",
    "servicio madrileno de salud",
    "hospital",
    "gerencia",
    "agencia sanitaria",
    # Empresas públicas con servicio de prevención propio
    "canal de isabel",
    "metro de madrid",
    "casa de la moneda",
    "fabrica nacional de moneda",
    "fnmt",
    "empresa municipal de transportes",
    "emt",
    # Grandes ayuntamientos de la Comunidad de Madrid (>100k hab.)
    "ayuntamiento de mostoles",
    "ayuntamiento de alcala de henares",
    "ayuntamiento de fuenlabrada",
    "ayuntamiento de leganes",
    "ayuntamiento de getafe",
    "ayuntamiento de alcorcon",
    "ayuntamiento de torrejon",
    "ayuntamiento de parla",
    "ayuntamiento de alcobendas",
]

# Palabras en el título que justifican descargar el PDF
PDF_TRIGGER_WORDS = [
    "concurso de meritos",
    "proceso selectivo",
    "convocatoria proceso selectivo",
    "convocatoria",
    "bolsa de empleo",
]

TITLE_FAST_KEYWORDS = ["enfermer", "salud laboral", "prevencion de riesgos"]


class BOCMSource(Source):
    name = "bocm"
    probe_url = BOCM_ULTIMO  # /ultimo-bocm: la portada del último boletín

    def fetch(self, since_date: date) -> list[RawItem]:
        items: list[RawItem] = []
        for delta in range((date.today() - since_date).days + 1):
            target = since_date + timedelta(days=delta)
            if target.weekday() >= 5:
                continue
            try:
                items.extend(self._fetch_day(target))
            except Exception as exc:
                logger.warning("BOCM %s error: %s", target, exc)
                self.last_errors.append(f"{target}: {exc}")
        return items

    def _fetch_day(self, target: date) -> list[RawItem]:
        xml_url = self._find_xml_url(target)
        if not xml_url:
            logger.info("BOCM: sin edición para %s", target)
            return []
        return self._parse_xml(xml_url, target)

    def _find_xml_url(self, target: date) -> str | None:
        """
        Busca la URL del XML del BOCM para una fecha dada.
        Para la fecha de hoy usa /ultimo-bocm; para fechas anteriores prueba
        números de edición conocidos usando la URL estructurada.
        """
        from bs4 import BeautifulSoup

        today = date.today()
        if target == today or target == today - timedelta(days=1):
            # Scrape la portada para obtener URL XML del día actual o ayer
            resp = requests.get(
                BOCM_ULTIMO, headers=self._default_headers(), timeout=20
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if ".xml" in href.lower() and "BOCM-" in href:
                    full_url = href if href.startswith("http") else BOCM_HOME + href
                    # Verificar que la fecha del XML coincide con target
                    if target.strftime("%Y%m%d") in href:
                        return full_url
            # Alternativa: buscar en el texto del enlace el número de edición
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if ".xml" in href.lower():
                    full_url = href if href.startswith("http") else BOCM_HOME + href
                    return full_url
        else:
            # Para fechas anteriores: construir URL probando números cerca del estimado
            return self._find_xml_url_by_brute_force(target)
        return None

    def _find_xml_url_by_brute_force(self, target: date) -> str | None:
        """
        El BOCM no tiene API de búsqueda por fecha para ediciones antiguas.
        Estima el número de edición (≈ días laborables desde inicio de año)
        y prueba ±5 números hasta encontrar uno que responda con 200.
        """
        # Estimar número de edición (aprox. 250 ediciones/año)
        day_of_year = target.timetuple().tm_yday
        estimated_num = max(1, int(day_of_year * 250 / 365))

        for candidate in range(
            max(1, estimated_num - 8), estimated_num + 8
        ):
            url = BOCM_XML_PATTERN.format(
                year=target.year,
                month=target.month,
                day=target.day,
                num=candidate,
            )
            try:
                r = requests.head(url, headers=self._default_headers(), timeout=8)
                if r.status_code == 200:
                    return url
            except Exception:
                pass
        return None

    def _parse_xml(self, xml_url: str, target: date) -> list[RawItem]:
        resp = requests.get(xml_url, headers=self._default_headers(), timeout=30)
        resp.raise_for_status()
        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError as exc:
            logger.error("BOCM: error parseando XML %s: %s", xml_url, exc)
            return []

        items: list[RawItem] = []
        seen_ids: set[str] = set()

        for disp in root.iter("disposicion"):
            id_elem = disp.find("identificador")
            if id_elem is None:
                continue
            item_id = id_elem.text or ""
            if item_id in seen_ids:
                continue
            seen_ids.add(item_id)

            titulo_elem = disp.find("titulo")
            titulo = (titulo_elem.text or "").strip() if titulo_elem is not None else ""
            # El título puede tener un encabezado corto antes del '•'
            if "•" in titulo or "\n" in titulo:
                titulo = titulo.replace("•", "\n").split("\n", 1)[-1].strip()

            url_html_elem = disp.find("url_html")
            url_html = (url_html_elem.text or "") if url_html_elem is not None else ""
            url_pdf_elem = disp.find("url_pdf")
            url_pdf = (url_pdf_elem.text or "") if url_pdf_elem is not None else ""

            # Determinar organismo y sección (para decidir si descargar PDF)
            dept_elem = disp.find("../..") or disp.find("..")
            org_name = self._find_organismo(root, item_id)
            seccion_name = self._find_seccion(root, item_id)

            titulo_norm = normalize(titulo)
            has_fast_kw = any(kw in titulo_norm for kw in TITLE_FAST_KEYWORDS)

            pdf_text = ""
            if not has_fast_kw and url_pdf:
                org_norm = normalize(org_name)
                is_health = any(kw in org_norm for kw in HEALTH_ORGS)
                has_trigger = any(kw in titulo_norm for kw in PDF_TRIGGER_WORDS)
                if is_health and has_trigger:
                    try:
                        pdf_text = self._extract_pdf_text(url_pdf, max_pages=None)
                    except Exception as exc:
                        logger.debug("BOCM PDF fetch error %s: %s", url_pdf, exc)

            combined = f"{titulo} {pdf_text}"
            if not any(kw in normalize(combined) for kw in TITLE_FAST_KEYWORDS):
                continue  # No hay nada relevante

            items.append(
                RawItem(
                    source=self.name,
                    url=url_html or url_pdf,
                    title=titulo,
                    date=target,
                    text=pdf_text,
                )
            )

        return items

    def _find_organismo(self, root: ET.Element, item_id: str) -> str:
        """Busca el nombre del organismo para un item_id dado."""
        for org in root.iter("organismo"):
            for disp in org:
                id_e = disp.find("identificador")
                if id_e is not None and id_e.text == item_id:
                    return org.get("nombre", "")
        return ""

    def _find_seccion(self, root: ET.Element, item_id: str) -> str:
        """Busca el nombre de la sección para un item_id dado."""
        for sec in root.iter("seccion"):
            for elem in sec.iter("disposicion"):
                id_e = elem.find("identificador")
                if id_e is not None and id_e.text == item_id:
                    return sec.get("nombre", "")
        return ""

    def _extract_pdf_text(self, pdf_url: str, max_pages: int | None = None) -> str:
        """Descarga el PDF y extrae texto completo (PDFs individuales son ~200-500KB)."""
        import pdfplumber

        resp = requests.get(pdf_url, headers=self._default_headers(), timeout=60)
        resp.raise_for_status()
        with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
            pages = pdf.pages if max_pages is None else pdf.pages[:max_pages]
            text_parts = [t for page in pages if (t := page.extract_text())]
        return " ".join(text_parts)
