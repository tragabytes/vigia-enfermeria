"""
Persistencia SQLite con deduplicación por hash(source + url + titulo).
"""
from __future__ import annotations

import hashlib
import logging
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "state" / "seen.db"


@dataclass
class Item:
    """
    Hallazgo ya validado por el extractor.

    Este es el objeto que viaja entre extractor.py → [enricher.py] → notifier.py.
    El enricher futuro puede rellenar los campos opcionales (summary, extra)
    sin necesidad de cambiar la firma de notifier.
    """
    source: str
    url: str
    titulo: str
    fecha: date
    categoria: str
    id_hash: str = ""
    first_seen_at: datetime = None
    summary: Optional[str] = None      # relleno por enricher.py (futuro)
    extra: dict = None                 # metadatos enriquecidos (futuro)

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
        # Migración idempotente para BDs creadas antes de exponer summary en
        # el dashboard. ALTER TABLE ADD COLUMN no es destructivo y mantiene los
        # datos previos. PRAGMA table_info devuelve filas (cid, name, type, ...).
        existing_cols = {
            row[1] for row in self._conn.execute("PRAGMA table_info(items)")
        }
        if "summary" not in existing_cols:
            self._conn.execute("ALTER TABLE items ADD COLUMN summary TEXT")
        self._conn.commit()

    def is_new(self, item: Item) -> bool:
        """Devuelve True si el ítem no está en la BD."""
        cur = self._conn.execute(
            "SELECT 1 FROM items WHERE id_hash = ?", (item.id_hash,)
        )
        return cur.fetchone() is None

    def save(self, item: Item) -> None:
        """Inserta el ítem; no falla si ya existe (INSERT OR IGNORE).

        El campo `summary` se inserta si ya viene relleno, pero el flujo
        habitual lo añade después con `update_summary()` (el enricher se
        ejecuta tras `filter_new`).
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
        """Persiste el `summary` generado por el enricher para un item ya guardado.

        Se invoca tras `enricher.enrich(...)` desde main.py. Si el item no
        tiene summary, no hace nada (evita pisar valores previos con NULL).
        """
        if not item.summary:
            return
        self._conn.execute(
            "UPDATE items SET summary = ? WHERE id_hash = ?",
            (item.summary, item.id_hash),
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

        Reconstruye `Item` con todos los campos persistidos. No incluye
        `extra.raw_text` (no se persiste): el enricher trabajará solo con
        título, fuente, url y categoría — basta para resúmenes razonables.
        """
        cur = self._conn.execute(
            """
            SELECT id_hash, source, url, titulo, fecha, categoria, first_seen_at
            FROM items
            WHERE summary IS NULL OR summary = ''
            ORDER BY first_seen_at DESC
            """
        )
        items: list[Item] = []
        for r in cur:
            it = Item(
                source=r[1],
                url=r[2],
                titulo=r[3],
                fecha=date.fromisoformat(r[4]),
                categoria=r[5],
                id_hash=r[0],
                first_seen_at=datetime.fromisoformat(r[6]),
            )
            items.append(it)
        return items

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
