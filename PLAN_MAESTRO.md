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
| 4 | Bot docente `vigia-docencia` (el entregable para el hermano) | ✅ **hecha** — **replanteada** (ver corrección abajo): bot nuevo **en producción** (vigia-core v0.4.0 + repo + CI verde + cutover sin re-alertas; fork archivado) |
| 5 | Reestructurar documentación (CLAUDE.md maestro + por bot) | ✅ **hecha** — maestro en `vigia-core` + CLAUDE.md por bot (reparto "autonomía operativa") + memoria reestructurada |
| 6 | Migrar enfermería a consumir `vigia-core` | ✅ **hecha** — repo fino sobre `vigia-core@v0.4.0` en producción (merge + run real con 0 re-alertas) |

Eje transversal continuo: expansión de fuentes (boletines autonómicos → core; Instituto Cervantes y portales privados → perfil docente). **Roadmap de fuentes docentes futuras (colegios privados, ELE, canales sindicales, InfoJobs/Jooble, alertas de calendario): `vigia-docencia/ROADMAP.md`.**

> **Mantenimiento — `vigia-core@v0.4.1` (2026-06-13):** desactivadas `ciemat` y `csic_sede` del perfil de enfermería (fallaban en **cada** run desde el runner de Actions y solo generaban ruido de error en Telegram/dashboard, sin hits útiles: `ciemat` SSL en probe/detail_watcher aunque el fetch lo sortea con `verify=False`; `csic_sede` `ConnectTimeout` persistente a `sede.csic.gob.es`, 0 hits históricos) + `ciemat` añadida a `EXCLUDED_SOURCES` del `DetailWatcher`. **Cierra el cabo suelto del probe de `csic_sede`** anotado en la Fase 6. Cobertura real intacta vía BOE. Ambos bots bumpeados a `@v0.4.1`. PRs: [vigia-core#2](https://github.com/tragabytes/vigia-core/pull/2), [vigia-enfermeria#9](https://github.com/tragabytes/vigia-enfermeria/pull/9), [vigia-docencia#7](https://github.com/tragabytes/vigia-docencia/pull/7).

> **Mejora de servicio — `vigia-core@v0.4.2` (2026-06-13):** (1) **Recordatorios de cierre de plazo** — fase diaria que re-avisa de convocatorias abiertas a 7/3/1 días del cierre (umbrales por perfil, idempotente vía tabla `deadline_reminders`), en una sección `⏰ Cierran pronto` del Telegram. (2) **Campos accionables** — el notifier ahora muestra `requisitos_clave` y `url_inscripcion` (ya los extraía el enricher, no se pintaban). Roadmap pendiente del eje "mejorar servicio": subir la tasa de extracción de `deadline_inscripcion` (hoy ~29%) y cobertura de **mutuas + servicios de prevención ajenos** (mayor empleador del gremio, sin fuente). PR: [vigia-core#4](https://github.com/tragabytes/vigia-core/pull/4).

> **Mejora de servicio — `vigia-core@v0.4.3` (2026-06-13):** **Incremento 3** del roadmap — mejor extracción de `deadline_inscripcion` (combustible de los recordatorios). El enricher inyecta snippets de la sección de PLAZO al prompt y calcula los plazos relativos ("N días hábiles desde la publicación en BOE") a fecha absoluta, marcándolos `deadline_estimated` → el notifier los muestra como "(estimada)". `ENRICHMENT_VERSION` 5→6 re-enriquece el histórico (una vez). PR: [vigia-core#6](https://github.com/tragabytes/vigia-core/pull/6). **Pendiente: Incremento 4** (mutuas/SPA) — registrado en `BACKLOG.md` › "Nuevas fuentes a añadir".

> ### ⚠️ Corrección de premisa (sesión 3, 2026-06-02)
> La Fase 4 se escribió asumiendo construir el bot docente **desde cero**. **No es así**: el bot del hermano **ya existía desplegado** — `alerta-empleo-profe` (repo `tragabytes/alerta-empleo-profe`, dashboard en vivo, cron L-V, 41 tests), creado el 26-abr como **fork monolítico** del pipeline (copia de `vigia/` con perfil docente inline). Había **tres copias** del pipeline (enfermería, vigia-core, fork docente).
>
> **Decisiones del usuario (sesión 3):** (1) rehacer limpio en **repo NUEVO `vigia-docencia`** que consume el core, migrar estado y **archivar el fork** al final; (2) **purista**: parametrizar el core → **vigia-core v0.4.0** (BOE configurable por `source_params`, enums de `process_type` profile-driven) para **compartir el BOE**; el **BOCM** del fork (reescritura RSS) va como **fuente custom**. El perfil docente real (informe.md) **excluye a propósito** universidad/PDI general y primaria; el boceto de "archivos/museos/universidad-Historia" de la Fase 4 original era **erróneo** y se descarta.
>
> **Plan detallado por etapas (E0–E11):** `.claude/plans/zazzy-splashing-dawn.md`.
>
> **✅ COMPLETADA (2026-06-02):** todas las etapas E0–E11 hechas. `vigia-core@v0.4.0` publicado; **github.com/tragabytes/vigia-docencia** en producción (CI verde, Pages, 3 secrets, `seen.db` del fork migrado → **0 re-alertas**, Telegram verificado); fork `alerta-empleo-profe` con cron apagado y **archivado**. Roadmap de ampliación: `vigia-docencia/ROADMAP.md`.

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

### Fase 4 — Bot docente `vigia-docencia` *(entregable, replanteada — ver corrección arriba)*

Migración por etapas que **porta** el perfil docente ya rodado del fork (no lo reinventa) y acaba jubilando `alerta-empleo-profe` con red. Detalle completo + riesgos en `.claude/plans/zazzy-splashing-dawn.md`. Estado:

**Core v0.4.0 (aditivo, enfermería byte-idéntico) — ✅ hecho y verificado (472/2):**
- [x] `boe.py`: `dept_keywords`/`fetch_pdfs`/`timeout_*` desde `source_params["boe"]` (defaults = enfermería). El `fast_keywords` del perfil ya cubre el pre-filtro de título (no hizo falta `title_fast_keywords`).
- [x] `profile.py` campo `valid_process_types` + `enricher.py` lo lee (default 6 genéricos). `CATEGORIES` **no** se hizo campo (nadie lo importa; `category_hints` ya es profile-driven).
- [x] Bump `pyproject.toml`/`__init__.py` → `0.4.0`.

**Repo nuevo `vigia-docencia` (local, consume `vigia-core@v0.4.0`) — ✅ scaffold + validación offline:**
- [x] `vigia_docencia/profile.py` (`PERFIL_DOCENCIA`, portado 1:1 del fork: strong/weak/FP, category_hints, 25 watchlist, prompt enricher, hosts; snippet keywords autoradas) + `__main__.py` (entrypoint: `set_active_profile` antes del pipeline, import diferido) + `sources/bocm.py` (BOCM-RSS custom que sobrescribe el del core vía `extra_sources`).
- [x] **Validación offline 19/19**: extractor del core + perfil docente sobre oráculo del fork + caso trampa multi-especialidad; wiring end-to-end (BOE core + BOCM custom + params + enums + prompt) verificado.

**Externo (publicación + cutover) — ✅ hecho (2026-06-02):**
- [x] E4: `vigia-core@v0.4.0` publicado (commit + tag pusheados).
- [x] E7-E8: `requirements.txt`(@v0.4.0) + `daily.yml` (`VIGIA_STATE_DIR`, entrypoint `python -m vigia_docencia`) + `web/` rebrand; repo **github.com/tragabytes/vigia-docencia** creado + 3 secrets + Pages. **CI en verde** (instala `vigia-core@v0.4.0`, tests, dry-run real: bocm 36 / boe 34, 0 errores).
- [x] E9-E11: `seen.db` del fork (74 items) migrado → **primer run real con 0 re-alertas** (3 matches → 0 nuevos); Telegram verificado (`send_test`); **cron del fork apagado + repo archivado**.
- **Resultado:** bot en producción (cron L-V 08:00 UTC), dashboard https://tragabytes.github.io/vigia-docencia/. Ampliación de fuentes: `vigia-docencia/ROADMAP.md`.

### Fase 5 — Documentación ✅
Reparto acordado con el usuario: **"autonomía operativa"** — lo genérico (Karpathy + guía
crear-bot) vive solo en el maestro; cada bot lleva sus convenciones del pipeline adaptadas
a sus rutas + enlace al maestro.
- [x] CLAUDE.md maestro en `vigia-core` (NUEVO): Parte 1 Karpathy (canónica) + Parte 2 convenciones del pipeline desacopladas de enfermería + Parte 3 guía "cómo crear un bot/perfil" (contrato `Profile`, entrypoint, repo-fino, cutover 0-realertas, contratos del core, publicación por tag). + fix README `@v0.3.0`→`@v0.4.0`. PR: tragabytes/vigia-core#1.
- [x] CLAUDE.md por bot: `vigia-docencia` (NUEVO, fino, enlaza al maestro; PR tragabytes/vigia-docencia#1) y `alerta-empleo` (reescrito: quita Karpathy→enlace, añade nota doble-rol core/enfermería, mantiene reglas 5–9 con rutas de enfermería + específicos sanitarios; en `feat/plataforma-multibot`).
- [x] Memoria reestructurada a proyecto maestro + nota por bot (`project_docencia.md` nuevo; `project_multibot.md` enfocado a plataforma; `project_vigia.md` adelgazado; `MEMORY.md` actualizado).
- **Verifica:** ✅ la guía del maestro (Parte 3) cubre cada paso realmente ejecutado en la Fase 4 (Profile, entrypoint, extra_sources, requirements@tag, VIGIA_STATE_DIR, daily.yml, web, 3 secrets, migración `seen.db`, cutover); enlaces resuelven; ningún bot duplica la guía larga.

### Fase 6 — Migrar enfermería al core ✅
- [x] `vigia-enfermeria` → **repo fino** que consume `vigia-core@v0.4.0` por pip: borrada la copia del core (`vigia/`, −7800 líneas) + `pyproject.toml`; paquete `vigia_enfermeria/` (entrypoint `python -m vigia_enfermeria` que fija `DEFAULT` antes del pipeline); `requirements.txt` → `vigia-core@v0.4.0`; `daily.yml`/`maintenance.yml` con `VIGIA_STATE_DIR=${{ github.workspace }}/state` + nuevo entrypoint. `state`/`gh-pages`/secrets/URL **intactos**. Decisión: paquete propio (no `python -m vigia.main` pelado), consistente con docencia.
- [x] **Verificación con red** (PR [tragabytes/vigia-enfermeria#8](https://github.com/tragabytes/vigia-enfermeria/pull/8)): `vigia/` (feat) byte-idéntico a `vigia-core@v0.4.0` (diff ignorando CRLF = vacío); `ci.yml` aislado en PR (pip install @v0.4.0 + **472 passed, 2 skipped** + dry-run, sin tocar state/gh-pages/Telegram); merge a `main`; primer run real controlado ([run 26824149227](https://github.com/tragabytes/vigia-enfermeria/actions/runs/26824149227)): **0 alertas enviadas** (6 matches; 1 "nuevo" = snapshot cosmético suprimido por diff_summarizer → 0 re-alertas, confirma `id_hash` idénticos). state/gh-pages actualizados con normalidad.
- **Cabos sueltos:** ✅ resuelto el `__pycache__` colado en `gh-pages` (limpieza antes del `git add -A` en los 3 workflows de ambos bots; los `.pyc` ya publicados se auto-limpian en el próximo cron). Queda solo el timeout transitorio de `csic_sede` en el probe (`continue-on-error`, no accionable).

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

### 2026-06-02 — Sesión 3 (Fase 4 replanteada)
- **Hallazgo:** el bot docente del hermano YA existía desplegado (`alerta-empleo-profe`, fork monolítico, 26-abr). La Fase 4 estaba escrita sobre premisa falsa (greenfield). Tres copias del pipeline en juego.
- **Decisiones del usuario:** repo NUEVO `vigia-docencia` consumiendo el core + jubilar el fork; vía **purista** (parametrizar el core, compartir BOE). Perfil real (informe.md) **excluye** universidad/PDI y primaria; el boceto original "archivos/museos/universidad" era erróneo.
- **Hecho y verificado (offline, sin recursos externos):**
  - **Core v0.4.0** (rama `feat/plataforma-multibot`): BOE parametrizable por `source_params` (dept_keywords/fetch_pdfs/timeouts, defaults = enfermería, resueltos en runtime); `valid_process_types` profile-driven; bump 0.4.0. **472 passed, 2 skipped** tras cada cambio + smoke de overrides docentes.
  - **`vigia-docencia`** (local `proyectos/vigia-docencia`): `Profile` docente portado 1:1 del fork + entrypoint `python -m vigia_docencia` (fija perfil antes del pipeline) + BOCM-RSS custom. **Validación offline 19/19** (oráculo del fork + caso trampa) + wiring end-to-end OK (BOE core + BOCM custom).
- **Plan por etapas (E0–E11):** `.claude/plans/zazzy-splashing-dawn.md`.
- **Cierre del cutover (misma sesión 3):** E4–E11 completadas. `vigia-core@v0.4.0` publicado; **github.com/tragabytes/vigia-docencia** creado, CI verde (`pip install @v0.4.0` + tests + dry-run real bocm 36/boe 34, 0 errores), Pages activo, 3 secrets (reutilizado el bot del fork). `seen.db` (74 items) migrado → **primer run real con 0 re-alertas** (3 matches → 0 nuevos); Telegram verificado (`send_test`). Fork: cron apagado (`bba0da2`) + **archivado**. **Fase 4 cerrada.** Ampliación futura de fuentes: `vigia-docencia/ROADMAP.md`. Pendiente opcional: Fases 5 (docs) y 6 (migrar enfermería al core).

### 2026-06-02 — Sesión 4 (Fase 5: documentación)
- **Hallazgo:** ni `vigia-core` ni `vigia-docencia` tenían `CLAUDE.md`; el único (enfermería) mezclaba genérico (Karpathy + convenciones del pipeline) con específico, sin guía "crear bot". Los tres repos están clonados en `proyectos/`; `vigia-core` se mantiene por copia manual (sin script de sync).
- **Decisiones del usuario:** reparto **"autonomía operativa"** (genérico solo en el maestro; cada bot con sus convenciones adaptadas + enlace); memoria **completa**; **rama + PR por repo**.
- **Hecho:**
  - **`vigia-core/CLAUDE.md`** (maestro, NUEVO): Karpathy + convenciones del pipeline (desacopladas de enfermería) + guía "cómo crear un bot/perfil" (Profile, entrypoint `set_active_profile`+import diferido, repo-fino, fuente core-vs-bot, cutover 0-realertas, contratos del core, publicación por tag) + fix README `@v0.4.0`. **PR [tragabytes/vigia-core#1](https://github.com/tragabytes/vigia-core/pull/1)**.
  - **`vigia-docencia/CLAUDE.md`** (NUEVO, fino): enlaza al maestro; específico de docencia (vigia-core@v0.4.0, entrypoint, perfil 005 G·H + ELE, BOCM custom) + convenciones con rutas del bot. **PR [tragabytes/vigia-docencia#1](https://github.com/tragabytes/vigia-docencia/pull/1)**.
  - **`alerta-empleo/CLAUDE.md`** (reescrito en `feat/plataforma-multibot`): quita Karpathy→enlace, añade nota doble-rol (enfermería en prod + copia de trabajo del core hasta F6), mantiene reglas 5–9 con rutas de enfermería + específicos sanitarios.
  - **Memoria** reestructurada a maestro + nota por bot.
- **Siguiente:** Fase 6 (migrar enfermería al core, opcional con red) o **ampliar fuentes del bot docente** (`vigia-docencia/ROADMAP.md`: ELE/privados/sindicatos — mayor valor para el hermano). Mergear antes los 2 PRs de docs.

### 2026-06-02 — Sesión 4 (Fase 6: migrar enfermería al core)
- **Estado de partida:** `feat/plataforma-multibot` = `main` + 8 commits (Fases 0-5) sin mergear; producción corría el código pre-refactor. `vigia/` (feat) verificado **byte-idéntico** a `vigia-core@v0.4.0` (diff ignorando CRLF = vacío). `vigia-core@v0.4.0` ya contiene el perfil de enfermería (`_default_profile.DEFAULT`) y sus 4 fuentes sanitarias.
- **Decisión del usuario:** repo fino con **paquete propio `vigia_enfermeria`** (entrypoint que fija `DEFAULT`), consistente con docencia.
- **Hecho:** paquete `vigia_enfermeria/` + `requirements.txt`→`vigia-core@v0.4.0` + `daily.yml`/`maintenance.yml` (`VIGIA_STATE_DIR` + entrypoint) + `ci.yml` (PR aislado) + borrado de `vigia/` (−7800) y `pyproject.toml`. Commit `c5cfd2f`.
- **Verificación con red:** CI del PR [#8](https://github.com/tragabytes/vigia-enfermeria/pull/8) verde (pip install @v0.4.0 + **472 passed, 2 skipped** + dry-run, sin tocar state/gh-pages/Telegram). Checkpoint con el usuario → OK. Merge a `main` (`d21a3e6`). **Primer run real** ([26824149227](https://github.com/tragabytes/vigia-enfermeria/actions/runs/26824149227)): 6 matches, 1 "nuevo" (snapshot cosmético suprimido por diff_summarizer) → **0 alertas enviadas, 0 re-alertas**. state/gh-pages actualizados con normalidad. **Fase 6 cerrada — todas las fases (0-6) completas.**
- **Cabos sueltos (no bloqueantes):** `git add -A` del paso "Publicar dashboard" cuela `__pycache__` en `gh-pages` (preexistente); probe `csic_sede` timeout transitorio.
- **Siguiente posible:** ampliar fuentes del bot docente (`vigia-docencia/ROADMAP.md`).
- **Cierre de sesión:** mergeados los 2 PRs de docs de la Fase 5 ([vigia-core#1](https://github.com/tragabytes/vigia-core/pull/1), [vigia-docencia#1](https://github.com/tragabytes/vigia-docencia/pull/1)) → CLAUDE.md maestro y de docencia en `main`, enlaces resueltos. Resuelto el cabo del `__pycache__` en `gh-pages` (3 workflows). **Plataforma multi-bot completa (Fases 0-6) y en producción.**
