"""
Persistencia SQLite con deduplicación por hash(source + url + titulo).

El modelo `Item` arrastra dos generaciones de enriquecimiento:

- v1 (sumario textual)  → solo `summary`, generado por el enricher single-shot.
- v2 (estructurado)     → campos discretos (is_relevant, plazas, deadline,
                          organismo, fase, next_action…) generados por el
                          enricher con tool use sobre la URL real. Permiten
                          filtrar falsos positivos, ordenar por urgencia y
                          dar CTA accionable en Telegram/dashboard.

`enriched_version` indica qué generación tiene un row:
    NULL/0 → sin enriquecer
    1      → solo summary
    2      → estructurado (incluye summary recalculado)

Las migraciones son aditivas (ALTER TABLE ADD COLUMN), idempotentes y no
destructivas: las BDs viejas de la rama `state` se actualizan solas en el
primer run sin perder filas.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)

# Ruta de la BD de estado. Por defecto, junto al repo (comportamiento
# histórico: <repo>/state/seen.db). Cuando el core se instala como paquete,
# `__file__` apunta a site-packages; por eso un bot que consuma el core debe
# fijar VIGIA_STATE_DIR para que su estado viva en su propio cwd/rama state.
_STATE_DIR_ENV = os.environ.get("VIGIA_STATE_DIR")
if _STATE_DIR_ENV:
    DB_PATH = Path(_STATE_DIR_ENV) / "seen.db"
else:
    DB_PATH = Path(__file__).parent.parent / "state" / "seen.db"

# Versión actual del esquema de enriquecimiento. Si subimos esto en el futuro
# (ej. v3 = clustering de procesos relacionados), `iter_items_for_enrichment`
# rebobinará automáticamente lo que esté por debajo.
# v3 (2026-04-26): el extractor ya no trunca raw_text a 2KB y el enricher
# inyecta hasta 12KB en el prompt + system prompt instruye al LLM a llamar
# a fetch_url ante sospecha de truncado.
# v4 (2026-04-26): el enricher inyecta SNIPPETS dirigidos (ventanas de
# 400 chars alrededor de cada keyword strong) en lugar de truncar el inicio.
# Imprescindible para items BOE largos donde el listado de plazas vive a
# partir del char 80k.
# v5 (2026-04-26): `enrich_pending` pre-fetchea el body completo desde la
# URL del item ANTES de pasar al LLM. Sin esto, items reprocesados desde
# BD llegaban con raw_text vacío (no se persiste) y los snippets no
# tenían sobre qué actuar. Cierra el bug definitivamente — Policía
# Nacional tampoco se rescató en v4 por este motivo.
ENRICHMENT_VERSION = 5


@dataclass
class Item:
    """Hallazgo validado por el extractor.

    Viaja entre extractor → enricher → notifier → storage. Los campos de
    enriquecimiento son todos opcionales: si la API key no está configurada
    o el enricher falla, el item sigue navegando por el pipeline sin ellos.
    """
    source: str
    url: str
    titulo: str
    fecha: date
    categoria: str
    id_hash: str = ""
    first_seen_at: datetime = None

    # Enriquecimiento v1 — sumario textual (~200 chars)
    summary: Optional[str] = None

    # Enriquecimiento v2 — campos estructurados extraídos por el LLM con
    # tool use sobre la URL real. Cada campo viene del JSON de salida del
    # enricher v2; ver `vigia/enricher.py` para el schema completo.
    is_relevant: Optional[bool] = None
    relevance_reason: Optional[str] = None
    process_type: Optional[str] = None        # oposicion|bolsa|concurso_traslados|interinaje|temporal|otro
    organismo: Optional[str] = None
    centro: Optional[str] = None
    plazas: Optional[int] = None
    deadline_inscripcion: Optional[str] = None    # YYYY-MM-DD
    fecha_publicacion_oficial: Optional[str] = None
    tasas_eur: Optional[float] = None
    url_bases: Optional[str] = None
    url_inscripcion: Optional[str] = None
    requisitos_clave: Optional[list[str]] = None
    fase: Optional[str] = None                # convocatoria|admitidos_provisional|admitidos_definitivo|examen|calificacion|propuesta_nombramiento|otro
    next_action: Optional[str] = None
    confidence: Optional[float] = None
    enriched_at: Optional[str] = None         # ISO timestamp
    enriched_version: Optional[int] = None    # 1 = string-only, 2 = estructurado

    # Soporte para resumen de diff (Análisis B) — sólo poblado para items
    # snapshot (título matchea `[snapshot ...]`).
    raw_text: Optional[str] = None            # cuerpo limpio, capeado, para comparar con futuras versiones
    change_summary: Optional[str] = None      # frase del diff_summarizer cuando el cambio es sustantivo
    change_substantive: Optional[bool] = None # True = cambio real, False = cosmético (filtra alerta), None = no aplica / primer snapshot

    # Buffer interno para datos efímeros del run (raw_text del extractor,
    # diagnósticos…). No se persiste.
    extra: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id_hash:
            self.id_hash = _make_hash(self.source, self.url, self.titulo)
        if self.first_seen_at is None:
            # `datetime.utcnow()` está deprecated en Python 3.12+. Construimos
            # un naive UTC equivalente para mantener compatibilidad con la
            # columna SQLite (TEXT con ISO sin TZ) y con el resto del código,
            # que espera datetimes naive.
            self.first_seen_at = datetime.now(timezone.utc).replace(tzinfo=None)
        if self.extra is None:
            self.extra = {}


def _make_hash(source: str, url: str, titulo: str) -> str:
    key = f"{source}|{url}|{titulo}".lower().strip()
    return hashlib.sha256(key.encode()).hexdigest()[:16]


# Columnas v2 a añadir si no existen. (nombre_sql, tipo_sql).
_V2_COLUMNS: list[tuple[str, str]] = [
    ("is_relevant",                "INTEGER"),
    ("relevance_reason",           "TEXT"),
    ("process_type",               "TEXT"),
    ("organismo",                  "TEXT"),
    ("centro",                     "TEXT"),
    ("plazas",                     "INTEGER"),
    ("deadline_inscripcion",       "TEXT"),
    ("fecha_publicacion_oficial",  "TEXT"),
    ("tasas_eur",                  "REAL"),
    ("url_bases",                  "TEXT"),
    ("url_inscripcion",            "TEXT"),
    ("requisitos_clave",           "TEXT"),     # JSON
    ("fase",                       "TEXT"),
    ("next_action",                "TEXT"),
    ("confidence",                 "REAL"),
    ("enriched_at",                "TEXT"),
    ("enriched_version",           "INTEGER"),
]


# Columnas para soporte del diff_summarizer (Análisis B). Aditivas e
# idempotentes igual que las anteriores; las BDs legacy se actualizan en
# el primer run sin perder filas.
_DIFF_COLUMNS: list[tuple[str, str]] = [
    ("raw_text",            "TEXT"),    # cuerpo limpio para diff
    ("change_summary",      "TEXT"),    # resumen del cambio
    ("change_substantive",  "INTEGER"), # 0/1, NULL si no se evaluó
]


class Storage:
    def __init__(self, db_path: Optional[Path] = None) -> None:
        # Resolución diferida de DB_PATH: si la usáramos como default del
        # parámetro, Python la captura al definir la clase y monkeypatching
        # `storage.DB_PATH` desde un test no surtiría efecto. Leerla aquí
        # garantiza que cualquier monkeypatch posterior sea respetado.
        self.db_path = db_path if db_path is not None else DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._migrate()

    def _migrate(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id_hash       TEXT PRIMARY KEY,
                source        TEXT NOT NULL,
                url           TEXT NOT NULL,
                titulo        TEXT NOT NULL,
                fecha         TEXT NOT NULL,
                categoria     TEXT NOT NULL,
                first_seen_at TEXT NOT NULL
            )
        """)
        existing_cols = {
            row[1] for row in self._conn.execute("PRAGMA table_info(items)")
        }
        # Migración v1 (idempotente): summary del enricher single-shot.
        if "summary" not in existing_cols:
            self._conn.execute("ALTER TABLE items ADD COLUMN summary TEXT")
            existing_cols.add("summary")
        # Migración v2 (idempotente): campos estructurados del enricher v2.
        for col_name, col_type in _V2_COLUMNS:
            if col_name not in existing_cols:
                self._conn.execute(
                    f"ALTER TABLE items ADD COLUMN {col_name} {col_type}"
                )
        # Migración B (idempotente): soporte para diff_summarizer.
        for col_name, col_type in _DIFF_COLUMNS:
            if col_name not in existing_cols:
                self._conn.execute(
                    f"ALTER TABLE items ADD COLUMN {col_name} {col_type}"
                )
        # Tabla detail_snapshots: estado del DetailWatcher genérico
        # (`vigia/watchers/detail_watcher.py`). Una fila por URL de detalle
        # que vigilamos automáticamente; guarda el último hash y el último
        # cuerpo limpio para detectar cambios y, en futuro, generar diff
        # resumido (Análisis B).
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS detail_snapshots (
                url             TEXT PRIMARY KEY,
                last_hash       TEXT NOT NULL,
                last_body       TEXT NOT NULL,
                last_checked_at TEXT NOT NULL
            )
        """)
        self._conn.commit()

    def is_new(self, item: Item) -> bool:
        """Devuelve True si el ítem no está en la BD."""
        cur = self._conn.execute(
            "SELECT 1 FROM items WHERE id_hash = ?", (item.id_hash,)
        )
        return cur.fetchone() is None

    def save(self, item: Item) -> None:
        """Inserta el ítem; no falla si ya existe (INSERT OR IGNORE).

        Persiste los campos básicos + summary + raw_text. Los campos del
        enricher v2 y de change_* se rellenan después con
        `update_enrichment()` / `update_change_summary()` — se calculan
        tras `filter_new`, no antes.

        `raw_text` SÍ se persiste en save() porque viene poblado desde el
        extractor para items snapshot, y el diff_summarizer (que corre
        después de save() pero antes de enrich) lo necesita disponible
        para futuras iteraciones.
        """
        self._conn.execute(
            """
            INSERT OR IGNORE INTO items
                (id_hash, source, url, titulo, fecha, categoria,
                 first_seen_at, summary, raw_text)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.id_hash,
                item.source,
                item.url,
                item.titulo,
                str(item.fecha),
                item.categoria,
                item.first_seen_at.isoformat(),
                item.summary,
                item.raw_text,
            ),
        )
        self._conn.commit()

    def update_summary(self, item: Item) -> None:
        """Persiste solo el `summary` v1. Se mantiene por compatibilidad
        con el flujo legacy y para entornos donde el enricher v2 no esté
        disponible (sin API key)."""
        if not item.summary:
            return
        self._conn.execute(
            "UPDATE items SET summary = ? WHERE id_hash = ?",
            (item.summary, item.id_hash),
        )
        self._conn.commit()

    def update_enrichment(self, item: Item) -> None:
        """Persiste todos los campos del enricher v2 + el summary.

        Idempotente: vuelve a escribir todos los campos (incluido NULL si
        el LLM no consiguió extraer alguno). Solo se invoca si el item
        salió del enricher con `enriched_version` ya set; si el enricher
        falló por completo, se llama a `update_summary()` o nada.
        """
        if item.enriched_version is None:
            return
        requisitos_json = (
            json.dumps(item.requisitos_clave, ensure_ascii=False)
            if item.requisitos_clave is not None else None
        )
        self._conn.execute(
            """
            UPDATE items SET
                summary = ?,
                is_relevant = ?,
                relevance_reason = ?,
                process_type = ?,
                organismo = ?,
                centro = ?,
                plazas = ?,
                deadline_inscripcion = ?,
                fecha_publicacion_oficial = ?,
                tasas_eur = ?,
                url_bases = ?,
                url_inscripcion = ?,
                requisitos_clave = ?,
                fase = ?,
                next_action = ?,
                confidence = ?,
                enriched_at = ?,
                enriched_version = ?
            WHERE id_hash = ?
            """,
            (
                item.summary,
                None if item.is_relevant is None else int(bool(item.is_relevant)),
                item.relevance_reason,
                item.process_type,
                item.organismo,
                item.centro,
                item.plazas,
                item.deadline_inscripcion,
                item.fecha_publicacion_oficial,
                item.tasas_eur,
                item.url_bases,
                item.url_inscripcion,
                requisitos_json,
                item.fase,
                item.next_action,
                item.confidence,
                item.enriched_at,
                item.enriched_version,
                item.id_hash,
            ),
        )
        self._conn.commit()

    def update_change_summary(self, item: Item) -> None:
        """Persiste `change_summary` y `change_substantive` para un item
        que ha pasado por el `diff_summarizer`.

        Idempotente: se escriben aunque sean NULL. Se invoca tras el
        diff (que vive entre filter_new y enrich), no afecta a los items
        sin `[snapshot ...]` en el título.
        """
        substantive_int = (
            None if item.change_substantive is None
            else int(bool(item.change_substantive))
        )
        self._conn.execute(
            """
            UPDATE items
            SET change_summary = ?, change_substantive = ?
            WHERE id_hash = ?
            """,
            (item.change_summary, substantive_int, item.id_hash),
        )
        self._conn.commit()

    def get_previous_snapshot_raw_text(
        self, source: str, url: str, exclude_id_hash: str
    ) -> Optional[str]:
        """Devuelve el `raw_text` del snapshot anterior para `(source, url)`,
        excluyendo el id_hash actual.

        Los hash-watchers (cm_ficha, isciii, canal_isabel_ii_calendario)
        y el DetailWatcher emiten snapshots sucesivos con el mismo `source`
        y la misma `url`, distinguidos sólo por el `[snapshot XXX]` del
        título — y por tanto por el `id_hash` derivado.

        Devuelve `None` si:
          - No hay snapshot previo (primer snapshot tras feature).
          - El snapshot previo tiene `raw_text` NULL (pre-migración).
        """
        row = self._conn.execute(
            """
            SELECT raw_text FROM items
            WHERE source = ? AND url = ? AND id_hash != ?
            ORDER BY first_seen_at DESC
            LIMIT 1
            """,
            (source, url, exclude_id_hash),
        ).fetchone()
        return row[0] if row and row[0] else None

    def update_categoria(self, id_hash: str, categoria: str) -> None:
        """Cambia la categoría de un item ya guardado. Lo usa la tarea de
        mantenimiento `reclassify_all` cuando se afina CATEGORY_HINTS y
        queremos rebobinar la clasificación de items históricos."""
        self._conn.execute(
            "UPDATE items SET categoria = ? WHERE id_hash = ?",
            (categoria, id_hash),
        )
        self._conn.commit()

    def update_fecha(self, id_hash: str, fecha: date) -> None:
        """Cambia la fecha de publicación de un item ya guardado. Lo usa la
        tarea `recalcular_fechas_comunidad_madrid` para corregir items
        históricos cuyo `pub_date` quedó como `today()` por el bug de regex
        de Comunidad de Madrid (BACKLOG #1, fix 2026-04-28)."""
        self._conn.execute(
            "UPDATE items SET fecha = ? WHERE id_hash = ?",
            (fecha.isoformat(), id_hash),
        )
        self._conn.commit()

    def iter_items_without_summary(self) -> list[Item]:
        """Devuelve los items en BD que aún no tienen summary.

        Útil para el flujo legacy de `enricher.enrich_pending()`. Para el
        backfill v2 usar `iter_items_for_enrichment()`, que devuelve también
        los items con summary v1 (necesitan re-enriquecerse a v2).
        """
        cur = self._conn.execute(
            """
            SELECT id_hash, source, url, titulo, fecha, categoria, first_seen_at
            FROM items
            WHERE summary IS NULL OR summary = ''
            ORDER BY first_seen_at DESC
            """
        )
        return [_row_to_basic_item(r) for r in cur]

    def iter_items_for_enrichment(self) -> list[Item]:
        """Devuelve items que aún no están al día con `ENRICHMENT_VERSION`.

        Incluye:
          - items sin enriquecimiento alguno (`enriched_version IS NULL`)
          - items con summary v1 pero sin estructura v2 (`enriched_version < 2`)

        Pensado para el backfill de mantenimiento: rebobina cuando se sube
        ENRICHMENT_VERSION sin perder lo que ya estaba bien.
        """
        cur = self._conn.execute(
            """
            SELECT id_hash, source, url, titulo, fecha, categoria, first_seen_at
            FROM items
            WHERE enriched_version IS NULL OR enriched_version < ?
            ORDER BY first_seen_at DESC
            """,
            (ENRICHMENT_VERSION,),
        )
        return [_row_to_basic_item(r) for r in cur]

    def iter_all_items(self) -> list[tuple[str, str, str]]:
        """Devuelve `(id_hash, titulo, categoria)` de todos los items.

        Tupla mínima orientada a `reclassify_all`: solo necesitamos el
        título para reclasificar y el id_hash para el UPDATE. Evitamos
        materializar `Item` completos para una operación de mantenimiento
        que puede recorrer miles de filas en el futuro.
        """
        return list(
            self._conn.execute("SELECT id_hash, titulo, categoria FROM items")
        )

    def filter_new(self, items: list[Item]) -> list[Item]:
        """Filtra la lista devolviendo solo los ítems nuevos, y los guarda."""
        new_items = []
        for item in items:
            if self.is_new(item):
                self.save(item)
                new_items.append(item)
                logger.info("Nuevo: [%s] %s", item.source, item.titulo[:80])
            else:
                logger.debug("Ya visto: %s", item.id_hash)
        return new_items

    def iter_live_items_for_detail_watch(
        self,
        excluded_sources: Iterable[str],
        days_without_deadline: int = 90,
        today: Optional[date] = None,
    ) -> list[tuple[str, str, str]]:
        """Devuelve `(source, url, titulo)` de items "vivos" cuyo source NO
        está en `excluded_sources`.

        "Vivo" = el proceso aún tiene un horizonte temporal abierto. Dos
        condiciones (OR):
          - `deadline_inscripcion >= today` (deadline declarado pendiente)
          - `deadline_inscripcion IS NULL AND first_seen_at >= today - N
            días` (sin deadline conocido, pero descubierto recientemente)

        Si una misma URL aparece en varios items (caso típico: snapshots
        sucesivos del mismo hash-watcher comparten `url`), devuelve sólo
        el más reciente — el `titulo` que devuelve es el más actual y
        sirve para construir el title del nuevo snapshot del DetailWatcher.
        """
        if today is None:
            today = date.today()
        cutoff_first_seen = (
            datetime.combine(today, datetime.min.time())
            - timedelta(days=days_without_deadline)
        ).isoformat()
        today_iso = today.isoformat()
        # Subquery: ranking por first_seen_at descendente dentro de cada
        # (source, url). Tomamos el más reciente.
        excluded = list(excluded_sources)
        placeholders = ",".join("?" * len(excluded)) if excluded else "''"
        cur = self._conn.execute(
            f"""
            SELECT source, url, titulo FROM (
                SELECT source, url, titulo, first_seen_at,
                       ROW_NUMBER() OVER (
                           PARTITION BY source, url
                           ORDER BY first_seen_at DESC
                       ) AS rn
                FROM items
                WHERE source NOT IN ({placeholders})
                  AND (
                      (deadline_inscripcion IS NOT NULL
                       AND deadline_inscripcion >= ?)
                      OR (deadline_inscripcion IS NULL
                          AND first_seen_at >= ?)
                  )
            ) WHERE rn = 1
            ORDER BY source, url
            """,
            (*excluded, today_iso, cutoff_first_seen),
        )
        return [(row[0], row[1], row[2]) for row in cur]

    # ------------------------------------------------------------------
    # detail_snapshots — estado del DetailWatcher genérico
    # ------------------------------------------------------------------

    def get_detail_snapshot(self, url: str) -> Optional[tuple[str, str, str]]:
        """Devuelve `(last_hash, last_body, last_checked_at)` para `url`,
        o `None` si no hay snapshot previo."""
        cur = self._conn.execute(
            "SELECT last_hash, last_body, last_checked_at "
            "FROM detail_snapshots WHERE url = ?",
            (url,),
        )
        row = cur.fetchone()
        return tuple(row) if row else None

    def upsert_detail_snapshot(
        self, url: str, last_hash: str, last_body: str, last_checked_at: str
    ) -> None:
        """Inserta o actualiza el snapshot de una URL de detalle.

        Idempotente: re-escribe los 3 campos. El timestamp es del
        llamador (no `datetime.now()` aquí) para que el DetailWatcher
        controle la granularidad y los tests sean deterministas.
        """
        self._conn.execute(
            """
            INSERT INTO detail_snapshots
                (url, last_hash, last_body, last_checked_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                last_hash = excluded.last_hash,
                last_body = excluded.last_body,
                last_checked_at = excluded.last_checked_at
            """,
            (url, last_hash, last_body, last_checked_at),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


# ---------------------------------------------------------------------------
# Helpers de reconstrucción (módulo-level para que tests puedan importarlos)
# ---------------------------------------------------------------------------

def _row_to_basic_item(row: tuple[Any, ...]) -> Item:
    """Reconstruye un `Item` a partir de los 7 campos básicos.

    No incluye campos de enriquecimiento — para casos donde el enricher
    los va a sobrescribir igualmente (backfill, re-enrichment).
    """
    return Item(
        source=row[1],
        url=row[2],
        titulo=row[3],
        fecha=date.fromisoformat(row[4]),
        categoria=row[5],
        id_hash=row[0],
        first_seen_at=datetime.fromisoformat(row[6]),
    )
