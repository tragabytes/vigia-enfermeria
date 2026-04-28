# vigia-enfermeria

Monitor automatizado de convocatorias de **Enfermería del Trabajo** en la administración pública de Madrid. Ejecuta cada día laborable, busca en BOE, BOCM, BOAM, Comunidad de Madrid, Ayuntamiento de Madrid, datos.madrid.es, Canal de Isabel II y CODEM, enriquece los hallazgos con Claude Sonnet 4.6 (tool use sobre la URL real → JSON estructurado con plazas, deadline, organismo, tasas, fase, próxima acción) y envía alertas por Telegram con countdown y CTAs accionables cuando aparece algo nuevo.

El estado se persiste en una BD SQLite en la rama `state` y se publica como JSON en la rama `gh-pages` para alimentar un dashboard web público.

---

## Pasos para poner en marcha el sistema

### 1. Crear el bot de Telegram

1. Abre Telegram y busca **@BotFather**.
2. Escribe `/newbot` y sigue las instrucciones (elige nombre y username).
3. Al terminar, BotFather te da un token con este formato:
   ```
   123456789:AAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```
   Guárdalo — es tu `TELEGRAM_BOT_TOKEN`.
4. Abre una conversación con tu nuevo bot (búscalo por su username) y pulsa **Iniciar**.
5. Para obtener tu `TELEGRAM_CHAT_ID`, envía cualquier mensaje al bot y luego abre en el navegador:
   ```
   https://api.telegram.org/bot<TU_TOKEN>/getUpdates
   ```
   En la respuesta JSON busca `"chat":{"id":XXXXXXXX}` — ese número es tu `TELEGRAM_CHAT_ID`.

### 2. Probar las credenciales localmente

```bash
# Desde la raíz del repositorio
pip install -r requirements.txt

TELEGRAM_BOT_TOKEN="123456789:AAxxxx" \
TELEGRAM_CHAT_ID="123456789" \
python utils/test_telegram.py
```

Si el mensaje llega a tu Telegram, las credenciales son correctas.

### 3. Crear el repositorio en GitHub

1. Ve a [github.com/new](https://github.com/new).
2. Pon de nombre `vigia-enfermeria` (o el que quieras).
3. Marca **Private** para que el token Telegram no sea público.
4. Deja las demás opciones vacías (sin README, sin .gitignore) — los añadirás tú.
5. Copia la URL SSH o HTTPS del repositorio (p. ej. `git@github.com:TU_USUARIO/vigia-enfermeria.git`).

### 4. Configurar los Secrets en GitHub

1. En tu repositorio GitHub ve a **Settings → Secrets and variables → Actions**.
2. Pulsa **New repository secret** y añade:
   - Nombre: `TELEGRAM_BOT_TOKEN` — Valor: el token del paso 1
   - Nombre: `TELEGRAM_CHAT_ID` — Valor: el chat ID del paso 1

> **Múltiples destinatarios:** `TELEGRAM_CHAT_ID` admite varios IDs separados por comas (p. ej. `123456789,987654321`). Cada persona debe enviar primero un mensaje al bot para que su chat ID sea descubrible vía `getUpdates`. Si un destinatario falla, el resto sigue recibiendo la notificación.

### 5. Subir el código al repositorio

Desde la raíz del proyecto (carpeta `alerta-empleo`):

```bash
git init
git add .
git commit -m "feat: vigia-enfermeria pipeline inicial"
git branch -M main
git remote add origin git@github.com:TU_USUARIO/vigia-enfermeria.git
git push -u origin main
```

### 6. Verificar que el workflow se ejecuta

1. En GitHub ve a la pestaña **Actions** de tu repositorio.
2. Verás el workflow `vigia-enfermeria daily` — aparecerá al día siguiente a las 08:00 UTC (09:00-10:00 hora España según la época del año).
3. Para ejecutarlo ahora mismo: pulsa **Run workflow** (botón azul arriba a la derecha en la pestaña Actions).
4. Comprueba que el workflow pasa en verde. En el log verás algo como:
   ```
   BOE: 3 raw items
   BOCM: 1 raw items
   Matches tras extractor: 1
   Nuevos (no vistos antes): 1
   ```
5. Comprueba que llega el mensaje a Telegram.

### 7. Verificar persistencia del estado

Tras la primera ejecución exitosa:

1. En tu repositorio GitHub, en la lista de ramas, aparecerá una rama **`state`**.
2. Dentro de esa rama hay un fichero `state/seen.db` — es la base de datos SQLite que guarda las convocatorias ya vistas.
3. En ejecuciones posteriores, solo se notificarán convocatorias **nuevas** (no duplicadas).
4. También aparecerá una rama **`gh-pages`** con `data/{items,sources_status,meta}.json` — el snapshot público que consume el dashboard web.

### 8. Habilitar el dashboard web (opcional)

1. **Settings → Pages → Source**: selecciona la rama `gh-pages` (raíz `/`).
2. La URL pública será `https://<usuario>.github.io/<repo>/` y servirá los JSON desde `/data/`.
3. El frontend estático (HTML/CSS/JS) se publica también en `gh-pages` y hace `fetch('data/items.json')` para renderizar el dashboard. La actualización ocurre automáticamente tras cada run del cron.

### 9. Habilitar la capa de IA (opcional)

Si configuras el secret `ANTHROPIC_API_KEY`, el enricher v2 hace una llamada agentica a **Claude Sonnet 4.6** con la tool `fetch_url` (whitelist de dominios oficiales, anti-SSRF) que descarga el cuerpo del boletín o PDF de bases y devuelve un JSON estructurado con 16 campos (`is_relevant`, `process_type`, `plazas`, `deadline_inscripcion`, `organismo`, `tasas_eur`, `url_bases`, `requisitos_clave`, `fase`, `next_action`, `confidence`…). Sin la key, el pipeline funciona igual pero sin enriquecer (graceful degradation): los items se guardan y se notifican como antes, sin chips/countdown/filtrado de falsos positivos.

Coste estimado al volumen real (≤3 items relevantes/día): ~$3-5/año. El pipeline diario solo paga por los items que pasan `filter_new` — días sin novedad son gratis.

**Backfill del histórico.** Tras configurar la key, ejecuta `gh workflow run maintenance.yml` para que `enrich_pending(storage)` reprocese todos los items que aún estén en `enriched_version < 2`. Idempotente.

---

## Ejecución local (debug / backfill)

```bash
# Instalar dependencias
pip install -r requirements.txt

# Ejecutar sin notificar (solo imprimir hallazgos)
python -m vigia.main --dry-run

# Backfill: procesar desde una fecha concreta
python -m vigia.main --since 2025-01-01 --dry-run

# Ejecutar completo (con Telegram y guardado en BD)
TELEGRAM_BOT_TOKEN="..." TELEGRAM_CHAT_ID="..." python -m vigia.main
```

## Ejecutar los tests

```bash
python -m pytest tests/ -v
```

---

## Fuentes monitorizadas

| Fuente | Método | Cobertura |
|--------|--------|-----------|
| BOE | API JSON oficial + body HTML inspeccionado por dept relevante | Nacional — convocatorias secciones 2A/2B/3, ministerios estatales con servicio de PRL propio (Interior, Defensa, Ciencia, Hacienda, etc.) |
| BOCM | XML sumario + descarga PDF | Comunidad de Madrid |
| BOAM | Stub (Akamai) | Cubierto por BOE 2B + datos.madrid.es |
| Comunidad de Madrid | Web sede.comunidad.madrid | Portal propio de empleo |
| Canal de Isabel II | Tabla web /puestos | Canal Isabel II directamente |
| CODEM | RSS feed (Empleo + Actualidad) | Colegio de Enfermería de Madrid |
| Ayuntamiento de Madrid | Stub (Akamai) | Cubierto por BOE 2B + datos.madrid.es |
| datos.madrid.es | API CKAN | OEPs y procesos selectivos del Ayto. (no geo-bloqueado) |
| CIEMAT | Listado HTML + extracción de PDFs anexos del propio dominio | Centro de Investigaciones Energéticas, Medioambientales y Tecnológicas (cobertura directa; el HTML BOE de OPIs conjuntas no detalla las plazas) |
| Universidades públicas Madrid | Listados HTML server-side de portales PTGAS | UCM (`convocatorias-vigentes-pas`), UAH (3 listados PAS funcionario/laboral/bolsa), UAM (2 listados funcionario/laboral). UC3M, URJC, UPM pendientes — ver BACKLOG. |
| Empresas públicas SAP SuccessFactors | Endpoint común `/search/` con HTML server-side y `<tr.data-row>` / `<div.job>` | RENFE (`empleo.renfe.com`), Correos (`empleo.correos.com`), Navantia (`empleo.navantia.es`). |
| Metro de Madrid | Stub (WAF) | Cubierto por BOE/BOCM |
| administracion.gob.es | Stub (JS-only) | Cubierto por BOE/BOCM |

## Patrones detectados

- **Match fuerte**: `Enfermería del Trabajo`, `Enfermería de Trabajo`, `Enfermera/o del Trabajo`, `Enfermera de Salud Laboral`, `Especialista en Enfermería del Trabajo`, etc.
- **Match débil**: `salud laboral` o `servicio de prevención` + `enfermer` en un radio de 100 caracteres.
- **Falsos positivos descartados**: TCAE, Auxiliar de Enfermería, Enfermería de Salud Mental, Enfermería Pediátrica, Matrona.

## Estructura del proyecto

```
vigia/
  config.py          # keywords, sources, normalización
  main.py            # pipeline principal
  extractor.py       # motor de matching (regex strong/weak, FP)
  enricher.py        # capa IA v2 (Sonnet 4.6 + tool use → JSON estructurado)
  notifier.py        # envío Telegram con countdown + chips
  storage.py         # SQLite con migración aditiva idempotente (v2)
  dashboard.py       # exportador JSON (items + sources + targets + meta + changelog)
  sources/
    boe.py           # API BOE
    bocm.py          # XML BOCM
    boam.py          # PDF BOAM
    comunidad_madrid.py
    canal_isabel_ii.py
    codem.py
    ayuntamiento_madrid.py
    datos_madrid.py  # API CKAN del Ayto. Madrid
    ciemat.py        # listado web + extracción de PDFs anexos
    metro_madrid.py
    administracion_gob.py
tests/
  test_extractor.py
  test_main_errors.py
  test_probe.py
  test_storage.py
  test_dashboard.py
  test_enricher.py
  test_codem_feeds.py
  test_datos_madrid.py
  test_ciemat_source.py
  test_boe_pdf_anexos.py
  test_organism_coverage.py
utils/
  test_telegram.py
.github/workflows/
  daily.yml
```

## Pipeline

```
sources/*.py  →  extractor.py  →  storage (filter_new)  →  enricher.py (v2)  →  storage (update_enrichment)  →  dashboard.export_all  →  notifier.py (filtra is_relevant=false)
```

1. Cada fuente devuelve `RawItem`.
2. El extractor aplica reglas (match fuerte/débil, falsos positivos por keywords) y devuelve `Item` o `None`.
3. La BD deduplica y guarda los items nuevos (campos básicos).
4. El enricher v2 (si hay `ANTHROPIC_API_KEY`) llama a Sonnet 4.6 con tool use sobre la URL real, valida el JSON contra el schema y persiste 16 campos estructurados (`is_relevant`, `process_type`, `plazas`, `deadline_inscripcion`, `organismo`, `tasas_eur`, `url_bases`, `fase`, `next_action`, `confidence`, …).
5. El dashboard exporta `items.json` (con chips), `sources_status.json`, `targets.json` (watchlist con countdown real), `meta.json` y `changelog.json` a `docs/data/`.
6. El notifier filtra los items con `is_relevant=false` (falsos positivos confirmados por el LLM) y manda el resumen accionable a Telegram con plazas, cierre, tasa, bases y `next_action`.
7. El workflow pushea la BD a la rama `state` y los JSON + frontend a la rama `gh-pages`.

**Mantenimiento.** El workflow `maintenance.yml` (manual, `workflow_dispatch`) corre `enrich_pending(storage)` para reprocesar items históricos cuando se sube `ENRICHMENT_VERSION` o se afina el prompt. Idempotente: items ya en la versión actual se saltan.
