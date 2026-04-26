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
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "state" / "seen.db"

# Versión actual del esquema de enriquecimiento. Si subimos esto en el futuro
# (ej. v3 = clustering de procesos relacionados), `iter_items_for_enrichment`
# rebobinará automáticamente lo que esté por debajo.
ENRICHMENT_VERSION = 2


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

    # Buffer interno para datos efímeros del run (raw_text del extractor,
    # diagnósticos…). No se persiste.
    extra: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id_hash:
            self.id_hash = _make_hash(self.source, self.url, self.titulo)
        if self.first_seen_at is None:
            self.first_seen_at = datetime.utcnow()
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
        self._conn.commit()

    def is_new(self, item: Item) -> bool:
        """Devuelve True si el ítem no está en la BD."""
        cur = self._conn.execute(
            "SELECT 1 FROM items WHERE id_hash = ?", (item.id_hash,)
        )
        return cur.fetchone() is None

    def save(self, item: Item) -> None:
        """Inserta el ítem; no falla si ya existe (INSERT OR IGNORE).

        Solo persiste los campos básicos + summary. Los campos del enricher
        v2 se rellenan después con `update_enrichment()` — el enricher se
        ejecuta tras `filter_new`, no antes.
        """
        self._conn.execute(
            """
            INSERT OR IGNORE INTO items
                (id_hash, source, url, titulo, fecha, categoria, first_seen_at, summary)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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

    def update_categoria(self, id_hash: str, categoria: str) -> None:
        """Cambia la categoría de un item ya guardado. Lo usa la tarea de
        mantenimiento `reclassify_all` cuando se afina CATEGORY_HINTS y
        queremos rebobinar la clasificación de items históricos."""
        self._conn.execute(
            "UPDATE items SET categoria = ? WHERE id_hash = ?",
            (categoria, id_hash),
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
