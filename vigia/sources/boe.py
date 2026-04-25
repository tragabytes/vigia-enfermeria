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
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import requests

from vigia.config import normalize
from vigia.sources.base import RawItem, Source

logger = logging.getLogger(__name__)

BOE_SUMARIO_URL = "https://boe.es/datosabiertos/api/boe/sumario/{fecha}"

# Secciones que pueden contener convocatorias de oposiciones/concursos
SECTIONS_TO_FETCH_BODY = {"2B", "2A", "3"}

# Departamentos de administración local o sanitaria (en minúsculas, sin tildes)
DEPT_KEYWORDS_FOR_BODY = [
    "administracion local",
    "comunidades autonomas",
    "consejeria de sanidad",
    "sermas",
    "ciemat",
    "canal de isabel",
    "metro de madrid",
    "ministerio de sanidad",
    "agencia sanitaria",
    "mutua",
    "prevencion",
]

# Para el match rápido en título antes de descargar body
TITLE_FAST_KEYWORDS = ["enfermer", "salud laboral", "prevencion de riesgos"]


class BOESource(Source):
    name = "boe"

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
        if should_fetch_body:
            try:
                body_text = self._fetch_html_text(url_html)
            except Exception as exc:
                logger.debug("BOE body fetch error %s: %s", url_html, exc)

        combined_text = f"{titulo} {body_text}"
        # Solo crear el item si hay algo relevante (título o body con fast keyword)
        if not has_fast_kw and not any(kw in normalize(combined_text) for kw in TITLE_FAST_KEYWORDS):
            return None

        return RawItem(
            source=self.name,
            url=url_html,
            title=titulo,
            date=target,
            text=body_text,
        )

    def _fetch_html_text(self, url: str) -> str:
        """Descarga el HTML de un ítem BOE y extrae el texto plano."""
        from bs4 import BeautifulSoup

        resp = requests.get(url, headers=self._default_headers(), timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        # El contenido del BOE está en div#textoxslt o div.diari-boe
        content = (
            soup.find("div", id="textoxslt")
            or soup.find("div", class_="diari-boe")
            or soup.find("div", id="texto")
            or soup.body
        )
        return content.get_text(" ", strip=True) if content else ""
