"""
Fuente datos.madrid.es: portal de datos abiertos del Ayuntamiento de Madrid.

Sustituye parcialmente la cobertura perdida de `boam.py` y
`ayuntamiento_madrid.py` (geo-bloqueados desde GitHub Actions): el dominio
`datos.madrid.es` admite IPs no españolas y expone datasets estructurados
mediante una API CKAN estándar (`/api/3/action/package_show?id=...`).

Datasets monitorizados (validado 2026-04-25):
  1. OEP del Ayuntamiento de Madrid y organismos autónomos (300701).
     CSV histórico desde 2018, ya contiene "enfermero/a del trabajo" 2025
     (6 plazas turno libre).
  2. Procesos selectivos de estabilización (300687). CSV con categorías
     incluidas en la convocatoria excepcional de estabilización.

Granularidad: cada fila relevante del CSV se convierte en un RawItem.
El título incluye una marca del dataset para que distintos años/periodos
no colisionen al deduplicar (hash = source + url + titulo).

Trade-off respecto a BOAM: aquí captamos OEPs y plantilla (decisiones
agregadas que se publican antes que cada convocatoria concreta) pero no
las disposiciones diarias del boletín. Para esas, la cobertura cae en
BOE 2B (Administración Local).

NOTA sobre la RPT (906052): se valoró incluir la Relación de Puestos de
Trabajo, pero genera ruido — son ~300 filas con nombres de unidades
organizativas y puestos vigentes, no convocatorias. Se descartó. Si en
el futuro hace falta detectar cambios estructurales (nuevo puesto, plaza
vacante), se puede reactivar añadiendo el id 906052 al listado y
adaptando la lógica para diferenciar.
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import date

import requests

from vigia.config import normalize
from vigia.sources.base import RawItem, Source

logger = logging.getLogger(__name__)

CKAN_API = "https://datos.madrid.es/api/3/action/package_show?id={ds_id}"

# (id_dataset, etiqueta_corta) — la etiqueta se incluye en el title del
# RawItem para que los hits de distintos datasets no colisionen.
DATASETS: list[tuple[str, str]] = [
    ("300701-0-empleo-oep", "OEP"),
    ("300687-0-plantilla-estabilizacion", "Estabilización"),
    # RPT excluida: ver explicación en el docstring del módulo.
]

FAST_KEYWORDS = ["enfermer", "salud laboral", "prevencion de riesgos"]
HTTP_TIMEOUT = 60


class DatosMadridSource(Source):
    name = "datos_madrid"
    # Probe contra la API CKAN: si responde, todos los datasets son
    # alcanzables (mismo backend).
    probe_url = "https://datos.madrid.es/api/3/action/status_show"

    def fetch(self, since_date: date) -> list[RawItem]:
        all_items: list[RawItem] = []
        for ds_id, label in DATASETS:
            all_items.extend(self._fetch_dataset(ds_id, label))
        logger.info(
            "datos.madrid.es: %d items relevantes encontrados (todos los datasets)",
            len(all_items),
        )
        return all_items

    def _fetch_dataset(self, ds_id: str, label: str) -> list[RawItem]:
        # 1. Pedir metadata del dataset a la API CKAN para obtener la URL del CSV.
        try:
            meta_resp = requests.get(
                CKAN_API.format(ds_id=ds_id),
                headers=self._default_headers(),
                timeout=HTTP_TIMEOUT,
            )
            meta_resp.raise_for_status()
        except Exception as exc:
            logger.warning("datos.madrid [%s] error metadata: %s", label, exc)
            self.last_errors.append(f"{label} metadata: {exc}")
            return []

        try:
            meta = meta_resp.json()["result"]
        except (KeyError, ValueError) as exc:
            logger.warning("datos.madrid [%s] respuesta inesperada: %s", label, exc)
            self.last_errors.append(f"{label} json: {exc}")
            return []

        csv_url = self._pick_csv_url(meta)
        if not csv_url:
            logger.warning("datos.madrid [%s] sin recurso CSV en %s", label, ds_id)
            self.last_errors.append(f"{label}: sin CSV en el dataset")
            return []

        # 2. Descargar el CSV y filtrar filas relevantes.
        try:
            csv_resp = requests.get(
                csv_url, headers=self._default_headers(), timeout=HTTP_TIMEOUT
            )
            csv_resp.raise_for_status()
        except Exception as exc:
            logger.warning("datos.madrid [%s] error CSV: %s", label, exc)
            self.last_errors.append(f"{label} CSV: {exc}")
            return []

        text = self._decode(csv_resp.content)
        items = self._parse_csv(text, label, csv_url, meta)
        logger.info("datos.madrid [%s]: %d items relevantes", label, len(items))
        return items

    def _pick_csv_url(self, meta: dict) -> str | None:
        """Devuelve la URL del primer recurso CSV del dataset, o None si no hay."""
        for res in meta.get("resources", []):
            if (res.get("format") or "").upper() == "CSV":
                return res.get("url")
        return None

    def _decode(self, content: bytes) -> str:
        """CSVs de datos.madrid.es vienen en UTF-8 o Latin-1; intentamos ambos."""
        for enc in ("utf-8", "latin-1", "cp1252"):
            try:
                return content.decode(enc)
            except UnicodeDecodeError:
                continue
        return content.decode("utf-8", errors="replace")

    def _parse_csv(
        self, text: str, label: str, csv_url: str, meta: dict
    ) -> list[RawItem]:
        """
        Lee el CSV línea a línea y crea un RawItem por cada fila que contenga
        algún FAST_KEYWORD en cualquiera de sus columnas.
        """
        items: list[RawItem] = []
        seen_titles: set[str] = set()  # dedup interno por dataset

        # Detectar separador (datos.madrid usa ';' generalmente, pero por si acaso)
        sample = text[:4096]
        delim = ";" if sample.count(";") > sample.count(",") else ","

        reader = csv.reader(io.StringIO(text), delimiter=delim)
        try:
            header = next(reader)
        except StopIteration:
            return items

        # Fecha aproximada del dataset: usar metadata_modified
        ds_date = self._parse_meta_date(meta)

        for row in reader:
            if not row:
                continue
            row_text = " ".join(c for c in row if c).strip()
            if not row_text:
                continue
            row_norm = normalize(row_text)
            if not any(kw in row_norm for kw in FAST_KEYWORDS):
                continue

            # Construir un title legible: extraer las celdas no vacías más
            # representativas (las que tienen texto, descartando códigos
            # numéricos puros y fechas).
            relevant = [
                c.strip() for c in row
                if c and c.strip() and not _is_just_id_or_date(c)
            ]
            content = " · ".join(relevant)[:300]
            title = f"[{label}] {content}"

            if title in seen_titles:
                continue
            seen_titles.add(title)

            items.append(
                RawItem(
                    source=self.name,
                    url=csv_url,
                    title=title,
                    date=ds_date,
                    text="",
                    extra={"dataset": label, "row": row[:10]},
                )
            )

        return items

    def _parse_meta_date(self, meta: dict) -> date:
        """Devuelve metadata_modified como date o today si no se puede parsear."""
        raw = (meta.get("metadata_modified") or "")[:10]
        try:
            return date.fromisoformat(raw)
        except (ValueError, TypeError):
            return date.today()


def _is_just_id_or_date(cell: str) -> bool:
    """Heurística: descarta celdas que son solo números, fechas o GUIDs."""
    s = cell.strip()
    if not s:
        return True
    # solo dígitos / códigos numéricos largos
    if s.replace(".", "").replace("-", "").replace("/", "").isdigit():
        return True
    # fechas tipo 04/10/2023 o 2023-10-04
    if len(s) == 10 and (s[4] == "-" or s[2] == "/"):
        return True
    return False
