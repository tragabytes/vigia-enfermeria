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
    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = db_path
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
        self._conn.commit()

    def is_new(self, item: Item) -> bool:
        """Devuelve True si el ítem no está en la BD."""
        cur = self._conn.execute(
            "SELECT 1 FROM items WHERE id_hash = ?", (item.id_hash,)
        )
        return cur.fetchone() is None

    def save(self, item: Item) -> None:
        """Inserta el ítem; no falla si ya existe (INSERT OR IGNORE)."""
        self._conn.execute(
            """
            INSERT OR IGNORE INTO items
                (id_hash, source, url, titulo, fecha, categoria, first_seen_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.id_hash,
                item.source,
                item.url,
                item.titulo,
                str(item.fecha),
                item.categoria,
                item.first_seen_at.isoformat(),
            ),
        )
        self._conn.commit()

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
