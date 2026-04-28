"""
Tareas de mantenimiento sobre la BD ya poblada.

Se ejecutan vía `python -m vigia.main --maintenance` (o el workflow
`maintenance.yml`) cuando queremos rebobinar el clasificador después de
afinar `CATEGORY_HINTS`, o aplicar lógica nueva sobre los items históricos.

Estas operaciones nunca corren en el cron diario porque solo cambian datos
ya guardados; el cron normal solo procesa hallazgos nuevos.
"""
from __future__ import annotations

import logging
from datetime import date, datetime

from vigia.config import normalize
from vigia.extractor import _classify
from vigia.storage import Storage

logger = logging.getLogger(__name__)


def reclassify_all(storage: Storage) -> int:
    """Recategoriza todos los items aplicando `_classify(normalize(titulo))`.

    Devuelve el nº de items cuya categoría ha cambiado. Útil tras ampliar
    `CATEGORY_HINTS` para que un caso histórico (p.ej. "Bolsa única de
    empleo temporal") deje de estar en `otro` y pase a la categoría real.

    Limitación conocida: usamos solo el título porque no persistimos el
    `raw_text` de la fuente. Si la categoría correcta dependía del cuerpo
    del documento (PDF del BOCM, p.ej.) y no del título, el reclasificador
    no podrá corregirla. En la práctica el título suele tener las pistas.
    """
    rows = storage.iter_all_items()
    n_changed = 0
    for id_hash, titulo, current_cat in rows:
        new_cat = _classify(normalize(titulo))
        if new_cat != current_cat:
            storage.update_categoria(id_hash, new_cat)
            logger.info(
                "Reclasificado %s: %s → %s (titulo=%.60s)",
                id_hash, current_cat, new_cat, titulo,
            )
            n_changed += 1
    return n_changed


def recalcular_fechas_comunidad_madrid(storage: Storage) -> tuple[int, int]:
    """Recalcula la fecha de publicación de items de Comunidad de Madrid.

    Aplica la cascada `detalle → año del título → today()` definida en
    `ComunidadMadridSource.resolve_pub_date_from_detail`. Cierra el bug
    histórico (BACKLOG #1) por el que items en estado "En tramitación" /
    "Plazo indefinido" / "Finalizado" tenían `fecha = today()` del run en
    que se descubrieron.

    Devuelve `(procesados, actualizados)`. La tarea es idempotente: una vez
    corregida una fecha, ejecuciones posteriores no la cambiarán salvo que
    el detalle del item se modifique en `sede.comunidad.madrid`.
    """
    from vigia.sources.comunidad_madrid import ComunidadMadridSource

    source = ComunidadMadridSource()
    rows = list(
        storage._conn.execute(
            "SELECT id_hash, url, titulo, fecha FROM items WHERE source = 'comunidad_madrid'"
        )
    )
    n_updated = 0
    for id_hash, url, titulo, fecha_raw in rows:
        try:
            current = datetime.strptime(fecha_raw, "%Y-%m-%d").date()
        except (TypeError, ValueError):
            current = None

        new_date = source.resolve_pub_date_from_detail(url, titulo)
        if new_date == current:
            continue

        storage.update_fecha(id_hash, new_date)
        logger.info(
            "Fecha recalculada %s: %s → %s (%.60s)",
            id_hash, current, new_date, titulo,
        )
        n_updated += 1

    return len(rows), n_updated
