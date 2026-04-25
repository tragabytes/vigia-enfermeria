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
