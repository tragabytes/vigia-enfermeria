# CLAUDE.md — vigia-enfermeria

Bot de **Enfermería del Trabajo** en la administración pública de Madrid: cada día laborable busca convocatorias, las resume con IA, avisa por Telegram y publica un dashboard (<https://tragabytes.github.io/vigia-enfermeria>). Es el bot original de vigia y un **repo fino**: todo el pipeline, las fuentes y hasta su perfil viven en [vigia-core](https://github.com/tragabytes/vigia-core), que se instala por etiqueta.

| Fichero | Para qué |
|---|---|
| [`RELEVO.md`](RELEVO.md) | Estado y pendientes de este bot. **Punto de entrada** |
| [vigia-core: `CLAUDE.md`](https://github.com/tragabytes/vigia-core/blob/main/CLAUDE.md) | Reglas del pipeline, comunes a todos los bots |
| [vigia-core: `DECISIONES.md`](https://github.com/tragabytes/vigia-core/blob/main/DECISIONES.md) | Decisiones tomadas en ausencia de Laureano, de todos los repos de vigia |
| [vigia-core: `MANTENIMIENTO.md`](https://github.com/tragabytes/vigia-core/blob/main/MANTENIMIENTO.md) | Ver producción, leer un run, publicar el núcleo y actualizar este bot |
| `requirements.txt` | La versión del núcleo que usa este bot |
| `vigia_enfermeria/__main__.py` | Arranque: fija el perfil antes de importar el pipeline |
| `web/` | El dashboard (copia también en vigia-docencia: un arreglo aquí suele tocar allí) |
| `tests/` | Solo el smoke del perfil; la suite del pipeline está en el núcleo |
| [`historico/`](historico/) | Plan original, plan maestro, backlog e incidentes hasta octubre de 2026. **Registro, no plan vivo**; guarda notas útiles de cómo es cada web y por qué se decidió cada cosa |

## Reglas propias

1. **El perfil de enfermería vive en el núcleo** (`vigia/_default_profile.py`), igual que sus fuentes sanitarias propias (`codem`, `cm_ficha_enfermeria`, `isciii`, `canal_isabel_ii_calendario`). Cambiar patrones, prompts o fuentes = cambio en vigia-core, nueva etiqueta y actualizar `requirements.txt` aquí.
2. **La palabra clave rápida es `enfermer`, no `enferm`**: la segunda deja pasar «enfermedades».
3. **Los errores de las fuentes nunca llegan al Telegram del usuario**: se ven en logs y dashboard (incidente de junio de 2026, en `historico/incidents/`).
4. **Este repo nunca copia tests del núcleo** (regla 6 del núcleo).
5. **Comprobar en producción, no en disco**: rama `state` (base de datos) y `gh-pages` (dashboard) de este repo (núcleo, `MANTENIMIENTO.md` §2).
