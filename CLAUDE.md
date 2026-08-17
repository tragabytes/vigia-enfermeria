# CLAUDE.md — vigia-enfermeria

Bot de la plataforma vigia para convocatorias de **Enfermería del Trabajo** en la
administración pública (Madrid). Es el bot original.

> **Reglas generales (obligatorias):** Karpathy Guidelines + convenciones del pipeline
> + guía "cómo crear un bot" viven en el **CLAUDE.md maestro** de vigia-core:
> <https://github.com/tragabytes/vigia-core/blob/main/CLAUDE.md>. Este documento recoge
> el **doble rol** de este repo y las **convenciones específicas de enfermería**.

---

## Repo fino sobre vigia-core

Este repo es **el bot de Enfermería del Trabajo en producción** (rama `main`, cron en
Actions, dashboard <https://tragabytes.github.io/vigia-enfermeria>), montado como
**repo fino** sobre el core:

- El pipeline entero (extractor, enricher, notifier, storage, dashboard y todas las
  fuentes) vive en **vigia-core** y se instala por pip con tag pineado
  (`requirements.txt`: `vigia-core @ git+…/vigia-core@vX.Y.Z`). Aquí **no hay copia
  local del core** — la antigua "Fase 6" (migración a pip) ya se completó.
- `vigia_enfermeria/__main__.py` es el entrypoint: fija el perfil **DEFAULT** del core
  (Enfermería del Trabajo, `vigia/_default_profile.py` en vigia-core) con
  `set_active_profile()` **antes** de importar `vigia.main`.
- `tests/` contiene solo el smoke del perfil (`conftest.py` que fija el perfil +
  `test_perfil_enfermeria.py`); la suite del pipeline vive en vigia-core (PR #31).
- Para tocar el core (patrones, prompts o fuentes del perfil incluidos): commit y
  **nuevo tag** en el repo vigia-core, y después bumpear el `requirements.txt` de este
  repo (y del resto de bots). Contratos y proceso: maestro §3.6-3.7.
- `PLAN.md`, `PLAN_MAESTRO.md`, `BACKLOG.md` e `incidents/` son **registro histórico**
  de la migración, no planes vivos.

---

## Convenciones del pipeline (con las rutas de enfermería)

Las versiones genéricas están en el maestro; aquí con los ejemplos reales de este bot.
Ordenadas por frecuencia de tropiezo.

### 5. El estado vive en GitHub, no en disco

**`state/seen.db` local casi nunca refleja producción.**

- Para diagnosticar: `git fetch origin state` y luego `git show FETCH_HEAD:state/seen.db > /tmp/prod.db`.
- Para ver el dashboard real: `git show origin/gh-pages:data/items.json`.
- No pushees `state/` local a la rama `state` ni edites la BD local sin restaurarla primero.

*test:* antes de afirmar "el item está/no está en BD", confirma contra la rama remota, nunca contra disco.

### 6. Verifica el daño real antes de proponer arreglo

**Un warning en logs no implica BD contaminada.**

- El parser puede emitir un RawItem que el extractor descarte aguas abajo. "Fallback a today()" en `comunidad_madrid` parecía catastrófico → 0 daño en BD (los items eran TCAE/auxiliar, descartados como FP).
- El conclusion `success` del workflow puede esconder errores acumulados en `last_errors` por fuente.

*test:* localiza el `id_hash` del ítem sospechoso en `data/items.json`. Si no está, el daño es solo log noise.

### 7. Segmenta backfills

**`since` con rango grande revienta el runner.**

- `since=2025-12-01` en GitHub Actions excede 27 min y se aborta. BOCM con `max_pages=None` × 100+ días = miles de PDFs grandes; BOE = miles de items con bodies + anexos.
- `dry_run=true` no acorta el pipeline (sigue fetchando todo). Solo evita persistencia y Telegram.
- Para histórico amplio: rangos mensuales (`since=2025-12-01`, luego `2026-01-01`…) o ejecución local.

*test:* si `since` es >30 días, divide en lotes mensuales o no lances el `daily.yml`.

### 8. Si lo cambias en una fuente, busca en las hermanas

**Los patrones se repiten en todas las fuentes; los fixes también.**

- Timeouts ajustados, fast-keywords, cascadas de fecha con fallback a `today()`, FALSE_POSITIVE_PATTERNS — todos viven duplicados en `boe.py / bocm.py / comunidad_madrid.py / ciemat.py / universidades_madrid.py / sap_successfactors.py`.
- Cuando subiste el timeout en `comunidad_madrid` a 30s, `ciemat` siguió en 20s con el mismo síntoma. Cuando creaste `recalcular_fechas_comunidad_madrid`, `universidades_madrid` quedó con el mismo bug sin equivalente.

*test:* al cerrar un fix de una fuente, lanza `grep -nE "timeout=|fallback a today\(\)" vigia/sources/*.py` **en el checkout de vigia-core** (aquí no hay fuentes) para localizar gemelos.

### 9. Probe ≠ runtime

**Una fuente puede dar `probe 200 OK` y aun así perder items por timeouts en GETs concretos.**

- El dashboard refleja solo el resultado del probe. La degradación silenciosa (timeouts en items individuales, listados perdidos por término) queda solo en logs del workflow.
- Síntoma típico: `comunidad_madrid 2 raw items, 1 errores` con probe verde — el "1 errores" es la rama perdida.

*test:* después de un fix, lee `gh run view <id> --log | grep -E "WARNING|errores"`, no solo el `conclusion: success`.

---

## Específico de enfermería

- **Fuentes sanitarias propias** (en `vigia/sources/` **de vigia-core**, registradas
  como `extra_sources` del perfil enfermería, no en `CORE_SOURCES`): `codem` (RSS del Colegio de Enfermería),
  `cm_ficha_enfermeria` (hash-watcher de la ficha de la Comunidad de Madrid — genera
  alerta real al usuario), `isciii` (hash-watcher, hoy snapshot silencioso) y
  `canal_isabel_ii_calendario`. El resto de fuentes son genéricas (`CORE_SOURCES`).
- **Perfil:** `vigia/_default_profile.py` **en vigia-core** (patrones, watchlist,
  prompts, hosts, branding de Enfermería del Trabajo). El fast-keyword es `"enfermer"`
  (no `"enferm"`: evita "enfermedades").
- **Entorno (Windows):** `python -m vigia_enfermeria --probe`/`--dry-run` revientan con
  `UnicodeEncodeError` (cp1252) al imprimir `→`; usa `PYTHONIOENCODING=utf-8`. No afecta
  al runner Linux de Actions.
- **pytest** en este shell requiere `--capture=no` (la captura por descriptores de
  fichero peta con "I/O operation on closed file").

---

**Estas reglas funcionan si:** menos cambios innecesarios en los diffs, menos rebobinados por sobrecomplicación, y las preguntas aclaratorias llegan antes de implementar — no después de un error.
