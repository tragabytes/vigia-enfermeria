# Backlog — vigia-enfermeria

Pendientes para retomar más adelante. Última actualización: 2026-04-26 (segunda iteración).

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

### ~~Optimización UX móvil del dashboard~~ ✅ Resuelto (2026-04-26)

Pulido de la navegación en móvil sin cambiar el contenido. Cambios aplicados en `web/app.js` y `web/styles.css`:

- **Doble "SYSTEM ONLINE" eliminado.** El indicador vivía a la vez en la status bar superior y en el `hero-meta` (esquina derecha). Se quita del hero — la status bar es la fuente única.
- **Animación de typing en el título.** En PC y móvil el `<h1>` arranca vacío y se va escribiendo char a char, con un typo intencional (`vigía-enfermenía`) que se corrige a `vigía-enfermería` simulando un humano tecleando. El cursor `▮` parpadea durante todo el proceso.
- **Counters lazy en móvil.** `countUp` se dispara con un `IntersectionObserver` cuando cada `[data-counter]` entra al viewport, en vez de animarse de golpe al cargar. En desktop se mantiene el comportamiento original (los counters están en viewport al cargar y disparan al instante).
- **Glitch-in de secciones al hacer scroll.** En ≤900px, las secciones 02-08 nacen con `opacity:0` (`prepGlitchMobile()` antes del fetch para evitar flash) y un IO les pone `.glitch-in` cuando entran al viewport. La animación es un keyframe de ~700ms con offset horizontal, hue-shift y `clip-path` que simula interferencia CRT. En desktop, sin IO, o con `prefers-reduced-motion`, se quitan las clases y se anima todo al instante via `fireAllAnimationsNow()`.
- **Bars + donut lazy en móvil.** Las `bar-row .fill` arrancan con `width:0` (CSS) y el donut con `stroke-dasharray="0 C"` solo en móvil. Cuando el panel `.intel` intersecta, JS aplica los target values y las transitions CSS hacen el sweep. En desktop el donut se renderiza directamente con su valor final (sin animación, comportamiento previo preservado).
- **Secciones colapsables en móvil.** Cada `.section-title` es clickable: toggle de `.collapsed` esconde el contenido y rota un chevron `▾`. El handler se añade siempre, pero el CSS asociado vive dentro del `@media (max-width: 900px)`, así que en desktop clickar es un no-op visual.

Limpieza colateral: eliminadas reglas CSS muertas de `.hero .hero-meta .right` (sobraban tras quitar el SYSTEM ONLINE) y el bloque `.bar.pre-chart` / `.donut-svg.pre-chart` que apuntaban a clases que el JS nunca añadía. Verificado vía preview en viewport mobile (375x812) y desktop (1280x800).

### ~~Hits clickables en la tabla SOURCES~~ ✅ Resuelto (2026-04-26, commit `57f7835`)

En la sección 05 (`SOURCES · TARGETS PROBED`), el número de **HITS** se renderiza como un `<button class="hits-link">` para fuentes con `total_hits > 0`. Al pulsarlo:

1. Se asigna el valor al `<select id="f-source">` de la `cmdbar` de la sección 03.
2. `syncFilter() + drawTable()` re-pinta el feed histórico filtrado.
3. `histSection.scrollIntoView({behavior:'smooth', block:'start'})` hace scroll suave hasta la sección. Si en móvil estaba colapsada, se descolapsa primero para que el filtro sea visible tras el scroll.

Click sobre el resto de la fila mantiene el comportamiento previo (toggle del FIELD MEMO con el `detail` de la fuente). Lo que evita el solape es un `e.stopPropagation()` en el handler del botón.

Estética: cursor pointer y borde fósforo tenue en hover/focus, sin alterar el color verde del número. Verificado con preview en desktop (1280×800).

### Pendiente: enricher Nivel 2 — tool use + output JSON estructurado

Evolucionar el enricher actual (single-shot Haiku que devuelve un string de ~200 chars) hacia una llamada con **tool use** y **respuesta JSON estructurada**. No es un agente loop completo (Nivel 3); seguimos en `client.messages.create()`, pero con dos herramientas registradas y un schema de salida fijo. El objetivo: confirmar links, extraer fechas reales y rellenar el watchlist con datos duros en vez de heurística de 90 días.

**Por qué.** Hoy el `summary` solo reformula lo que ya viene en el título. No sabemos si el link sigue vivo, no extraemos plazo de inscripción, no contamos plazas. La sección 06 del dashboard (`ACTIVE/COLD`) es una heurística pragmática que falla en bolsas permanentes y en procesos que ya cerraron. El Nivel 3 (agente con loop) sería más potente pero introduce coste impredecible y complejidad operativa que no compensa al volumen actual.

**Tools a registrar.**
- `fetch_url(url)` — descarga el HTML/PDF del link de la convocatoria. Whitelist estricta de dominios oficiales (`boe.es`, `bocm.es`, `madrid.es`, `comunidad.madrid`, `convocatoriascanaldeisabelsegunda.es`, `codem.es`, `datos.madrid.es`) para evitar SSRF. Tamaño máximo 5MB.
- `web_search(query)` *(opcional, fase 2)* — `web_search` nativo de la API de Anthropic para cruzar con BOE/BOCM cuando el link primario no dé fecha. Coste extra (~$10/1000 búsquedas); activable con flag.

**Schema de salida (JSON).**
```json
{
  "summary":    "string corto, ~200 chars, estilo telegrama",
  "deadline":   "YYYY-MM-DD" | null,
  "plazas":     integer | null,
  "organismo":  "string" | null,
  "url_bases":  "string (URL al PDF de bases)" | null,
  "link_alive": true | false,
  "confidence": "high" | "medium" | "low"
}
```

**Plan de implementación.**
1. Migración BD idempotente: añadir `deadline TEXT`, `plazas INTEGER`, `organismo TEXT`, `url_bases TEXT`, `link_alive INTEGER`, `enriched_at TEXT` a `items`. Mantener `summary`. Opcional: persistir `raw_text TEXT` para re-enriquecer históricos sin re-descargar.
2. `vigia/enricher.py`: prompt nuevo a JSON, registro del tool `fetch_url`, parseo con `json.loads` y validación contra schema (`dataclass` con `__post_init__` o `pydantic` si entra como dep).
3. `vigia/storage.py`: nuevo `update_enrichment(item, payload)` que persiste todos los campos de una vez. Sustituye al actual `update_summary`.
4. `vigia/dashboard.py`: `_items_payload` expone los nuevos campos. `_targets_payload` usa `deadline >= today` cuando exista, fallback a la heurística 90d si es `NULL`.
5. Frontend (`web/app.js`): la card del feed muestra `📅 Plazo: 15/06/2026 · 47 plazas` cuando estén disponibles. Badge `LINK DEAD` en rojo si `link_alive == false`. La tabla 03 (Historical) añade columna opcional "DEADLINE".
6. Mantenimiento: extender `vigia/maintenance.py` con `enrich_pending_v2(storage)` para re-procesar los ~12 items históricos. El prompt-cache de Anthropic puede abaratar el reenriquecido.
7. Tests con mocks del SDK + tool use: respuesta válida, JSON malformado, tool error, dominios fuera de whitelist, link 404.

**Coste estimado.** ~$30-50/año al volumen actual (12 items/día × 2-3 iteraciones × ~1500 tokens output). Latencia: 10-20s/item (vs. 2s hoy). Aceptable: 12 × 15s ≈ 3 min extra de workflow.

**Decisiones a tomar antes de empezar.**
- Si el link está muerto pero el item es real → guardar `link_alive=false` y mostrar badge; no descartar el item.
- ¿Re-fetchamos en cada run o solo una vez? → solo una vez (campo `enriched_at`); maintenance re-enriquece cuando se actualice el prompt.
- ¿`web_search` de pago en MVP? → empezar sin, ver si `fetch_url` solo cubre suficientes casos.

**Migración hacia Nivel 3 (futuro).** Si Nivel 2 funciona pero queremos detectar duplicados entre items o vincular resoluciones con sus correcciones, entonces Claude Agent SDK con loop. No bloqueante hoy.

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

### ~~4. SOURCES con `null/UNKNOWN` en producción tras maintenance~~ ✅ Resuelto (2026-04-26, commit `1dd68cb`)

**Síntoma:** la sección 05 del dashboard mostraba todas las fuentes con `URL: null`, `HTTP: null`, `STATUS: UNKNOWN`. Solo la columna HITS tenía valores reales.

**Diagnóstico.** El `sources_status.json` se generó en algún momento con `probe_results=None` y sin un JSON previo en `docs/data/`, cayendo al branch `else` de `_sources_payload()` que escribe entradas degradadas (todo a `null`/`unknown`). Los runs posteriores entraban al branch `elif sources_path.exists()`, leían el JSON degradado y lo reutilizaban tal cual sin regenerar — bug latente desde el commit `570f5e0`.

**Fix.** Nueva función `_refresh_total_hits()` en `vigia/dashboard.py`: cuando se reutiliza el JSON existente, los `total_hits` por fuente se refrescan contra la BD y las fuentes nuevas con hits pero sin probe se añaden marcadas como `unknown`. El resto de campos del último probe (url/code/status/last_probe_at) se mantienen — el contrato "no degradar el último probe" sigue vigente, validado por `test_sin_probe_no_pisa_sources_status_existente`.

**Acción inmediata.** Disparar `daily.yml` manualmente vía `gh workflow run daily.yml` ([run 24953550653](https://github.com/tragabytes/vigia-enfermeria/actions/runs/24953550653)) regeneró el JSON con datos vivos. Tras el push de los 4 commits a main, el siguiente cron (lunes 27/04 08:00 UTC) y futuros maintenance ya no pueden volver a degradar la sección.

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

### ~~Empresas públicas estatales (RENFE, ADIF, RTVE, Navantia, AENA, Correos…)~~ ✅ Cobertura indirecta (2026-04-26, commit `de9b67c`)

Añadidos a `HEALTH_ORGS` (bocm.py) y `DEPT_KEYWORDS_FOR_BODY` (boe.py):
- `rtve`, `radio y television espanola`
- `renfe`, `renfe operadora`
- `adif`, `administrador de infraestructuras ferroviarias`
- `navantia`
- `aena`
- `correos`, `sociedad estatal correos`
- `paradores`, `paradores de turismo`
- `loterias y apuestas`

Cuando una de estas empresas aparezca como organismo emisor en BOE/BOCM, se descargará el cuerpo/PDF para buscar la especialidad. `test_organism_coverage.py` parametrizado con los nombres oficiales reales (50 → 70 casos cubiertos).

**Pendiente como mejora futura:**
- Añadir las anteriores a `WATCHLIST_ORGS` para que aparezcan como tiles propios en la sección 06 del dashboard.
- Parser dedicado del portal de RTVE: `https://convocatorias.rtve.es/puestos-ofertados`. Ofrece el listado completo de procesos de RTVE con su estado, sin depender del BOE. Misma ventaja que Las Rozas: detección temprana + garantía de plazo abierto.

### ~~Variante "enfermería de empresa" en STRONG_PATTERNS~~ ✅ Resuelto (2026-04-26, commit `f409b90`)

Añadidas tres variantes a `STRONG_PATTERNS` para cubrir la denominación histórica previa al MIR (todavía en uso en RTVE y otras empresas públicas estatales):
- `r"enfermeri[ao]\s+de\s+empresa"`
- `r"enfermer[ao]\s+(?:[ao]\s+)?de\s+empresa"` — soporta "Enfermero/a de Empresa" tras `normalize()` (la `/` se vuelve espacio).
- `r"diplomado\s+en\s+enfermeria\s+de\s+empresa"`

Dos tests nuevos en `test_extractor.py` con títulos realistas tipo RTVE y RENFE.

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
