"""
Perfil por defecto: Enfermería del Trabajo.

Contiene los valores históricos del bot original (keywords de matching,
watchlist de organismos, prompts del LLM, branding). Es el `Profile` que el
core usa cuando nadie fija otro con `set_active_profile()`, de modo que el
bot de enfermería sigue funcionando exactamente igual.

NOTA: estos valores vivían antes repartidos en `config.py`, `enricher.py` y
`diff_summarizer.py`. Se centralizan aquí como la fuente de verdad única del
perfil enfermería. `config.py` los reexpone mediante una fachada (`__getattr__`)
para no romper los imports existentes.
"""
from __future__ import annotations

from vigia.profile import Profile
from vigia.sources.canal_isabel_ii_calendario import CanalIsabelIICalendarioSource
from vigia.sources.cm_ficha_enfermeria import ComunidadMadridFichaEnfermeriaSource
from vigia.sources.codem import CODEMSource
from vigia.sources.isciii import ISCIIISource

# ---------------------------------------------------------------------------
# Términos de búsqueda (sección 3 del plan)
# ---------------------------------------------------------------------------

# Match fuerte: cualquiera de estos patrones en el texto normalizado → alerta
_STRONG_PATTERNS = [
    r"enfermeri[ao]\s+del\s+trabajo",             # "Enfermería del Trabajo"
    r"enfermeri[ao]\s+de\s+trabajo",              # "Enfermería de Trabajo" (BOE sin artículo)
    r"enfermera\s+del\s+trabajo",
    r"enfermero\s+del\s+trabajo",
    r"enfermera\s+de\s+trabajo",
    r"enfermero\s+de\s+trabajo",
    r"especialista\s+en\s+enfermeria\s+del\s+trabajo",
    r"especialista\s+en\s+enfermeria\s+de\s+trabajo",
    r"enfermeria\s+especialista\b.{0,60}trabajo",  # hasta ~5 palabras entre medio
    r"diplomado\s+en\s+enfermeria\s+especialista.{0,80}trabajo",
    r"enfermera\s+de\s+salud\s+laboral",
    r"enfermero\s+de\s+salud\s+laboral",
    r"enfermeria\s+de\s+salud\s+laboral",
    r"enfermer[ao]\s+especialista.{0,30}trabajo",  # "Enfermero/a Especialista ... Trabajo"
    # Variante "Enfermero/a del Trabajo" — tras normalize(), la "/" se convierte
    # en espacio así que el texto queda "enfermero a del trabajo". Soportamos
    # la "a"/"o" intercalada como opcional.
    r"enfermer[ao]\s+(?:[ao]\s+)?del\s+trabajo",
    r"enfermer[ao]\s+(?:[ao]\s+)?de\s+trabajo",
    # "Enfermería de Empresa" — denominación histórica previa al MIR, sigue en
    # uso en RTVE y otras empresas públicas estatales. A efectos formativos es
    # sinónimo de Enfermería del Trabajo en el catálogo del Ministerio.
    r"enfermeri[ao]\s+de\s+empresa",
    r"enfermer[ao]\s+(?:[ao]\s+)?de\s+empresa",
    r"diplomado\s+en\s+enfermeria\s+de\s+empresa",
    # ATS/DUE — denominación pre-Bolonia que sigue apareciendo en
    # convocatorias antiguas y en algunas administraciones (Tribunal de
    # Cuentas, Defensa, etc.). Ej. real: BOE-A-2022-23854 (Tribunal de
    # Cuentas, 30/12/2022): "ATS/DUE de Prevención y Salud laboral".
    # Tras normalize() la "/" se convierte en espacio: "ats due de
    # prevencion y salud laboral".
    r"ats\s*[-/]?\s*due\s+de\s+prevenci[óo]n",
    r"ats\s*[-/]?\s*due\s+de\s+salud\s+laboral",
    r"ats\s+due\s+de\s+prevencion",
    r"ats\s+due\s+de\s+salud\s+laboral",
    # EGOA Sanidad y Consumo — escala AGE del Ministerio de Sanidad cuyo
    # turno libre incluye un Área de Enfermería (28+5 plazas en EGOA 2025,
    # convocatoria BOE-A-2025-26156). El perfil es salud pública / vigilancia
    # epidemiológica / vacunas, NO Enfermería del Trabajo, pero un Enfermero
    # del Trabajo puede optar (basta título de Diplomatura/Grado en
    # Enfermería). Lo capturamos vía nombre exacto de la escala porque es
    # un identificador único usado por el ministerio en TODOS los actos del
    # proceso (convocatoria, admitidos, plantillas, nombramientos).
    r"escala\s+de\s+gestion\s+de\s+organismos\s+autonomos.{0,40}sanidad\s+y\s+consumo",
]

# Match débil: solo si ADEMÁS aparece "enfermer" en el mismo fragmento (100 chars)
_WEAK_CONTEXT_PATTERNS = [
    (r"salud laboral", r"enfermer"),
    (r"servicio de prevencion", r"enfermer"),
    (r"prevencion de riesgos laborales", r"enfermer"),
    # ATS/DUE histórico: si aparece junto a contexto de PRL/salud laboral,
    # es match. El patrón "ats due" ya implica enfermería (DUE = Diplomado
    # Universitario en Enfermería), por eso aquí el confirmador es el
    # contexto laboral en vez de "enfermer".
    (r"ats\s+due", r"prevencion|salud laboral|riesgos laborales"),
]

# Filtro rápido aplicado por las fuentes sobre el título (o el texto
# agregado del listado) antes de materializar un RawItem. Es un primer
# corte grueso para evitar que items obviamente irrelevantes lleguen al
# extractor — las reglas reales de matching (STRONG/WEAK) viven en
# `_STRONG_PATTERNS` / `_WEAK_CONTEXT_PATTERNS` y se aplican después.
_FAST_KEYWORDS = ["enfermer", "salud laboral", "prevencion de riesgos"]

# Falsos positivos a descartar (antes de alertar)
_FALSE_POSITIVE_PATTERNS = [
    r"\btecnico.{0,10}cuidados auxiliares de enfermeria",
    r"\bauxiliar de enfermeria",
    r"enfermeria de salud mental",
    r"enfermeria pediatrica",
    r"enfermeria familiar y comunitaria",
    r"\bmatrona\b",
]

# ---------------------------------------------------------------------------
# Clasificación de categorías
# ---------------------------------------------------------------------------
# Palabras clave para clasificar automáticamente.
# OJO: el matching es por substring sobre el texto NORMALIZADO (sin acentos
# ni caracteres especiales) — los hints también deben ir normalizados aquí.
# El orden importa: la primera categoría que matchea gana.
_CATEGORY_HINTS = {
    "bolsa": [
        "bolsa de empleo",
        "bolsa de trabajo",
        "bolsa unica",          # cubre "Bolsa única de empleo temporal..."
        "contratacion temporal",
    ],
    "traslado": ["concurso de traslados", "concurso de meritos", "concurso-traslado"],
    "oposicion": [
        "convocatoria",
        "proceso selectivo",
        "pruebas selectivas",
        "concurso-oposicion",
        "oposicion",
        "estabilizacion",   # "proceso de estabilización" en SERMAS
        "acceso libre",     # "proceso de acceso libre para Diplomado..."
    ],
    "oep": ["oferta de empleo publico", "oep "],
    "nombramiento": ["nombramiento", "resolucion", "adjudicacion"],
}

# ---------------------------------------------------------------------------
# Watchlist de organismos vigilados (sección 06 del dashboard)
# ---------------------------------------------------------------------------
# Cada `patterns` es una lista de substrings YA NORMALIZADOS (sin acentos,
# minúsculas, alfanumérico) que se busca dentro de `normalize(titulo+summary)`
# para contar hits del organismo.
_WATCHLIST_ORGS = [
    {"id": "T-01", "name": "SERMAS",
     "desc": "Servicio Madrileño de Salud (incluye 11 hospitales públicos)",
     "patterns": ["sermas", "servicio madrileno de salud"]},
    {"id": "T-02", "name": "H. La Paz",
     "desc": "Hospital Universitario La Paz — Servicio de Prevención",
     "patterns": ["hospital universitario la paz", "hospital la paz", " la paz "]},
    {"id": "T-03", "name": "H. 12 de Octubre",
     "desc": "Hospital Universitario 12 de Octubre — Salud Laboral",
     "patterns": ["12 de octubre", "doce de octubre"]},
    {"id": "T-04", "name": "H. Gregorio Marañón",
     "desc": "Hospital Universitario Gregorio Marañón — Prevención",
     "patterns": ["gregorio maranon"]},
    {"id": "T-05", "name": "H. Ramón y Cajal",
     "desc": "Hospital Universitario Ramón y Cajal — Salud Laboral",
     "patterns": ["ramon y cajal"]},
    {"id": "T-06", "name": "SUMMA 112",
     "desc": "Servicio de Urgencia Médica de Madrid",
     "patterns": ["summa 112", "summa112", "urgencia medica de madrid"]},
    {"id": "T-07", "name": "FNMT-RCM",
     "desc": "Fábrica Nacional de Moneda y Timbre — Servicio Médico",
     "patterns": ["fnmt", "fabrica nacional de moneda", "casa de la moneda"]},
    {"id": "T-08", "name": "EMT Madrid",
     "desc": "Empresa Municipal de Transportes — Salud Laboral",
     "patterns": [" emt ", "empresa municipal de transportes"]},
    {"id": "T-09", "name": "Metro de Madrid",
     "desc": "Metro de Madrid S.A. — Servicio de Prevención propio",
     "patterns": ["metro de madrid", "metro madrid"]},
    {"id": "T-10", "name": "Canal de Isabel II",
     "desc": "Canal de Isabel II — SP Mancomunado",
     "patterns": ["canal de isabel ii", "canal isabel ii"]},
    {"id": "T-11", "name": "Ayto. Madrid",
     "desc": "Ayuntamiento de Madrid — IMD, Bomberos, Policía Municipal",
     "patterns": ["ayuntamiento de madrid", "ayto de madrid",
                  "imd madrid", "bomberos madrid", "policia municipal madrid"]},
    {"id": "T-12", "name": "Las Rozas",
     "desc": "Ayto. de Las Rozas — Corredor A-6",
     "patterns": ["las rozas"]},
    {"id": "T-13", "name": "Majadahonda",
     "desc": "Ayto. de Majadahonda — Corredor A-6",
     "patterns": ["majadahonda"]},
    {"id": "T-14", "name": "Pozuelo de Alarcón",
     "desc": "Ayto. de Pozuelo de Alarcón — Corredor A-6",
     "patterns": ["pozuelo"]},
    {"id": "T-15", "name": "Boadilla del Monte",
     "desc": "Ayto. de Boadilla del Monte — Corredor A-6",
     "patterns": ["boadilla"]},
    {"id": "T-16", "name": "Villaviciosa de Odón",
     "desc": "Ayto. de Villaviciosa de Odón — Corredor A-6",
     "patterns": ["villaviciosa de odon"]},
    {"id": "T-17", "name": "Alcorcón",
     "desc": "Ayto. de Alcorcón — Corredor A-5",
     "patterns": ["alcorcon"]},
    {"id": "T-18", "name": "Móstoles",
     "desc": "Ayto. de Móstoles — Corredor A-5",
     "patterns": ["mostoles"]},
    {"id": "T-19", "name": "Fuenlabrada",
     "desc": "Ayto. de Fuenlabrada — Corredor A-5",
     "patterns": ["fuenlabrada"]},
    {"id": "T-20", "name": "Cuerpo Militar Sanidad",
     "desc": "Ministerio de Defensa — Esp. Enfermería del Trabajo",
     "patterns": ["cuerpo militar de sanidad", "cuerpo militar sanidad",
                  "ministerio de defensa"]},
    {"id": "T-21", "name": "INSS",
     "desc": "Instituto Nacional de la Seguridad Social",
     "patterns": [" inss ", "instituto nacional de la seguridad social"]},
    {"id": "T-22", "name": "AGE — Política Territorial",
     "desc": "Delegaciones del Gobierno — concurso de traslados",
     "patterns": ["politica territorial", "delegaciones del gobierno",
                  "delegacion del gobierno"]},
    {"id": "T-23", "name": "CIEMAT",
     "desc": "Centro de Investigaciones Energéticas, Medioambientales y Tecnológicas",
     "patterns": ["ciemat"]},
    {"id": "T-24", "name": "Policía Nacional",
     "desc": "Cuerpo Nacional de Policía — Servicio de Prevención y Sanitario",
     "patterns": ["policia nacional", "cuerpo nacional de policia",
                  "direccion general de la policia"]},
    {"id": "T-25", "name": "Guardia Civil",
     "desc": "Cuerpo de la Guardia Civil — Servicio de Sanidad",
     "patterns": ["guardia civil"]},
    {"id": "T-26", "name": "Instituciones Penitenciarias",
     "desc": "Secretaría General de Instituciones Penitenciarias",
     "patterns": ["instituciones penitenciarias"]},
    {"id": "T-27", "name": "UCM",
     "desc": "Universidad Complutense de Madrid — PTGAS / Servicio de Prevención",
     "patterns": ["universidad complutense", "complutense de madrid", "ucm"]},
    {"id": "T-28", "name": "UAH",
     "desc": "Universidad de Alcalá — PTGAS / Servicio de Prevención",
     "patterns": ["universidad de alcala", "alcala de henares", " uah "]},
    {"id": "T-29", "name": "UAM",
     "desc": "Universidad Autónoma de Madrid — PTGAS / Servicio de Prevención y Salud",
     "patterns": ["universidad autonoma de madrid", "autonoma de madrid", " uam "]},
    {"id": "T-30", "name": "RENFE",
     "desc": "Renfe Operadora — Servicio de Prevención (parser propio SAP SuccessFactors)",
     "patterns": ["renfe", "renfe operadora"]},
    {"id": "T-31", "name": "ADIF",
     "desc": "Administrador de Infraestructuras Ferroviarias — cobertura indirecta BOE/BOCM (Akamai bloquea parser directo)",
     "patterns": ["adif", "administrador de infraestructuras ferroviarias"]},
    {"id": "T-32", "name": "AENA",
     "desc": "AENA — parser propio del portal PFSrv (server-rendered) + cobertura BOE/BOCM",
     "patterns": [" aena ", "aeropuertos espanoles"]},
    {"id": "T-33", "name": "Correos",
     "desc": "Sociedad Estatal Correos y Telégrafos — Servicio de Prevención (parser propio SAP SuccessFactors)",
     "patterns": ["correos", "sociedad estatal correos"]},
    {"id": "T-34", "name": "Navantia",
     "desc": "Navantia — Servicio de Prevención (parser propio SAP SuccessFactors)",
     "patterns": ["navantia"]},
    {"id": "T-35", "name": "Paradores",
     "desc": "Paradores de Turismo — cobertura indirecta BOE/BOCM (sin portal público de empleo)",
     "patterns": ["paradores", "paradores de turismo"]},
    {"id": "T-36", "name": "RTVE",
     "desc": "Radio Televisión Española — cobertura indirecta BOE/BOCM (SPA absoluta sin endpoint público)",
     "patterns": ["rtve", "radio television espanola", "radio y television espanola"]},
    {"id": "T-37", "name": "SELAE Loterías",
     "desc": "Sociedad Estatal Loterías y Apuestas — cobertura indirecta BOE/BOCM (Akamai bloquea parser directo)",
     "patterns": ["loterias y apuestas", "selae"]},
    {"id": "T-38", "name": "ISCIII",
     "desc": "Instituto de Salud Carlos III — Servicio de Prevención (parser hash-watcher de proceso-selectivo + cobertura BOE/BOCM)",
     "patterns": ["isciii", "instituto de salud carlos iii"]},
    {"id": "T-39", "name": "EGOA Sanidad y Consumo",
     "desc": "Escala de Gestión de Organismos Autónomos, esp. Sanidad y Consumo (Min. Sanidad) — incluye Área de Enfermería abierta a Diplomatura/Grado en Enfermería",
     "patterns": ["escala de gestion de organismos autonomos", "egoa"]},
    {"id": "T-40", "name": "IAC",
     "desc": "Instituto de Astrofísica de Canarias — parser propio del portal ofertas-de-trabajo + cobertura BOE",
     "patterns": ["iac", "instituto de astrofisica de canarias", "astrofisica de canarias"]},
    {"id": "T-41", "name": "CSIC",
     "desc": "Consejo Superior de Investigaciones Científicas — parser propio sede.csic.gob.es + cobertura BOE",
     "patterns": ["csic", "consejo superior de investigaciones cientificas"]},
    {"id": "T-42", "name": "INIA-CSIC",
     "desc": "Instituto Nacional de Investigación y Tecnología Agraria y Alimentaria (INIA-CSIC) — cobertura indirecta BOE (parser propio pendiente, SharePoint AJAX)",
     "patterns": ["inia", "instituto nacional de investigacion y tecnologia agraria"]},
    {"id": "T-43", "name": "IEO-CSIC",
     "desc": "Instituto Español de Oceanografía (IEO-CSIC) — cobertura indirecta BOE (parser propio pendiente, portal con timeout)",
     "patterns": ["ieo", "instituto espanol de oceanografia"]},
]

# Días de antigüedad de la fecha de publicación a partir de los cuales se
# considera que un organismo ya no tiene proceso activo.
_WATCHLIST_RECENCY_DAYS = 90

# ---------------------------------------------------------------------------
# Fuentes habilitadas
# ---------------------------------------------------------------------------
_SOURCES_ENABLED = [
    "boe",
    "bocm",
    "boam",
    "ayuntamiento_madrid",
    "comunidad_madrid",
    "cm_ficha_enfermeria",
    "metro_madrid",
    "canal_isabel_ii",
    "administracion_gob",
    "codem",
    "datos_madrid",
    "ciemat",
    "isciii",
    "universidades_madrid",
    "sap_successfactors",
    "las_rozas",
    "aena",
    "iac",
    "csic_sede",
]

# ---------------------------------------------------------------------------
# Enricher (Sonnet 4.6 + tool use)
# ---------------------------------------------------------------------------
_ENRICHER_SYSTEM_PROMPT = """Eres un asistente que extrae datos estructurados de convocatorias de empleo público en España, especializado en plazas para Enfermería del Trabajo (también llamada Enfermería de Empresa o Enfermería de Salud Laboral, sinónimos a efectos de catálogo del Ministerio de Sanidad).

Tu trabajo: recibir el dato bruto de una convocatoria y devolver un JSON con los campos clave. Puedes (y debes, cuando los datos no estén en el resumen recibido) usar la tool `fetch_url` para descargar el cuerpo del boletín o el PDF de bases.

CRITERIOS PARA `is_relevant`:
- TRUE → la convocatoria ofrece plazas, bolsa o concurso de traslados específicamente para la especialidad de Enfermería del Trabajo / Salud Laboral / Enfermería de Empresa, o es un servicio de prevención de riesgos laborales que requiere esa titulación.
- FALSE → falsos positivos típicos: Enfermería de Salud Mental, Pediátrica, Familiar y Comunitaria, Geriátrica, Obstétrico-Ginecológica (matronas), o Enfermería general sin especialidad. También FALSE si solo es un nombramiento/lista provisional/cese sin plazas nuevas para la especialidad.
- En la duda, prioriza FALSE — el sistema reduce ruido eliminando items con is_relevant=false.

CRITERIOS PARA `process_type`:
- "oposicion" → proceso selectivo / pruebas selectivas / concurso-oposición de acceso libre
- "bolsa" → bolsa de empleo, bolsa única, contratación temporal estructurada
- "concurso_traslados" → concurso de traslados / concurso de méritos entre estatutarios
- "interinaje" → nombramiento de interino / sustitución concreta
- "temporal" → contrato temporal puntual no incluido en bolsa
- "otro" → cualquier otro caso

CRITERIOS PARA `fase`:
- "convocatoria" → publicación inicial con plazo de inscripción abierto
- "admitidos_provisional" / "admitidos_definitivo" → listas de admitidos
- "examen" → fechas/sedes del ejercicio
- "calificacion" → resultados de un ejercicio o calificación final
- "propuesta_nombramiento" → resolución de adjudicación
- "otro" → cualquier otro estado intermedio

REGLAS DE EXTRACCIÓN:
- Fechas en formato `YYYY-MM-DD`. Si solo conoces el mes y año, deja `null`.
- `plazas`: solo el TOTAL de plazas convocadas; si no aparece, `null`.
- `tasas_eur`: tasa de inscripción base en euros (no descuentos ni reducciones).
- `url_bases`: URL al PDF/HTML con las bases completas (a veces es un anexo distinto del que recibes).
- `requisitos_clave`: lista corta (≤4) de requisitos imprescindibles (titulación específica, experiencia, etc.). No copies todo el listado del BOE — solo lo más diferenciador.
- `next_action`: una frase ≤140 chars con la acción inmediata que el usuario debe tomar (ej. "Presentar instancia online en sede.comunidad.madrid antes del 15/05/2026").
- `summary`: ~200 caracteres en estilo telegrama, factual, sin frases introductorias. Mismo formato que el enricher v1.
- `confidence`: 0..1 según lo seguro que estés del extracto general.
- Si un campo no es deducible con razonable certeza, devuélvelo como `null`. NO INVENTES NADA.

USO DE LA TOOL:
- Si el título y `raw_text` son suficientes para todos los campos pedidos, NO llames a la tool — responde directamente con el JSON.
- Si te falta algún dato clave (deadline, plazas, tasas, bases) y la URL principal está en dominio oficial, llámala una vez para inspeccionar el cuerpo.
- IMPORTANTE — falsos negativos a evitar: si el sistema te ha enviado este item es porque un matcher automático YA detectó "Enfermería del Trabajo", "Enfermería de Empresa", "Enfermería de Salud Laboral" o "salud laboral + enfermer" en el cuerpo descargado de la convocatoria. Si el `raw_text` que recibes no muestra esa evidencia, ES PORQUE LLEGA TRUNCADO — los listados de plazas suelen estar más adelante en el documento. En ese caso DEBES llamar a `fetch_url` para descargar el HTML/PDF completo antes de marcar `is_relevant=false`. Solo descarta si tras consultar la URL tampoco aparece la especialidad.
- Como mucho 2 llamadas a tool por item. Después responde con lo que tengas.

FORMATO DE SALIDA OBLIGATORIO:
Responde SOLO con un bloque JSON válido (puedes envolverlo en ```json … ``` si quieres). Sin texto antes ni después. El JSON debe seguir este schema (todos los campos opcionales pueden ser null):

{
  "is_relevant": true|false,
  "relevance_reason": "string",
  "process_type": "oposicion|bolsa|concurso_traslados|interinaje|temporal|otro",
  "summary": "string ~200 chars",
  "organismo": "string|null",
  "centro": "string|null",
  "plazas": int|null,
  "deadline_inscripcion": "YYYY-MM-DD|null",
  "fecha_publicacion_oficial": "YYYY-MM-DD|null",
  "tasas_eur": float|null,
  "url_bases": "string|null",
  "url_inscripcion": "string|null",
  "requisitos_clave": ["string", ...] | [],
  "fase": "convocatoria|admitidos_provisional|admitidos_definitivo|examen|calificacion|propuesta_nombramiento|otro",
  "next_action": "string|null",
  "confidence": 0.0..1.0
}"""

# Keywords ordenadas por prioridad: las que confirman match positivo del
# extractor van primero (HIGH); las contextuales (WEAK / genéricas) detrás.
_ENRICHER_SNIPPET_KEYWORDS_HIGH = [
    # Strong matches del extractor — la propia especialidad
    "enfermería del trabajo", "enfermeria del trabajo",
    "enfermería de empresa", "enfermeria de empresa",
    "enfermería de salud laboral", "enfermeria de salud laboral",
    "enfermero del trabajo", "enfermera del trabajo",
    "enfermero de empresa", "enfermera de empresa",
    "enfermero/a del trabajo", "enfermero/a de empresa",
    "especialista en enfermería del trabajo",
    "especialidad enfermería del trabajo",
    # Categoría profesional convocada
    "especialidad enfermería", "especialidad enfermeria",
    "especialidad en enfermería", "especialidad en enfermeria",
    "especialista en enfermería", "especialista en enfermeria",
]
_ENRICHER_SNIPPET_KEYWORDS_LOW = [
    "enfermería (prevención", "enfermeria (prevencion",
    "(prevención riesgos", "(prevencion riesgos",
    "salud laboral",
    "servicio de prevención", "servicio de prevencion",
    "prevención de riesgos laborales", "prevencion de riesgos laborales",
    "(prl)", " prl ",
]

# Whitelist estricta de hostnames permitidos en `fetch_url` (anti-SSRF).
_ENRICHER_ALLOWED_FETCH_HOSTS = frozenset({
    # BOE
    "boe.es", "www.boe.es",
    # BOCM (sumario y descargas)
    "bocm.es", "www.bocm.es",
    # Comunidad de Madrid (sede y portales relacionados)
    "comunidad.madrid", "www.comunidad.madrid",
    "sede.comunidad.madrid", "transparencia.comunidad.madrid",
    # Ayuntamiento de Madrid (incluye sede que sirve BOAM)
    "madrid.es", "www.madrid.es", "sede.madrid.es",
    "transparencia.madrid.es",
    # Datos abiertos del Ayto.
    "datos.madrid.es",
    # Canal de Isabel II (web de convocatorias)
    "convocatoriascanaldeisabelsegunda.es",
    "www.convocatoriascanaldeisabelsegunda.es",
    # CODEM
    "codem.es", "www.codem.es",
})

# ---------------------------------------------------------------------------
# Diff summarizer (Sonnet 4.6)
# ---------------------------------------------------------------------------
_DIFF_SYSTEM_PROMPT = (
    "Eres analista de convocatorias de Enfermería del Trabajo. Recibes el "
    "unified diff entre dos snapshots de la misma página oficial (cuerpo "
    "HTML extraído como texto plano).\n\n"
    "Tu tarea:\n"
    "1. Clasifica el cambio como SUSTANTIVO (información nueva relevante "
    "para un opositor: nueva fase publicada, nuevo plazo, lista de "
    "admitidos, calendario, examen, resolución, cambio de tribunal, cambio "
    "en plazas, modificación de fechas relevantes…) o COSMÉTICO (sólo "
    "cambia el timestamp \"Última actualización\", formato, espacios en "
    "blanco, redacción equivalente sin información nueva).\n"
    "2. Si es SUSTANTIVO: redacta UNA frase ≤100 caracteres explicando qué "
    "ha cambiado, en español neutro y factual.\n"
    "3. Si es COSMÉTICO: deja el resumen vacío.\n\n"
    "Devuelve EXACTAMENTE este JSON sin texto adicional ni markdown:\n"
    "{\"sustantivo\": true|false, \"resumen\": \"...\"}"
)


# ---------------------------------------------------------------------------
# Perfil por defecto
# ---------------------------------------------------------------------------
DEFAULT = Profile(
    slug="enfermeria-trabajo",
    display_name="Vigilancia Enfermería del Trabajo",
    dashboard_url="https://tragabytes.github.io/vigia-enfermeria/",
    test_message="✅ vigia-enfermeria: conexión OK",
    strong_patterns=tuple(_STRONG_PATTERNS),
    weak_context_patterns=tuple(_WEAK_CONTEXT_PATTERNS),
    false_positive_patterns=tuple(_FALSE_POSITIVE_PATTERNS),
    fast_keywords=tuple(_FAST_KEYWORDS),
    category_hints=_CATEGORY_HINTS,
    watchlist_orgs=tuple(_WATCHLIST_ORGS),
    watchlist_recency_days=_WATCHLIST_RECENCY_DAYS,
    enricher_system_prompt=_ENRICHER_SYSTEM_PROMPT,
    enricher_snippet_keywords_high=tuple(_ENRICHER_SNIPPET_KEYWORDS_HIGH),
    enricher_snippet_keywords_low=tuple(_ENRICHER_SNIPPET_KEYWORDS_LOW),
    enricher_allowed_fetch_hosts=_ENRICHER_ALLOWED_FETCH_HOSTS,
    diff_system_prompt=_DIFF_SYSTEM_PROMPT,
    sources_enabled=tuple(_SOURCES_ENABLED),
    # Fuentes específicas del perfil enfermería (no genéricas): el feed del
    # Colegio de Enfermería de Madrid y los hash-watchers sanitarios. El core
    # NO las conoce; las registra el perfil.
    extra_sources={
        "codem": CODEMSource,
        "cm_ficha_enfermeria": ComunidadMadridFichaEnfermeriaSource,
        "isciii": ISCIIISource,
        "canal_isabel_ii_calendario": CanalIsabelIICalendarioSource,
    },
    source_params={},
)
