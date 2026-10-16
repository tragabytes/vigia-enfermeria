# Relevo — vigia-enfermeria

Para arrancar una sesión: lee primero el `RELEVO.md` de vigia-core (estado común) y luego esto.

**Estado (14/10/2026).** En producción con vigia-core **v0.10.0** (mira 3 días hacia atrás). Dailies en verde del 1 al 14/10, salvo el 7/10: GitHub devolvió un error 500 al subir el dashboard (fallo suyo, pasajero).

## Resuelto el 16/10/2026 (núcleo v0.10.0, DECISIONES D24-D26)
- **URJC y UPM**: no necesitan fuente propia. Sus oposiciones salen en el BOE, y el BOE y el BOCM ya abren las convocatorias de personal no docente de universidades. Las bolsas temporales de la UPM solo están en su web; hoy no compensa (no hay ninguna de enfermería).
- **ePreselec**: con una página basta (pocas ofertas al día). Se añaden SPMAS y Applus, **solo ofertas de Madrid**. Preving ya no usa ePreselec.
- **«Vigilancia de la salud» + enfermería** cuenta como señal válida.

## Pendientes vivos

Sacados de `historico/BACKLOG.md`, `historico/PLAN_MAESTRO.md`, `historico/PLAN.md` e `historico/incidents/`, y comprobados contra el código el 14/10/2026. Lo que el backlog daba por pendiente pero ya está hecho u obsoleto no aparece.

### Fuentes que faltan
- **UAH, bolsa de empleo**: algunas ofertas quedan escondidas en un desplegable. *Pequeño.*
- **INIA (SharePoint), IEO (no responde), FNMT, EMT, Paradores, Majadahonda y otros ayuntamientos**: hoy solo hay cobertura indirecta por BOE/BOCM. *Medio cada uno.*
- **Mutuas y servicios de prevención en InfoJobs, TalentClue y portales que dan 403**: bloqueado; haría falta un navegador automatizado. *Grande.*
- **Metro de Madrid por InfoEmpleo o LinkedIn**: solo si se demuestra que se pierde algo. *Medio.*

### Mejoras
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
