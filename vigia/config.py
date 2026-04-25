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

# Palabras clave para clasificar automáticamente
CATEGORY_HINTS: dict[str, list[str]] = {
    "bolsa": ["bolsa de empleo", "bolsa de trabajo", "contratacion temporal"],
    "traslado": ["concurso de traslados", "concurso de meritos", "concurso-traslado"],
    "oposicion": ["convocatoria", "proceso selectivo", "pruebas selectivas", "concurso-oposicion", "oposicion"],
    "oep": ["oferta de empleo publico", "oep "],
    "nombramiento": ["nombramiento", "resolucion", "adjudicacion"],
}


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
