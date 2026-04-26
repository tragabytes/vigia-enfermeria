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

### ~~Enricher Nivel 2 — tool use + output JSON estructurado~~ ✅ Resuelto (2026-04-26)

El enricher v1 (single-shot Haiku 4.5 que devolvía string ~200 chars) se ha reemplazado por una llamada agentica corta a **Claude Sonnet 4.6** con tool use sobre la URL real de la convocatoria. La salida es JSON estructurado (16 campos) que alimenta filtrado de falsos positivos, watchlist con deadlines reales y notificaciones accionables.

**Schema final implementado** (`Item` dataclass + columnas SQL aditivas):

```jsonc
{
  "is_relevant": true|false,        // descarta FP confirmados (Salud Mental, Pediátrica, Matrona…)
  "relevance_reason": "string",
  "process_type": "oposicion|bolsa|concurso_traslados|interinaje|temporal|otro",
  "summary": "~200 chars (estilo telegrama)",
  "organismo": "SERMAS",            // entidad convocante normalizada
  "centro": "Hospital La Paz",
  "plazas": 12,
  "deadline_inscripcion": "YYYY-MM-DD",
  "fecha_publicacion_oficial": "YYYY-MM-DD",
  "tasas_eur": 30.5,
  "url_bases": "URL al PDF de bases",
  "url_inscripcion": "URL portal pasarela",
  "requisitos_clave": ["Título de Enfermería del Trabajo", "Experiencia 1 año"],
  "fase": "convocatoria|admitidos_provisional|admitidos_definitivo|examen|calificacion|propuesta_nombramiento|otro",
  "next_action": "Presentar instancia online antes del 15/05/2026",
  "confidence": 0.0..1.0
}
```

**Tool registrada.** `fetch_url(url)` con whitelist estricta de 17 hostnames oficiales (BOE, BOCM, sede madrid/comunidad madrid, datos.madrid, convocatoriascanaldeisabelsegunda, codem, transparencia.*). Anti-SSRF: scheme http/https obligatorio, validación del host antes de la request y tras los redirects, límite 5MB, timeout 15s, extracción de PDF (pdfplumber, max 30 páginas) y HTML (BeautifulSoup, sin `<script>`/`<style>`/etc). Loop limitado a `MAX_TOOL_ITERATIONS = 4` para cortar runaway costs.

**Cambios derivados desbloqueados.**
- **Falsos positivos a "papelera".** El pipeline filtra `is_relevant=false` antes de Telegram (`main.py`). Siguen guardados en BD para auditoría; el frontend los oculta por defecto y los revela con el toggle `show discarded` en la sección 03.
- **Watchlist con deadlines reales.** `_targets_payload` deja de depender de la heurística de 90 días: cada organismo expone `nearest_deadline`, `days_until`, `urgent` (≤7 días), `latest_phase`. La sección 06 ordena urgent → active → cold y pinta countdown amber para los urgentes.
- **Telegram accionable.** `notifier._format_item` añade chips de proceso/plazas/tasa, línea de cierre con countdown ("en 18 días", "HOY", "mañana"), `next_action` y enlace a bases si difiere del anuncio principal. El descartado nunca llega al chat.
- **Frontend nuevo.** Cards y filas expandidas muestran chips estructurados, link a bases, organismo, next_action. El header del summary distingue `claude-sonnet-4-6` (v2) / `claude-haiku-4-5` (v1 legacy) / `pending enrichment` según `enriched_version`.

**Migración BD.** Aditiva e idempotente: 17 columnas nuevas (`is_relevant`, `relevance_reason`, `process_type`, `organismo`, `centro`, `plazas`, `deadline_inscripcion`, `fecha_publicacion_oficial`, `tasas_eur`, `url_bases`, `url_inscripcion`, `requisitos_clave`, `fase`, `next_action`, `confidence`, `enriched_at`, `enriched_version`). Mismas garantías que la migración previa de `summary`: ALTER TABLE ADD COLUMN, no destructivo, BDs viejas se actualizan al primer run sin perder filas. La constante `ENRICHMENT_VERSION = 2` es el ancla del backfill — `iter_items_for_enrichment()` rebobina cuando se sube.

**Backfill histórico.** `enrich_pending(storage)` selecciona items con `enriched_version IS NULL OR < ENRICHMENT_VERSION` y los reprocesa. El workflow `maintenance.yml` ya estaba cableado para esto: tras mergear, ejecutar manualmente `gh workflow run maintenance.yml` con `ANTHROPIC_API_KEY` en secrets reprocesa los 24 items históricos. Coste único: ~$0.50 (24 × ~5k tokens × Sonnet $15/MTok output + $3/MTok input).

**Coste recurrente estimado.** ~$3-5/año al volumen real (≤3 items relevantes/día × ~5k tokens × Sonnet 4.6). El pipeline diario solo enriquece items nuevos (post `filter_new`); cero gasto cuando no hay novedades.

**Tests añadidos.** 26 tests en `test_enricher.py`: graceful degradation (sin key, sin SDK, lista vacía), JSON directo, JSON envuelto en fence, loop con tool use de 1 turno, runaway con tope a `MAX_TOOL_ITERATIONS`, sanitización de enums (process_type/fase fuera de catálogo → "otro", fechas mal formateadas → null, plazas como string → int, tasas con coma decimal), aislamiento de fallos por item, whitelist de fetch (dominio fuera de la lista, scheme distinto a http, redirect a host malicioso), backfill `enrich_pending` con item legacy v1 → v2.

**Decisiones tomadas durante la implementación.**
- Modelo: **Sonnet 4.6** directo (no Haiku) — al volumen real, los días sin novedad dominan; el coste extra es marginal y la calidad de extracción merece la pena.
- `is_relevant=false` se persiste pero se oculta por defecto, con toggle de auditoría — el usuario puede verificar que el descartado era correcto sin abrir la BD.
- Items con `enriched_version=NULL` (no enriquecidos todavía) se notifican igual — graceful degradation cuando el enricher está apagado por falta de key.
- `confidence` es float `0..1`, no enum `high/medium/low` — más útil para ordenar y filtrar.
- Cap de 4 iteraciones (no 2) en el loop tool use — Sonnet a veces hace 2 fetches secuenciales (anuncio + PDF de bases) antes de responder.

**Migración hacia Nivel 3 (futuro).** Si en el futuro queremos vincular item existente con su corrección/anexo (timeline de la convocatoria), entonces Claude Agent SDK con loop. No bloqueante hoy.

### Pendiente: bug — fecha `published` siempre = `detected` en items de Comunidad de Madrid

**Síntoma observado en producción (2026-04-26):** todos los items de la sección 03 (Historical DB) procedentes de `comunidad_madrid` muestran `published = 2026-04-26` (idéntica al `detected`), aunque sean bolsas de 2024 / 2025 etiquetadas explícitamente con esos años en el título.

**Diagnóstico.** En [`vigia/sources/comunidad_madrid.py:121`](vigia/sources/comunidad_madrid.py:121), `pub_date = date.today()` es el fallback cuando el regex `Apertura.*?(\d{2}/\d{2}/\d{4})` no matchea. Las bolsas en estado "Subsanación", "En tramitación" o cerradas no muestran "Apertura de plazo" en el bloque `div.estado` — solo lo hacen las que tienen plazo abierto. Resultado: el sistema asume que se publicaron hoy.

**Fix propuesto (1-2h):**
1. Probar regex adicionales sobre el `div.estado`: "Fin de plazo", "Resolución de", "Última actualización", "Fecha BOCM".
2. Bajar el detalle del item (link relativo bajo el título) y buscar fecha de publicación oficial ahí.
3. Como último fallback: extraer el año de `(YYYY)` que aparece en muchos títulos ("Bolsa única (2024). Subsanación") y usar `date(YYYY, 1, 1)` para indicar "no exacta, año conocido".
4. Añadir test que use HTML de respuesta real con cada uno de los estados.

Validar el fix también contra los 11 items históricos en BD: corregir su `fecha` con un script de mantenimiento puntual.

---

### Pendiente: parser propio Metro de Madrid (caso `Técnico/a en Enfermería del Trabajo`)

**Caso real:** [https://www.metromadrid.es/es/oferta-empleo/tecnicoa-en-enfermeria-del-trabajo-en-el-servicio-de-salud-laboral-del-area-de-prevencion-y-salud-laboral](https://www.metromadrid.es/es/oferta-empleo/tecnicoa-en-enfermeria-del-trabajo-en-el-servicio-de-salud-laboral-del-area-de-prevencion-y-salud-laboral) — el sistema NO la pilló.

**Estado actual.** [`vigia/sources/metro_madrid.py`](vigia/sources/metro_madrid.py) es un stub porque `metromadrid.es` está protegido por WAF (F5/Akamai-style). Devuelve "Request Rejected" a cualquier UA/IP no-autorizado. Verificado el 2026-04-26 con UA Firefox real desde IP no-española: HTTP 200 con cuerpo de 245 bytes "Request Rejected".

**Implicación.** Metro Madrid contrata directamente vía su portal — las plazas de su Servicio de Salud Laboral NO siempre acaban en BOE/BOCM (al ser una S.A. pública con autonomía contratante). Hoy no las vemos.

**Solución requiere:** ejecutar el cron desde IP española. Ver tarea de "Investigar acceso desde IP española" más abajo. Una vez resuelta esa, implementar el parser dedicado del portal de oferta de empleo de metromadrid.es (HTML server-side, listado de ofertas activas + detalle).

---

### Pendiente: parsers de universidades públicas de Madrid (UAM, UCM, UPM, URJC, UC3M, UAH)

Las universidades públicas convocan plazas para sus servicios de prevención y unidades sanitarias. Casos reales que perdemos:

- **UAM** — [Pruebas selectivas ingreso Escala Especial Superior de Servicios — Enfermero (nov 2024)](https://www.uam.es/uam/ptgas/concursos-oposiciones-bolsas/pruebas-selectivas-ingreso-escala-especial-superior-de-servicios-enfermero-noviembre-2024)
- **UCM** — [Orden 4 DU — Enfermería del Trabajo](https://www.ucm.es/orden-4-du-enfermeria-del-trabajo)
- **UPM** — algo reciente (URL exacta a investigar)
- **URJC, UC3M, UAH** — añadir por completitud

Estructura típica: cada universidad tiene una sección "Concursos / Oposiciones / Bolsas" en su portal de PTGAS / RR.HH. donde lista las convocatorias activas. Cada plaza enlaza a PDF de bases.

**Trabajo:**
1. Investigar selectores HTML de cada portal universitario.
2. Crear `vigia/sources/universidades_madrid.py` (un solo módulo con varias URLs base) o uno por universidad.
3. Extraer listado + detalle + PDFs de bases (whitelist anti-SSRF por universidad).
4. Añadir cada universidad a `WATCHLIST_ORGS` (T-27 UAM, T-28 UCM, etc.).
5. Tests con mocks.

Estimación: 1-2h por universidad.

---

### Pendiente: tracking de proceso específico en Comunidad de Madrid

**URL en seguimiento manual del usuario:** [https://www.comunidad.madrid/empleo/diplomado-enfermeria-trabajo](https://www.comunidad.madrid/empleo/diplomado-enfermeria-trabajo)

Esta es una página estática del portal `www.comunidad.madrid` (NO `sede.comunidad.madrid` que es lo que monitorizamos hoy). Es una "ficha de proceso" que describe la categoría profesional Diplomado en Enfermería del Trabajo y enlaza a las convocatorias activas cuando existen.

**¿El sistema avisará si sale algo nuevo?**
- *Probablemente sí* indirectamente: cuando se publique una convocatoria concreta (bolsa, oposición, traslados) para esta categoría, aparecerá en el buscador `sede.comunidad.madrid/buscador?t=enfermeria` que ya monitorizamos via `comunidad_madrid.py`.
- *Pero no garantizado*: si la "ficha del proceso" se actualiza ANTES de que la convocatoria salga (cambio de fecha previsto, novedad informativa), no lo detectaríamos. La ficha tiene su propio ciclo de vida.

**Tarea:** añadir un parser específico que monitorice la URL del proceso (HTTP GET periódico, hash del cuerpo o detección de cambios en `<time>` / sección de convocatorias). Si cambia, generar un `RawItem` con marcador "ACTUALIZACIÓN DE FICHA". Patrón mínimo, ~1h.

---

### Pendiente: investigación profunda del problema de IP geo-bloqueada

**Estado.** Hoy `BOAM`, `ayuntamiento_madrid` y `metro_madrid` son fuentes degradadas porque `madrid.es` y `metromadrid.es` filtran las IPs de los runners de GitHub Actions (Azure US/EU). Tenemos workaround parcial (`datos_madrid.py` vía API CKAN), pero:

- BOAM: no vemos las disposiciones diarias del Boletín del Ayuntamiento.
- Ayuntamiento Madrid: solo cobertura indirecta vía BOE / datos.madrid.
- Metro Madrid: contrata por portal propio que no vemos en absoluto. **Plazas perdidas comprobadas.**

**Esto no debería quedar así.** Opciones a investigar a fondo:

1. **Self-host en VPS español.** Hetzner Helsinki / Contabo Madrid (~3-5€/mes) o Raspberry Pi en casa con conexión doméstica. Ventaja: IP española real, sin tonterías. Desventaja: salir de GitHub Actions implica gestionar cron, persistencia BD, SSH, monitoreo.

2. **Proxy en región Madrid solo para fuentes geo-bloqueadas.** fly.io con `regions=mad`, o Vercel Edge Functions con `region: ['mad1']`, o un Cloudflare Worker corriendo en datacenter cercano. El cron seguiría en GitHub Actions; solo redirigiría las requests a `madrid.es` / `metromadrid.es` a través del proxy. Ventaja: cero migración. Desventaja: latencia añadida + posible coste si supera free tier.

3. **Servicio comercial de proxies residenciales.** Bright Data / Smartproxy con IP rotativa española. Desventaja: caro (~$10-30/mes) + ético cuestionable + a veces detectado igualmente.

4. **Tor exit node en España.** Free pero detectable y poco fiable.

**Decisión a tomar:**
- Si vamos por 1: dimensionar VPS, decidir si copiamos todo el stack o solo movemos cron + BD a allí dejando el dashboard publicado a gh-pages.
- Si vamos por 2: probar fly.io primero (free tier amplio, region MAD disponible). Mock-up de proxy con un pequeño script que reciba URL + auth token y reenvíe.

**Validar primero:** ¿es realmente la IP el factor único, o también el UA / cookies / TLS fingerprint? Ya validamos UA Firefox y headers básicos. Para confirmar 100%: probar la URL desde casa (IP española residencial) con curl + Firefox UA y ver si pasa. Si SÍ pasa, IP es el único filtro y opciones 1/2 son válidas. Si NO pasa, hay protección JS-only o TLS fingerprinting y necesitamos navegador real headless (Playwright) — eso es otro nivel de complejidad.

Prioridad: **alta**. Cada plaza perdida en Metro/BOAM es señal directa de fallo.

---

### ~~Variante "ATS/DUE" en STRONG_PATTERNS~~ ✅ Resuelto (2026-04-26)

Añadidas variantes para la denominación pre-Bolonia "ATS/DUE" (Ayudante Técnico Sanitario / Diplomado Universitario en Enfermería) en `STRONG_PATTERNS` y `WEAK_CONTEXT_PATTERNS`:
- STRONG: `ats due de prevencion`, `ats due de salud laboral` y variantes con guión/barra.
- WEAK: `ats due` + (`prevencion` | `salud laboral` | `riesgos laborales`) en ventana de 100 chars.

Caso real motivador: [BOE-A-2022-23854](https://www.boe.es/diario_boe/txt.php?id=BOE-A-2022-23854) (Tribunal de Cuentas, 30/12/2022) — "Resolución por la que se convoca proceso selectivo, por el turno de acceso libre, para la provisión de plaza vacante de ATS/DUE de Prevención y Salud laboral." Verificado: el extractor ahora hace match (`Categoría: oposicion`).

---

### Pendiente: revisar pickup de CIEMAT tras cron del 27/04/2026

Tras commit `b8d47f3` (parser CIEMAT con extracción de PDFs anexos), el siguiente cron del lunes **27/04/2026 a las 08:00 UTC** debería:

1. Ejecutar el parser nuevo `vigia/sources/ciemat.py` por primera vez en producción.
2. Detectar la oferta `2380` (Concurso Específico I 2026 — Personal Funcionario CIEMAT) cuyo PDF de perfiles formativos contiene "Especialidad de Enfermería del trabajo".
3. Pasarla por extractor + enricher v2 → JSON estructurado con plazas, organismo, deadline.
4. Notificar por Telegram + sumar 1 hit al tile `T-23 CIEMAT` del watchlist.

**Cosas que validar el lunes** cuando llegue la notificación / refrescando el dashboard:
- ¿El item aparece en el feed con `is_relevant=true` y la oferta etiquetada como CIEMAT?
- ¿El enricher extrajo deadline/plazas correctamente del PDF (puede que el PDF no tenga esos campos explícitos)?
- ¿El tile T-23 CIEMAT del watchlist pasa a `hits=1` y `active=true` (o `urgent` si plazo ≤7 días)?
- ¿La fuente `ciemat` en la sección 5 del dashboard reporta `status=ok` con hits=1?

Si algo no encaja: ajustar selectores, prompt del enricher, o la lista PDF host whitelist según lo observado.

### Pendiente: parsers propios para OPIs estatales (CIEMAT, IAC, INIA, ISCIII…)

CIEMAT publica plazas en su web propia (`ciemat.es/ofertas-de-empleo/-/ofertas/oferta/<id>`) que no monitorizamos directamente. Las convocatorias en BOE bajo "Ministerio de Ciencia, Innovación y Universidades" son OPIs conjuntas y a veces el HTML del item no da pista en los primeros KB. Pillamos el caso por departamento + plan B (anexos PDF) cuando aplica, pero un parser dedicado al portal CIEMAT detecta antes y cubre plazas que solo viven ahí.

Mismo patrón aplica a otros Organismos Públicos de Investigación con servicio de prevención propio:

- **CIEMAT** — Centro de Investigaciones Energéticas, Medioambientales y Tecnológicas. Portal: `ciemat.es/ofertas-de-empleo`. Ya en watchlist (T-23).
- **IAC** — Instituto de Astrofísica de Canarias. Portal: `iac.es/es/empleo`.
- **INIA** — Instituto Nacional de Investigación y Tecnología Agraria y Alimentaria (ahora INIA-CSIC). Portal: `inia.es` (a investigar URL exacta de empleo).
- **ISCIII** — Instituto de Salud Carlos III. Portal: `isciii.es/Personal/Paginas/EmpleoPublico.aspx`.
- **IEO** — Instituto Español de Oceanografía. Portal: `ieo.es/empleo` (ahora dependiente del CSIC).
- **CSIC** — Consejo Superior de Investigaciones Científicas (paraguas de varios). Portal: `csic.es/es/empleo`.

Patrón de implementación (similar a `vigia/sources/canal_isabel_ii.py`):
1. Una clase Source por organismo, con `name`, `probe_url`, `fetch(since_date)`.
2. Listar las ofertas activas del portal (HTML render server-side; CSS selectors a investigar).
3. Para cada oferta, descargar la página de detalle y devolver `RawItem(title, url, text)`.
4. El extractor + enricher v2 ya hacen el resto (matcher + estructurado).
5. Añadir cada uno a `WATCHLIST_ORGS` con su id (T-27, T-28…) y patterns.

Coste: ~1-2h por parser, x6 organismos = 6-12h totales si se quieren todos. Priorización razonable: **CIEMAT primero** (caso real motivador), **ISCIII segundo** (instituto sanitario, mayor probabilidad de plazas de Enfermería del Trabajo en su SP), el resto por orden de tamaño/relevancia. Validar primero el portal HTML de CIEMAT — si está renderizado vía JS-only (como `administracion.gob.es`), habría que delegar al BOE/BOCM y abandonar este parser.

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

### ~~4-bis. Regresión SOURCES null/UNKNOWN tras `maintenance.yml` (segunda ocurrencia)~~ ✅ Blindado (2026-04-26, commits `ae58586` + `94ed7cd`)

**Síntoma.** El primer run real de `maintenance.yml` con el enricher v2 reprodujo el mismo síntoma: las 6 fuentes con hits acabaron en `status=unknown`/`code=null` en `gh-pages`.

**Diagnóstico.** El fix de `1dd68cb` añadió `_refresh_total_hits` para que, si el JSON existía en disco, no se degradara. Pero en CI el workflow hace checkout limpio: `docs/data/` arranca vacío y el JSON bueno solo vive en `gh-pages`. Por tanto `dashboard.export_all` veía `sources_status.json` ausente, caía al branch `else`, escribía un payload degradado, y el step "Publicar dashboard" lo subía a `gh-pages` haciendo `rm -rf data/* && cp docs/data/* data/`, pisando el bueno.

**Fix triple capa** para que esta forma del bug ya no pueda escapar:

1. **Código** (`vigia/dashboard.py`): cuando `probe_results=None` y el JSON tampoco existe en disco, **no escribir el fichero** y emitir `logger.warning`. Mejor que la sección quede transitoriamente vacía a que muestre datos falsos.
2. **Workflows** (`maintenance.yml` + `daily.yml`): nuevo step "Restaurar último snapshot del dashboard" que trae `data/sources_status.json` desde `gh-pages` a `docs/data/` antes de correr Python, usando `git show FETCH_HEAD:path > file` (no `git checkout`, que ensucia el índice y rompe los `git checkout -B _state_tmp/_pages_tmp` posteriores con `local changes would be overwritten`).
3. **Frontend** (`web/app.js`): `fetch('data/sources_status.json')` cae a `[]` con `.catch(() => [])` igual que `targets`/`changelog`. `renderSources` pinta un placeholder `NO PROBE DATA — RUN --probe TO REFRESH` en lugar de tabla rota.

**Test de regresión.** `test_sin_probe_y_sin_snapshot_previo_no_escribe_degradado` en `tests/test_dashboard.py` pinea el contrato: si no hay probe ni snapshot previo, `dashboard.export_all` no crea `sources_status.json`. 194/194 tests offline pasan.

**Validación end-to-end.** Tras los pushes, `daily.yml` ([run 24955464750](https://github.com/tragabytes/vigia-enfermeria/actions/runs/24955464750)) regeneró el JSON con `--probe`, y `maintenance.yml` ([run 24955590508](https://github.com/tragabytes/vigia-enfermeria/actions/runs/24955590508)) corrió sin degradar nada — las 10 fuentes (6 OK + 2 error 403 + 2 skipped) se preservaron en `gh-pages`. La cadena de degradación CI → push → gh-pages está cortada en tres puntos distintos.

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

## ~~🤖 Capa de enriquecimiento con IA — v1 (Haiku string-only)~~ ✅ Sustituida por v2 (Sonnet + tool use, 2026-04-26)

Implementación inicial con Claude **Haiku 4.5**: `enrich()` recibía la lista de items nuevos tras `filter_new` y rellenaba `Item.summary` (string ~200 chars). Sustituida por la v2 estructurada — ver "Enricher Nivel 2" arriba. La compatibilidad con summaries v1 se conserva: items con `enriched_version=1` siguen pintándose en el dashboard mientras el backfill v2 los procesa.

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
