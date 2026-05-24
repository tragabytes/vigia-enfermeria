"""
Fuente Ayuntamiento de Las Rozas — portal Convocatorias-en-plazo.

URL: https://www.lasrozas.es/el-ayuntamiento/Convocatorias-en-plazo
HTTP 200, server-side rendered (CMS propio, sin WAF detectable).

Ventaja sobre la cobertura indirecta vía BOCM: el listado SOLO expone
procesos con plazo abierto (filtrado por el propio ayuntamiento), así
que detectamos antes (sin esperar a la publicación oficial) y con la
garantía de plazo vivo. BOCM, en cambio, publica sumarios diarios y
puede listar aperturas pasadas o avisos sin plazo activo.

Estructura HTML:

  <table>
    <tbody>
      <tr>
        <td>{expediente}</td>            <!-- col 1, con <a> al detalle -->
        <td>{título}</td>                <!-- col 2 -->
        <td>{plazo}</td>                 <!-- col 3: "Desde el ... hasta el ..." -->
        <td>{subgrupo}</td>              <!-- col 4 -->
        <td>{turno}</td>                 <!-- col 5 -->
        <td>{plazas}</td>                <!-- col 6 -->
        <td>{tipo}</td>                  <!-- col 7 -->
        <td>{estado}</td>                <!-- col 8 -->
        <td>{enlaces a bases}</td>       <!-- col 9 -->
      </tr>
    </tbody>
  </table>

Hoy (2026-05-24) el listado contiene 1 proceso vivo: "Técnico/a de
Emergencias Sanitarias" (PI-02/2025) — no es Enfermería del Trabajo y el
filtro fast-keyword lo descarta. El parser está listo para cuando aparezca
una plaza de Enfermería en el portal.
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import date
from typing import Optional
from urllib.parse import urljoin

import requests

from vigia.config import FAST_KEYWORDS, normalize
from vigia.sources.base import RawItem, Source

logger = logging.getLogger(__name__)

LAS_ROZAS_LISTADO_URL = "https://www.lasrozas.es/el-ayuntamiento/Convocatorias-en-plazo"
FETCH_TIMEOUT = 30

# Meses en castellano para "Desde el 23 de junio hasta el 18 de julio de 2025"
_MESES_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}

# Apertura del plazo, formato pleno: "Desde el DD de mes de YYYY hasta...".
_PLAZO_DESDE_CON_ANO_RE = re.compile(
    r"desde\s+el\s+(\d{1,2})\s+de\s+([a-záéíóú]+)\s+de\s+(\d{4})",
    re.IGNORECASE,
)
# Apertura sin año (formato real más frecuente del portal):
# "Desde el 23 de junio hasta el 18 de julio de 2025" — el año está al final
# del "hasta el ..."; lo tomamos prestado para el mes de apertura.
_PLAZO_DESDE_SIN_ANO_RE = re.compile(
    r"desde\s+el\s+(\d{1,2})\s+de\s+([a-záéíóú]+)"
    r"\s+hasta\s+el\s+\d{1,2}\s+de\s+[a-záéíóú]+\s+de\s+(\d{4})",
    re.IGNORECASE,
)
# Fallback final: cierre del plazo. "hasta el DD de mes de YYYY".
_PLAZO_HASTA_RE = re.compile(
    r"hasta\s+el\s+(\d{1,2})\s+de\s+([a-záéíóú]+)\s+de\s+(\d{4})",
    re.IGNORECASE,
)


class LasRozasSource(Source):
    name = "las_rozas"
    probe_url = LAS_ROZAS_LISTADO_URL

    def fetch(self, since_date: date) -> list[RawItem]:
        from bs4 import BeautifulSoup

        try:
            resp = requests.get(
                LAS_ROZAS_LISTADO_URL,
                headers=self._default_headers(),
                timeout=FETCH_TIMEOUT,
            )
            resp.raise_for_status()
        except Exception as exc:
            logger.warning("Las Rozas listado error: %s", exc)
            self.last_errors.append(str(exc))
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        items: list[RawItem] = []
        seen_urls: set[str] = set()

        for row in soup.select("table tbody tr"):
            cells = row.find_all("td")
            if len(cells) < 3:
                continue  # cabecera (<th>) o fila vacía

            title = cells[1].get_text(" ", strip=True)
            if not title:
                continue

            # Filtro fast-keyword sobre el texto COMPLETO de la fila — el
            # título a veces lleva la categoría general ("Técnico/a Medio")
            # y la especialidad ("Enfermería del Trabajo") aparece en otra
            # celda (subgrupo, observaciones). Buscamos en toda la fila.
            row_text = row.get_text(" ", strip=True)
            if not any(kw in normalize(row_text) for kw in FAST_KEYWORDS):
                continue

            # URL: la primera celda suele contener el <a> al detalle del
            # expediente. Si no, generamos URL sintética estilo UAM para
            # tener id estable.
            anchor = row.find("a", href=True)
            if anchor:
                url = urljoin(LAS_ROZAS_LISTADO_URL, anchor["href"])
            else:
                digest = hashlib.sha1(title.encode("utf-8")).hexdigest()[:12]
                url = f"{LAS_ROZAS_LISTADO_URL}#{digest}"

            if url in seen_urls:
                continue
            seen_urls.add(url)

            # Plazo: primero en la celda 2 (suele estar ahí en fase de
            # apertura). Si el item está en fase post-apertura (admitidos,
            # alegaciones, nombramiento del tribunal…) la celda 2 ya no
            # tiene fechas — buscamos en toda la fila como fallback.
            plazo_text = cells[2].get_text(" ", strip=True)
            pub_date = _try_parse_pub_date(plazo_text)
            if pub_date is None:
                pub_date = _try_parse_pub_date(row_text)
            if pub_date is None:
                pub_date = date.today()

            if pub_date < since_date:
                continue

            items.append(RawItem(
                source=self.name,
                url=url,
                title=title,
                date=pub_date,
                text=row_text,
            ))
            logger.info("Las Rozas match: %s", title[:90])

        logger.info("Las Rozas: %d items relevantes", len(items))
        return items


def _try_parse_pub_date(plazo_text: str) -> Optional[date]:
    """Intenta extraer fecha de apertura del plazo. Devuelve None si no.

    Cascada: "Desde el DD de mes de YYYY" (apertura con año explícito) →
    "Desde el DD de mes hasta ... de YYYY" (apertura sin año, año tomado
    del cierre) → "hasta el ..." (solo cierre, aproximación).
    """
    for regex in (
        _PLAZO_DESDE_CON_ANO_RE,
        _PLAZO_DESDE_SIN_ANO_RE,
        _PLAZO_HASTA_RE,
    ):
        m = regex.search(plazo_text)
        if not m:
            continue
        mes = _MESES_ES.get(m.group(2).lower())
        if not mes:
            continue
        try:
            return date(int(m.group(3)), mes, int(m.group(1)))
        except ValueError:
            continue
    return None
