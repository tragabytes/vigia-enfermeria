# Relevo — vigia-enfermeria

Para arrancar una sesión: lee primero el `RELEVO.md` de vigia-core (estado común) y luego esto.

**Estado (14/10/2026).** En producción con vigia-core **v0.8.5**. Dailies en verde del 1 al 14/10, salvo el 7/10: GitHub devolvió un error 500 al subir el dashboard (fallo suyo, pasajero).

## Pendientes vivos

Sacados de `historico/BACKLOG.md`, `historico/PLAN_MAESTRO.md`, `historico/PLAN.md` e `historico/incidents/`, y comprobados contra el código el 14/10/2026. Lo que el backlog daba por pendiente pero ya está hecho u obsoleto no aparece.

### Fuentes que faltan
- **Universidad Rey Juan Carlos (URJC)**: no se vigila. Antes, comprobar si sus plazas ya llegan por el BOE. Notas técnicas en el backlog. *Medio.*
- **Universidad Politécnica de Madrid (UPM)**: falta investigar dónde publica. *Medio.*
- **UAH, bolsa de empleo**: algunas ofertas quedan escondidas en un desplegable. *Pequeño.*
- **ePreselec**: solo lee la primera página y solo una empresa (Fraternidad-Muprespa); falta encontrar el subdominio de Preving. *Pequeño/medio.*
- **INIA (SharePoint), IEO (no responde), FNMT, EMT, Paradores, Majadahonda y otros ayuntamientos**: hoy solo hay cobertura indirecta por BOE/BOCM. *Medio cada uno.*
- **Mutuas y servicios de prevención en InfoJobs, TalentClue y portales que dan 403**: bloqueado; haría falta un navegador automatizado. *Grande.*
- **Metro de Madrid por InfoEmpleo o LinkedIn**: solo si se demuestra que se pierde algo. *Medio.*

### Mejoras
- **Añadir «vigilancia de la salud» como contexto débil** del extractor, cuando aparezca un caso real que se escape. *Pequeño.*
- **Medir y subir la tasa de plazos de inscripción extraídos** (~29 % en junio; hay una mejora en v0.4.3 sin medir). *Medio.*
- **Dashboard en el móvil**: rediseñar «Base de datos histórica» (tarjetas, filtros plegables). El backlog pide hacer antes una maqueta con Laureano. *Medio.*
- **Decidir si se desactivan `isciii` y `las_rozas`** para quitar ruido de los logs. *Pequeño, decisión de Laureano.*

### Ideas grandes (sin decidir)
- **Suscripción de terceros** (formulario en la web). *Grande.*
- **Seguir un proceso concreto** (`/seguir`, botón en cada aviso, avisos cuando cambie). El diseño está hecho en el backlog. *Grande.*
- **Servidor en España** para las webs que bloquean a GitHub. *Grande.*
- **Enricher nivel 3**: enlazar correcciones y anexos con su convocatoria. *Grande.*
- **Auditoría mensual con IA de organismos que faltan** (el agente semanal solo vigila las fuentes que ya existen). *Medio.*
- **CSV histórico de todos los hallazgos.** *Pequeño.*

### Mantenimiento
- **Acciones de GitHub con Node 20** (`checkout@v4`, `setup-python@v5`): GitHub ya las ejecuta con Node 24 y funcionan, pero avisa. Ver núcleo, `DECISIONES.md` D17.
