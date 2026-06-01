"""
Configuración central del core: credenciales, constantes genéricas y fachada
al perfil activo.

Los términos de búsqueda (STRONG/WEAK/FALSE_POSITIVE patterns, FAST_KEYWORDS),
la clasificación (CATEGORY_HINTS), la watchlist (WATCHLIST_ORGS,
WATCHLIST_RECENCY_DAYS) y la lista de fuentes (SOURCES_ENABLED) son
ESPECÍFICOS de cada perfil profesional y viven en el `Profile` activo (ver
`vigia/profile.py` y `vigia/_default_profile.py`). Este módulo los reexpone
con sus nombres históricos mediante `__getattr__` (PEP 562) para no romper los
imports existentes (`from vigia.config import FAST_KEYWORDS`, etc.).

Lo que se queda aquí es genérico y común a todos los perfiles: credenciales
de Telegram, User-Agent, el catálogo de CATEGORIES y el helper `normalize`.
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
# Categorías de hallazgos (genérico, común a todos los perfiles)
# ---------------------------------------------------------------------------
CATEGORIES = {
    "oposicion": "Oposición",
    "bolsa": "Bolsa de empleo",
    "traslado": "Concurso de traslados",
    "nombramiento": "Nombramiento / resolución",
    "oep": "Oferta de Empleo Público (OEP)",
    "otro": "Otro",
}

# ---------------------------------------------------------------------------
# Fachada al perfil activo (PEP 562)
# ---------------------------------------------------------------------------
# Estos símbolos eran constantes de este módulo; ahora viven en el `Profile`
# activo. Se reexponen con su nombre histórico para no tocar los ~16 imports
# existentes (`from vigia.config import FAST_KEYWORDS`, etc.). El valor se
# resuelve en el momento del import del consumidor contra el perfil activo
# (que en un proceso normal es el DEFAULT, fijado de forma perezosa la primera
# vez que se accede). Modelo: un proceso = un bot = un perfil.
#
# Se devuelven como `list`/`dict` (no las tuplas internas del Profile) para
# preservar exactamente el tipo que tenían estas constantes históricamente.
_PROFILE_ATTRS = {
    # nombre histórico -> (atributo del Profile, ¿convertir a list?)
    "STRONG_PATTERNS": ("strong_patterns", True),
    "WEAK_CONTEXT_PATTERNS": ("weak_context_patterns", True),
    "FALSE_POSITIVE_PATTERNS": ("false_positive_patterns", True),
    "FAST_KEYWORDS": ("fast_keywords", True),
    "CATEGORY_HINTS": ("category_hints", False),
    "WATCHLIST_ORGS": ("watchlist_orgs", True),
    "WATCHLIST_RECENCY_DAYS": ("watchlist_recency_days", False),
    "SOURCES_ENABLED": ("sources_enabled", True),
}


def __getattr__(name: str):
    """Resuelve los símbolos de perfil contra el perfil activo (PEP 562)."""
    spec = _PROFILE_ATTRS.get(name)
    if spec is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    attr, as_list = spec
    from vigia.profile import get_active_profile
    value = getattr(get_active_profile(), attr)
    return list(value) if as_list else value


# ---------------------------------------------------------------------------
# Helpers de normalización (genérico)
# ---------------------------------------------------------------------------
def normalize(text: str) -> str:
    """Minúsculas, sin acentos, sin caracteres especiales → solo [a-z0-9 ]."""
    nfkd = unicodedata.normalize("NFKD", text.lower())
    ascii_text = nfkd.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9\s]", " ", ascii_text)
