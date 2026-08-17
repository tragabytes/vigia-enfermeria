"""Fija el perfil de enfermería ANTES de que se importe el pipeline del core.

`conftest.py` se ejecuta al arrancar pytest, antes de recolectar los módulos de
test. Como el extractor y el enricher del core compilan sus patrones/enums en
import-time leyendo `get_active_profile()`, fijar aquí DEFAULT (Enfermería del
Trabajo) hace explícito el perfil bajo test en vez de depender del default
perezoso del core — igual que hace `vigia_enfermeria/__main__.py` en runtime y
homogéneo con `vigia-docencia`.

Para la validación offline local (sin `pip install vigia-core`), añade el repo
del core al PYTHONPATH al invocar:
    PYTHONPATH=../vigia-core python -m pytest tests
En CI, vigia-core está pip-instalado y el PYTHONPATH no hace falta.
"""
from vigia.profile import set_active_profile
from vigia._default_profile import DEFAULT

set_active_profile(DEFAULT)
