# Backlog — vigia-enfermeria

Pendientes para retomar más adelante. Última actualización: 2026-04-25.

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

Pendiente como mejora futura: parsers dedicados de portales propios con feed/API estructurado para los que los tengan. Top 5 a investigar (por población): Móstoles, Alcalá, Fuenlabrada, Leganés, Getafe.

| Municipio | Población | A investigar |
|-----------|-----------|--------------|
| Móstoles | 209k | URL portal empleo |
| Alcalá de Henares | 195k | Sede electrónica |
| Fuenlabrada | 192k | URL convocatorias |
| Leganés | 187k | URL convocatorias |
| Getafe | 187k | URL convocatorias |
| Alcorcón | 173k | URL convocatorias |
| Torrejón de Ardoz | 134k | URL convocatorias |
| Parla | 130k | URL convocatorias |
| Alcobendas | 117k | URL convocatorias |

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
- **Dashboard mínimo:** página estática en GitHub Pages con la lista de convocatorias detectadas, ordenadas por fecha. El JSON podría generarse desde la BD en cada run y commitearse a la rama `gh-pages`.
- ~~**Test de fuentes "vivas":**~~ ✅ Resuelto (2026-04-25, commit `44f7240`). Añadido `python -m vigia.main --probe` que hace HEAD/GET ligero a la URL principal de cada fuente y muestra una tabla de salud. Integrado en `daily.yml` con `if: always() + continue-on-error: true` para que cada run del cron deje el estado de las fuentes en los logs sin afectar la conclusion del job.
