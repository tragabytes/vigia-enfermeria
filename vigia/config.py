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
# User-Agent identificable (ver sección 9 del plan)
# ---------------------------------------------------------------------------
USER_AGENT = "vigia-enfermeria/1.0 (contacto: l.t.lombardia@gmail.com; github: vigia-enfermeria)"

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
]


# ---------------------------------------------------------------------------
# Helpers de normalización
# ---------------------------------------------------------------------------
def normalize(text: str) -> str:
    """Minúsculas, sin acentos, sin caracteres especiales → solo [a-z0-9 ]."""
    nfkd = unicodedata.normalize("NFKD", text.lower())
    ascii_text = nfkd.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9\s]", " ", ascii_text)
