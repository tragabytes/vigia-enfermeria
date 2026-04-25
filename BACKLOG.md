# Backlog — vigia-enfermeria

Pendientes para retomar más adelante. Última actualización: 2026-04-25.

---

## 🐛 Bugs / fixes a corregir

### ~~1. Notificación Telegram silenciosa cuando fallan fuentes~~ ✅ Resuelto (2026-04-25, commit `881da0b`)

Implementado con la opción A del plan: atributo `self.last_errors` en la clase base `Source`, las 7 fuentes lo rellenan junto a su `logger.warning(...)`, `_run_source()` lo devuelve como tercer elemento de la tupla y `main.py` lo extiende a la lista global `errors`. 9 tests nuevos en `test_main_errors.py` cubren el comportamiento. Validado end-to-end con un run real: BOAM y Comunidad Madrid caídos generaron mensaje en Telegram.

### 2. BOAM y Ayuntamiento Madrid bloqueados por geolocalización (parcial)

**Investigado el 2026-04-25, commit `b4e8c36`.** El primer 403 que veíamos era por User-Agent (`vigia-enfermeria/1.0...` filtrado): cambiando el UA global a uno de Firefox, **en local desde España BOAM funciona** (descarga PDF del sumario y parsea). Pero desde **GitHub Actions sigue dando 403**, y ahora la URL que falla es `https://www.madrid.es/boam` directamente, antes del redirect a `sede.madrid.es`.

Conclusión: `madrid.es` filtra por **IP + UA combinados**. Solo desde IP española con UA de navegador real deja pasar. El runner de GHA (Azure US/EU) está fuera del rango admitido. La fuente `ayuntamiento_madrid` (que también pega a `madrid.es/portales/...`) tiene exactamente el mismo síntoma.

**Impacto real:** bajo. BOAM publica las convocatorias del Ayuntamiento de Madrid, que en su mayoría también aparecen en BOE sección 2B (Administración Local). La cobertura primaria sigue siendo BOE + BOCM + Comunidad Madrid.

**Opciones de futuro (ordenadas por viabilidad):**
1. **Self-host del cron en VPS español** (Hetzner Helsinki ~€4/mes, Contabo ES, OVH FR; o Raspberry Pi en casa). Requiere migrar el workflow a un cron de sistema + decidir cómo persistir la BD (igual que ahora pero local).
2. **Investigar URL alternativa pública del BOAM** (¿RSS, JSON, endpoint XML como BOCM?). Sin garantía de que exista. **Vale la pena explorar antes de la opción 1.**
3. **Proxy europeo gratis** — descartado: poco fiable, infringe TOS de muchos servicios.

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

## 🤖 Capa de enriquecimiento con IA (Sección 10 del PLAN.md)

Punto de extensión ya preparado en `vigia/main.py`:

```python
# Punto de extensión: para añadir enricher.py insertar aquí:
#   matched = enricher.enrich(matched)
matched = []
for raw in raw_items_all:
    item = extract(raw)
    ...
```

Y en `vigia/storage.py`:

```python
@dataclass
class Item:
    ...
    summary: Optional[str] = None      # relleno por enricher.py (futuro)
    extra: dict = None                 # metadatos enriquecidos (futuro)
```

`vigia/notifier.py` ya muestra el `summary` si existe (`if item.summary: lines.append(...)`), así que basta con añadir `enricher.py` y una línea en `main.py` para activarlo.

**Funcionalidad propuesta:**
- Para cada `Item` con match, enviar al LLM (Claude Haiku, Sonnet o GPT-4o-mini) el título + URL + extracto del PDF/HTML.
- LLM extrae: número de plazas, requisitos clave (titulación), fecha límite de inscripción, organismo.
- Devuelve un resumen de 2-3 líneas en español que se inyecta en `Item.summary`.

**Decisiones a tomar:**
- ¿Qué proveedor (Anthropic, OpenAI, OpenRouter)? Coste estimado: <$0.01/día con Haiku.
- ¿API key como nuevo Secret de GitHub Actions?
- ¿Filtros de calidad? (No enriquecer si el extracto < N caracteres, etc.)
- ¿Caché del enriquecimiento por `id_hash` para no re-procesar al re-ejecutar?

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
