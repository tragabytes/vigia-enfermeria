"""
Configuración central: términos de búsqueda, fuentes y constantes.
"""
import os
import unicodedata
import re

# ---------------------------------------------------------------------------
# Credenciales (leídas de entorno; nunca hardcodeadas)
# ---------------------------------------------------------------------------
TELEGRAM_BOT_TOKEN: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.environ.get("TELEGRAM_CHAT_ID", "")

# ---------------------------------------------------------------------------
# User-Agent
# ---------------------------------------------------------------------------
# Originalmente usábamos un UA identificable ("vigia-enfermeria/1.0 (contacto:
# ...; github: ...)") siguiendo la sección 9 del PLAN, pero sede.madrid.es
# (al que redirige www.madrid.es/boam) filtra UAs no-navegador y devuelve 403
# con cualquier identificación honesta. Validado el 2026-04-25: con UA Firefox
# devuelve 200 + 142KB; con el UA identificable, 403.
# Como las demás fuentes admiten cualquier UA y solo hacemos 1 request/día por
# fuente, usamos un UA de navegador estándar para toda la red de fuentes y
# evitamos complejidad de override por fuente.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) "
    "Gecko/20100101 Firefox/128.0"
)

# ---------------------------------------------------------------------------
# Términos de búsqueda (sección 3 del plan)
# ---------------------------------------------------------------------------

# Match fuerte: cualquiera de estos patrones en el texto normalizado → alerta
STRONG_PATTERNS: list[str] = [
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
]

# Match débil: solo si ADEMÁS aparece "enfermer" en el mismo fragmento (100 chars)
WEAK_CONTEXT_PATTERNS: list[tuple[str, str]] = [
    (r"salud laboral", r"enfermer"),
    (r"servicio de prevencion", r"enfermer"),
    (r"prevencion de riesgos laborales", r"enfermer"),
]

# Falsos positivos a descartar (antes de alertar)
FALSE_POSITIVE_PATTERNS: list[str] = [
    r"\btecnico.{0,10}cuidados auxiliares de enfermeria",
    r"\bauxiliar de enfermeria",
    r"enfermeria de salud mental",
    r"enfermeria pediatrica",
    r"enfermeria familiar y comunitaria",
    r"\bmatrona\b",
]

# ---------------------------------------------------------------------------
# Categorías de hallazgos
# ---------------------------------------------------------------------------
CATEGORIES = {
    "oposicion": "Oposición",
    "bolsa": "Bolsa de empleo",
    "traslado": "Concurso de traslados",
    "nombramiento": "Nombramiento / resolución",
    "oep": "Oferta de Empleo Público (OEP)",
    "otro": "Otro",
}

# Palabras clave para clasificar automáticamente.
# OJO: el matching es por substring sobre el texto NORMALIZADO (sin acentos
# ni caracteres especiales) — los hints también deben ir normalizados aquí.
# El orden importa: la primera categoría que matchea gana.
CATEGORY_HINTS: dict[str, list[str]] = {
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
# para contar hits del organismo. Pensar en variantes y formas comunes — las
# convocatorias se publican con denominaciones inconsistentes.
WATCHLIST_ORGS: list[dict] = [
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
]

# Días de antigüedad de la fecha de publicación a partir de los cuales se
# considera que un organismo ya no tiene proceso activo. Heurística: las
# convocatorias suelen tener plazo de 20-30 días desde publicación; pasados
# 90 días, en la inmensa mayoría de casos el plazo cerró. Aproximación
# pragmática hasta que el enricher sepa extraer la fecha de cierre real.
WATCHLIST_RECENCY_DAYS = 90

# ---------------------------------------------------------------------------
# Fuentes habilitadas
# ---------------------------------------------------------------------------
SOURCES_ENABLED: list[str] = [
    "boe",
    "bocm",
    "boam",
    "ayuntamiento_madrid",
    "comunidad_madrid",
    "metro_madrid",
    "canal_isabel_ii",
    "administracion_gob",
    "codem",
    "datos_madrid",
]


# ---------------------------------------------------------------------------
# Helpers de normalización
# ---------------------------------------------------------------------------
def normalize(text: str) -> str:
    """Minúsculas, sin acentos, sin caracteres especiales → solo [a-z0-9 ]."""
    nfkd = unicodedata.normalize("NFKD", text.lower())
    ascii_text = nfkd.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9\s]", " ", ascii_text)
