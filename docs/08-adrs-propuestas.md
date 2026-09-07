# ADRs propuestas

Estas ADRs complementan las decisiones ya registradas en `docs/02-SDD.md`. Deben promoverse a ADR formal cuando el equipo apruebe el alcance tecnico.

## SDD-ADR-016 Versiones base del stack

- Frontend: Node.js 22 LTS, pnpm 10, React 19, TypeScript 5.8, Vite 7.
- Backend: Python 3.12, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic.
- Pruebas: Pytest, Playwright, Ruff, MyPy, Vitest.
- Infraestructura local: Docker Compose con PostgreSQL 16 y Redis 7.

Justificacion: fija reproducibilidad sin introducir dependencias de negocio prematuras.

## SDD-ADR-017 Contratos compartidos por JSON Schema

Los contratos entre apps, API, gateway y workers se versionaran en `packages/contracts/schemas`.

Reglas:

- todo contrato publico incluye `schema_version`,
- los cambios incompatibles crean version nueva,
- las pruebas de contrato validan ejemplos deterministas,
- los adaptadores externos traducen hacia el modelo canonico.

## SDD-ADR-018 Health checks y readiness

Cada servicio expone:

- `GET /health/live`: proceso vivo,
- `GET /health/ready`: dependencias minimas disponibles,
- `GET /health/version`: version, commit y entorno.

Fase 0 implementa health sin dominio. Fases posteriores agregan dependencias reales.

## SDD-ADR-019 Gateway Windows instalable

El gateway local se implementara como servicio instalable para Windows con:

- SQLite WAL,
- outbox/inbox persistente,
- spool persistente de impresion,
- WebSocket local,
- logs JSON,
- actualizacion controlada y rollback.

El gateway no se despliega en Easypanel.

## SDD-ADR-020 Modelo inicial de errores

Los errores de negocio usaran codigos estables:

- `VALIDATION_ERROR`,
- `PERMISSION_DENIED`,
- `STATE_TRANSITION_DENIED`,
- `IDEMPOTENCY_CONFLICT`,
- `OFFLINE_CONFLICT`,
- `EXTERNAL_PROVIDER_UNAVAILABLE`,
- `AUDIT_REQUIRED`.

Los controladores HTTP solo traducen errores; no contienen reglas de dominio.

## SDD-ADR-021 Auditoria append-only

La auditoria se modela como eventos append-only con:

- actor,
- alcance,
- accion,
- entidad,
- antes/despues cuando aplique,
- correlation id,
- causation id,
- timestamp UTC.

No se elimina auditoria para simplificar pruebas o migraciones.

## SDD-ADR-022 Services como limites logicos iniciales

El directorio `services/` representa limites de dominio y pruebas, no procesos desplegables independientes durante fase 0 y fase 1.

Esto preserva monolito modular y evita un big bang de microservicios.

## SDD-ADR-023 Propuesta — transición reversible a perfiles acumulativos

**Estado: aprobada el 2026-08-10.** Alternativas evaluadas: (A) mapear cada rol semilla explícitamente a un
perfil nuevo y requerir decisión para Administrador corporativo; (B) convertir Administrador
corporativo automáticamente en Dueño; (C) conservar permisos efectivos y presentar nuevos perfiles
sólo como plantillas. Se recomienda A con dry-run, tabla de mapeo, reporte de diferencias,
aprobación por organización y downgrade que restaure asignaciones. B queda descartada porque concede
todo/todas las sucursales sin decisión individual verificable. PCO-001 siembra perfiles/permisos y
registro de mapeo, pero no asigna Dueño automáticamente ni altera permisos legacy de Cajero.

El registro conserva ciclos históricos append-only: sólo puede existir un mapping activo
`pending|mapped` por usuario/perfil; los `reversed` anteriores coexisten. La concesión
`organization_all_permissions` es un invariante estructural de `scope=organization`: no se borra,
reduce por permisos ni convierte a branch. Renombrar no modifica autoridad y exige al mismo nivel de
autoridad; `access.organization.all_branches` ordinario no sustituye el grant.

El bootstrap inicial queda fuera de Alembic y HTTP: es un comando interno idempotente que sólo acepta
organización, actor operacional, procedencia y la configuración explícita de los dos usuarios
confirmados. La validación de ambos usuarios/rol/conflictos precede cualquier inserción. El mapeo pasa
por `PENDING -> MAPPED -> REVERSED`, guarda snapshot mínimo sin PII y sólo añade/retira la asignación
destino creada por él; no elimina historial ni convierte por nombre o automáticamente a un legacy.

## SDD-ADR-024 Aprobada — identidad y versiones de conceptos de caja

**Estado: aprobada por el Dueño de producto para PCO-002 el 2026-08-11 mediante la instrucción
“Sí, adelante”.** No sustituye ni revoca otro ADR. Se separa la identidad corporativa con código
inmutable de sus versiones publicadas. La alternativa de sobrescribir una sola fila se descarta
porque pierde la configuración histórica que los movimientos de PCO-003 deberán congelar. La
alternativa de activar el ledger en la misma entrega se descarta para conservar un incremento
reversible sin escrituras financieras.

Cada mutación se registra en una tabla de comandos con clave idempotente organizacional, hash del
payload canónico y resultado estable. Archivar conserva identidad/versiones y sólo la excluye de la
proyección efectiva. El downgrade de esquema sólo elimina tablas vacías; si existe historia queda
bloqueado y el rollback de aplicación desactiva rutas conservando datos.

La aprobación autoriza especificación e implementación aislada de PCO-002; no autoriza PCO-003,
commit, push, despliegue, migración productiva ni modificación de datos reales. La implementación
queda a cargo de Terra y sólo cambia de `Disenado` después de evidencia técnica auditada por Sol.

## SDD-ADR-025 Aprobada — ledger de caja compatible y compensatorio

**Estado: aprobada por el Dueño de producto para PCO-003 el 2026-08-11 mediante la instrucción
“Adelante con el PCO-003 completamente”.** No sustituye ni revoca `SDD-ADR-024`: consume el catálogo
versionado que ese ADR dejó como precondición y conserva identidad e historia de conceptos.

PCO-003 amplía en sitio la tabla legacy `cash_movements` sin reescribir ni borrar sus filas. Los
movimientos nuevos conservan importe positivo en centavos, tipo persistido `deposit|withdrawal`,
snapshot de la versión efectiva del concepto para comandos manuales, referencia, evidencias opacas,
actor, turno, sucursal, procedencia e identidad de compensación. Las filas legacy `withdrawal` y
`cash_reversal` continúan legibles; la proyección Python interpreta `cash_reversal` como entrada
compensatoria y no lo duplica. La alternativa de crear un segundo ledger se descarta porque dividiría
la fuente financiera y duplicaría compras; la alternativa de normalizar destructivamente la historia
legacy se descarta porque impediría una reversión verificable.

Una tabla de comandos separada aplica idempotencia por `(organization_id, idempotency_key)` y guarda
hash canónico y resultado estable. La clave técnica de la fila legacy puede ser un derivado SHA-256,
pero nunca sustituye la identidad de comando ni se expone como autoridad. La compensación crea un
movimiento opuesto, exacto y único; no actualiza ni elimina el original. El efectivo esperado se
calcula sólo en Python como fondo inicial más pagos `cash` confirmados más depósitos menos retiros,
incluidas compras y compensaciones exactamente una vez.

La aprobación autoriza especificación, implementación aislada por Terra, auditoría iterativa por Sol
y, sólo después de todos los gates verdes, commit, PR/merge y push. No autoriza despliegue,
`alembic upgrade` productivo, datos reales, PCO-004+, corte final, cierre operativo nuevo ni
sincronización offline. El edge gateway permanece fail-closed para movimientos manuales hasta PCO-008.

## SDD-ADR-026 Aprobada — cierre operativo, turno de cobro y snapshots de ventas

**Estado: aprobada por el Dueño de producto para PCO-004 el 2026-08-12 mediante la instrucción
“Adelante autorizado, bajo las mismas condiciones y requerimientos”.** Extiende, no sustituye,
`SDD-ADR-025`: cierre, movimientos, compras cash y pagos comparten la frontera transaccional del
turno, mientras corte final permanece en PCO-006.

Se elige un cierre append-only separado en `cash_shift_closures`, con estado
`OPEN -> CLOSING -> OPERATIVELY_CLOSED`, actor y resumen autoritativo congelado. Apertura/cierre usan
un command log idempotente. El cierre canónico recibe turno por ruta y body vacío; contado, esperado,
diferencia y cualquier autoridad afirmada por el navegador se rechazan. `cash_shift_cuts` conserva
historia legacy, pero PCO-004 no vuelve a escribirlo. El alias `/cash-shifts/close` falla cerrado ante
el payload anterior de contado para impedir que un cliente desactualizado fabrique diferencias.

Se elige atribuir cada pago al turno `OPEN` de la caja que efectivamente confirma el cobro.
`orders.cash_shift_id` conserva el turno de captura y `payments.cash_shift_id` el turno de cobro. La
alternativa de reutilizar el turno de captura se descarta porque un pago diferido puede ocurrir tras
su cierre; la alternativa de permitir pagos sin turno se descarta porque rompe efectivo esperado,
responsabilidad por caja y resumen congelado. Si pago y cierre compiten, sólo el ganador del guard
confirma; el perdedor falla sin escritura parcial.

Se eligen snapshots append-only de operación y línea al confirmar pago, más familia congelada al
crear/enmendar la línea. El backfill legacy desde producto-categoría se marca
`legacy_catalog_backfill`; no se presenta como verdad histórica perfecta. Impuesto, descuento o
cortesía sin fuente quedan desconocidos. Cada indicador devuelve centavos conocidos y número de
operaciones desconocidas. Se descarta consultar catálogo vigente, aplicar una tasa de IVA asumida o
inferir cortesía por diferencia, porque cualquiera reescribiría la historia. Todos los agregados y
conteos viven en Python; React sólo presenta DTOs.

La superficie canónica del monitor vive en POS `/sales-monitor`, protegida por
`reports.sales.read`. No duplica el placeholder Admin ni introduce estación, impresión,
Excel/descarga o formato de nota de consumo. La revisión `0038` es aditiva y lineal desde `0037`; el
downgrade sólo retira backfill sin historia nueva y se bloquea cuando existe cierre, comando o
snapshot capturado.

La aprobación autoriza documentación, pruebas RED, implementación aislada por Terra Alto, auditoría
iterativa por Sol y, con todos los gates verdes, commit, PR/merge, despliegue, migración y canary
controlado de PCO-004. No autoriza cierre de un turno comercial real: el canary debe usar una caja QA
dedicada o detenerse para autorización específica. Tampoco autoriza corte final, reapertura, offline,
PCO-005+ ni cálculo fiscal no definido.

## SDD-ADR-027 Aprobada — reapertura mediante corrección enlazada y compensatoria

**Estado: aprobada por el Dueño de producto el 2026-08-14 mediante la instrucción exacta
“Apruebo SDD-ADR-027 y el paquete PCO-005B”.** La aprobación autoriza propagación documental,
implementación y pruebas R3 en una tarea aislada de Terra, y auditoría iterativa de Sol. No autoriza
commit/merge/push del código resultante, despliegue, migración, configuración ni datos productivos;
esos gates conservan autorización separada.

PCO-005A demostró que solicitud y decisión pueden operar sin alterar el pedido protegido. Para
PCO-005B se propone que `APPROVED -> APPLIED` no reabra ni reescriba el pedido, pago, snapshot de
venta, turno o corte original. En su lugar, crea una corrección enlazada, append-only y versionada,
cuya imagen deseada de líneas y plan de compensación son aprobados de forma exacta por Dueño antes
de ejecutarse atómicamente.

La corrección calcula en backend Python, con enteros de centavos y snapshots históricos, la
diferencia financiera y de componentes. El pago original permanece `CONFIRMED`. Una diferencia
positiva genera un cargo adicional confirmado en un turno vigente; una diferencia negativa genera
un reembolso enlazado. Efectivo crea el movimiento compensatorio correspondiente en el turno actual;
tarjeta o transferencia requieren método y evidencia de confirmación manual mientras no exista un
adaptador de proveedor. Ninguna operación histórica cambia de turno ni se libera de un corte.

Para producción, una reducción de una línea `PENDING` cancela la tarea y libera sólo su reserva; una
línea `IN_PROGRESS` bloquea la aplicación para evitar una clasificación ambigua; una reducción de
una línea `COMPLETED` exige por cantidad afectada la clasificación explícita `waste|recovery`. La
merma conserva el consumo y agrega evidencia; la recuperación crea movimiento positivo enlazado.
Toda cantidad agregada crea una reserva y una tarea nueva. La corrección no consulta recetas o
precios actuales para reconstruir lo histórico: la imagen original usa snapshots y las adiciones
usan el catálogo/receta vigentes como una operación nueva identificable.

Alternativas descartadas en la propuesta: cambiar el total del pedido cerrado dejando el pago
original apuntando a un total distinto; borrar o editar el pago; revertir snapshots; reasignar la
venta al turno actual; y permitir una corrección con producción `IN_PROGRESS`. Una alternativa más
estrecha, permitir sólo correcciones de total idéntico y producción `PENDING`, reduce riesgo pero no
completa el requerimiento de modificación de cuentas pagadas.

La transición de propuesta a aprobada habilita especificación, RED e implementación aislada.
`/apply` conserva `order_reopen_policy_pending` en `main` y en producción hasta que la implementación
PCO-005B supere auditoría, publicación, migración y canary mediante sus gates independientes.

## SDD-ADR-028 Aprobada — identidad offline limitada y reconciliación atómica

**Estado: aprobada por el Dueño de producto el 2026-08-15 mediante “Apruebo SDD-ADR-028 y el paquete
PCO-008”.** El alcance es exclusivamente `cash.movement.create.v1` para depósitos y retiros manuales
ya gobernados por PCO-003. Pedidos, pagos, compras, compensaciones, apertura/cierre, cortes, KDS,
impresión e inventario permanecen fail-closed fuera de la allowlist.

El transporte usa una credencial técnica rotatoria ligada a organización, sucursal y dispositivo; el
actor usa un grant offline firmado, emitido desde una sesión vigente, ligado a los mismos bindings y
con duración máxima de dos horas. El gateway no recibe la clave de sesión ni puede afirmar permisos.
Al reconciliar, PostgreSQL vuelve a resolver actor activo, permiso exacto, alcance, turno `OPEN`,
concepto efectivo e idempotencia.

El outbox transita `PENDING_SYNC -> SYNCING -> CONFIRMED|CONFLICT`. Los fallos de transporte regresan
a pendiente con backoff; una denegación estable queda visible como conflicto y nunca genera
compensación automática. Movimiento, command log, inbox, evento, auditoría y checkpoint por sucursal
se confirman en una sola transacción. El checkpoint usa una fila serializada, no `max()+1` sin lock.

## SDD-ADR-029 Aprobada — Ed25519 y runtime local del gateway

**Estado: aprobada por el Dueño de producto el 2026-08-15 mediante “Apruebo SDD-ADR-029 y el paquete
PCO-008R”.** El grant se firma con Ed25519: la clave privada vive sólo en la API central y el gateway
recibe únicamente un llavero público versionado por `kid`. Firma, versión, ventana, capability y todos
los bindings fallan cerrados. Se aprueba `cryptography` como dependencia crítica acotada.

El runtime escucha sólo en loopback, usa CORS de origen exacto, SQLite WAL versionado, transporte TLS
verificado sin redirects/proxy ambiental y timeouts finitos. Configuración, credencial y SQLite se
separan; credenciales/grants nunca aparecen en logs o respuestas. Instalación real, provisión real,
despliegue, migración productiva y rollout siguen requiriendo autorización separada.

## Reserva de numeración PCO-008/008R

`SDD-ADR-028` y `SDD-ADR-029` están aprobadas en el paquete local PCO-008/008R, pero sus artefactos
aún no pertenecen a `main`. `PCO-008P` debe trasplantarlas sin renumerarlas antes de declarar
trazabilidad completa. Esta reserva no declara publicado, integrado ni desplegado ese paquete.

## SDD-ADR-030 Aprobada — frontera operacional default-deny y artefactos sensibles

**Estado: aprobada por el Dueño de producto el 2026-08-19 mediante la instrucción exacta
“Apruebo SDD-ADR-030, SDD-ADR-031 y los paquetes SEC-001A, OPS-WAVE-001R, MOB-ORD-001 y PCO-008P
para implementación y pruebas aisladas por Terra, con auditoría posterior de Sol”.**

Se propone exigir identidad humana o de dispositivo, capacidad granular y alcance backend en todas
las rutas operacionales de seed, KDS, sync e impresión; mover seeds a comandos internos idempotentes;
y separar `QUEUED/CLAIMED/FAILED` del acuse autoritativo `PRINTED`. Se propone además bloquear en CI
bases, respaldos y secretos, y conservar sólo fixtures sintéticos.

La decisión de código no autoriza por sí misma cambiar la visibilidad del repositorio, rotar
credenciales, reescribir historia Git ni eliminar copias remotas. Esas operaciones se ejecutarán como
contención `SEC-001B`, con inventario, responsables, respaldo, ventana y autorización humana propia.

Consecuencias: rompe clientes anónimos existentes y exige rollout coordinado de credenciales de
dispositivo; reduce superficie de escalación y evita estados de impresión falsos. La especificación
completa, alternativas y rollback están en SDD §39.1/39.4.

## SDD-ADR-031 Aprobada — ingreso público canónico y confirmaciones veraces

**Estado: aprobada por el Dueño de producto el 2026-08-19 con la misma instrucción registrada en
SDD-ADR-030.**

Se propone persistir una `PublicOrderIntent` idempotente, resuelta por clave pública de sucursal y
validada/calculada en Python, antes de mostrar éxito. La aceptación autenticada reutiliza el dominio
canónico de pedidos y nunca crea o escoge un turno de caja. Redis limita escrituras públicas; una
indisponibilidad de control, configuración o persistencia falla cerrada. WhatsApp queda como
proyección posterior al commit mediante adaptador configurable.

Consecuencias: el flujo pasa de mejor esfuerzo a resultado consultable y puede exigir un paso de
revisión operacional; elimina folios simulados y divergencia de totales, a costa de una migración
aditiva, nuevos estados y una UI de error/resultado incierto. La especificación completa,
alternativas y rollback están en SDD §39.2/39.4.

## SDD-ADR-034 Aprobada — IA administrativa propone y Python conserva autoridad

**Estado: aprobada por el Dueño de producto el 2026-08-29 mediante la instrucción de implementar el
plan del asistente administrativo con Terra medio y auditoría posterior.** La autorización cubre
especificación, código y pruebas locales. No autoriza clave, envío de datos real, configuración,
despliegue, migración o canary productivo.

Se adopta un adaptador de proveedor únicamente backend y default-off. El modelo recibe contexto
allowlist mínimo y produce JSON estricto; no recibe SQL, credenciales ni puertos de escritura. La
salida se persiste sólo después de validación Python como una propuesta de una acción, con estado,
fingerprint, expiración, fuentes y evidencia humana. La aceptación explícita revalida identidad,
permiso, versión e idempotencia y llama el servicio canónico; por tanto el LLM nunca constituye
autoridad de producto, receta, insumo, modificador, dinero o inventario.

Se descartan acceso directo del modelo a la base, tool-calling de mutación, aplicar al terminar la
conversación, change sets multiacción con commits parciales, confiar en permisos del cliente y
persistir prompts/transcripts. La contrapartida es una configuración compuesta por pasos revisables;
se acepta para preservar atomicidad, reversibilidad y auditoría del MVP.


## SDD-ADR-035 — Transporte HTTP y worker de disponibilidad SaaS

Estado: adoptada en el paquete local autorizado de remediación SaaS; publicación/configuración
productiva conserva autorización separada. Se mueve `httpx`, ya utilizado en pruebas, a
runtime para el adaptador Uber y el worker. OAuth y disponibilidad usan tiempos límite,
respuestas verificadas y no exponen credenciales. No se acopla dominio a tipos del cliente:
el adaptador conserva la frontera. Alternativa descartada: marcar sincronizado sin I/O;
`urllib` directo exigiría duplicar transporte inyectable y manejo uniforme de errores.
Consecuencia: nueva dependencia runtime con revisión de vulnerabilidades en CI; fallos de
red se modelan como reintento/error, nunca confirmación. Lease/CAS y reconciliación de versión
están definidos en SDD SaaS; el worker se detiene sin borrar comandos pendientes.
