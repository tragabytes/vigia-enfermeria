# Backlog — vigia-enfermeria

Pendientes para retomar más adelante. Última actualización: 2026-04-25.

---

## 🐛 Bugs / fixes a corregir

### 1. Notificación Telegram silenciosa cuando fallan fuentes

**Síntoma observado en el primer run real (2026-04-25):**
```
WARNING vigia.sources.boam: BOAM 2026-04-24 error: 403 ...
WARNING vigia.sources.comunidad_madrid: 404 Not Found for url: ...
INFO __main__: Sin novedades hoy — no se envía notificación Telegram
```

Las fuentes capturan sus excepciones internamente con `try/except` y emiten un `logger.warning(...)`, pero no propagan el fallo al `main.py`. Por eso `errors` llega vacío al `notifier.send()` y el `if new_items or errors` no dispara mensaje. Resultado: **si una fuente cae, no te enteras hasta que entras a Actions a mirar los logs.**

**Propuestas:**
- Que cada `Source.fetch()` exponga una lista `self.last_errors` que `main.py` pueda recoger sin que la excepción se pierda.
- O bien: capturar los WARNINGs con un `logging.Handler` custom que los inyecte en la lista `errors` que llega al notifier.
- O bien: que `main.py` re-eleve si una fuente devuelve 0 items y ha habido WARNINGs en su logger.

La primera opción es la más limpia.

### 2. BOAM devuelve 403 desde GitHub Actions

`https://www.madrid.es/boam` redirige internamente a `https://sede.madrid.es/portal/site/tramites/menuitem...` y este devuelve 403 al runner de Actions. En local (España) funcionaba.

**Hipótesis:**
- Geo-bloqueo (los runners de Azure están en US/EU, posiblemente bloquean IPs no-españolas).
- WAF que bloquea por User-Agent (probar UAs más estándar tipo Firefox).
- Cookies/session que se piden tras el primer GET.

**Plan de investigación:**
1. Ejecutar `curl -v` con varios UAs desde un VPS europeo.
2. Si es geo-bloqueo: usar la URL XML directa del BOAM si existe (igual que hace `bocm.py` que tiene `BOCM_XML_PATTERN`).
3. Si es UA: cambiar el `_default_headers()` solo de esta fuente.

### 3. Comunidad de Madrid `/buscador` da 404

URL que probamos durante la investigación: `https://sede.comunidad.madrid/buscador?tipo=7&...`. En el run del 2026-04-25 devuelve 404.

**Plan:**
1. Visitar `https://sede.comunidad.madrid/empleo-publico` y ver a qué buscador enlaza ahora.
2. Probar si el portal Drupal ha cambiado a `/empleo` o a un dominio nuevo (Comunidad de Madrid migra portales con frecuencia).
3. Replantear el parser con la URL actualizada.

---

## 🆕 Nuevas fuentes a añadir

### CODEM — sección de comunicaciones

Actualmente solo se monitoriza el RSS de **empleo público**:
```
Menu=e0fed1d6-aff3-4b0d-be4d-7a276dea3867   ← empleo público
```

CODEM tiene otra sección llamada **"Comunicaciones"** (o similar — verificar nombre exacto en codem.es) donde a veces publican avisos sobre concursos, bolsas y movimientos del SERMAS antes de que aparezcan en BOCM.

**Plan:**
1. Explorar codem.es y localizar la sección de comunicaciones / noticias.
2. Comprobar si tiene RSS feed propio (URL similar a `RssHyperLink.ashx?Menu=...`).
3. Si lo tiene, añadir como segunda fuente dentro de `vigia/sources/codem.py` (lista de URLs de RSS) o como fuente nueva `codem_comunicaciones.py`.

### Casa de la Moneda (FNMT-RCM)

Fábrica Nacional de Moneda y Timbre — Real Casa de la Moneda. Es organismo público estatal con plantilla considerable y servicio de prevención propio, así que de tanto en tanto convoca puestos de Enfermería del Trabajo.

**Plan:**
1. Investigar `https://www.fnmt.es/empleo` (verificar URL real).
2. Las convocatorias salen también en BOE sección 2A (organismo "FNMT"), así que actualmente quedan cubiertas por `boe.py`. Añadir "fnmt" o "casa de la moneda" o "fabrica nacional de moneda" a `DEPT_KEYWORDS_FOR_BODY` de `boe.py` para garantizar que se baja el body HTML.
3. Considerar fuente directa solo si el portal propio expone convocatorias antes que BOE.

### EMT Madrid (Empresa Municipal de Transportes)

Como Metro Madrid, es una empresa pública municipal con servicio de prevención. Convocan ocasionalmente Enfermería del Trabajo.

**Plan:**
1. Investigar `https://www.emtmadrid.es/Empresa/Empleo` (URL a verificar).
2. EMT publica en BOAM (al ser municipal) y a veces en BOCM. Verificar que `boam.py` y `bocm.py` capturan correctamente sus convocatorias.
3. Añadir "emt" o "empresa municipal de transportes" a:
   - `HEALTH_ORGS` de `bocm.py`
   - `DEPT_KEYWORDS_FOR_BODY` de `boe.py`
4. Considerar fuente directa si el portal propio resulta scrapeable.

### Boletines oficiales de otros ayuntamientos grandes de la Comunidad de Madrid

Solo se monitoriza el BOAM (Madrid capital). Otros ayuntamientos grandes con servicios de prevención propios y plantilla suficiente para tener Enfermería del Trabajo:

| Municipio | Población | Boletín oficial propio | A investigar |
|-----------|-----------|------------------------|--------------|
| Móstoles | 209k | Posible BOM | URL portal empleo |
| Alcalá de Henares | 195k | ¿BO Alcalá? | Sede electrónica |
| Fuenlabrada | 192k | Sede electrónica | URL convocatorias |
| Leganés | 187k | Sede electrónica | URL convocatorias |
| Getafe | 187k | Sede electrónica | URL convocatorias |
| Alcorcón | 173k | Sede electrónica | URL convocatorias |
| Torrejón de Ardoz | 134k | Sede electrónica | URL convocatorias |
| Parla | 130k | Sede electrónica | URL convocatorias |
| Alcobendas | 117k | Sede electrónica | URL convocatorias |

**Nota:** muchos de estos municipios publican sus convocatorias **directamente en el BOCM** (no tienen boletín propio), así que `bocm.py` ya los cubre indirectamente. Pero es interesante:
- Tener un parser dedicado para los que sí tienen portal propio con RSS / API.
- Añadir los nombres de estos municipios a `HEALTH_ORGS` de `bocm.py` para forzar descarga de PDF cuando sus convocatorias aparezcan.

**Plan:**
1. Investigar individualmente cada uno (top 5: Móstoles, Alcalá, Fuenlabrada, Leganés, Getafe).
2. Para los que tengan portal con feed/API estructurado, crear `vigia/sources/ayto_<municipio>.py`.
3. Para el resto, ampliar la cobertura indirecta en BOCM.

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
- **Test de fuentes "vivas":** un workflow opcional, manual, que ejecute solo el `fetch()` de cada fuente con un `--probe` y reporte cuáles devuelven HTTP 200 con contenido parseable. Útil para detectar URLs que han cambiado **antes** de que empiecen a fallar en el cron diario.
