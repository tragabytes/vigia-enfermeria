# Plan maestro: vigia como plataforma multi-bot

> **Documento vivo.** Se trabaja en varias sesiones. Marca las casillas de cada fase
> a medida que se completen y anota avances en el [Diario de sesiones](#diario-de-sesiones).
> Fecha de inicio: **2026-06-01**.

## Estado actual

| Fase | Descripción | Estado |
|---|---|---|
| 0 | Red de seguridad (empaquetado + baseline) | ✅ hecha (tests verdes; editable install pendiente de toolchain) |
| 1 | `Profile` + enfermería byte-idéntico (refactor interno) | ✅ hecha (472 tests verdes) |
| 2 | Registro extensible de fuentes + fix multi-repo (`DB_PATH`) | ✅ hecha (472 tests verdes) |
| 3 | Publicar el core como repo `vigia-core` (no toca enfermería) | ✅ hecha (repo público + tag v0.3.0) |
| 4 | Bot docente `vigia-docencia` (el entregable para el hermano) | ⬜ pendiente |
| 5 | Reestructurar documentación (CLAUDE.md maestro + por bot) | ⬜ pendiente |
| 6 | (Opcional) Migrar enfermería a consumir `vigia-core` | ⬜ pendiente |

Eje transversal continuo: expansión de fuentes (boletines autonómicos → core; Instituto Cervantes y portales privados → perfil docente).

---

## Contexto

Hoy el repo `vigia-enfermeria` (carpeta local `alerta-empleo`) es **un solo bot** acoplado a "Enfermería del Trabajo", en producción en GitHub Actions. Objetivo:

1. **Proyecto maestro**: un núcleo reutilizable (`vigia`) empaquetado, sobre el que montar varios bots, de modo que arreglos y aprendizajes del core se compartan entre todos.
2. **Segundo bot, perfil docente** (hermano del usuario): historiador + máster de profesorado + máster ELE; busca historia o profesor de secundaria. Nichos: secundaria pública (Geografía e Historia), ELE (Instituto Cervantes/EOI), universidad/archivos/museos, privado/academias. Ámbito: España + extranjero (ELE).
3. **Reestructurar la documentación** (CLAUDE.md) en general + específica por bot.

**Hallazgo clave:** el núcleo ya es casi agnóstico (extractor, storage, main, base de fuentes, watchers y ~18/25 fuentes son reutilizables). Lo específico de enfermería se concentra en 6 sitios: `config.py`, `enricher.py` (SYSTEM_PROMPT + snippet keywords + `ALLOWED_FETCH_HOSTS`), `diff_summarizer.py` (1 línea), `notifier.py` (título + `DASHBOARD_URL` + `send_test`), `boe.py` (`DEPT_KEYWORDS_FOR_BODY`) y `comunidad_madrid.py` (`SEARCH_TERMS`). El coste real es **parametrizar, no reescribir**.

## Decisiones

**Del usuario:** arquitectura = core como paquete instalable + repos finos · nichos = los cuatro · ámbito = España + extranjero (ELE) · alcance = plan completo por fases.

**De diseño:**
- **El valor antes que el riesgo.** El bot docente se construye consumiendo el core *sin tocar enfermería*. La migración de enfermería a depender del core externo es la última fase, opcional y con red.
- **Fuentes genéricas → core; de perfil → repo fino.** Boletines autonómicos al core (benefician también a enfermería). Solo Instituto Cervantes y portales de profesores en `vigia-docencia`.
- **Enfermería nunca cambia de repo.** Conserva ramas `state`/`gh-pages`, secrets y URL de Pages (`tragabytes.github.io/vigia-enfermeria`) intactos.

## Arquitectura objetivo

```
vigia-core (repo nuevo, paquete pip "vigia-core" → import vigia)
  vigia/            core agnóstico: main, extractor, storage, enricher,
  ├ profile.py        diff_summarizer, notifier, dashboard, watchers,
  ├ sources/          sources/* genéricas + sources/registry.py (CORE_SOURCES)
  └ ...             + Profile (contrato) y get/set_active_profile
  pyproject.toml · tests/ del core · CLAUDE.md maestro

vigia-enfermeria (repo actual, PRODUCCIÓN — no se mueve)
  vigia_enfermeria/profile.py   keywords/prompts/watchlist de enfermería
  vigia_enfermeria/main.py      set_active_profile(PERFIL) + delega
  vigia_enfermeria/sources/     fuentes sanitarias (cm_ficha, isciii, codem…)
  web/ · daily.yml · ramas state/gh-pages · CLAUDE.md del bot

vigia-docencia (repo nuevo, el bot del hermano)
  vigia_docencia/profile.py     keywords/prompts/watchlist docentes
  vigia_docencia/main.py · sources/ (instituto_cervantes…) · web/ · daily.yml
```

Cada bot ancla `vigia-core @ git+https://github.com/tragabytes/vigia-core.git@vX.Y.Z` en su `requirements.txt`. Estado, secrets, dashboard y bot de Telegram aislados por repo.

## El concepto `Profile`

`@dataclass(frozen=True)` en `vigia/profile.py` (core) que encapsula lo específico de un perfil. Cada repo fino construye una instancia; el core la consume vía `get_active_profile()` / `set_active_profile(p)` (singleton de módulo con default lazy = enfermería), leído **en tiempo de llamada** para preservar los contratos de los tests.

| Campo del `Profile` | Hoy vive en |
|---|---|
| `slug`, `display_name`, `dashboard_url`, `test_message` | notifier.py:52,78,94 |
| `strong_patterns`, `weak_context_patterns`, `false_positive_patterns`, `fast_keywords`, `category_hints` | config.py:35-150 |
| `watchlist_orgs`, `watchlist_recency_days` | config.py:160-301 |
| `enricher_system_prompt`, `snippet_keywords_high/low`, `allowed_fetch_hosts` | enricher.py:69,125,486 |
| `diff_system_prompt` | diff_summarizer.py:75 |
| `sources_enabled`, `extra_sources`, `source_params` | config.py:306, main.py:58, comunidad_madrid.py:46, boe.py:65 |

Se quedan en el core (genéricos): `normalize()`, `CATEGORIES`, `USER_AGENT`, credenciales Telegram, esquema SQLite, enums de proceso/fase.

Contratos que el refactor NO puede romper (fijados por los tests):
- `extract(raw)` mantiene firma (regex cacheada por perfil con `lru_cache`, invalidada en `set_active_profile`).
- `main.SOURCE_REGISTRY` y `main.SOURCES_ENABLED` siguen siendo atributos de módulo (varios tests los monkeypatchean).
- `normalize` sigue importable desde `vigia.config`.

---

## Fases (detalle y verificación)

Cada fase = un PR en rama (nunca commit directo a `main` sin pedir). Criterio común pre-extracción: **`pytest` verde sin tocar los tests existentes**.

### Fase 0 — Red de seguridad ✅
- [x] `pyproject.toml` mínimo (nombre `vigia-core`, paquetes `vigia*`, deps de `requirements.txt`, extra `test`). `requires-python = ">=3.9"` (Python local es 3.9.6). No se borra `requirements.txt`.
- [x] Baseline de producción guardado en `/tmp/vigia-baseline/` (`prod_items.json` 83 KB, `prod_seen.db` 240 KB).
- [x] Baseline de tests verde: **472 passed, 2 skipped** (`PYTHONIOENCODING=utf-8 python -m pytest tests --capture=no`; este shell no soporta la captura por fd de pytest).
- **Verifica:** `import vigia` OK; `pytest` verde. ⚠️ `pip install -e .` NO valida en local por toolchain de 2021 (pip 21.1.3 < 21.3, setuptools 56 < 61); el empaquetado se validará en CI / Fase 3 con toolchain moderno.

### Fase 1 — `Profile`, enfermería byte-idéntico ✅
- [x] `vigia/profile.py` (`Profile` frozen) + `get/set_active_profile` (un perfil por proceso, default perezoso).
- [x] `vigia/_default_profile.py` con el perfil Enfermería del Trabajo: patrones, watchlist, 2 SYSTEM_PROMPT, snippet keywords, `ALLOWED_FETCH_HOSTS`, branding (display_name/dashboard_url/test_message).
- [x] `config.py` convertido en fachada `__getattr__` (PEP 562): reexpone los 8 símbolos de perfil → `extractor`, las 13 fuentes y `dashboard` NO se tocan.
- [x] `enricher`/`diff_summarizer`/`notifier` migrados a leer del perfil activo.
- **Verifica:** ✅ **472 passed, 2 skipped** sin tocar tests + sanity check de la fachada.
- **Notas de diseño:** el extractor lee de la fachada en import-time (modelo *un perfil por proceso*, sin cache dinámica). `vigia/main.py` (core) se deja **agnóstico**: NO fija perfil; el lazy default cubre enfermería y cada bot fijará el suyo (Fase 4). `SEARCH_TERMS`/`DEPT_KEYWORDS_FOR_BODY` se quedan de momento en sus fuentes; se moverán a `source_params` en Fase 4.

### Fase 2 — Registro extensible + fix multi-repo ✅
- [x] `vigia/sources/registry.py` con `CORE_SOURCES` (16 genéricas). Específicas de enfermería (`codem`, `cm_ficha_enfermeria`, `isciii`, `canal_isabel_ii_calendario`) → `DEFAULT.extra_sources`.
- [x] `main.py`: `SOURCE_REGISTRY = {**CORE_SOURCES, **get_active_profile().extra_sources}` (sigue como atributo de módulo; 20 fuentes).
- [x] `storage.py` `DB_PATH`: override por `VIGIA_STATE_DIR` + fallback histórico idéntico (`<repo>/state/seen.db`).
- [x] `codem` migrado a leer `fast_keywords` del perfil en call-time (rompe el ciclo de import perfil↔fuente).
- **Verifica:** ✅ **472 passed, 2 skipped**; registro = 20 fuentes (16+4) sin ciclo; 19 habilitadas; override `VIGIA_STATE_DIR` OK.
- **Nota:** los archivos de las 4 fuentes específicas siguen físicamente en `vigia/sources/`; se moverán al repo del bot en Fase 3/6. En Fase 2 solo cambió quién las registra (el perfil, no el core).

### Fase 3 — Publicar `vigia-core` ✅
- [x] Repo nuevo **https://github.com/tragabytes/vigia-core** (público) con `vigia/` + `tests/` + `pyproject.toml` + `requirements.txt` + `README.md`. Tag **v0.3.0**. (Snapshot por copia, sin historia; sin `web/`/`daily.yml`/`docs` de enfermería.)
- [x] El repo `vigia-enfermeria` NO se modificó (conserva su copia; duplicación temporal hasta Fase 6).
- **Verifica:** ✅ la suite pasa en la copia autónoma (**472 passed, 2 skipped**); tag `v0.3.0` en remoto; contenido = solo el core. ⚠️ `pip install git+…@v0.3.0` no validable en local (toolchain 2021); se valida en el CI del bot docente (Fase 4).

### Fase 4 — Bot docente `vigia-docencia` *(entregable)*
- [ ] Repo nuevo: `requirements.txt` con `vigia-core@v0.3.0`; `vigia_docencia/{profile,main}.py`, `sources/`, `web/`, `daily.yml`, secrets + bot de Telegram, ramas `state`/`gh-pages`, Pages.
- [ ] Perfil docente MVP — `strong_patterns`: "geografia e historia", "profesor de historia", "profesor(a) de secundaria", "cuerpo de profesores de enseñanza secundaria", "español para extranjeros / ELE", "archivero", "bibliotecario", "conservador de museos"… · `false_positive_patterns`: otras especialidades (matemáticas, inglés, ed. física…), primaria/infantil · prompts del enricher/diff reescritos · watchlist: consejerías de educación, EOI, universidades (Historia/Geografía), Instituto Cervantes, archivos/bibliotecas/museos.
- [ ] Fuentes MVP (Madrid + nacional): `boe`, `bocm`, `comunidad_madrid` (con `search_terms` docentes) + **fuente nueva `instituto_cervantes`** (ELE/extranjero).
- **Verifica:** suite propia verde; `--probe`; `--dry-run` con matches docentes plausibles; primer run real revisando `gh run view <id> --log | grep -E "WARNING|errores"`.

### Fase 5 — Documentación
- [ ] CLAUDE.md maestro en `vigia-core`: Karpathy + convenciones genéricas del pipeline + guía "cómo crear un nuevo bot/perfil".
- [ ] CLAUDE.md por bot (enfermería, docencia) con puntero al maestro.
- [ ] Memoria (`MEMORY.md`, `project_vigia.md`) reestructurada a proyecto maestro + nota por bot.
- **Verifica:** un bot nuevo se puede arrancar siguiendo solo la guía del maestro.

### Fase 6 — (Opcional) Migrar enfermería al core
- [ ] `vigia-enfermeria`: borrar copia del core; crear `vigia_enfermeria/`; `requirements.txt` → `vigia-core@tag`; `daily.yml` → `python -m vigia_enfermeria.main`. **No tocar state/gh-pages/secrets/URL.**
- **Verifica:** `workflow_dispatch` `dry_run=true`; comparar `items.json` contra baseline de Fase 0; mergear solo si coincide; primer run real controlado.

## Eje transversal — expansión de fuentes (post-MVP, incremental, 1 por PR)
- [ ] Boletines autonómicos (secundaria por CCAA) → **al core** (genéricos). Patrón calcado de `boe.py`/`bocm.py`. Priorizar por dónde busque el hermano.
- [ ] Universidad PDI (profesor de Historia): `universidades_madrid.py` hoy vigila PTGAS, no PDI; ampliar o nueva fuente.
- [ ] Privado/academias (colegios, academias ELE): enfoque distinto (portales con anti-scraping); evaluar ROI antes de invertir.

## Archivos críticos
`vigia/config.py` · `vigia/main.py` (registry/sources como atributos de módulo) · `vigia/extractor.py` (firma `extract(raw)`) · `vigia/enricher.py:69,125,486` · `vigia/notifier.py:52,78,94` · `vigia/diff_summarizer.py:75` · `vigia/dashboard.py` · `vigia/storage.py:35` (`DB_PATH`) · `vigia/sources/base.py` · `vigia/sources/comunidad_madrid.py:46` · `vigia/sources/boe.py:65` · `.github/workflows/daily.yml`.

## Riesgos y compromisos
| Decisión | Ganas | Pagas |
|---|---|---|
| Singleton `set_active_profile` + fachada en `config` | Tests intactos, migración por pasos | Estado global mutable (acotado: `frozen`, único setter) |
| Registro `{**CORE_SOURCES, **extra_sources}` | Simple, explícito | El repo fino importa sus clases a mano |
| `pip install git+…@tag` | Despliegue de una línea | Bump manual del tag por bot (trivial con 2) |
| Publicar core (F3) antes de migrar enfermería (F6) | Bot docente sin riesgo | Duplicación temporal del core hasta F6 |
| MVP de fuentes docentes | Entregable pronto | España completa / privado / PDI quedan en backlog |

## Qué NO incluye
- No reescribe el frontend del dashboard (ya agnóstico; solo branding por `meta.json`).
- No implementa las ~17 CCAA ni portales privados en el MVP.
- No mueve estado/secrets/URL de enfermería.

---

## Diario de sesiones

### 2026-06-01 — Sesión 1 (planificación)
- Exploración completa del proyecto (3 agentes) + diseño del refactor (agente Plan).
- Decisiones del usuario fijadas (4 preguntas). Plan escrito y persistido en este documento.
- Plan de sesión de Claude: `.claude/plans/quiero-hacer-crecer-este-parallel-graham.md`.

### 2026-06-01 — Sesión 1 (Fase 0)
- `pyproject.toml` creado (`vigia-core`, PEP 621, `requires-python>=3.9`). Rama `feat/plataforma-multibot`.
- Baseline de producción guardado en `/tmp/vigia-baseline/`. Baseline de tests: **472 passed, 2 skipped**.
- Entorno: Python **3.9.6**; toolchain de empaquetado viejo (pip 21.1.3, setuptools 56) → editable install local no disponible; se valida en CI/Fase 3.
- Gotcha: pytest en este shell requiere `--capture=no` (la captura por descriptores de fichero peta con "I/O operation on closed file").
- **Siguiente:** Fase 1 — crear `vigia/profile.py` + `vigia/_default_profile.py` (trasladar valores/prompts exactos), migrar consumidores leyendo del perfil activo, verificar `pytest` verde sin tocar tests.

### 2026-06-01 — Sesión 1 (Fase 1)
- Creados `vigia/profile.py` (dataclass `Profile` + `get/set_active_profile`) y `vigia/_default_profile.py` (perfil Enfermería del Trabajo).
- `config.py` → fachada `__getattr__` (8 símbolos de perfil). `enricher`/`diff_summarizer`/`notifier` migrados a leer del perfil.
- `extractor`, 13 fuentes y `dashboard` NO tocados (leen vía fachada). `vigia/main.py` se deja agnóstico (no fija perfil).
- Verificado: **472 passed, 2 skipped** sin tocar tests + sanity check.
- **Siguiente:** Fase 2 — `vigia/sources/registry.py` (CORE_SOURCES) + mover fuentes sanitarias a `extra_sources` del perfil + fix `DB_PATH` (cwd / `VIGIA_STATE_DIR`).

### 2026-06-02 — Sesión 2 (Fase 2)
- `vigia/sources/registry.py` con `CORE_SOURCES` (16 genéricas). Las 4 específicas de enfermería → `DEFAULT.extra_sources`.
- `main.py`: `SOURCE_REGISTRY = {**CORE_SOURCES, **extra_sources}` (atributo de módulo, 20 fuentes).
- `storage.DB_PATH`: override `VIGIA_STATE_DIR` + fallback histórico. `codem` migrado a call-time (rompe ciclo de import perfil↔fuente).
- Verificado: **472 passed, 2 skipped**; registro 20 (16+4) sin ciclo; 19 habilitadas; override DB_PATH OK.
- **Siguiente:** Fase 3 (publicar core como repo `vigia-core`: subtree split + pyproject + tag) o Fase 4 (bot docente), según prioridad.

### 2026-06-02 — Sesión 2 (Fase 3)
- Publicado **https://github.com/tragabytes/vigia-core** (público), tag **v0.3.0**. Contenido: `vigia/` + `tests/` + `pyproject.toml` + `requirements.txt` + `README.md` (snapshot por copia; sin historia ni assets de enfermería).
- Verificado: la copia es autónoma (472 passed, 2 skipped); tag en remoto; contenido correcto. `vigia-enfermeria` intacto.
- Instalable: `pip install git+https://github.com/tragabytes/vigia-core.git@v0.3.0` (validación real de instalación en Fase 4 / CI con toolchain moderno).
- **Siguiente:** Fase 4 — bot docente `vigia-docencia` (repo fino que consume `vigia-core@v0.3.0`): definir perfil docente (keywords/prompts), fuente Instituto Cervantes, bot de Telegram, web, daily.yml. Requiere recursos del usuario (repo + token Telegram).
