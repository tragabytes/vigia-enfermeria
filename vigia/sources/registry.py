"""
Registro de fuentes del core: las genéricas, agnósticas al perfil profesional.

Cualquier perfil las reutiliza tal cual cambiando solo sus keywords. Las
fuentes ESPECÍFICAS de un perfil (p.ej. el feed del Colegio de Enfermería o
los hash-watchers sanitarios) NO viven aquí: las aporta el propio perfil vía
`Profile.extra_sources`. El registro efectivo lo compone `vigia.main`:

    SOURCE_REGISTRY = {**CORE_SOURCES, **get_active_profile().extra_sources}
"""
from vigia.sources.administracion_gob import AdministracionGobSource
from vigia.sources.aena import AENASource
from vigia.sources.ayuntamiento_madrid import AyuntamientoMadridSource
from vigia.sources.boam import BOAMSource
from vigia.sources.bocm import BOCMSource
from vigia.sources.boe import BOESource
from vigia.sources.canal_isabel_ii import CanalIsabelIISource
from vigia.sources.ciemat import CIEMATSource
from vigia.sources.comunidad_madrid import ComunidadMadridSource
from vigia.sources.csic_sede import CSICSedeSource
from vigia.sources.datos_madrid import DatosMadridSource
from vigia.sources.iac import IACSource
from vigia.sources.las_rozas import LasRozasSource
from vigia.sources.metro_madrid import MetroMadridSource
from vigia.sources.sap_successfactors import SapSuccessfactorsSource
from vigia.sources.universidades_madrid import UniversidadesMadridSource

# Fuentes genéricas: boletines oficiales, portales de organismos y agregadores
# que cualquier perfil puede aprovechar cambiando solo las keywords de matching.
CORE_SOURCES = {
    "boe": BOESource,
    "bocm": BOCMSource,
    "boam": BOAMSource,
    "ayuntamiento_madrid": AyuntamientoMadridSource,
    "comunidad_madrid": ComunidadMadridSource,
    "metro_madrid": MetroMadridSource,
    "canal_isabel_ii": CanalIsabelIISource,
    "administracion_gob": AdministracionGobSource,
    "datos_madrid": DatosMadridSource,
    "ciemat": CIEMATSource,
    "universidades_madrid": UniversidadesMadridSource,
    "sap_successfactors": SapSuccessfactorsSource,
    "las_rozas": LasRozasSource,
    "aena": AENASource,
    "iac": IACSource,
    "csic_sede": CSICSedeSource,
}
