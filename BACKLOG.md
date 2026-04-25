# Backlog — vigia-enfermeria

Pendientes para retomar más adelante. Última actualización: 2026-04-25.

---

## 🌐 Dashboard web público

### ~~Capa de datos: export JSON desde la BD~~ ✅ Resuelto (2026-04-25)

Creado `vigia/dashboard.py` con `export_all(storage, out_dir, probe_results, last_run_at)` que vuelca tres JSON a `docs/data/`:

- **`items.json`** — array completo de hallazgos (orden `first_seen_at desc`) con `id_hash`, `source`, `url`, `titulo`, `fecha`, `categoria`, `first_seen_at`, `summary`.
- **`sources_status.json`** — estado vivo del último probe + `total_hits` agregado por fuente (incluye fuentes con hits pero sin probe en el run, marcadas como `unknown`).
- **`meta.json`** — métricas globales: `total_items`, `total_today`, `by_category`, `days_watching`, `first_seen_at`, `last_run_at`.

Para que el `summary` del enricher sea visible en la web, se migró el esquema SQLite añadiendo la columna `summary TEXT` (idempotente: las BDs viejas de la rama `state` se actualizan solas en el primer run sin perder datos). El flujo de `main.py` ahora llama a `storage.update_summary(item)` tras `enricher.enrich(...)`.

El workflow `daily.yml` tiene un step nuevo "Publicar JSON del dashboard en gh-pages" que pushea `docs/data/` a la rama `gh-pages` siguiendo el mismo patrón que la rama `state`. El step solo toca `data/`, sin pisar el HTML del dashboard cuando esté.

20 tests nuevos (`test_storage.py`, `test_dashboard.py`) cubren migración, persistencia del summary y los tres exports. Todos los runs de pytest son herméticos (no escriben en `docs/` ni `state/` reales).

### ~~HTML del dashboard~~ ✅ Resuelto (2026-04-25)

Claude Design entregó HTML/CSS/JS estilo "hacker terminal / retro CRT" con 9 secciones (hero, daily feed, historical DB, intelligence, sources, watchlist, subscribe, how it works, footer). Vive en `web/` de `main`; el workflow `daily.yml` lo copia a la raíz de `gh-pages` junto a `data/`. Live en `https://tragabytes.github.io/vigia-enfermeria/`.

Ajustes aplicados sobre el diseño original:
- `SOURCE_LABEL` con las keys reales del backend (snake_case) y `boam`/`metro_madrid`/`administracion_gob` añadidos.
- `meta.json` ampliado con `sources_online`, `sources_total`, `next_run_at`, `version`, `commit` para alimentar el header.
- `next_run_at` mostrado con día (`LUN 27/04 08:00 UTC`).
- "vigía" con tilde en todos los textos visibles.
- Mensaje Telegram termina con enlace al dashboard.
- "CONTINUOUS UPTIME SINCE …" usa `meta.first_seen_at` (era hardcoded a 2022-11-25).
- Mini-renderer de Markdown inline en el AI summary (`**bold**`, `*italic*`, `` `code` ``, saltos) — anti-XSS.
- Eliminado el panel ACTIVITY HEATMAP + sparkline (sintético, no real).
- Fix `dashboard.export_all`: `--maintenance` ya no degrada `sources_status.json`.

### Pendiente: hits clickables en la tabla SOURCES

En la sección 05 (`SOURCES · TARGETS PROBED`) la columna **HITS** muestra el nº acumulado de hallazgos por fuente (ej. COMUNIDAD = 11). Hoy es solo informativo: no se puede pinchar para ver *cuáles* son esos 11 items.

**Funcionalidad deseada:** click en una fila (o en el número de HITS) → filtra la sección 03 (`HISTORICAL DATABASE`) por esa fuente y hace scroll suave hasta ella, dejando el filtro visible en la `cmdbar`. El filtro `source: [...]` ya existe en esa cmdbar; solo hay que disparar el cambio desde JS y desplazar.

Sketch técnico (frontend puro, no toca backend):
- En `renderSources()`, añadir `data-source="{name}"` al `<tr>` y un handler `onclick` que:
  1. Set del `<select>` `source:` al name de la fuente.
  2. Re-render del feed historical aplicando el filtro.
  3. `document.getElementById('historical-anchor').scrollIntoView({behavior:'smooth'})`.
- Pista visual: cursor pointer + hover state en filas con `total_hits > 0`. Las filas a 0 hits no son clickables.

Coste: ~30 líneas de JS, sin dependencias. Encaja con el "FIELD MEMO" que ya promete la cabecera de la sección.

### Pendiente: extracción estructurada de deadline (mejora del ACTIVE/COLD)

Hoy la sección 06 (Watchlist) marca un organismo como `ACTIVE` si tiene al menos un hit con `fecha` (publicación oficial) en los últimos 90 días. Es una heurística pragmática — funciona porque las convocatorias suelen tener plazo 20-30 días desde publicación, así que pasados 90 lo razonable es asumir el plazo cerrado. Pero hay falsos positivos (procesos que cerraron antes) y falsos negativos (bolsas permanentes).

**Mejora ideal:** que el enricher (Claude Haiku) devuelva JSON estructurado con `summary + deadline + plazas` cuando los detecte en el cuerpo del aviso. Persistir `deadline DATE` en `items`. Después `active = (deadline IS NULL OR deadline >= today)`.

**Bloqueador conocido:** los items ya guardados no tienen `extra.raw_text` persistido (solo se usa en runtime para enriquecer en el momento). Para extraer deadline de items históricos habría que re-descargar el cuerpo, o aceptar que solo los items futuros tendrán deadline real.

**Plan mínimo:**
1. Persistir `raw_text TEXT` en BD (migración idempotente, otra columna).
2. Cambiar el prompt del enricher para que devuelva `{"summary": "...", "deadline": "YYYY-MM-DD"|null}`.
3. Storage: `update_enrichment(item)` que guarda summary + deadline.
4. Dashboard: `_targets_payload` usa `deadline > today` cuando exista, fallback a la heurística 90d cuando sea NULL.

Coste IA: ~mismo que ahora ($0.001/item). Coste BD: ~2KB extra por item.

### Pendiente: backend de suscripción Telegram

Sigue siendo un sprint aparte. El formulario `/subscribe` del dashboard necesita un Cloudflare Worker que:
- Reciba el code de pairing del usuario
- Lo valide contra el bot (que generó el code al recibir `/start`)
- Persista el `chat_id` en KV (o en la rama `state` del repo)
- Exponga `GET /api/subscribers` para que el cron lea la lista actualizada en lugar del Secret `TELEGRAM_CHAT_ID`

Coste: 0 € en free tier de Cloudflare. Latencia: despreciable.

---

## 🐛 Bugs / fixes a corregir

### ~~1. Notificación Telegram silenciosa cuando fallan fuentes~~ ✅ Resuelto (2026-04-25, commit `881da0b`)

Implementado con la opción A del plan: atributo `self.last_errors` en la clase base `Source`, las 7 fuentes lo rellenan junto a su `logger.warning(...)`, `_run_source()` lo devuelve como tercer elemento de la tupla y `main.py` lo extiende a la lista global `errors`. 9 tests nuevos en `test_main_errors.py` cubren el comportamiento. Validado end-to-end con un run real: BOAM y Comunidad Madrid caídos generaron mensaje en Telegram.

### ~~2. BOAM y Ayuntamiento Madrid bloqueados por geolocalización~~ 🟡 Mitigado (2026-04-25, commit `69e796c`)

**Diagnóstico.** `madrid.es` filtra por **IP + UA combinados**. Solo desde IP española con UA de navegador real deja pasar. El runner de GHA (Azure US/EU) está fuera del rango admitido. Las fuentes `boam.py` y `ayuntamiento_madrid.py` (que pegan a `madrid.es/...`) siguen devolviendo 403 desde el cron.

**Mitigación implementada.** Investigando alternativas se descubrió que **`datos.madrid.es` (portal de datos abiertos del Ayuntamiento) NO está geo-bloqueado** y expone los datos del Ayto vía API CKAN estándar. Se creó la fuente `vigia/sources/datos_madrid.py` que monitoriza:
- **OEP del Ayuntamiento** (300701-0-empleo-oep): detectó las 6 plazas de Enfermero/a del Trabajo OEP 2025 en el primer run real.
- **Procesos selectivos de estabilización** (300687-0-plantilla-estabilizacion).

Cobertura recuperada: OEPs y procesos selectivos del Ayto Madrid (decisiones agregadas, lo que más interesa). Lo que se sigue perdiendo: las disposiciones diarias del BOAM (pero la convocatoria con bases acabará apareciendo también en BOE 2B Administración Local, que sí monitorizamos).

**Pendiente real (opcional, baja prioridad):** ejecutar el cron desde IP española para recuperar literalmente todo. Opciones:
1. **Self-host en VPS español** (Hetzner Helsinki, Contabo ES, OVH FR; ~4€/mes; o Raspberry Pi en casa). Migra el workflow a cron de sistema, decide persistencia de BD.
2. **fly.io con región Madrid** o **Vercel Edge Functions con región mad1** como proxy: free tier, IP española real. Solo el `boam.py` apuntaría a ese proxy, el resto seguiría como ahora.

Coste-beneficio: con `datos_madrid.py` ya tenemos lo más jugoso del Ayto Madrid (OEPs + procesos). Migrar a VPS por las disposiciones diarias del BOAM es trabajo adicional con beneficio marginal.

### ~~3. Comunidad de Madrid `/buscador` da 404~~ ✅ Resuelto colateralmente (2026-04-25, commit `b4e8c36`)

Era el mismo problema que el bug #2: el portal `sede.comunidad.madrid` también filtraba el UA `vigia-enfermeria/1.0`. Al cambiar al UA de Firefox, el 404 desapareció. En el run de validación pasó de `0 raw items, 2 errores` a `93 raw items, 0 errores` y disparó **11 hallazgos reales** (primer "find" del sistema).

---

## 🆕 Nuevas fuentes a añadir

### ~~CODEM — sección de comunicaciones~~ ✅ Resuelto (2026-04-25, commit `a6fa1ef`)

Añadido el feed RSS de "Actualidad" de CODEM (~2400 items, 8MB) además del de "Empleo público" original. La fuente `codem.py` ahora itera sobre `CODEM_RSS_FEEDS = [(label, url), ...]` y deduplica vía `extra["feed"]`. En la inspección manual aparecía ya un match obvio en los primeros items: *"Canal de Isabel II convoca una plaza de enfermera especialista en Enfermería del Trabajo"*.

### ~~Casa de la Moneda (FNMT-RCM)~~ ✅ Cobertura indirecta (2026-04-25, commit `b67ec63`)

Añadido `"fnmt"`, `"casa de la moneda"` y `"fabrica nacional de moneda"` a `HEALTH_ORGS` (BOCM) y `DEPT_KEYWORDS_FOR_BODY` (BOE). Cuando aparezca una convocatoria del organismo en BOE/BOCM, se descargará el cuerpo/PDF para buscar la especialidad. Si en el futuro se decide añadir una fuente directa al portal de FNMT, sigue pendiente investigar URL.

### ~~EMT Madrid (Empresa Municipal de Transportes)~~ ✅ Cobertura indirecta (2026-04-25, commit `b67ec63`)

Añadido `"emt"` y `"empresa municipal de transportes"` a `HEALTH_ORGS` (BOCM) y `DEPT_KEYWORDS_FOR_BODY` (BOE). Si en el futuro se decide añadir una fuente directa al portal de EMT, sigue pendiente investigar URL.

### Boletines oficiales de otros ayuntamientos grandes de la Comunidad de Madrid

✅ **Cobertura indirecta vía BOCM** (2026-04-25, commit `b67ec63`): añadidos los 9 grandes ayuntamientos (>100k hab.) a `HEALTH_ORGS` de `bocm.py` para forzar la descarga de PDF cuando sus convocatorias aparezcan en el BOCM. La cobertura BOE viene gratis vía `"administracion local"`.

✅ **Ampliación corredores A-6 y A-5** (2026-04-25): añadidos a `HEALTH_ORGS` los municipios medianos del noroeste (Las Rozas, Pozuelo, Majadahonda, Boadilla, Collado Villalba, Villanueva de la Cañada, Villanueva del Pardillo, Galapagar, Torrelodones, San Lorenzo de El Escorial, El Escorial, Guadarrama) y la extensión A-5 más allá de Móstoles/Alcorcón (Arroyomolinos, Navalcarnero, Villaviciosa de Odón). Verificado por `test_organism_coverage.py` (50/50). Investigación previa confirmó que ninguno tiene boletín municipal propio: todos publican en BOCM.

Pendiente como mejora futura: parsers dedicados de portales propios con feed/API estructurado para los que los tengan. Casos interesantes detectados:
- Majadahonda: `majadahonda.convoca.online` (plataforma específica de convocatorias)
- Varios usan PORTALEMP: `lasrozas.portalemp.com`, `majadahonda.portalemp.com`, `colladovillalba.portalemp.com`
- **Las Rozas portal oficial:** `https://www.lasrozas.es/el-ayuntamiento/Convocatorias-en-plazo` — listado HTML estático que muestra solo procesos con plazo abierto (filtrado por el propio ayuntamiento). Beneficio adicional sobre BOCM: detectaríamos ANTES (sin esperar publicación oficial) y con la garantía de plazo vivo. Investigar estructura HTML para parser dedicado.

### Pendiente: empresas públicas estatales (RENFE, ADIF, RTVE, Navantia, AENA, Correos…)

Las grandes empresas públicas con servicio médico/SP propio convocan plazas de Enfermería del Trabajo periódicamente. Ahora mismo solo las pillaríamos si el BOE publica la convocatoria (sección 2A o 2B), pero las que tienen procesos selectivos propios (RTVE en su web, RENFE/ADIF en BOE…) merecen vigilancia explícita.

**Mínimo viable** — añadir a `HEALTH_ORGS` (bocm.py) y `DEPT_KEYWORDS_FOR_BODY` (boe.py):
- `"rtve"`, `"corporacion radio television espanola"`, `"radio television espanola"`
- `"renfe"`, `"renfe operadora"`, `"renfe cercanias"`
- `"adif"`, `"administrador de infraestructuras ferroviarias"`
- `"navantia"`
- `"aena"`
- `"correos"`, `"sociedad estatal correos"`
- `"paradores"`, `"paradores de turismo"`
- `"loteria"`, `"loterias y apuestas del estado"` (si interesa)

Y opcionalmente como `WATCHLIST_ORGS` para que aparezcan como tiles propios en la sección 06 del dashboard.

**Mejora siguiente** — parser dedicado del portal de RTVE: `https://convocatorias.rtve.es/puestos-ofertados`. Ofrece el listado completo de procesos de RTVE con su estado, sin depender del BOE. Misma ventaja que Las Rozas: detección temprana + garantía de plazo abierto si filtran por estado.

### Pendiente: variante "enfermería de empresa" en STRONG_PATTERNS

Algunos organismos —RTVE entre ellos— llaman a la especialidad **"Enfermería de Empresa"** en lugar de "Enfermería del Trabajo". Es la denominación histórica previa al MIR (en el catálogo del Ministerio siguen como sinónimos a efectos formativos), y sigue apareciendo en convocatorias del sector público estatal.

**Cambio:** ampliar `STRONG_PATTERNS` en `vigia/config.py` con:
- `r"enfermeri[ao]\s+de\s+empresa"`
- `r"enfermer[ao]\s+de\s+empresa"`
- `r"diplomado\s+en\s+enfermeria\s+de\s+empresa"`

Y añadir test en `test_extractor.py` con un título realista tipo "Convocatoria de la Corporación RTVE para plazas de Enfermería de Empresa".

Riesgo: ninguno aparente. "Enfermería de empresa" es lo bastante específico como para no producir falsos positivos.

---

## ~~🤖 Capa de enriquecimiento con IA~~ ✅ Resuelto (2026-04-25, commit `81b0b6d`)

Implementado `vigia/enricher.py` con Claude **Haiku 4.5** vía SDK oficial Anthropic. El enricher se invoca tras `filter_new` (solo enriquece items realmente nuevos para no pagar tokens en duplicados) y rellena `Item.summary`, que `notifier.py` ya mostraba si existía.

**Diseño:**
- Graceful degradation: si `ANTHROPIC_API_KEY` no está configurada, `enrich()` devuelve la lista intacta.
- Tolerancia a fallos: si una llamada concreta falla, ese item queda sin summary y los demás siguen.
- Sin streaming, sin thinking, sin caching (tarea acotada de ~250 tokens output).
- El extractor ahora copia `raw.text` (truncado a 2KB) al `Item.extra["raw_text"]` para que el enricher tenga contexto sin re-descargar nada.
- 7 tests con mocks del SDK Anthropic en `test_enricher.py`.

**Validado localmente** con la key real sobre 2 items reales (OEP 2025 Ayto Madrid + concurso traslados Comunidad Madrid). Resúmenes generados son concisos, factuales (no inventan datos), y cubren plazas/categoría/organismo/turno cuando aparecen en el contenido.

**Coste estimado:** ~$5/año al volumen actual (12 hallazgos/día × 600 tokens × 365 días con Haiku 4.5). Anthropic da $5 de crédito gratis a usuarios nuevos.

**Validación end-to-end por Telegram:** pendiente de la próxima novedad real (la BD ya tenía los 12 hallazgos previos).

---

## 👥 Auto-suscripción de terceros (sin tu intervención)

A día de hoy, añadir un nuevo destinatario al bot requiere:
1. Que la persona envíe un mensaje al bot.
2. Que tú llames manualmente a `getUpdates` para sacar su chat ID.
3. Que actualices a mano el Secret `TELEGRAM_CHAT_ID` en GitHub.

Eso no escala si quieres compartirlo con compañeros del gremio. Para que cualquiera pueda suscribirse autónomamente con un `/subscribe` al bot, hace falta:

### Arquitectura básica

- **El bot tiene que escuchar mensajes** (no solo enviar). Dos formas:
  - **Polling**: un proceso que llama `getUpdates` cada N segundos. Requiere un servicio siempre vivo → no encaja con GitHub Actions (que es batch).
  - **Webhook**: Telegram hace POST a una URL cuando llega un mensaje. Requiere un endpoint HTTPS público → encaja con un Cloudflare Worker, AWS Lambda, Vercel Function o similar (gratis o casi).

- **Persistencia de la lista de suscriptores** fuera de un Secret de GitHub:
  - Opción 1: rama `state` del repo (igual que `seen.db`), guardando `subscribers.json`. Lee/escribe el workflow + el endpoint webhook.
  - Opción 2: KV store del proveedor del webhook (Cloudflare KV, Upstash Redis…). Más robusto pero introduce dependencia.

- **Comandos del bot**:
  - `/start` → mensaje de bienvenida + explicación.
  - `/subscribe` → añade el `chat_id` a la lista.
  - `/unsubscribe` → lo elimina.
  - `/status` → comprueba si está suscrito.

### Control de abuso

Si lo abres a cualquiera:
- **Aprobación manual** (más seguro): el bot solo guarda solicitudes pendientes y tú las apruebas con `/approve <chat_id>` desde tu chat (que es admin).
- **Lista blanca por código de invitación**: `/subscribe ABC123` solo funciona si el código es válido.
- **Apertura total**: cualquiera con el username del bot puede suscribirse. Riesgo bajo si el bot es público y solo recibe alertas (no envías información sensible).

### Plan mínimo viable

1. **Cloudflare Worker** (free tier de sobra para esto) que actúa como webhook de Telegram.
2. KV namespace para la lista de chat IDs.
3. El Worker procesa `/subscribe` y `/unsubscribe`, escribiendo en KV.
4. El cron de GitHub Actions, en lugar de leer `TELEGRAM_CHAT_ID` de los Secrets, llama a un endpoint del Worker (`GET /subscribers`) protegido por un token compartido para obtener la lista actualizada.
5. `notifier.py` cambia mínimamente: en vez de leer `TELEGRAM_CHAT_ID` lee la lista del Worker.

Coste: 0 € si nos quedamos dentro del free tier de Cloudflare. Latencia añadida: ~50ms al inicio de cada run del cron, despreciable.

### Alternativa más sencilla (sin webhook)

Si solo quieres compartirlo con un puñado de gente y no te molesta intervenir manualmente:
- Mantener `TELEGRAM_CHAT_ID` como lista en el Secret (lo que tenemos ahora).
- Crear una pequeña página estática en GitHub Pages con un formulario que recoja el chat ID y te lo mande por email.
- Tú añades el ID al Secret a mano cuando recibas la solicitud. Tarda 30 segundos por solicitud.

---

## Otras ideas sueltas (para no olvidarme)

- **Logs persistidos:** además de la BD `seen.db` en la rama `state`, considerar volcar un CSV histórico de todos los hallazgos (no solo nuevos) para análisis posterior.
- ~~**Dashboard mínimo:**~~ ✅ Capa de datos resuelta (2026-04-25); ver sección "Dashboard web público" arriba. Falta el HTML, en manos de Claude Design.
- ~~**Test de fuentes "vivas":**~~ ✅ Resuelto (2026-04-25, commit `44f7240`). Añadido `python -m vigia.main --probe` que hace HEAD/GET ligero a la URL principal de cada fuente y muestra una tabla de salud. Integrado en `daily.yml` con `if: always() + continue-on-error: true` para que cada run del cron deje el estado de las fuentes en los logs sin afectar la conclusion del job.
