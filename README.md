# vigia-enfermeria

Monitor automatizado de convocatorias de **Enfermería del Trabajo** en la administración pública de Madrid. Ejecuta cada día laborable, busca en BOE, BOCM, BOAM, Comunidad de Madrid, Canal de Isabel II y CODEM, y envía alertas por Telegram cuando aparece algo nuevo.

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
| BOE | API JSON oficial | Nacional — convocatorias secciones 2A/2B/3 |
| BOCM | XML sumario + descarga PDF | Comunidad de Madrid |
| BOAM | PDF sumario (primeras 10 pág.) | Ayuntamiento de Madrid |
| Comunidad de Madrid | Web sede.comunidad.madrid | Portal propio de empleo |
| Canal de Isabel II | Tabla web /puestos | Canal Isabel II directamente |
| CODEM | RSS feed | Colegio de Enfermería de Madrid |
| Ayuntamiento de Madrid | Web estática oposiciones | Complemento a BOAM |
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
  extractor.py       # motor de matching
  notifier.py        # envío Telegram
  storage.py         # SQLite deduplicación
  sources/
    boe.py           # API BOE
    bocm.py          # XML BOCM
    boam.py          # PDF BOAM
    comunidad_madrid.py
    canal_isabel_ii.py
    codem.py
    ayuntamiento_madrid.py
    metro_madrid.py
    administracion_gob.py
tests/
  test_extractor.py
utils/
  test_telegram.py
.github/workflows/
  daily.yml
```
