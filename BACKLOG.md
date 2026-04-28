# Backlog — vigia-enfermeria

Pendientes para retomar más adelante. Última actualización: 2026-04-28 (segunda iteración).

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

### ~~Bug — fecha `published` siempre = `detected` en items de Comunidad de Madrid~~ ✅ Resuelto en código (2026-04-28)

**Síntoma original (2026-04-26):** los 11 items de `comunidad_madrid` mostraban `published = 2026-04-26` aunque fueran bolsas de 2024/2025 etiquetadas con esos años en el título.

**Causa raíz.** [`vigia/sources/comunidad_madrid.py:121`](vigia/sources/comunidad_madrid.py:121) usaba `pub_date = date.today()` como fallback cuando el regex `Apertura.*?(\d{2}/\d{2}/\d{4})` no matchaba. Tras inspección del HTML real (28/04/2026), el listado solo expone fecha en `div.estado` para items "En plazo" (`Inicio: DD/MM/YYYY | Fin: DD/MM/YYYY`). Los estados "En tramitación" / "Plazo indefinido" / "Finalizado" — que son la inmensa mayoría — no traen fecha en el listado.

**Fix aplicado.** Cascada de fallbacks ordenada por fiabilidad descendente, implementada en `_resolve_pub_date`:

1. **Listado** — regex ampliado a `(?:Apertura|Inicio)\D*?(\d{2}/\d{2}/\d{4})` para cubrir el formato "En plazo".
2. **Detalle** — fetch de la página individual del item:
    - `.fecha-actualizacion` ("Última actualización: DD/MM/YYYY") como señal preferente.
    - Último `.hito-fecha` (el más antiguo del calendario de actuaciones) como respaldo cuando la página no tiene actualización.
3. **Título** — año `(YYYY)` entre paréntesis → `date(YYYY, 1, 1)` (rango admitido 2000..año actual+1).
4. **`date.today()` con `logger.warning`** — red de seguridad final que preserva el comportamiento previo de "no perder items" pero deja rastro en logs.

17 tests nuevos en `tests/test_comunidad_madrid_dates.py` cubren los cuatro niveles de la cascada y los HTML reales observados. **241/241 tests offline pasan.**

**Recálculo de fechas históricas implementado (2026-04-28).** Nueva función `maintenance.recalcular_fechas_comunidad_madrid(storage)` que itera items con `source='comunidad_madrid'`, aplica la cascada `detalle → año del título → today()` y persiste la fecha real vía `Storage.update_fecha(id_hash, fecha)`. Cableada en `_run_maintenance` para que la próxima ejecución del workflow `maintenance.yml` corrija los 11 items históricos automáticamente — idempotente: re-ejecuciones no tocan lo ya bien fechado. 3 tests nuevos en `test_maintenance.py`. **Aplicado en producción (2026-04-28, run [25038352118](https://github.com/tragabytes/vigia-enfermeria/actions/runs/25038352118))**: 11/11 fechas recalculadas en un único pase (rango real 2022-01-01 .. 2026-03-26 en lugar del incorrecto 2026-04-26 uniforme). Run posterior [25072512322](https://github.com/tragabytes/vigia-enfermeria/actions/runs/25072512322) confirmó idempotencia: `0/11` actualizadas, sin warnings.

---

### Pendiente: parser propio Metro de Madrid (caso `Técnico/a en Enfermería del Trabajo`)

**Caso real:** [https://www.metromadrid.es/es/oferta-empleo/tecnicoa-en-enfermeria-del-trabajo-en-el-servicio-de-salud-laboral-del-area-de-prevencion-y-salud-laboral](https://www.metromadrid.es/es/oferta-empleo/tecnicoa-en-enfermeria-del-trabajo-en-el-servicio-de-salud-laboral-del-area-de-prevencion-y-salud-laboral) — el sistema NO la pilló.

**Estado actual.** [`vigia/sources/metro_madrid.py`](vigia/sources/metro_madrid.py) es un stub porque `metromadrid.es` está protegido por WAF (F5/Akamai-style). Devuelve "Request Rejected" a cualquier UA/IP no-autorizado. Verificado el 2026-04-26 con UA Firefox real desde IP no-española: HTTP 200 con cuerpo de 245 bytes "Request Rejected".

**Implicación.** Metro Madrid contrata directamente vía su portal — las plazas de su Servicio de Salud Laboral NO siempre acaban en BOE/BOCM (al ser una S.A. pública con autonomía contratante). Hoy no las vemos.

**Solución requiere:** ejecutar el cron desde IP española. Ver tarea de "Investigar acceso desde IP española" más abajo. Una vez resuelta esa, implementar el parser dedicado del portal de oferta de empleo de metromadrid.es (HTML server-side, listado de ofertas activas + detalle).

---

### 🟡 Parsers de universidades públicas de Madrid — UCM, UAH, UAM implementadas (2026-04-28)

Las universidades públicas convocan plazas para sus servicios de prevención y unidades sanitarias. Casos reales detectados:

- **UAM** — [Pruebas selectivas ingreso Escala Especial Superior de Servicios — Enfermero (nov 2024)](https://www.uam.es/uam/ptgas/concursos-oposiciones-bolsas/pruebas-selectivas-ingreso-escala-especial-superior-de-servicios-enfermero-noviembre-2024)
- **UCM** — [Orden 4 DU — Enfermería del Trabajo](https://www.ucm.es/orden-4-du-enfermeria-del-trabajo)
- **UPM** — pendiente investigar URL.
- **URJC, UC3M, UAH** — pendientes (ver notas de research abajo).

**Implementado en `vigia/sources/universidades_madrid.py` (commit en `main`):** arquitectura genérica `UniConfig` + `UniListing` que permite añadir una nueva universidad como entrada de configuración sin tocar la clase Source. Filtrado fast-keyword aplicado al **texto completo del contenedor** del item (no solo al `<a>`) para soportar portales que llevan el título descriptivo en `<p>` o atributos sueltos. URL sintética `listing#sha1` cuando un portal no expone enlace por convocatoria.

#### UCM — Universidad Complutense de Madrid ✅
- **URL**: `https://www.ucm.es/convocatorias-vigentes-pas`
- **HTTP**: 200, sin WAF. Plataforma: CMS propio.
- **Selector**: `div.wg_txt li, div.wg_txt p`
- **Fechas**: "(Actualizado el DD/MM/YYYY)" (items recientes) o "(Actualizado el DD de mes de YYYY)" (históricos).
- **Notas**: el propio listado UCM tiene una sección "OTRAS UNIVERSIDADES: UAH" que enlaza directo a PDFs del BOE; el parser los acepta con su URL real (filtro por keyword, no por host) — captura indirecta de UAH desde UCM.

#### UAH — Universidad de Alcalá ✅
- **URLs (3 listados)**:
  - `https://www.uah.es/es/empleo-publico/PAS/funcionario/`
  - `https://www.uah.es/es/empleo-publico/PAS/laboral/`
  - `https://www.uah.es/es/empleo-publico/PAS/bolsa-de-empleo/`
- **HTTP**: 200, sin WAF.
- **Selector**: `ul.main-ul article` con `<h4 class="title-element"><a>` interno y `<p><strong>Resolución</strong> DD de mes de YYYY</p>` hermano.
- **Match real**: bolsa "Enfermería del Trabajo" (B1, link a PDF `B1-Enfermeria-03.09.2020.pdf`).
- **Limitación conocida**: en `bolsa-de-empleo/` algunos items adicionales viven dentro de un acordeón colapsado por JS — se detectan los `<article>` ya expandidos en el HTML inicial pero no los ocultos. Mejora futura: bajar también la URL del PDF cuando es accesible y extraer la fecha del filename `XX.YY.ZZZZ.pdf`.

#### UAM — Universidad Autónoma de Madrid ✅
- **URLs (2 listados)**:
  - `https://www.uam.es/uam/ptgas/listado-concursos-oposiciones-bolsas-personal-funcionario`
  - `https://www.uam.es/uam/ptgas/listado-concursos-oposiciones-bolsas-personal-laboral`
- **HTTP**: 200, sin WAF.
- **Selector**: `div.uam-card` (excluyendo cards con clase `uam-filters`, que es panel de filtros).
- **Caso atípico**: UAM **no expone enlaces `<a>` por convocatoria** — solo texto plano dentro de `<p>`. Generamos URL sintética `listing_url#<sha1[:12]>(title)` para que cada item tenga URL única determinista.
- **Match real validado end-to-end**: 7 items históricos de Enfermero/a y Titulado Medio Enfermería del Trabajo (resoluciones desde 2022 hasta enero 2026).
- **Limitación**: los cards llevan estado (`Resuelta` / `Abierta` / `Cerrada` / `Próxima apertura`) en `<span class="uam-becas-status">`, valioso para filtrar por fase. Hoy lo conservamos en `RawItem.text` pero no se persiste estructuradamente; el enricher v2 puede recuperarlo del cuerpo. Mejora futura: extraer `state` como campo dedicado del item.

#### Watchlist
Tres tiles añadidos a `WATCHLIST_ORGS`: T-27 UCM, T-28 UAH, T-29 UAM.

---

### Pendientes con notas técnicas reproducibles para una próxima iteración

#### UC3M — Universidad Carlos III de Madrid
- **URL útil descubierta**: `https://www.uc3m.es/empleo/pas/novedades_empleo_publico` (HTTP 200).
- **Plataforma**: CMS propio. Plantilla "MiniSiteB". El tradicional `Satellite/...Portal_de_Empleo` redirige a una página vacía con menú genérico.
- **Estructura del listado**: tabla `<tr>` con columnas `[CUERPO O ESCALA, GRUPO, ESPECIALIDAD, PLAZAS, FECHA PREVISTA CONVOCATORIA, FECHA PREVISTA INICIO PLAZO PRESENTACIÓN SOLICITUDES]`. 33 filas en captura de 2026-04-28.
- **Bloqueo**: las celdas son texto plano sin `<a>` por fila — necesitamos URL sintética igual que UAM. **Hoy ESPECIALIDAD = ADMINISTRACIÓN / BIBLIOTECA / INFORMÁTICA**, sin Enfermería. Cuando UC3M planifique una plaza de Enfermería, aparecerá en este cuadro.
- **Implementación recomendada**: añadir entrada en `UNI_CONFIGS` con `item_css="table tr"`, filtrar `<th>` (cabecera), aceptar URL sintética con fragment basado en el contenido completo del `<tr>`.
- **Estimación**: ~30 min con la arquitectura actual.

#### URJC — Universidad Rey Juan Carlos
- **URL**: `https://www.urjc.es/empleo-publico` (HTTP 200, ~1.1MB).
- **Plataforma**: Joomla `com_k2`.
- **Estructura del listado**: bloques `<p>` con texto y links a `https://sede.urjc.es/tablon-oficial/anexo/<id>/` (anexos individuales: notas, plantillas, resoluciones de cada fase del proceso).
- **Bloqueo**: en el momento del research había un proceso de Enfermería con 7 anexos publicados, pero ninguno apuntaba al texto de la convocatoria original — todos eran fases posteriores ("Plantilla provisional segundo ejercicio. Enfermería"). Parser sería ruidoso (un único proceso genera 7+ items).
- **Alternativa**: cobertura indirecta vía BOE 2A está activa para procesos selectivos universitarios. Confirmar que un proceso de Enfermería en URJC se publica vía BOE 2A antes de decidir.
- **Implementación recomendada**: dedicación posterior, después de validar la hipótesis de cobertura indirecta.

#### UPM — Universidad Politécnica de Madrid
- **Estado**: portal público de convocatorias PTGAS no localizado.
- **URLs probadas**: `/personal-administracion-servicios`, `/sfs/Rectorado/Gerencia/Servicio%20de%20Personal/...`, `/personal/empleo` → 404 o redirección a página genérica.
- **Hipótesis**: UPM publica todo vía BOE / BOUPM (boletín interno) sin listado HTTP libre. Confirmar consultando el organigrama y la sección RR.HH. del portal principal.
- **Acción**: requerirá research adicional con navegación manual antes de poder añadir parser.

#### Mejora compartida — URL al detalle real del PDF en UAM/UAH bolsa
Los items donde se cae a `today()` por falta de fecha en el listado (4 casos en validación end-to-end del 2026-04-28) podrían rescatarse extrayendo la fecha del filename del PDF cuando el `<a>` apunta a uno: patrón `(\d{2})\.(\d{2})\.(\d{4})\.pdf` o variantes con `_`/`-` separadores. Trabajo acotado: ~30 min y un par de tests.

---

### Pendiente: tracking de proceso específico en Comunidad de Madrid

**URL en seguimiento manual del usuario:** [https://www.comunidad.madrid/empleo/diplomado-enfermeria-trabajo](https://www.comunidad.madrid/empleo/diplomado-enfermeria-trabajo)

Esta es una página estática del portal `www.comunidad.madrid` (NO `sede.comunidad.madrid` que es lo que monitorizamos hoy). Es una "ficha de proceso" que describe la categoría profesional Diplomado en Enfermería del Trabajo y enlaza a las convocatorias activas cuando existen.

**¿El sistema avisará si sale algo nuevo?**
- *Probablemente sí* indirectamente: cuando se publique una convocatoria concreta (bolsa, oposición, traslados) para esta categoría, aparecerá en el buscador `sede.comunidad.madrid/buscador?t=enfermeria` que ya monitorizamos via `comunidad_madrid.py`.
- *Pero no garantizado*: si la "ficha del proceso" se actualiza ANTES de que la convocatoria salga (cambio de fecha previsto, novedad informativa), no lo detectaríamos. La ficha tiene su propio ciclo de vida.

**Tarea:** añadir un parser específico que monitorice la URL del proceso (HTTP GET periódico, hash del cuerpo o detección de cambios en `<time>` / sección de convocatorias). Si cambia, generar un `RawItem` con marcador "ACTUALIZACIÓN DE FICHA". Patrón mínimo, ~1h.

---

### ~~Investigación profunda del problema de IP geo-bloqueada~~ ✅ Resuelto como research (2026-04-28)

**Validación experimental** desde IP residencial española (Orange Sevilla, AS12479) con UA Firefox 121 y headers de navegador real.

#### `madrid.es` (BOAM + ayuntamiento_madrid) — **NO es IP geo, es Akamai Bot Manager**

Sigue devolviendo HTTP 403 desde la IP española. El cuerpo del 403 expone el origen del bloqueo:

```
Reference #18.b5f31402.1777385094.8ef59e8
https://errors.edgesuite.net/...
```

Y el header `Server-Timing: ak_p; desc="..."` confirma **Akamai**. `errors.edgesuite.net` es la URL de error de Akamai. Por tanto el filtro inspecciona **TLS fingerprint (JA3/JA4), HTTP/2 frame ordering, headers exactos del navegador y opcionalmente cookies/JS challenge** — no la IP de origen sola. La home raíz `https://www.madrid.es/` también devuelve 403; está toda la propiedad detrás del mismo Bot Manager. `datos.madrid.es` no comparte la configuración Akamai (HTTP 200 sin más), por eso ya funcionaba.

Para superarlo haría falta:
- `curl-impersonate` (TLS fingerprint Chrome/Firefox), no garantizado contra Akamai.
- Navegador real headless (Playwright/Chromium), runtime caro en GitHub Actions.

**Veredicto: descartar parser directo de `madrid.es`.** El ROI es bajo: las plazas relevantes acaban en **BOE sección 2B** (Administración Local — `"administracion local"` ya en `DEPT_KEYWORDS_FOR_BODY`) y en **`datos.madrid.es`** (API CKAN del Ayuntamiento, ya monitorizada para OEPs y procesos selectivos). La cobertura indirecta es suficiente.

#### `metromadrid.es` — **F5/BIG-IP WAF, IP-sensitive con white-list de rutas**

Comportamiento mixto desde IP residencial española:

- **Detalles individuales** `https://www.metromadrid.es/es/oferta-empleo/<slug>` → **HTTP 200** (108KB de HTML real).
- **Listados, sitemap, robots.txt, RSS, home `/es`** → "Request Rejected" 245B (firma F5 BIG-IP). Bloqueados deliberadamente.

El WAF tiene una lista blanca de rutas finales conocidas pero bloquea cualquier endpoint que pueda enumerar páginas. Wayback Machine tampoco tiene snapshots útiles de los listados (`archived_snapshots: {}`). Google/Bing site search tampoco devuelven slugs en SERPs sin JS.

**Veredicto: no invertir en proxy fly.io / VPS español solo para Metro Madrid.** Aunque desbloquearía los detalles, no podemos descubrir slugs nuevos sin pasar por el listado, así que el proxy no resuelve el problema real (descubrimiento). Las plazas estructurales de Metro Madrid (S.A. pública) sí acaban en BOCM y BOE, y `"metro de madrid"` ya está en `HEALTH_ORGS` (bocm.py) y `DEPT_KEYWORDS_FOR_BODY` (boe.py) para forzar descarga de PDF — la convocatoria con bases acabará apareciendo. Lo que se sigue perdiendo: ofertas puntuales o de bolsa publicadas exclusivamente en su portal sin pasar por boletín. Trabajo abierto futuro: investigar feeds externos (InfoEmpleo, LinkedIn API) como descubridor alternativo, no como parser directo.

#### Conclusión técnica global

| Fuente | Bloqueo | Soluble con IP española | Soluble con browser real | Cobertura indirecta actual |
|---|---|---|---|---|
| `madrid.es/boam` | Akamai Bot Manager | ❌ | ⚠️ no garantizado | BOE 2B + datos.madrid.es ✅ |
| `madrid.es/oposiciones.html` | Akamai Bot Manager | ❌ | ⚠️ no garantizado | BOE 2B + datos.madrid.es ✅ |
| `metromadrid.es` (detalle) | F5/BIG-IP geo | ✅ | ✅ | BOE 2B + BOCM con keyword forzada |
| `metromadrid.es` (listado) | F5/BIG-IP estricto | ❌ | ⚠️ depende | — |

Tarea cerrada. No se invierte en infraestructura proxy/VPS/Playwright porque el coste-beneficio no compensa: la cobertura indirecta vía BOE/BOCM/datos.madrid.es captura la mayoría de plazas que terminaríamos viendo desde los portales nativos. Si en el futuro se detecta una pérdida sistemática de ofertas concretas de Metro Madrid (no estructurales) que justifique el coste, se puede reabrir la línea de feeds externos (InfoEmpleo / LinkedIn) como alternativa al parser directo.

---

### ~~Variante "ATS/DUE" en STRONG_PATTERNS~~ ✅ Resuelto (2026-04-26)

Añadidas variantes para la denominación pre-Bolonia "ATS/DUE" (Ayudante Técnico Sanitario / Diplomado Universitario en Enfermería) en `STRONG_PATTERNS` y `WEAK_CONTEXT_PATTERNS`:
- STRONG: `ats due de prevencion`, `ats due de salud laboral` y variantes con guión/barra.
- WEAK: `ats due` + (`prevencion` | `salud laboral` | `riesgos laborales`) en ventana de 100 chars.

Caso real motivador: [BOE-A-2022-23854](https://www.boe.es/diario_boe/txt.php?id=BOE-A-2022-23854) (Tribunal de Cuentas, 30/12/2022) — "Resolución por la que se convoca proceso selectivo, por el turno de acceso libre, para la provisión de plaza vacante de ATS/DUE de Prevención y Salud laboral." Verificado: el extractor ahora hace match (`Categoría: oposicion`).

---

### ~~Pickup de CIEMAT tras cron del 27/04/2026~~ 🟡 Parcialmente resuelto (2026-04-27, run [24989135333](https://github.com/tragabytes/vigia-enfermeria/actions/runs/24989135333))

El cron del 27/04 corrió a las 10:12 UTC y validó las 4 expectativas en BD/dashboard:

1. ✅ Parser nuevo ejecutado: `CIEMAT listado: 2 ofertas en rango`.
2. ✅ Match en PDF: `CIEMAT [2380]: match en https://www.ciemat.es/doc/ficheros_oe/2380CIEMATPerfiles_formativos_2025Ff0EmLM.pdf`.
3. ✅ Extractor + enricher v2: `Match fuerte [ciemat]: CONCURSO ESPECIFICO I - 2026 PERSONAL FUNCIONARIO DEL CIEMAT` + `Enricher v2: 1/1 items enriquecidos (0 fallidos)`.
4. ❌ **Notificación Telegram falló** — ver bug #5 abajo. El item está en el dashboard pero el usuario no recibió aviso por chat.

### ~~5. Notificación Telegram falla con `Bad Request: can't parse entities` cuando la URL contiene `_`~~ ✅ Resuelto (2026-04-28, commit `9b8ccd1`)

**Síntoma.** Run del 27/04 (CIEMAT 2380) reportó `status=400 body={"ok":false,"error_code":400,"description":"Bad Request: can't parse entities: Can't find end of the entity starting at byte offset 1263"}` en ambos chat_ids destinatarios. Item nuevo correctamente detectado, enriquecido y publicado en `gh-pages`, pero entrega Telegram silenciada.

**Diagnóstico.** El `url_bases` apuntaba al PDF de perfiles formativos del CIEMAT: `https://www.ciemat.es/doc/ficheros_oe/2380CIEMATPerfiles_formativos_2025Ff0EmLM.pdf`. La URL contiene varios `_`. El notifier usaba `parse_mode: "Markdown"` (v1), donde `_` empareja para itálica; con número impar de pares en el mensaje completo, Telegram no encuentra el cierre de entidad y rechaza el envío. El `_escape()` aplicaba a títulos/summary/categoría pero NO a las URLs (escaparlas las habría roto como hipervínculos clickables).

**Fix.** Migrado `vigia/notifier.py` a `parse_mode: "HTML"`:
- `_escape()` ahora escapa solo `& < >` (los `_` pasan intactos).
- Negritas/cursivas con `<b>...</b>` / `<i>...</i>` en lugar de `*...*` / `_..._`.
- URLs siguen sin envoltura — Telegram las autodetecta como links en HTML mode igual que en Markdown.
- 224/224 tests offline pasan.

**Pendiente menor.** El item del CIEMAT `2380` ya está marcado como `seen` en la rama `state`, por lo que el próximo cron no lo re-emitirá. El usuario lo ve directamente en el dashboard. Si en el futuro pasa otra vez con un item importante, se puede borrar su `id_hash` de la BD remota para forzar re-notificación.

### Pendiente: parsers propios para OPIs estatales (CIEMAT, IAC, INIA, ISCIII…)

CIEMAT publica plazas en su web propia (`ciemat.es/ofertas-de-empleo/-/ofertas/oferta/<id>`) que no monitorizamos directamente. Las convocatorias en BOE bajo "Ministerio de Ciencia, Innovación y Universidades" son OPIs conjuntas y a veces el HTML del item no da pista en los primeros KB. Pillamos el caso por departamento + plan B (anexos PDF) cuando aplica, pero un parser dedicado al portal CIEMAT detecta antes y cubre plazas que solo viven ahí.

Mismo patrón aplica a otros Organismos Públicos de Investigación con servicio de prevención propio:

- **CIEMAT** — Centro de Investigaciones Energéticas, Medioambientales y Tecnológicas. Portal: `ciemat.es/ofertas-de-empleo`. Ya en watchlist (T-23).
- **IAC** — Instituto de Astrofísica de Canarias. Portal: `iac.es/es/empleo`.
- **INIA** — Instituto Nacional de Investigación y Tecnología Agraria y Alimentaria (ahora INIA-CSIC). Portal: `inia.es` (a investigar URL exacta de empleo).
- **ISCIII** — Instituto de Salud Carlos III. **Investigado 2026-04-28: portal sin listado dinámico viable; cobertura por keywords cerrada (ver bloque dedicado abajo).**
- **IEO** — Instituto Español de Oceanografía. Portal: `ieo.es/empleo` (ahora dependiente del CSIC).
- **CSIC** — Consejo Superior de Investigaciones Científicas (paraguas de varios). Portal: `csic.es/es/empleo`.

Patrón de implementación (similar a `vigia/sources/canal_isabel_ii.py`):
1. Una clase Source por organismo, con `name`, `probe_url`, `fetch(since_date)`.
2. Listar las ofertas activas del portal (HTML render server-side; CSS selectors a investigar).
3. Para cada oferta, descargar la página de detalle y devolver `RawItem(title, url, text)`.
4. El extractor + enricher v2 ya hacen el resto (matcher + estructurado).
5. Añadir cada uno a `WATCHLIST_ORGS` con su id (T-27, T-28…) y patterns.

Coste: ~1-2h por parser, x6 organismos = 6-12h totales si se quieren todos. Priorización razonable: **CIEMAT primero** (caso real motivador), **ISCIII segundo** (instituto sanitario, mayor probabilidad de plazas de Enfermería del Trabajo en su SP), el resto por orden de tamaño/relevancia. Validar primero el portal HTML de CIEMAT — si está renderizado vía JS-only (como `administracion.gob.es`), habría que delegar al BOE/BOCM y abandonar este parser.

### 🟡 ISCIII — research 2026-04-28: parser propio descartado, cobertura por keywords cerrada

**URL del backlog original (`isciii.es/Personal/Paginas/EmpleoPublico.aspx`) → HTTP 404.** Tras inspeccionar la home (HTTP 200, 312KB), las únicas vías de empleo expuestas son tres páginas estáticas bajo `/bolsa-empleo/`:

- `https://www.isciii.es/bolsa-empleo/proceso-selectivo` — describe UNA convocatoria viva (publicada 19/07/2023). 3 documentos enlazados (bases, FAQ, anexo III). Sin actualizaciones recientes.
- `https://www.isciii.es/bolsa-empleo/listado-valoracion-meritos` — fase 1 de la bolsa. **27 PDFs**, fechas hasta marzo 2026.
- `https://www.isciii.es/bolsa-empleo/valoracion-tecnica` — fase 2 de la bolsa. **64 PDFs** con códigos opacos `SGPY-XXX-26-M3-DDCP` (proyectos de investigación), fechas hasta marzo 2026.

**Sede electrónica `sede.isciii.gob.es`** (HTTP 200) descartada: solo expone catálogo de procedimientos administrativos genéricos (instancias, recursos potestativos, quejas). Sin tablón de anuncios ni sección de empleo.

**Por qué no parser propio.** El portal NO tiene listado dinámico de convocatorias en formato `[título → URL detalle]`. Las dos páginas de fases activas son flujos administrativos donde se publican muchas resoluciones cada quincena, todas con códigos opacos que no revelan el perfil profesional sin abrir el PDF. Un parser hash-watcher detectaría docenas de cambios al mes, casi todos irrelevantes para Enfermería del Trabajo. El enricher v2 podría leer cada PDF, pero coste/beneficio negativo: 91 documentos × Sonnet ≈ ruido caro.

**Lo que sí se ha hecho (cobertura indirecta cerrada).** Añadidas `"isciii"` y `"instituto de salud carlos iii"` a:
- `DEPT_KEYWORDS_FOR_BODY` en `vigia/sources/boe.py` — fuerza descarga del HTML del item BOE para inspeccionar plazas concretas, igual que CIEMAT.
- `HEALTH_ORGS` en `vigia/sources/bocm.py` — fuerza descarga del PDF del BOCM cuando el ISCIII aparece como organismo emisor.

`tests/test_organism_coverage.py` parametrizado con "Instituto de Salud Carlos III" e "ISCIII" en ambos sets. **300/300 tests offline pasan**. Las plazas estructurales de Enfermería del Trabajo del Servicio de Prevención del ISCIII llegan vía BOE (Ministerio de Ciencia e Innovación, OPIs conjuntas) y ahora tenemos garantía de inspección del cuerpo.

**Parser hash-watcher implementado (2026-04-28).** [`vigia/sources/isciii.py`](vigia/sources/isciii.py) monitoriza SOLO `https://www.isciii.es/bolsa-empleo/proceso-selectivo` (no las dos páginas de fase, demasiado ruidosas). Cada run descarga la página, extrae el cuerpo principal limpio (quitando nav/header/footer), calcula `sha1(body)[:10]` e incorpora ese hash al título del RawItem como `[snapshot <hash>]`. Como `id_hash = sha256(source|url|titulo)`, snapshots distintos generan items distintos en BD; snapshots repetidos los descarta `filter_new` aguas abajo. El extractor decide si el contenido menciona Enfermería del Trabajo: si lo hace, entra al pipeline (matcher + enricher v2); si no, se descarta silenciosamente como cualquier otro item irrelevante.

Sin persistencia adicional (no tabla `isciii_state`): el truco de incorporar el hash al título reutiliza la deduplicación natural del sistema. Coste por run: 1 GET ~225KB. Watchlist tile T-38. 12 tests en [test_isciii.py](tests/test_isciii.py) cubren limpieza del cuerpo, idempotencia, snapshot distinto cuando cambia el contenido, errores HTTP/red/body vacío y fallback de fecha. Validado smoke contra portal real (28/04/2026, 06:51): probe HTTP 200, fecha extraída `2023-07-19`, snapshot `01070353ed`, 748 chars de cuerpo (banner cookies + menú fases + convocatoria + anexos). Hoy no menciona Enfermería → extractor lo descarta sin emitir nada al pipeline.

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

### ~~2. BOAM y Ayuntamiento Madrid bloqueados~~ ✅ Convertidos a stub (2026-04-28)

**Cierre definitivo tras el research del 2026-04-28.** Confirmado que no es filtro IP geo sino Akamai Bot Manager (ver sección "Investigación profunda del problema de IP geo-bloqueada"). `boam.py` y `ayuntamiento_madrid.py` se han reescrito como stubs (igual patrón que `metro_madrid.py` y `administracion_gob.py`): devuelven lista vacía sin hacer requests, evitando los HTTP 403 recurrentes que aparecían cada día en la notificación Telegram. Sin `probe_url`, la sección 5 del dashboard los marca como `skipped` con detalle "fuente sin probe_url (stub o cobertura delegada)". Cobertura intacta vía BOE 2B + datos.madrid.es.

#### Histórico (mitigación previa, 2026-04-25)

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

### ~~Empresas públicas estatales — parsers propios SAP SuccessFactors~~ 🟡 RENFE, Correos, Navantia ✅ / ADIF, AENA, RTVE, Paradores, SELAE ❌ (2026-04-28)

**Implementado en `vigia/sources/sap_successfactors.py`**: parser único para los 3 portales que comparten plataforma SAP SuccessFactors Career Site Builder, detectada al inspeccionar `/platform/js/search/search.js` en sus respuestas. Endpoint `/search/?startrow=N&num=10` devuelve HTML server-side completo con `<tr class="data-row">` (Correos) o `<div class="job">` (RENFE), `<a class="jobTitle-link">` y `<span class="jobDate">DD mes YYYY</span>` español. Soporta paginación hasta 5 páginas (volumen real ≤1 página).

**Lección aprendida del research**: SAP SuccessFactors hace búsqueda OR amplia con `?q=`, devolviendo TODAS las ofertas aunque ninguna mencione el término. Validado con RENFE `?q=prevención` → 6 puestos no relacionados. Por eso descargamos listado completo y filtramos con `FAST_KEYWORDS` aplicado al título.

**Watchlist**: T-30 RENFE, T-31 ADIF, T-32 AENA, T-33 Correos, T-34 Navantia, T-35 Paradores, T-36 RTVE, T-37 SELAE Loterías. Las 5 sin parser propio quedan cubiertas indirectamente vía BOE/BOCM (keywords ya en `DEPT_KEYWORDS_FOR_BODY` y `HEALTH_ORGS`).

#### Empresas NO implementadas como parser propio — notas técnicas reproducibles

**ADIF** (`https://www.adif.es/empleo-publico`): HTTP 403 con `Reference #...errors.edgesuite.net` y `Server-Timing: ak_p` → mismo Akamai Bot Manager que `madrid.es`. NO factible sin browser real. Cobertura indirecta vía BOE 2A.

**SELAE Loterías** (`https://www.selae.es/es/empleo`): HTTP 403 con misma firma Akamai. Idéntico veredicto que ADIF.

**AENA** (`https://empleo.aena.es/empleo/`): HTTP 200 pero body_text=929 — SPA/landing sin contenido server-side. **NO es SAP SuccessFactors** (`/search/` da 404). Sistema custom propio. Para implementar parser haría falta inspeccionar el bundle JS y descubrir el endpoint API real (probable AJAX a `/api/...` con JSON). Trabajo: 1-2h de research adicional. Cobertura indirecta vigente vía BOE 2B + AENA en `DEPT_KEYWORDS_FOR_BODY`.

**RTVE** (`https://convocatorias.rtve.es/puestos-ofertados`): HTTP 200 pero **body_text=0** — SPA absoluta donde la respuesta inicial es el shell vacío de React/Vue, todo el contenido se hidrata client-side desde una API que no aparece en el HTML inicial. Endpoints triviales `/api/puestos`, `/data.json`, etc. devuelven el mismo shell (10402B). Para implementar haría falta abrir DevTools y rastrear la primera request XHR/fetch al cargar la página. Cobertura indirecta vía BOE 2A + RTVE en `DEPT_KEYWORDS_FOR_BODY` ("Convocatorias RTVE" suele publicarse en BOE como "Resolución de la Corporación de Radio y Televisión Española").

**Paradores** (`https://www.paradores.es/es/ofertas`): HTTP 200, 216KB de body, pero `/es/ofertas` es un listado de **ofertas turísticas** (descuentos en estancias), NO empleo. La home no expone link directo a portal de empleo público. Hipótesis: Paradores S.M.E. publica todas las plazas vía BOE como cualquier S.M.E. estatal sin web propia de empleo. Confirmar antes de descartar definitivamente.

#### Histórico (cobertura indirecta previa, 2026-04-26)

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
