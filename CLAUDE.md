# CLAUDE.md

Reglas operativas para esta base de código. Dos bloques:

1. **Karpathy Guidelines** — comportamiento general para reducir errores típicos de un LLM al programar. Adaptado de [forrestchang/andrej-karpathy-skills](https://github.com/forrestchang/andrej-karpathy-skills) (MIT). Genérico, aplica a cualquier proyecto.
2. **Convenciones de vigia-enfermeria** — gotchas operativos específicos de este pipeline. Aprendidos en producción.

**Compromiso:** estas reglas priman cautela sobre velocidad. Para tareas triviales, usa el sentido común.

---

## Parte 1 — Karpathy Guidelines (adaptado, MIT)

### 1. Pensar antes de programar

**No asumas. No ocultes confusión. Saca a la luz los compromisos.**

Antes de implementar:
- Enuncia tus supuestos. Si dudas, pregunta.
- Si hay varias interpretaciones posibles, preséntalas — no elijas en silencio.
- Si existe una alternativa más simple, dilo. Empuja cuando esté justificado.
- Si algo no está claro, para. Nombra lo que te confunde. Pregunta.

### 2. Simplicidad primero

**El mínimo código que resuelve el problema. Nada especulativo.**

- Ningún feature más allá de lo pedido.
- Sin abstracciones para código de un solo uso.
- Sin "flexibilidad" o "configurabilidad" que no se haya pedido.
- Sin manejo de errores para escenarios imposibles.
- Si escribes 200 líneas y podían ser 50, reescríbelo.

Pregúntate: "¿Un ingeniero senior diría que esto está sobrecomplicado?". Si sí, simplifica.

### 3. Cambios quirúrgicos

**Toca solo lo que debas. Limpia solo tu propio desorden.**

Al editar código existente:
- No "mejores" código adyacente, comentarios o formato.
- No refactorices lo que no está roto.
- Imita el estilo existente, aunque tú lo harías de otra manera.
- Si ves código muerto no relacionado, menciónalo — no lo borres.

Cuando tus cambios crean huérfanos:
- Elimina imports/variables/funciones que TUS cambios dejaron sin usar.
- No elimines código muerto preexistente salvo que se pida.

*test:* cada línea modificada debe trazar directamente a la petición del usuario.

### 4. Ejecución guiada por objetivo

**Define criterios de éxito. Itera hasta verificar.**

Transforma tareas en metas verificables:
- "Añadir validación" → "Escribe tests para inputs inválidos y haz que pasen".
- "Arregla el bug" → "Escribe un test que lo reproduzca y haz que pase".
- "Refactoriza X" → "Asegura que los tests pasan antes y después".

Para tareas multipaso, enuncia un plan breve:
```
1. [Paso] → verifica: [check]
2. [Paso] → verifica: [check]
3. [Paso] → verifica: [check]
```

Criterios fuertes te permiten iterar sin supervisión. Criterios débiles ("haz que funcione") obligan a aclarar todo el rato.

---

## Parte 2 — Convenciones de vigia-enfermeria

Específicas de este repo. Ordenadas por frecuencia de tropiezo en sesiones reales.

### 5. El estado vive en GitHub, no en disco

**`state/seen.db` local casi nunca refleja producción.**

- Para diagnosticar: `git fetch origin state` y luego `git show FETCH_HEAD:state/seen.db > /tmp/prod.db`.
- Para ver el dashboard real: `git show origin/gh-pages:data/items.json`.
- No pushees `state/` local a la rama `state` ni edites la BD local sin restaurarla primero.

*test:* antes de afirmar "el item está/no está en BD", confirma contra la rama remota, nunca contra disco.

### 6. Verifica el daño real antes de proponer arreglo

**Un warning en logs no implica BD contaminada.**

- El parser puede emitir un RawItem que el extractor descarte aguas abajo. "Fallback a today()" en `comunidad_madrid` parecía catastrófico → 0 daño en BD (los items eran TCAE/auxiliar, descartados como FP).
- El conclusion `success` del workflow puede esconder errores acumulados en `last_errors` por fuente.

*test:* localiza el `id_hash` del ítem sospechoso en `data/items.json`. Si no está, el daño es solo log noise.

### 7. Segmenta backfills

**`since` con rango grande revienta el runner.**

- `since=2025-12-01` en GitHub Actions excede 27 min y se aborta. BOCM con `max_pages=None` × 100+ días = miles de PDFs grandes; BOE = miles de items con bodies + anexos.
- `dry_run=true` no acorta el pipeline (sigue fetchando todo). Solo evita persistencia y Telegram.
- Para histórico amplio: rangos mensuales (`since=2025-12-01`, luego `2026-01-01`…) o ejecución local.

*test:* si `since` es >30 días, divide en lotes mensuales o no lances el `daily.yml`.

### 8. Si lo cambias en una fuente, busca en las hermanas

**Los patrones se repiten en todas las fuentes; los fixes también.**

- Timeouts ajustados, fast-keywords, cascadas de fecha con fallback a `today()`, FALSE_POSITIVE_PATTERNS — todos viven duplicados en `boe.py / bocm.py / comunidad_madrid.py / ciemat.py / universidades_madrid.py / sap_successfactors.py`.
- Cuando subiste el timeout en `comunidad_madrid` a 30s, `ciemat` siguió en 20s con el mismo síntoma. Cuando creaste `recalcular_fechas_comunidad_madrid`, `universidades_madrid` quedó con el mismo bug sin equivalente.

*test:* al cerrar un fix de una fuente, lanza `grep -nE "timeout=|fallback a today\(\)" vigia/sources/*.py` para localizar gemelos.

### 9. Probe ≠ runtime

**Una fuente puede dar `probe 200 OK` y aun así perder items por timeouts en GETs concretos.**

- El dashboard refleja solo el resultado del probe. La degradación silenciosa (timeouts en items individuales, listados perdidos por término) queda solo en logs del workflow.
- Síntoma típico: `comunidad_madrid 2 raw items, 1 errores` con probe verde — el "1 errores" es la rama perdida.

*test:* después de un fix, lee `gh run view <id> --log | grep -E "WARNING|errores"`, no solo el `conclusion: success`.

---

**Estas reglas funcionan si:** menos cambios innecesarios en los diffs, menos rebobinados por sobrecomplicación, y las preguntas aclaratorias llegan antes de implementar — no después de un error.
