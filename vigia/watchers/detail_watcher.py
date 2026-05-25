"""DetailWatcher genérico — vigila páginas de detalle de items "vivos".

Problema que resuelve:
los listing parsers (canal_isabel_ii, universidades_madrid, sap_successfactors,
ciemat, etc.) detectan ALTAS de procesos al ver una fila nueva en su listado.
Pero los UPDATES posteriores del proceso (apertura de plicas, lista provisional
de admitidos, examen, calificaciones) viven en sub-páginas que el listing
parser no mira. Hasta ahora cubríamos este gap caso por caso con hash-watchers
ad-hoc (`cm_ficha_enfermeria`, `isciii`, `canal_isabel_ii_calendario`).

El DetailWatcher generaliza el patrón:

1. Lee de BD todos los items "vivos" (deadline futuro, o sin deadline pero
   descubiertos recientemente).
2. Para cada `(source, url)` único hace GET + extrae texto limpio
   + calcula `sha1(body)[:10]`.
3. Compara contra la fila correspondiente en `detail_snapshots`.
4. Si NO había snapshot previo (primera vez que vemos esta URL): guarda el
   snapshot SIN emitir alerta (modo "seed" implícito). Esto evita un primer
   run que emita decenas de snapshots de procesos ya conocidos.
5. Si había snapshot y el hash difiere: actualiza la fila y emite un
   `RawItem` con `[snapshot <hash>]` en el título — entra al pipeline normal
   (extractor → enricher → notifier).
6. Si el hash coincide: nada.

El `source` del RawItem emitido es el `source` original del item de BD (no
"detail_watcher"). Así el dashboard agrupa los snapshots con su parser de
origen y el usuario reconoce de qué proceso viene la alerta.

Sources excluidos (`EXCLUDED_SOURCES`):
- BOE/BOCM/CODEM: el item ES el detalle, no hay sub-página dinámica que vigilar.
- BOAM/Ayto Madrid/Metro Madrid/Administración GOB: stubs por WAF, GET fallará.
- Hash-watchers dedicados (`cm_ficha_enfermeria`, `isciii`,
  `canal_isabel_ii_calendario`): ya emiten sus propios snapshots con selector
  específico — vigilarlos otra vez aquí duplicaría snapshots ruidosos.
- `datos_madrid`: API CKAN JSON, no HTML.

Coste estimado: ~20-50 URLs vivas × 1 GET (~20-30s adicionales con
ThreadPoolExecutor max_workers=4 + timeout 20s por URL).
"""
from __future__ import annotations

import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional

import requests

from vigia.config import USER_AGENT
from vigia.sources._html import extract_clean_text
from vigia.sources.base import RawItem
from vigia.storage import Storage

logger = logging.getLogger(__name__)

# Cascada genérica de selectores. Acepta páginas Drupal, Liferay, layouts
# clásicos con `<main>` o `<article>`, y portales sin tags semánticos.
DEFAULT_BODY_SELECTORS = (
    "main",
    "article",
    "#main-content",
    "section#content",
    "div#content",
    "body",
)

# Sources cuyo `url` original ya es el detalle (no hay sub-página que
# evolucione), o que sabemos bloqueados por WAF, o que ya tienen
# hash-watcher dedicado.
EXCLUDED_SOURCES = frozenset({
    # item == detalle (no aporta vigilar de nuevo):
    "boe", "bocm", "codem", "datos_madrid",
    # WAF / stubs:
    "boam", "ayuntamiento_madrid", "metro_madrid", "administracion_gob",
    # hash-watchers dedicados (ya emiten sus snapshots):
    "cm_ficha_enfermeria", "isciii", "canal_isabel_ii_calendario",
})

FETCH_TIMEOUT = 20
MAX_BODY_BYTES = 16 * 1024  # cap defensivo al persistir el body
MAX_WORKERS = 4


@dataclass
class _FetchResult:
    """Resultado de la fase paralela (HTTP + extract + hash). Sin BD."""
    source: str
    url: str
    titulo: str
    body: str
    new_hash: str


class DetailWatcher:
    """Vigila páginas de detalle de items vivos. Ver docstring del módulo."""

    def __init__(
        self,
        storage: Storage,
        excluded_sources: frozenset = EXCLUDED_SOURCES,
        body_selectors: tuple = DEFAULT_BODY_SELECTORS,
        timeout: int = FETCH_TIMEOUT,
        max_workers: int = MAX_WORKERS,
    ) -> None:
        self.storage = storage
        self.excluded_sources = excluded_sources
        self.body_selectors = body_selectors
        self.timeout = timeout
        self.max_workers = max_workers
        self.last_errors: list[str] = []

    def run(self) -> list[RawItem]:
        """Punto de entrada — devuelve RawItems para inyectar en el pipeline.

        Dos fases:
          1. **Paralela** (`_fetch_and_hash`): GET + body limpio + sha1.
             Sin acceso a Storage. ThreadPoolExecutor seguro.
          2. **Secuencial** (`_compare_and_emit`): compara con
             `detail_snapshots`, upsert si difiere, emite RawItem.
             Sólo el thread principal toca la conexión SQLite — evita
             el error "SQLite objects can only be used in the thread
             they were created in".
        """
        targets = self.storage.iter_live_items_for_detail_watch(
            excluded_sources=self.excluded_sources,
        )
        if not targets:
            logger.info("DetailWatcher: 0 items vivos para vigilar")
            return []

        logger.info("DetailWatcher: %d URLs a vigilar", len(targets))

        # Fase 1: fetch paralelo (sin BD).
        fetched: list[_FetchResult] = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {
                pool.submit(self._fetch_and_hash, source, url, titulo):
                    (source, url)
                for source, url, titulo in targets
            }
            for fut in as_completed(futures):
                source, url = futures[fut]
                try:
                    result = fut.result()
                    if result is not None:
                        fetched.append(result)
                except Exception as exc:
                    msg = f"{source} {url}: {exc}"
                    logger.warning("DetailWatcher inesperado: %s", msg)
                    self.last_errors.append(msg)

        # Fase 2: compare + upsert + emit (secuencial, BD).
        new_raw_items: list[RawItem] = []
        for fr in fetched:
            raw = self._compare_and_emit(fr)
            if raw is not None:
                new_raw_items.append(raw)

        logger.info(
            "DetailWatcher: %d snapshots nuevos emitidos, %d errores",
            len(new_raw_items), len(self.last_errors),
        )
        return new_raw_items

    def _fetch_and_hash(
        self, source: str, url: str, titulo: str
    ) -> Optional[_FetchResult]:
        """Paralelizable: GET + body limpio + sha1. SIN acceso a Storage.

        Registra fallos en `last_errors` (la lista no necesita
        sincronización porque sólo se hacen `append`, atómicos en CPython
        bajo el GIL).
        """
        try:
            resp = requests.get(
                url,
                headers={"User-Agent": USER_AGENT},
                timeout=self.timeout,
            )
            resp.raise_for_status()
        except Exception as exc:
            msg = f"{source} {url}: {exc}"
            logger.warning("DetailWatcher GET: %s", msg)
            self.last_errors.append(msg)
            return None

        body = extract_clean_text(
            resp.text, target_selectors=self.body_selectors
        )
        if not body.strip():
            msg = f"{source} {url}: cuerpo vacío tras limpieza"
            logger.warning("DetailWatcher body: %s", msg)
            self.last_errors.append(msg)
            return None

        # Cap defensivo: 16 KB es suficiente para todos los hash-watchers
        # actuales (cm_ficha 3.5 KB, isciii ~10 KB, calendario 167 bytes).
        # Si una URL real se trunca, queda log para reevaluar.
        if len(body.encode("utf-8")) > MAX_BODY_BYTES:
            logger.info(
                "DetailWatcher: body de %s excede %d bytes, truncando",
                url, MAX_BODY_BYTES,
            )
            body = body.encode("utf-8")[:MAX_BODY_BYTES].decode(
                "utf-8", errors="ignore"
            )

        new_hash = hashlib.sha1(body.encode("utf-8")).hexdigest()[:10]
        return _FetchResult(
            source=source, url=url, titulo=titulo,
            body=body, new_hash=new_hash,
        )

    def _compare_and_emit(self, fr: _FetchResult) -> Optional[RawItem]:
        """Secuencial: usa Storage. Devuelve RawItem si hay snapshot nuevo
        a notificar, `None` si no hay cambio o era seed."""
        prev = self.storage.get_detail_snapshot(fr.url)
        now_iso = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

        if prev is None:
            # Seed implícito: primera vez que vemos esta URL. Guardamos
            # el snapshot pero no alertamos — el usuario ya conocía este
            # proceso vía su parser original.
            self.storage.upsert_detail_snapshot(fr.url, fr.new_hash, fr.body, now_iso)
            logger.debug("DetailWatcher seed: %s [%s]", fr.url, fr.new_hash)
            return None

        prev_hash = prev[0]
        if prev_hash == fr.new_hash:
            return None  # sin cambios

        # Cambio detectado: persistimos y emitimos.
        self.storage.upsert_detail_snapshot(fr.url, fr.new_hash, fr.body, now_iso)
        logger.info(
            "DetailWatcher snapshot %s → %s en %s",
            prev_hash, fr.new_hash, fr.url,
        )

        # Título: reutiliza el del item original (truncado) para que el
        # usuario reconozca el proceso, más el marcador [snapshot XXX].
        # El extractor matchea sobre normalize(title + text), así que si
        # el título original incluye "Enfermería del Trabajo" — que es la
        # razón por la que este item estaba en BD — el snapshot pasará.
        snapshot_title = self._build_snapshot_title(fr.titulo, fr.new_hash)

        return RawItem(
            source=fr.source,  # source original del item, no "detail_watcher"
            url=fr.url,
            title=snapshot_title,
            date=date.today(),
            text=fr.body,
            extra={"detected_by": "detail_watcher", "previous_hash": prev_hash},
        )

    @staticmethod
    def _build_snapshot_title(original_title: str, new_hash: str) -> str:
        # Limpia un eventual `[snapshot XXX]` previo del título (si el item
        # original venía de otro hash-watcher) para no acumular marcadores.
        import re
        cleaned = re.sub(r"\s*\[snapshot [0-9a-f]+\]\s*$", "", original_title)
        # Cap a 150 chars para no inflar el title (Telegram tiene su propio
        # límite, y los snapshots de items con título largo quedaban ilegibles).
        cleaned = cleaned[:150].rstrip()
        return f"{cleaned} [snapshot {new_hash}]"
