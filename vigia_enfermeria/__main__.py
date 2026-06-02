"""Punto de entrada del bot de enfermería: `python -m vigia_enfermeria`.

Modelo "un perfil por proceso": el extractor y el enricher del core compilan sus
patrones/enums en import-time leyendo `get_active_profile()`. Por eso fijamos el
perfil de enfermería ANTES de importar el pipeline (`vigia.main`), con import
diferido dentro de `main()`.

El perfil de enfermería es el perfil por defecto del core (`DEFAULT`); lo fijamos
de forma explícita para no depender del default perezoso y quedar homogéneos con
los demás bots (p.ej. `vigia_docencia`).

Acepta los mismos flags que el core (se leen de sys.argv en `vigia.main.main`):
    python -m vigia_enfermeria                  # run completo
    python -m vigia_enfermeria --dry-run        # sin persistir ni notificar
    python -m vigia_enfermeria --since 2026-01-01
    python -m vigia_enfermeria --probe          # salud de las fuentes
    python -m vigia_enfermeria --maintenance    # reclasifica/enriquece la BD
"""
from __future__ import annotations

from vigia.profile import set_active_profile
from vigia._default_profile import DEFAULT

# 1) Fijar el perfil ANTES de tocar el pipeline.
set_active_profile(DEFAULT)


def main() -> None:
    # 2) Import diferido: al importarse aquí, vigia.main (y con él extractor,
    #    enricher, notifier y SOURCE_REGISTRY) se enlaza contra el perfil activo.
    from vigia.main import main as _core_main
    _core_main()


if __name__ == "__main__":
    main()
