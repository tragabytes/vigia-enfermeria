"""
Fuente BOE: API oficial de sumarios diarios.

Endpoint: GET https://boe.es/datosabiertos/api/boe/sumario/YYYYMMDD
          Accept: application/json

Hallazgo de investigación:
  Los títulos del sumario (sección 2B) suelen decir "referente a la convocatoria
  para proveer varias plazas" sin mencionar la especialidad. El keyword
  "Enfermería del Trabajo" aparece en el CUERPO HTML del ítem. Por eso:
  - Se comprueban primero los títulos
  - Para items de sección 2B/2A sin match en título se descarga el HTML
    si procede de ADMINISTRACIÓN LOCAL o entidades sanitarias
  - Para convocatorias OPI conjuntas (Ministerio de Ciencia + CIEMAT/IAC/INIA…)
    el HTML del item BOE no lleva la lista de plazas — vive como anexo PDF.
    Si tras leer el HTML aún no hay match pero el departamento es
    relevante, descargamos hasta `MAX_PDFS_PER_ITEM` PDFs anexos del
    propio dominio BOE para inspeccionarlos.
"""
from __future__ import annotations

import io
import logging
import re
from datetime import date, timedelta
from urllib.parse import urljoin, urlparse

import requests

from vigia.config import normalize
from vigia.sources.base import RawItem, Source

logger = logging.getLogger(__name__)

# Whitelist anti-SSRF para los PDFs anexos. Solo dominio BOE: los anexos
# de convocatorias estatales se publican ahí. Si un día queremos seguir
# enlaces a PDFs de bases técnicas en otros dominios oficiales (como hace
# `enricher._run_fetch_url`), añadirlos aquí explícitamente.
PDF_HOST_WHITELIST: set[str] = {"boe.es", "www.boe.es"}
MAX_PDFS_PER_ITEM = 3
MAX_PDF_PAGES = 30
MAX_PDF_BYTES = 5 * 1024 * 1024
PDF_FETCH_TIMEOUT = 20

# id BOE de un item ("BOE-A-2026-795"). Lo usamos para excluir el PDF
# "Versión PDF del item" (mismo contenido que el HTML, no aporta).
_BOE_ID_RE = re.compile(r"BOE-[A-Z]-\d{4}-\d+")

BOE_SUMARIO_URL = "https://boe.es/datosabiertos/api/boe/sumario/{fecha}"

# Secciones que pueden contener convocatorias de oposiciones/concursos
SECTIONS_TO_FETCH_BODY = {"2B", "2A", "3"}

# Departamentos relevantes (minúsculas, sin tildes) que justifican descargar
# el HTML del cuerpo para buscar la especialidad. La cobertura de
# "administracion local" ya engloba los ayuntamientos grandes de Madrid
# (Móstoles, Alcalá, Fuenlabrada…). Se añaden empresas públicas con servicio
# de prevención propio que pueden no caer bajo esa etiqueta.
DEPT_KEYWORDS_FOR_BODY = [
    "administracion local",
    "comunidades autonomas",
    "consejeria de sanidad",
    "sermas",
    "ciemat",
    "isciii",
    "instituto de salud carlos iii",
    "canal de isabel",
    "metro de madrid",
    "ministerio de sanidad",
    "agencia sanitaria",
    "mutua",
    "prevencion",
    # Empresas públicas con servicio de prevención propio
    "fnmt",
    "casa de la moneda",
    "fabrica nacional de moneda",
    "emt",
    "empresa municipal de transportes",
    # Empresas públicas estatales con servicio médico/SP propio
    "rtve",
    "radio y television espanola",
    "renfe",
    "renfe operadora",
    "adif",
    "administrador de infraestructuras ferroviarias",
    "navantia",
    "aena",
    "correos",
    "sociedad estatal correos",
    "paradores",
    "paradores de turismo",
    "loterias y apuestas",
    # Ministerios estatales con servicio de prevención de riesgos laborales propio.
    # Sus convocatorias suelen englobar varias especialidades de "personal
    # facultativo y técnico" sin mencionar "enfermería" en el título — por eso
    # necesitamos descargar el cuerpo HTML para inspeccionarlas.
    # Ej. real perdido (BOE-A-2026-795, Policía Nacional, 14/01/2026) que
    # listaba 5 plazas T012-T016 de Enfermería en PRL.
    "ministerio del interior",
    "direccion general de la policia",
    "policia nacional",
    "cuerpo nacional de policia",
    "guardia civil",
    "direccion general de la guardia civil",
    "instituciones penitenciarias",
    "secretaria general de instituciones penitenciarias",
    "ministerio de defensa",
    "subsecretaria de defensa",
    "ministerio de ciencia",
    "ministerio de ciencia innovacion y universidades",
    "ministerio de transportes",
    "ministerio para la transicion ecologica",
    "ministerio de transicion ecologica",
    "ministerio de hacienda",
    "ministerio de inclusion",
    "ministerio de trabajo y economia social",
    "ministerio de la presidencia",
    "ministerio de agricultura",
    "ministerio de cultura",
    "ministerio de educacion",
    "ministerio de justicia",
    "ministerio de asuntos exteriores",
    "ministerio de igualdad",
    "ministerio de derechos sociales",
    "ministerio de industria",
    "ministerio de economia",
    "ministerio de vivienda",
    "ministerio de juventud",
]

# Para el match rápido en título antes de descargar body
TITLE_FAST_KEYWORDS = ["enfermer", "salud laboral", "prevencion de riesgos"]


class BOESource(Source):
    name = "boe"
    # Probe: la home del API de datos abiertos. No depende de fecha.
    probe_url = "https://boe.es/datosabiertos/"

    def fetch(self, since_date: date) -> list[RawItem]:
        items: list[RawItem] = []
        for delta in range((date.today() - since_date).days + 1):
            target = since_date + timedelta(days=delta)
            if target.weekday() >= 5:  # no hay BOE los sábados y domingos normalmente
                continue
            try:
                items.extend(self._fetch_day(target))
            except Exception as exc:
                logger.warning("BOE %s error: %s", target, exc)
                self.last_errors.append(f"{target}: {exc}")
        return items

    def _fetch_day(self, target: date) -> list[RawItem]:
        url = BOE_SUMARIO_URL.format(fecha=target.strftime("%Y%m%d"))
        resp = requests.get(
            url,
            headers={**self._default_headers(), "Accept": "application/json"},
            timeout=20,
        )
        if resp.status_code == 404:
            return []  # día sin BOE (festivo nacional)
        resp.raise_for_status()
        data = resp.json()
        return self._parse_sumario(data, target)

    def _parse_sumario(self, data: dict, target: date) -> list[RawItem]:
        items: list[RawItem] = []
        try:
            diario_list = data["data"]["sumario"]["diario"]
        except (KeyError, TypeError):
            logger.warning("BOE: estructura inesperada del sumario")
            return items

        if isinstance(diario_list, dict):
            diario_list = [diario_list]

        for diario in diario_list:
            secciones = diario.get("seccion", [])
            if isinstance(secciones, dict):
                secciones = [secciones]
            for sec in secciones:
                sec_code = sec.get("codigo", "")
                depts = sec.get("departamento", [])
                if isinstance(depts, dict):
                    depts = [depts]
                for dept in depts:
                    dept_name = dept.get("nombre", "")
                    raw_items = self._extract_items_from_node(dept)
                    for raw in raw_items:
                        titulo = raw.get("titulo", "")
                        url_html = raw.get("url_html", "") or raw.get("url_xml", "")
                        if not url_html:
                            continue
                        item = self._build_raw_item(
                            titulo, url_html, target, sec_code, dept_name
                        )
                        if item:
                            items.append(item)
        return items

    def _extract_items_from_node(self, node: dict) -> list[dict]:
        """Extrae items directos y de epígrafes de un nodo (departamento o epígrafe)."""
        results = []
        raw = node.get("item")
        if raw:
            if isinstance(raw, dict):
                results.append(raw)
            else:
                results.extend(raw)
        epigs = node.get("epigrafe", [])
        if isinstance(epigs, dict):
            epigs = [epigs]
        for epig in epigs:
            results.extend(self._extract_items_from_node(epig))
        return results

    def _build_raw_item(
        self,
        titulo: str,
        url_html: str,
        target: date,
        sec_code: str,
        dept_name: str,
    ) -> RawItem | None:
        """
        Construye un RawItem con el texto del body HTML si es necesario.
        Solo descarga el body para secciones 2A/2B/3 y departamentos relevantes.

        Si tras leer el HTML aún no hay match pero el departamento es
        relevante, intenta descargar hasta `MAX_PDFS_PER_ITEM` PDFs anexos
        enlazados desde el body. Esto cubre convocatorias OPI conjuntas
        del Ministerio de Ciencia (CIEMAT, IAC, INIA…) donde la lista de
        plazas vive en un anexo separado, y procesos genéricos de Defensa
        / Mutuas con bases técnicas anexas.
        """
        titulo_norm = normalize(titulo)

        # Check rápido: ¿el título ya contiene algo relevante?
        has_fast_kw = any(kw in titulo_norm for kw in TITLE_FAST_KEYWORDS)

        # ¿Vale la pena descargar el body?
        dept_norm = normalize(dept_name)
        is_relevant_dept = any(kw in dept_norm for kw in DEPT_KEYWORDS_FOR_BODY)
        should_fetch_body = (
            sec_code in SECTIONS_TO_FETCH_BODY
            and (is_relevant_dept or has_fast_kw)
            and url_html
        )

        body_text = ""
        pdf_text = ""
        pdf_links: list[str] = []
        if should_fetch_body:
            try:
                body_text, pdf_links = self._fetch_html_with_pdf_links(url_html)
            except Exception as exc:
                logger.debug("BOE body fetch error %s: %s", url_html, exc)

        # Si el HTML del item no ha matcheado todavía Y el departamento es
        # relevante, descargamos los PDFs anexos. Limitamos a items con
        # departamento en la whitelist (no por has_fast_kw alone) para no
        # disparar fetch de PDF para items con un "enfermería" tangencial
        # en el título de un dept totalmente no-sanitario.
        if (
            is_relevant_dept
            and pdf_links
            and not any(kw in normalize(body_text) for kw in TITLE_FAST_KEYWORDS)
            and not has_fast_kw
        ):
            for pdf_url in pdf_links[:MAX_PDFS_PER_ITEM]:
                try:
                    chunk = self._fetch_pdf_text(pdf_url)
                except Exception as exc:
                    logger.debug("BOE PDF anexo fetch error %s: %s", pdf_url, exc)
                    chunk = ""
                if chunk:
                    pdf_text += "\n\n[ANEXO PDF " + pdf_url + "]\n" + chunk
                    if any(kw in normalize(pdf_text) for kw in TITLE_FAST_KEYWORDS):
                        # Match encontrado en este anexo: paramos para no
                        # descargar el resto. Volumen optimista: una sola
                        # llamada a pdfplumber suele bastar.
                        logger.info(
                            "BOE [%s] match en anexo PDF: %s", titulo[:60], pdf_url,
                        )
                        break

        combined_text = f"{titulo} {body_text} {pdf_text}"
        # Solo crear el item si hay algo relevante (título, body o anexo)
        if not has_fast_kw and not any(kw in normalize(combined_text) for kw in TITLE_FAST_KEYWORDS):
            return None

        # Si hubo match en anexo PDF, lo concatenamos al body para que el
        # extractor + enricher tengan el contexto completo.
        full_text = body_text + pdf_text
        return RawItem(
            source=self.name,
            url=url_html,
            title=titulo,
            date=target,
            text=full_text,
        )

    def _fetch_html_text(self, url: str) -> str:
        """Compat: solo el texto plano del HTML del item BOE."""
        text, _ = self._fetch_html_with_pdf_links(url)
        return text

    def _fetch_html_with_pdf_links(self, url: str) -> tuple[str, list[str]]:
        """Descarga el HTML del ítem BOE y devuelve (texto plano, lista
        de URLs PDF anexas en orden de prioridad).

        La lista excluye el "Versión PDF" del propio item (mismo contenido
        que el HTML, no aporta). Se priorizan enlaces cuyo href o texto
        contenga "anexo" / "bases" / "convocatoria" / "oferta".
        """
        from bs4 import BeautifulSoup

        resp = requests.get(url, headers=self._default_headers(), timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        content = (
            soup.find("div", id="textoxslt")
            or soup.find("div", class_="diari-boe")
            or soup.find("div", id="texto")
            or soup.body
        )
        text = content.get_text(" ", strip=True) if content else ""

        # id del item para excluir su propio PDF.
        m = _BOE_ID_RE.search(url)
        current_id = m.group(0) if m else ""

        pdf_links: list[str] = []
        seen: set[str] = set()
        if content:
            for a in content.find_all("a", href=True):
                full = urljoin(url, a["href"])
                if full in seen:
                    continue
                parsed = urlparse(full)
                host = (parsed.hostname or "").lower()
                if host not in PDF_HOST_WHITELIST:
                    continue
                if not full.lower().endswith(".pdf"):
                    continue
                if current_id and current_id in full:
                    continue   # PDF del mismo item, ya está en el HTML
                seen.add(full)
                pdf_links.append(full)

        # Orden de prioridad: anexo > bases > convocatoria > oferta > resto.
        def priority(u: str) -> int:
            low = u.lower()
            for i, kw in enumerate(("anexo", "bases", "convocatoria", "oferta")):
                if kw in low:
                    return i
            return 99

        pdf_links.sort(key=priority)
        return text, pdf_links

    def _fetch_pdf_text(self, url: str) -> str:
        """Descarga un PDF y devuelve su texto extraído (max 30 páginas).

        El PDF se descarga en streaming hasta `MAX_PDF_BYTES`. pdfplumber
        ya está en requirements.txt (lo usan también `bocm.py` y
        `enricher.py`). Si el PDF está corrupto o cifrado, devuelve string
        vacío y el caller lo trata como "anexo no útil".
        """
        import pdfplumber

        resp = requests.get(
            url,
            headers=self._default_headers(),
            timeout=PDF_FETCH_TIMEOUT,
            stream=True,
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
            logger.debug("BOE PDF parse error %s: %s", url, exc)
            return ""
