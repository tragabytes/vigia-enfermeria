"""
Exportador JSON para el dashboard web público.

Se ejecuta al final del pipeline (main.py) y vuelca el contenido relevante
de la BD `seen.db` en tres ficheros que el frontend estático consumirá:

    items.json           — array de hallazgos ordenados por first_seen_at desc
    sources_status.json  — última foto del probe + total acumulado por fuente
    meta.json            — métricas globales del sistema (contadores, fechas)

El frontend (rama gh-pages) hace fetch a estos JSON y renderiza todo en
cliente. No requiere backend para la parte de visualización.

El dashboard se monta sobre los datos que ya guardamos; este módulo solo
los reformatea, no añade ningún campo nuevo a la BD.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from vigia.storage import Storage

logger = logging.getLogger(__name__)


def export_all(
    storage: Storage,
    out_dir: Path,
    probe_results: Optional[list[dict]] = None,
    last_run_at: Optional[datetime] = None,
) -> dict[str, Path]:
    """
    Genera los tres ficheros JSON del dashboard en `out_dir`.

    :param storage:        instancia ya abierta de Storage
    :param out_dir:        directorio destino (se crea si no existe)
    :param probe_results:  salida de Source.probe() para cada fuente; si es
                           None, se rellena con el campo correspondiente vacío.
    :param last_run_at:    timestamp del run actual; si None, datetime.utcnow().
    :return: dict con las rutas escritas {"items": ..., "sources": ..., "meta": ...}
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    now = last_run_at or datetime.now(timezone.utc)

    items_path = out_dir / "items.json"
    sources_path = out_dir / "sources_status.json"
    meta_path = out_dir / "meta.json"

    items_payload = _items_payload(storage)
    sources_payload = _sources_payload(storage, probe_results, now)
    meta_payload = _meta_payload(storage, now)

    _write_json(items_path, items_payload)
    _write_json(sources_path, sources_payload)
    _write_json(meta_path, meta_payload)

    logger.info(
        "Dashboard exportado: %d items, %d fuentes en %s",
        len(items_payload), len(sources_payload), out_dir,
    )
    return {"items": items_path, "sources": sources_path, "meta": meta_path}


# ---------------------------------------------------------------------------
# Payloads
# ---------------------------------------------------------------------------

def _items_payload(storage: Storage) -> list[dict]:
    """Lista de hallazgos en formato plano, ordenados por first_seen_at desc."""
    cur = storage._conn.execute(
        """
        SELECT id_hash, source, url, titulo, fecha, categoria,
               first_seen_at, summary
        FROM items
        ORDER BY first_seen_at DESC
        """
    )
    rows = []
    for r in cur:
        rows.append({
            "id_hash": r[0],
            "source": r[1],
            "url": r[2],
            "titulo": r[3],
            "fecha": r[4],
            "categoria": r[5],
            "first_seen_at": r[6],
            "summary": r[7],
        })
    return rows


def _sources_payload(
    storage: Storage,
    probe_results: Optional[list[dict]],
    now: datetime,
) -> list[dict]:
    """
    Une el resultado del probe (estado HTTP en vivo) con el conteo agregado
    de hallazgos por fuente. Si `probe_results` es None, devuelve solo los
    contadores agregados.
    """
    hits_by_source: dict[str, int] = {}
    for source, count in storage._conn.execute(
        "SELECT source, COUNT(*) FROM items GROUP BY source"
    ):
        hits_by_source[source] = count

    last_probe_iso = now.isoformat()
    rows: list[dict] = []

    if probe_results:
        for r in probe_results:
            name = r.get("name", "")
            rows.append({
                "name": name,
                "url": r.get("url"),
                "status": r.get("status"),
                "code": r.get("code"),
                "detail": r.get("detail", ""),
                "last_probe_at": last_probe_iso,
                "total_hits": hits_by_source.get(name, 0),
            })
        # Cualquier fuente con hallazgos pero sin probe (ej. fuentes-stub
        # que devolverían "skipped") la añadimos para que el dashboard la
        # cuente igualmente.
        names_with_probe = {r["name"] for r in rows}
        for name, count in hits_by_source.items():
            if name not in names_with_probe:
                rows.append({
                    "name": name,
                    "url": None,
                    "status": "unknown",
                    "code": None,
                    "detail": "sin probe en este run",
                    "last_probe_at": last_probe_iso,
                    "total_hits": count,
                })
    else:
        for name, count in hits_by_source.items():
            rows.append({
                "name": name,
                "url": None,
                "status": "unknown",
                "code": None,
                "detail": "",
                "last_probe_at": last_probe_iso,
                "total_hits": count,
            })

    rows.sort(key=lambda r: r["name"])
    return rows


def _meta_payload(storage: Storage, now: datetime) -> dict:
    """Métricas globales: total, hoy, días vigilando, último run."""
    total = storage._conn.execute(
        "SELECT COUNT(*) FROM items"
    ).fetchone()[0]

    today_iso = date.today().isoformat()
    total_today = storage._conn.execute(
        "SELECT COUNT(*) FROM items WHERE substr(first_seen_at, 1, 10) = ?",
        (today_iso,),
    ).fetchone()[0]

    by_category = dict(
        storage._conn.execute(
            "SELECT categoria, COUNT(*) FROM items GROUP BY categoria"
        )
    )

    first_seen_min = storage._conn.execute(
        "SELECT MIN(first_seen_at) FROM items"
    ).fetchone()[0]

    days_watching = 0
    if first_seen_min:
        try:
            first_dt = datetime.fromisoformat(first_seen_min)
            # Si el datetime guardado no tiene tz, asumimos UTC para que el
            # delta sea consistente con `now`.
            if first_dt.tzinfo is None:
                first_dt = first_dt.replace(tzinfo=timezone.utc)
            days_watching = max(0, (now - first_dt).days)
        except ValueError:
            days_watching = 0

    return {
        "total_items": total,
        "total_today": total_today,
        "by_category": by_category,
        "days_watching": days_watching,
        "first_seen_at": first_seen_min,
        "last_run_at": now.isoformat(),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_json(path: Path, payload) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
