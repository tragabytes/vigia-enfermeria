# Incidente 2026-06-26 — Muros de errores de fuentes enviados a los usuarios

**Estado:** corregido en vigia-core `v0.5.1` ([PR #11](https://github.com/tragabytes/vigia-core/pull/11)) · bump del bot en curso
**Severidad:** media (no hay pérdida de datos; sí degradación grave de la experiencia)
**Bot afectado:** vigia-enfermeria (y, por compartir núcleo, vigia-docencia — ver follow-up)

## Síntoma

Los usuarios reciben por Telegram mensajes cuyo único contenido son errores de
infraestructura (`⚠️ Fuente <b>X</b> no respondió: …`), sin ninguna convocatoria. Pasa
incluso en días en que no hay ninguna novedad de empleo.

## Magnitud (últimos 6 runs del cron `daily.yml`)

El `conclusion: success` del workflow esconde estos errores (regla #6 de CLAUDE.md): se
acumulan en `last_errors` por fuente y el pipeline los adjunta al mensaje de Telegram.

| Día | Nuevos relevantes | Errores de fuentes | ¿Mensaje a usuarios? |
|-----|-------------------|--------------------|----------------------|
| 26 Jun (hoy) | 0 (2 cosméticos suprimidos) | ~11 (boe×2, comunidad_madrid×2, uam×2, codem, aena, isciii, las_rozas, detail_watcher) | ❌ muro de errores |
| 25 Jun | 0 | 1 (isciii 500) | ❌ solo error |
| 24 Jun | 0 (2 cosméticos) | 1 (isciii 500) | ❌ solo error |
| 23 Jun | 0 (1 cosmético) | 5 (isciii, bocm×2, uam, detail_watcher) | ❌ solo error |
| 22 Jun | 0 (1 cosmético) | 0 | ✅ silencio (sin envío) |
| 19 Jun | 0 | 5 (las_rozas, uam×3, detail_watcher) | ❌ solo error |

**5 de los últimos 6 días** el único contenido del Telegram fue ruido de errores. El día
limpio (22 Jun) lo fue solo porque ese día no hubo errores.

## Causa raíz

Código real de `vigia-core@v0.5.0` (el repo fino lo consume por pip vía `requirements.txt`):

1. **`vigia/main.py:392`** — `if notifiable or errors or reminders:` → se envía aunque
   `notifiable` y `reminders` estén vacíos, con solo errores.
2. **`vigia/notifier.py` `_build_message()`** — bucle que renderiza, dentro del mensaje del
   usuario, una línea `⚠️ Fuente <b>{nombre}</b> no respondió: {error}` por cada error.

Un test fijaba este comportamiento como deseado
(`test_main_errors.py::test_pipeline_envia_telegram_con_errores_aunque_no_haya_novedades`);
era una decisión de diseño antigua (antes el bug era que los errores NO se enviaban). Se
revierte: los errores deben ser visibles para el **operador** (logs de Actions, dashboard),
nunca para el **usuario**.

## Naturaleza de los errores (ninguno accionable para un opositor)

- **Transitorios (mayoría):** ConnectTimeout/ReadTimeout a `boe.es`,
  `sede.comunidad.madrid`, `uam.es`, `codem.es`, `empleo.aena.es`. Throttling de la IP del
  runner de GitHub Actions — los mismos hosts del plan aparcado de relay VPS.
- **Persistentes:** `isciii` devuelve 500 cuatro días seguidos (23–26 Jun); `las_rozas`
  devuelve 415 (Unsupported Media Type). Probable problema de endpoint/headers
  (bot-detection, `Accept` ausente). Se investiga aparte; no deben llegar al usuario igualmente.

## Acción correctiva

Los errores de fuentes **dejan de mostrarse a los usuarios**. Solo se envía Telegram si hay
convocatorias o recordatorios reales; los errores siguen en los logs de Actions y el
dashboard (el operador no pierde visibilidad).

Cambios (en `vigia-core`, rama `fix/no-notificar-errores-fuentes` → tag `v0.5.1`):
- `main.py:392`: condición `if notifiable or reminders:` + log INFO
  `"N fuentes con errores — no se notifica a usuarios"` para dejar constancia al operador.
- `notifier._build_message()`: se elimina el render del bloque de errores.
- Tests invertidos en `vigia-core` y en la copia del repo fino (`tests/test_main_errors.py`),
  porque `daily.yml` corre `pytest tests/` contra el core instalado antes de lanzar el bot.

Release: tag `vigia-core@v0.5.1` → bump de `requirements.txt` en este repo.

## Follow-ups

- **vigia-docencia** (`@v0.4.4`): mismo bug por compartir núcleo. Backport del mismo cambio
  (rama desde `v0.4.4` → `v0.4.5` → bump), en sesión aparte.
- **Endpoints persistentes** `isciii` (500) y `las_rozas` (415): investigar headers/método.
