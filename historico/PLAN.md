# Plan: Vigilancia automática de oposiciones de Enfermería del Trabajo en Madrid

## 1. Objetivo

Rastrear a diario convocatorias, bolsas de empleo y concursos de traslados de **Enfermería del Trabajo** en el ámbito de Madrid (administraciones públicas madrileñas y empresas públicas con sede en Madrid) y recibir alerta en Telegram cuando aparezca algo nuevo.

Alcance inicial: convocatorias estrictas + salud laboral con enfermería + bolsas de empleo + concursos de traslados.

---

## 2. Fuentes a monitorizar

### Capa primaria — Boletines oficiales (fuente de verdad)

| Fuente | URL de consulta | Método técnico |
|---|---|---|
| **BOE** | `https://boe.es/datosabiertos/api/boe/sumario/YYYYMMDD` | API XML oficial de sumarios diarios. Documentación: `https://www.boe.es/datosabiertos/api/api.php` |
| **BOCM** | `https://www.bocm.es/` | Scraping del sumario diario (HTML + PDF). No hay API pública |
| **BOAM** (Boletín Oficial del Ayuntamiento de Madrid) | `https://sede.madrid.es/portal/site/tramites/` → sección BOAM | Scraping del sumario diario |

### Capa secundaria — Portales propios de los organismos

| Organismo | URL de vigilancia |
|---|---|
| Ayuntamiento de Madrid — Buscador de oposiciones | `https://www.madrid.es/portales/munimadrid/es/Inicio/Educacion-y-empleo/Empleo/Oposiciones/Buscador-de-oposiciones/` |
| Comunidad de Madrid — Ofertas de empleo | `https://sede.comunidad.madrid/empleo` |
| SERMAS (vía Comunidad de Madrid) | `https://www.comunidad.madrid/servicios/salud` |
| Metro de Madrid — Trabaja con nosotros | `https://www.metromadrid.es/es/metro-de-madrid/trabaja-con-nosotros` |
| Canal de Isabel II — Convocatorias públicas | `https://convocatoriascanaldeisabelsegunda.es/` y `https://www.cyii.es/en/convocatorias-publicas-de-empleo` |

### Capa de seguridad — Agregadores

| Fuente | URL | Rol |
|---|---|---|
| administracion.gob.es | `https://administracion.gob.es/pagFront/empleoBecas/empleo/buscadorEmpleo.htm` | Agregador nacional, red de seguridad |
| CODEM (Colegio Oficial de Enfermería de Madrid) | `https://www.codem.es/empleo-publico` | Recopilación filtrada para verificación cruzada |

---

## 3. Términos de búsqueda y reglas de extracción

Normalizar texto a minúsculas y sin acentos antes de comparar.

**Match fuerte** (alta confianza — alertar siempre):
- `enfermeria del trabajo`
- `enfermera del trabajo` / `enfermero del trabajo`
- `especialista en enfermeria del trabajo`
- `enfermeria especialista ... trabajo` (hasta 5 palabras entre medio)
- `diplomado en enfermeria especialista, especialidad enfermeria del trabajo`
- `enfermera de salud laboral` / `enfermero de salud laboral`

**Match débil** (requiere contexto — alertar solo si también aparece `enfermer`):
- `salud laboral` + `enfermer`
- `servicio de prevencion` + `enfermer`

**Falsos positivos a descartar:**
- Solo `enfermera` / `enfermero` sin especialidad (hay miles)
- `tecnico en cuidados auxiliares de enfermeria`
- `enfermeria de salud mental`, `enfermeria pediatrica`, `enfermeria familiar y comunitaria`, `matrona`

**Clasificación de cada hallazgo:**
- Oposición (convocatoria de pruebas selectivas)
- Bolsa de empleo temporal
- Concurso de traslados
- Nombramiento / resolución administrativa posterior
- Oferta de Empleo Público (OEP) — las plazas están aprobadas pero la convocatoria llegará después

---

## 4. Casos históricos de validación

Usar como tests de regresión — el sistema debe detectar estos casos cuando se le pase la fecha correspondiente:

| Fecha publicación | Fuente | Qué debe detectar |
|---|---|---|
| 26/11/2021 | BOAM nº 9.024 | Bases específicas Enfermero/a (Enfermería de Trabajo) del Ayuntamiento de Madrid |
| 24/04/2023 | BOAM nº 9.370 | Convocatoria de 5 plazas OEP 2020 Ayto Madrid |
| 08/05/2023 | BOE | Anuncio/extracto de la convocatoria anterior |
| 20/12/2023 | metromadrid.es | Técnico/a en Enfermería del Trabajo, Servicio de Salud Laboral |
| 18/03/2024 | BOCM | Concurso de Méritos Enfermero/a Especialista en Enfermería del Trabajo (SERMAS) |
| 08/05/2025 | BOCM | Orden 1074/2025 — 9 plazas Diplomado en Enfermería Especialista del Trabajo (personal laboral CAM) |
| 30/01/2025 | BOE | Concurso de traslados plaza Enfermera/o Especialista del Trabajo CIEMAT |

---

## 5. Arquitectura del repositorio

```
vigia-enfermeria/
├── .github/
│   └── workflows/
│       └── daily.yml
├── vigia/
│   ├── __init__.py
│   ├── config.py              # términos de búsqueda, fuentes, constantes
│   ├── sources/
│   │   ├── __init__.py
│   │   ├── base.py            # clase abstracta Source
│   │   ├── boe.py
│   │   ├── bocm.py
│   │   ├── boam.py
│   │   ├── ayuntamiento_madrid.py
│   │   ├── comunidad_madrid.py
│   │   ├── metro_madrid.py
│   │   ├── canal_isabel_ii.py
│   │   ├── administracion_gob.py
│   │   └── codem.py
│   ├── extractor.py           # reglas de match + clasificación
│   ├── storage.py             # SQLite (deduplicación)
│   ├── notifier.py            # Telegram
│   └── main.py                # orquestador con tolerancia a fallos
├── state/
│   └── seen.db                # persistido en rama `state`
├── tests/
│   └── test_extractor.py      # tests de los casos históricos
├── requirements.txt
├── README.md
└── .gitignore
```

**Responsabilidades clave:**
- `sources/base.py` — define `class Source` con método `fetch(since_date) -> list[Item]`
- Cada fuente hereda y implementa `fetch`
- `extractor.py` — filtra + clasifica; única fuente de verdad de las reglas
- `storage.py` — SQLite con tabla `items(id_hash, source, url, titulo, fecha, categoria, first_seen_at)`. Clave natural: hash del `source + url + titulo`
- `notifier.py` — agrupa hallazgos del día en un mensaje Markdown y envía a Telegram
- `main.py` — ejecuta todas las fuentes en paralelo (ThreadPoolExecutor), tolerando fallos individuales. Si una fuente rompe, las demás siguen; los errores se reportan al final

---

## 6. Persistencia del estado (GitHub Actions es efímero)

**Estrategia recomendada: rama `state` dedicada.**

Al final de cada ejecución, el workflow hace commit de `state/seen.db` a una rama `state`. Al inicio de la siguiente ejecución, checkout de esa rama para restaurar el fichero. Duradero, trazable, sencillo.

Alternativa más simple pero menos duradera: `actions/cache` (expira a 7 días de inactividad).

---

## 7. Canal de notificación — Telegram

**Pasos previos (una sola vez):**

1. Desde el móvil, abrir Telegram → buscar **@BotFather**.
2. Enviar `/newbot`, elegir nombre y username.
3. @BotFather devuelve un **token** tipo `123456789:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`.
4. Buscar el bot recién creado y enviarle al menos un mensaje (`/start` vale).
5. En el navegador abrir `https://api.telegram.org/bot<TOKEN>/getUpdates` y copiar el **chat_id** (campo `result[0].message.chat.id`).
6. En GitHub: Settings → Secrets and variables → Actions → New repository secret:
   - `TELEGRAM_BOT_TOKEN` = token de BotFather
   - `TELEGRAM_CHAT_ID` = chat_id

**Formato de mensaje sugerido:**

```
🔔 Vigilancia Enfermería del Trabajo — 24/04/2026

🟢 NUEVO en BOCM
Orden 1074/2025 — 9 plazas Diplomado en Enfermería Especialista del Trabajo
📌 Oposición · Personal laboral Comunidad de Madrid
🔗 https://www.bocm.es/...

🟡 NUEVO en metromadrid.es
Bolsa de empleo — Técnico/a en Enfermería del Trabajo
📌 Bolsa de empleo
🔗 https://www.metromadrid.es/...

⚠️ Fuente BOAM no respondió (reintentar mañana)
```

---

## 8. Workflow de GitHub Actions (`.github/workflows/daily.yml`)

```yaml
name: Vigilancia diaria
on:
  schedule:
    - cron: '0 7 * * *'   # 07:00 UTC ≈ 09:00 Madrid invierno / 08:00 verano
  workflow_dispatch:       # permite ejecución manual desde la UI

jobs:
  run:
    runs-on: ubuntu-latest
    permissions:
      contents: write       # necesario para commitear la rama state
    steps:
      - uses: actions/checkout@v4

      - name: Restaurar estado previo
        run: |
          git fetch origin state:state 2>/dev/null || echo "Primera ejecución, no hay rama state"
          mkdir -p state
          git show state:state/seen.db > state/seen.db 2>/dev/null || echo "BD vacía"

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'

      - run: pip install -r requirements.txt

      - name: Ejecutar vigilancia
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: python -m vigia.main

      - name: Guardar estado actualizado
        if: always()
        run: |
          git config user.name "vigia-bot"
          git config user.email "vigia-bot@users.noreply.github.com"
          git checkout --orphan state-new
          git reset
          git add -f state/seen.db
          git commit -m "Estado $(date -u +%Y-%m-%d)" || exit 0
          git branch -M state
          git push -f origin state
```

---

## 9. Consideraciones operativas

- **Primer arranque.** La primera vez detectará todo lo activo hoy. Implementar modo `--init` que puebla la BD sin enviar notificaciones, o aceptar la avalancha inicial.
- **Tolerancia a fallos.** Si BOCM cae un día, las demás fuentes deben ejecutarse igualmente. Los fallos se reportan al final del mensaje de Telegram, no tumban el proceso.
- **User-Agent.** Configurar uno identificable y con email de contacto (ej. `vigia-enfermeria/1.0 (contacto: tuemail@dominio.com)`). Los boletines oficiales lo aprecian y no bloquean.
- **BOCM sin API.** El sumario requiere scraping. El formato es estable pero puede cambiar; dejar logging abundante para detectar roturas rápido.
- **Revisión semestral.** Cada 6 meses revisar si alguna web ha cambiado estructura y si aparecen fuentes nuevas.
- **Coste.** Todo gratis: GitHub Actions (2000 min/mes gratis, este uso es de ~1 min/día = 30 min/mes), Telegram, APIs públicas.

---

## 10. Mejora futura — Capa de IA con la API de Claude (NO implementar todavía)

> **Estado:** en el radar, no se construye en la v1. Lanzaremos primero el sistema sin IA, evaluaremos durante semanas/meses, y volveremos a este apartado cuando haya datos reales (calidad de mensajes, falsos positivos, fuentes perdidas).

### 10.1 Por qué se deja para después

La IA no debe sustituir el motor de keywords (determinista, gratis, trazable). Su valor es como **capa de enriquecimiento** opcional, y solo merece la pena si después del primer despliegue detectamos:
- Mensajes de Telegram poco legibles o difíciles de interpretar de un vistazo
- Falsos positivos sutiles que la regex no filtra
- Sospecha de que se nos están escapando convocatorias

Si nada de eso pasa, no añadimos IA. La complejidad solo se justifica con un problema observado.

### 10.2 Dos usos previstos cuando llegue el momento

**A. Segunda opinión sobre cada candidato (síncrono, en cada ejecución diaria).**

Tras el filtro por keywords, mandar cada candidato a Claude Haiku 4.5 con un prompt que pida:
1. Confirmar si es realmente Enfermería del Trabajo (sí/no/dudoso)
2. Clasificar tipo (oposición / bolsa / traslado / nombramiento / OEP)
3. Extraer datos estructurados: organismo, nº de plazas, fecha límite de presentación, sistema selectivo, requisitos clave
4. Redactar resumen humano-legible de 2-3 líneas para Telegram

Salida esperada: JSON estructurado. Si la API falla o no hay credenciales, el sistema sigue funcionando con los datos crudos (no bloqueante).

**B. Auditoría mensual de fuentes (asíncrono, una vez al mes).**

Job adicional en GitHub Actions con cron mensual que:
1. Recopila todos los hallazgos del mes desde la BD
2. Cruza con los anuncios públicos de OEP del mes (BOE, BOCM)
3. Pregunta a Claude: "Dado este conjunto de hallazgos y este contexto de OEPs publicadas, ¿detectas fuentes u organismos que pueden tener convocatorias relevantes y que no estamos vigilando?"
4. Envía el análisis por Telegram como informe mensual

Coste anual estimado: céntimos.

### 10.3 Diseño técnico previsto

- Módulo nuevo `vigia/enricher.py` entre `extractor.py` y `notifier.py`
- Activable por variable de entorno `ENABLE_AI_ENRICHMENT=true` — desactivado por defecto
- Caché en SQLite: cada anuncio se enriquece una sola vez aunque aparezca varios días
- Secret nuevo en GitHub: `ANTHROPIC_API_KEY`
- Job mensual separado en `.github/workflows/monthly_audit.yml`

### 10.4 Criterio para reactivar este apartado

Volver a leer esta sección cuando se cumpla **alguna** de estas condiciones:
- Llevamos 1-2 meses con el sistema funcionando y los mensajes son poco útiles tal cual
- Detectamos a posteriori una convocatoria que nuestro sistema no pilló
- Aparecen falsos positivos que las reglas no consiguen filtrar sin perder hallazgos legítimos

---

## 11. Prompt para Claude Code

Una vez tengas este fichero guardado como `PLAN.md` en una carpeta vacía, abre Claude Code en esa carpeta y pega este prompt:

```
Tienes el plan completo en PLAN.md en este directorio. Léelo entero
primero, y luego implementa el sistema siguiendo esa especificación
en 5 pasos. Después de CADA paso, párate y valida con un test real
contra las fuentes antes de continuar.

IMPORTANTE: la sección 10 (Mejora futura — Capa de IA) NO se
implementa en esta versión. Léela para tener contexto pero no
construyas nada de ella. Sí debes dejar el código preparado para
que añadirla después sea fácil: el flujo entre extractor.py y
notifier.py debe permitir interponer un futuro enricher.py sin
refactor.

Paso 1 — Esqueleto base:
  - Estructura del repositorio tal y como se describe en el plan
  - config.py con los términos de búsqueda y fuentes
  - sources/base.py con la clase abstracta Source
  - storage.py con SQLite y deduplicación
  - notifier.py con Telegram
  - Incluye un script utils/test_telegram.py que envíe un mensaje
    de prueba para validar credenciales antes de seguir

Paso 2 — Fuentes primarias (boletines oficiales):
  - sources/boe.py usando la API oficial de sumarios
  - sources/bocm.py por scraping del sumario diario
  - sources/boam.py por scraping
  - Validar cada una contra los casos históricos de la sección 4
    del plan. NO sigas sin que todos los casos se detecten.

Paso 3 — Fuentes secundarias (portales propios):
  - Ayuntamiento de Madrid, Comunidad de Madrid, Metro de Madrid,
    Canal de Isabel II

Paso 4 — Agregadores:
  - administracion.gob.es, CODEM

Paso 5 — Integración y despliegue:
  - extractor.py con las reglas del plan
  - main.py con ejecución paralela y tolerancia a fallos
  - tests/test_extractor.py cubriendo los casos históricos
  - .github/workflows/daily.yml
  - README.md con instrucciones de setup paso a paso

Reglas de trabajo:
  - No inventes URLs ni estructuras HTML. Si una URL no responde o
    el HTML ha cambiado, investígalo con curl/requests antes de
    escribir el parser.
  - Usa requests + beautifulsoup4 + lxml para scraping; pypdf o
    pdfplumber para extraer texto de PDFs del BOCM/BOE.
  - User-Agent identificable en todas las requests.
  - Logging a INFO por defecto, DEBUG opcional por env var.
  - Tests unitarios del extractor ANTES de integrar fuentes.

Al terminar, dame una lista numerada y concreta de lo que YO tengo
que hacer: crear el bot de Telegram (pasos exactos), configurar los
GitHub Secrets, crear el repositorio, primer push, y cómo verificar
que el workflow funciona.
```

---

## 12. Qué pasa después del primer despliegue

1. **Primer día** — avalancha inicial con todo lo activo. Revisar y ajustar falsos positivos.
2. **Primera semana** — ver si alguna fuente da errores recurrentes; refinar parsers.
3. **Primer mes** — valorar si hay que añadir/quitar términos o fuentes.
4. **Cada 6 meses** — auditoría: ¿hay fuentes nuevas? ¿alguna cambió de URL? ¿el volumen de falsos positivos es razonable?
