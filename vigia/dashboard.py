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
import os
import re
import subprocess
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Optional

from vigia import __version__
from vigia.config import (
    SOURCES_ENABLED,
    WATCHLIST_ORGS,
    WATCHLIST_RECENCY_DAYS,
    normalize,
)
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
    targets_path = out_dir / "targets.json"
    changelog_path = out_dir / "changelog.json"

    items_payload = _items_payload(storage)

    # Política de sources_status:
    # - Si tenemos `probe_results` (caller normal: --probe), regeneramos todo.
    # - Si no (caller normal: pipeline diario sin probe, o --maintenance), no
    #   sobrescribimos el JSON existente — el último probe sigue siendo el
    #   más informativo. Pero sí refrescamos `total_hits` con datos vivos de
    #   la BD: el resto de campos (url/code/status/last_probe_at) se quedan
    #   congelados al último --probe real, los hits sí cambian cada run.
    # - Si tampoco existe el fichero EN DISCO, NO lo regeneramos como
    #   degradado: en CI cada run hace checkout fresh y el sources_status.json
    #   bueno vive en gh-pages. Si el workflow no lo trae a `docs/data/`
    #   antes del export, escribir un payload de "unknown/null" aquí pisaría
    #   el bueno cuando se publique. La sección queda transitoriamente
    #   vacía hasta el siguiente `--probe`, lo cual es preferible a mostrar
    #   todas las fuentes como caídas (regresión histórica del bug 1dd68cb).
    if probe_results is not None:
        sources_payload = _sources_payload(storage, probe_results, now)
        _write_json(sources_path, sources_payload)
    elif sources_path.exists():
        sources_payload = json.loads(sources_path.read_text(encoding="utf-8"))
        sources_payload = _refresh_total_hits(storage, sources_payload, now)
        _write_json(sources_path, sources_payload)
    else:
        logger.warning(
            "dashboard: sources_status.json no existe en %s y no hay "
            "probe_results — se omite su generación para no escribir un "
            "snapshot degradado. El próximo `--probe` lo regenerará. "
            "Si esto pasa en CI, asegúrate de que el workflow haga fetch "
            "del JSON desde gh-pages antes de exportar.",
            sources_path,
        )
        # Generamos payload en memoria SOLO para alimentar `_meta_payload`
        # (sources_online/sources_total). No lo persistimos.
        sources_payload = _sources_payload(storage, None, now)

    targets_payload = _targets_payload(storage, now)
    changelog_payload = _changelog_payload()
    meta_payload = _meta_payload(storage, sources_payload, targets_payload, now)

    _write_json(items_path, items_payload)
    _write_json(targets_path, targets_payload)
    _write_json(changelog_path, changelog_payload)
    _write_json(meta_path, meta_payload)

    logger.info(
        "Dashboard exportado: %d items, %d fuentes, %d targets en %s",
        len(items_payload), len(sources_payload), len(targets_payload), out_dir,
    )
    return {
        "items": items_path,
        "sources": sources_path,
        "meta": meta_path,
        "targets": targets_path,
        "changelog": changelog_path,
    }


# ---------------------------------------------------------------------------
# Payloads
# ---------------------------------------------------------------------------

def _items_payload(storage: Storage) -> list[dict]:
    """Lista de hallazgos en formato plano, ordenados por first_seen_at desc.

    Incluye los campos del enricher v2 (is_relevant, plazas, deadline,
    organismo, fase, next_action…). Los items marcados como falsos positivos
    (is_relevant=false) viajan igualmente al frontend pero con la flag al
    descubierto: el cliente decide si los oculta por defecto o los muestra
    con badge "DISCARDED" para auditoría.
    """
    cur = storage._conn.execute(
        """
        SELECT id_hash, source, url, titulo, fecha, categoria,
               first_seen_at, summary,
               is_relevant, relevance_reason, process_type, organismo, centro,
               plazas, deadline_inscripcion, fecha_publicacion_oficial,
               tasas_eur, url_bases, url_inscripcion, requisitos_clave,
               fase, next_action, confidence, enriched_at, enriched_version
        FROM items
        ORDER BY first_seen_at DESC
        """
    )
    rows = []
    for r in cur:
        # is_relevant viene como 0/1/NULL: lo expresamos como bool|None para
        # que el frontend trate los `null` como "sin enriquecer todavía"
        # (no descartado, no confirmado).
        is_relevant: Optional[bool] = (
            None if r[8] is None else bool(r[8])
        )
        try:
            requisitos = json.loads(r[19]) if r[19] else None
        except (TypeError, json.JSONDecodeError):
            requisitos = None

        rows.append({
            "id_hash": r[0],
            "source": r[1],
            "url": r[2],
            "titulo": r[3],
            "fecha": r[4],
            "categoria": r[5],
            "first_seen_at": r[6],
            "summary": r[7],
            "is_relevant": is_relevant,
            "relevance_reason": r[9],
            "process_type": r[10],
            "organismo": r[11],
            "centro": r[12],
            "plazas": r[13],
            "deadline_inscripcion": r[14],
            "fecha_publicacion_oficial": r[15],
            "tasas_eur": r[16],
            "url_bases": r[17],
            "url_inscripcion": r[18],
            "requisitos_clave": requisitos,
            "fase": r[20],
            "next_action": r[21],
            "confidence": r[22],
            "enriched_at": r[23],
            "enriched_version": r[24],
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


def _refresh_total_hits(
    storage: Storage,
    sources_payload: list[dict],
    now: datetime,
) -> list[dict]:
    """Refresca `total_hits` en un sources_payload pre-existente.

    El resto de campos del último probe (url, code, status, last_probe_at,
    detail) se mantienen — no tenemos información más fresca sobre ellos
    sin volver a ejecutar `--probe`. Lo único que sí ha podido cambiar
    desde el probe anterior es el conteo acumulado por fuente, así que
    lo refrescamos contra la BD.

    Si la BD tiene una fuente que no estaba en el payload (fuente nueva
    aún no probeada), se añade marcada como `unknown`. Si una fuente del
    payload ya no tiene hits, se conserva con `total_hits=0`.
    """
    hits_by_source: dict[str, int] = dict(storage._conn.execute(
        "SELECT source, COUNT(*) FROM items GROUP BY source"
    ))
    known: set[str] = set()
    for entry in sources_payload:
        name = entry.get("name", "")
        known.add(name)
        entry["total_hits"] = hits_by_source.get(name, 0)
    for name, count in hits_by_source.items():
        if name in known:
            continue
        sources_payload.append({
            "name": name,
            "url": None,
            "status": "unknown",
            "code": None,
            "detail": "sin probe en este run",
            "last_probe_at": now.isoformat(),
            "total_hits": count,
        })
    sources_payload.sort(key=lambda r: r["name"])
    return sources_payload


def _targets_payload(storage: Storage, now: datetime) -> list[dict]:
    """Calcula hits y estado de cada organismo del watchlist.

    Para cada organismo:

    - `hits`: nº de items cuyo título/summary/organismo contienen alguno de
      los `patterns` (substring sobre texto normalizado). Los items con
      `is_relevant=False` (descartados por el enricher v2) NO cuentan.
    - `nearest_deadline`: la fecha de cierre de inscripción más próxima en
      el futuro entre los hits del organismo (formato `YYYY-MM-DD`). `null`
      si ningún hit tiene deadline o todos vencieron.
    - `days_until`: días desde hoy hasta `nearest_deadline`, o `null`.
    - `urgent`: `True` si `days_until <= 7`.
    - `active`: `True` si hay deadline futuro O — para items sin deadline
      conocido (no enriquecidos a v2) — si hay fecha de publicación dentro
      de los últimos `WATCHLIST_RECENCY_DAYS` días. La heurística sigue
      como fallback hasta que el backfill v2 cubra todo el histórico.
    - `latest_phase`: fase del proceso más recientemente actualizada para
      este organismo (`convocatoria`, `examen`, …) o `null`.

    Solo se ignora `is_relevant=False`. `is_relevant=None` (sin enriquecer)
    se considera potencialmente relevante para no degradar el dashboard
    durante el backfill.
    """
    today_iso = now.date().isoformat()
    cutoff_iso = (now - timedelta(days=WATCHLIST_RECENCY_DAYS)).date().isoformat()

    rows = list(storage._conn.execute(
        """
        SELECT id_hash,
               titulo,
               COALESCE(summary, ''),
               COALESCE(organismo, ''),
               fecha,
               deadline_inscripcion,
               is_relevant,
               fase,
               first_seen_at
        FROM items
        """
    ))
    # Pre-normalizamos una sola vez por item para no pagar normalize() N×M.
    # Rodeamos con espacios para que patterns como " emt " (con guard de
    # palabra) puedan matchear al inicio o final del texto.
    items_idx = []
    for id_hash, titulo, summary, organismo, fecha, deadline, is_rel, fase, first_seen in rows:
        if is_rel == 0:    # explícitamente descartado por el enricher v2
            continue
        text = " " + normalize(titulo + " " + summary + " " + organismo) + " "
        items_idx.append({
            "id_hash": id_hash,
            "text": text,
            "fecha": fecha,
            "deadline": deadline,
            "fase": fase,
            "first_seen": first_seen,
        })

    targets: list[dict] = []
    for org in WATCHLIST_ORGS:
        hits = 0
        item_ids: list[str] = []
        recent_pub = False
        nearest_deadline: Optional[str] = None
        latest_phase: Optional[str] = None
        latest_phase_seen_at = ""

        for it in items_idx:
            if not any(p in it["text"] for p in org["patterns"]):
                continue
            hits += 1
            item_ids.append(it["id_hash"])

            # Recency fallback (item sin deadline_inscripcion conocido).
            if not it["deadline"] and it["fecha"] >= cutoff_iso:
                recent_pub = True

            # Deadline real: cogemos el más próximo en el futuro.
            dl = it["deadline"]
            if dl and dl >= today_iso:
                if nearest_deadline is None or dl < nearest_deadline:
                    nearest_deadline = dl

            # Fase del proceso más reciente (por first_seen).
            if it["fase"] and (it["first_seen"] or "") > latest_phase_seen_at:
                latest_phase = it["fase"]
                latest_phase_seen_at = it["first_seen"] or ""

        days_until: Optional[int] = None
        if nearest_deadline:
            try:
                dl_date = date.fromisoformat(nearest_deadline)
                days_until = max(0, (dl_date - now.date()).days)
            except ValueError:
                days_until = None

        active = bool(nearest_deadline) or recent_pub
        urgent = days_until is not None and days_until <= 7

        targets.append({
            "id": org["id"],
            "name": org["name"],
            "desc": org["desc"],
            "hits": hits,
            "active": active,
            "nearest_deadline": nearest_deadline,
            "days_until": days_until,
            "urgent": urgent,
            "latest_phase": latest_phase,
            # Lista de id_hash de los items que matchean este organismo.
            # El frontend la usa para abrir el modal con los items concretos
            # sin tener que replicar la lógica de normalización + match.
            "item_ids": item_ids,
        })
    return targets


def _meta_payload(
    storage: Storage,
    sources_payload: list[dict],
    targets_payload: list[dict],
    now: datetime,
) -> dict:
    """Métricas globales: contadores, ventana temporal, build info."""
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
            if first_dt.tzinfo is None:
                first_dt = first_dt.replace(tzinfo=timezone.utc)
            days_watching = max(0, (now - first_dt).days)
        except ValueError:
            days_watching = 0

    # Salud de fuentes: solo cuentan las que tienen estado conocido (las
    # "unknown" son fuentes con hits en BD pero sin probe en este run, y
    # por tanto no aportan señal de vivacidad).
    sources_total = max(len(SOURCES_ENABLED), len(sources_payload))
    sources_online = sum(
        1 for s in sources_payload if s.get("status") in ("ok", "skipped")
    )

    targets_active = sum(1 for t in targets_payload if t.get("active"))
    targets_urgent = sum(1 for t in targets_payload if t.get("urgent"))
    targets_total = len(targets_payload)

    # Métricas del enricher v2: cuántos items siguen sin enriquecer (informa
    # al dashboard cuándo ejecutar mantenimiento), cuántos quedaron como
    # falso positivo confirmado, y cuántos tienen plazo de inscripción
    # vivo. Sirve también de telemetría: una caída fuerte en
    # `total_relevant_open` puede indicar un problema con el extractor.
    total_enriched = storage._conn.execute(
        "SELECT COUNT(*) FROM items WHERE enriched_version IS NOT NULL"
    ).fetchone()[0]
    total_irrelevant = storage._conn.execute(
        "SELECT COUNT(*) FROM items WHERE is_relevant = 0"
    ).fetchone()[0]
    total_relevant = total - total_irrelevant

    today_iso_full = date.today().isoformat()
    total_open_deadlines = storage._conn.execute(
        """
        SELECT COUNT(*) FROM items
        WHERE deadline_inscripcion IS NOT NULL
          AND deadline_inscripcion >= ?
          AND (is_relevant IS NULL OR is_relevant = 1)
        """,
        (today_iso_full,),
    ).fetchone()[0]

    return {
        "total_items": total,
        "total_today": total_today,
        "total_relevant": total_relevant,
        "total_irrelevant": total_irrelevant,
        "total_enriched": total_enriched,
        "total_open_deadlines": total_open_deadlines,
        "by_category": by_category,
        "days_watching": days_watching,
        "first_seen_at": first_seen_min,
        "last_run_at": now.isoformat(),
        "next_run_at": _next_cron_run(now).isoformat(),
        "sources_online": sources_online,
        "sources_total": sources_total,
        "targets_active": targets_active,
        "targets_urgent": targets_urgent,
        "targets_total": targets_total,
        "version": __version__,
        "commit": _commit_short(),
    }


def _next_cron_run(now: datetime) -> datetime:
    """Próxima ejecución del cron (lunes-viernes 08:00 UTC).

    El schedule está hardcodeado en .github/workflows/daily.yml; aquí lo
    replicamos para que el dashboard pueda mostrar el próximo run sin
    parsear el YAML.
    """
    candidate = now.astimezone(timezone.utc).replace(
        hour=8, minute=0, second=0, microsecond=0,
    )
    if candidate <= now:
        candidate += timedelta(days=1)
    while candidate.weekday() > 4:  # 5=sat, 6=sun
        candidate += timedelta(days=1)
    return candidate


def _commit_short() -> str:
    """SHA corto del commit actual.

    En GitHub Actions viene en `GITHUB_SHA`; en local devuelve "local".
    """
    sha = os.environ.get("GITHUB_SHA", "")
    return sha[:7] if sha else "local"


# Prefijos conventional-commits que consideramos "newsworthy" para mostrar
# en la sección "FIELD NOTES" del dashboard. Otros prefijos (chore, test,
# style…) y los commits sin scope se filtran porque rara vez aportan
# información útil al lector externo.
_CHANGELOG_PREFIXES = ("feat", "fix", "ci", "refactor", "perf")
_CONVENTIONAL_RE = re.compile(
    r"^(?P<kind>" + "|".join(_CHANGELOG_PREFIXES) + r")"
    r"(?:\((?P<scope>[^)]+)\))?:\s*(?P<title>.+)$"
)


def _changelog_payload(
    repo_dir: Optional[Path] = None,
    max_entries: int = 4,
) -> list[dict]:
    """Genera la lista FIELD NOTES desde el `git log` real del repo.

    Filtra commits con prefijo conventional-commits (`feat:`, `fix:`,
    `ci:`, `refactor:`, `perf:`). Para cada commit devuelve un dict con
    `date`, `commit` (SHA corto), `kind`, `scope`, `title` y `body`
    (primera línea no-vacía y no-Co-Authored del cuerpo, truncada).

    En entornos donde `git` no está disponible (entornos sandbox de tests,
    runners exóticos…) o el directorio no es un repo, devuelve [] y el
    frontend simplemente esconde la sección.
    """
    repo_dir = repo_dir or Path.cwd()
    sep_field = "\x1f"   # entre campos de un commit
    sep_record = "\x1e"  # entre commits

    fmt = sep_field.join(["%h", "%ad", "%s", "%b"]) + sep_record
    try:
        out = subprocess.check_output(
            [
                "git", "log", "--no-merges",
                # Pedimos varias veces el max porque muchos commits caen
                # fuera del filtro conventional (chore, docs sin scope, etc.).
                "-n", str(max_entries * 6),
                "--date=short",
                f"--pretty=format:{fmt}",
            ],
            cwd=str(repo_dir),
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError) as exc:
        logger.info("changelog: git no disponible (%s) — devolviendo []", exc)
        return []

    entries: list[dict] = []
    for raw in out.split(sep_record):
        raw = raw.strip("\n")
        if not raw:
            continue
        parts = raw.split(sep_field)
        if len(parts) < 4:
            continue
        sha, dt, subject, body = parts[0], parts[1], parts[2], parts[3]
        match = _CONVENTIONAL_RE.match(subject)
        if not match:
            continue

        body_clean = ""
        for line in body.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.lower().startswith("co-authored-by"):
                continue
            body_clean = line
            break

        entries.append({
            "date": dt,
            "commit": sha,
            "kind": match.group("kind"),
            "scope": match.group("scope") or "",
            "title": match.group("title").strip(),
            "body": body_clean[:240],
        })
        if len(entries) >= max_entries:
            break

    return entries


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_json(path: Path, payload) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
