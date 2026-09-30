# TDD — remediación previa a piloto

**Estado:** estrategia R3 aprobada el 2026-08-19; toda implementación inicia con RED observable y
termina con auditoría independiente de Sol.
**Regla aritmética:** centavos `int` y cantidades/conversiones `Decimal` en Python. TypeScript sólo
valida interacción y presenta DTO autoritativo.

## TDD-TS-089 Frontera operacional, impresión y política de repositorio

Pruebas de contrato/API:

- parametrizar cada ruta sensible sin token, con token inválido, revocado, de capacidad distinta y
  de otra sucursal; todas fallan antes del servicio;
- comprobar que las rutas HTTP de seed no existen y el comando interno valida/dry-run/aplica/replay;
- KDS y sync aceptan exclusivamente comandos de su allowlist e identidad de dispositivo;
- list/retry/ack de impresión separan actor humano y agente; retry no puede escribir `PRINTED`;
- el mismo retry devuelve el intento persistido; payload distinto con la clave falla conflicto;
- fallos inyectados antes/después de enqueue o ack no dejan transición parcial.

Pruebas de repositorio/CI:

- enumeración determinista por path, extensión, tamaño y firma sensible, sin leer/mostrar valores en
  el reporte;
- fixture permitido debe estar en allowlist mínima y pasar validación sintética;
- fuentes de tests, encabezados PEM/OpenSSH, sidecars SQLite y dumps/exportes SQL se inspeccionan;
- base, backup, clave o patrón sensible introducidos intencionalmente hacen fallar CI;
- `.gitignore` sin retirar un archivo tracked no satisface el gate;
- comprobar que el workflow cubre pull request y rama protegida, sin credenciales en artifacts.

### TDD-TC-141 Denegación uniforme de rutas operacionales

Given la tabla completa de rutas de BDD-SC-355 y cero autoridad
When cada ruta se invoca con un payload válido
Then todas responden 401/403 estable y sus tablas conservan las mismas huellas y conteos.

### TDD-TC-142 Seed interno idempotente sin superficie HTTP

Given una base aislada vacía y un actor operacional explícito
When dry-run, apply y replay usan el mismo manifest
Then sólo apply ejecuta, en orden, los handlers allowlisted `ensure_organization.v1`,
`ensure_branch_topology.v1` y `ensure_menu_catalog.v1`, crea el snapshot esperado una vez y el
router no contiene endpoints seed.
La huella de esquema, datos y auditoría no cambia en dry-run; una base no migrada se rechaza sin DDL,
la validación completa rechaza referencias/orden/tipos/importes/cantidades antes de escribir, un
fallo inyectado revierte todos los handlers, la auditoría organizacional usa branch nula y contenido
redactado, y los entrypoints legacy fallan cerrados sin ejecutar ventas ni mocks aleatorios.

### TDD-TC-143 Scope y capacidad de dispositivo

Given credenciales independientes para impresión, KDS y gateway en dos sucursales
When se cruzan capacidad, sucursal, organización, revocación y replay
Then sólo la combinación exacta opera y toda denegación deja cero efecto.
Incluye dispositivo KDS de sucursal B visible sólo en B y humano sin `kds.tasks.operate` denegado.
Incluye humano con KDS, impresión y `sync.events.read` en sucursal B: B funciona y A se deniega; un
actor con sólo `orders.create` no observa sync.
Incluye replay sync particionado por organización/sucursal/dispositivo y descarga de eventos
pendientes por organización/sucursal persistidas, incluso si otro gateway de esa sucursal originó
el comando; también envelope malformado sin 500, ownership organización-sucursal y rechazo de
scopes inactivos.

### TDD-TC-213 Grants granulares y scope humano sin sucursal global

- Runtime: `apps/api/tests/test_sec001_operational_boundary.py::test_human_operational_routes_reauthorize_explicit_branch_scope`
- Migración: `apps/api/tests/test_operational_human_scope_migration.py`

La revisión posterior a 0056 crea un solo `sync.events.read` y asigna por IDs reservados las cuatro
capacidades operacionales a Supervisor, Administrador y Dueño, sin tocar los tres perfiles inferiores.
SQLite prueba upgrade/downgrade vacío; downgrade se bloquea ante grants externos. El runtime prueba
dos sucursales y confirma que ninguna ruta humana pasa una constante global al servicio. Un guard de
arquitectura exige además que `platform_shell.py` permanezca ausente: el proceso web sólo sirve las
SPAs construidas y no conserva una segunda UI legacy capaz de llamar KDS, impresión o sync.

### TDD-TC-215 Contención forward-only de la semilla 0049

- Migración: `apps/api/tests/test_la_primavera_seed_guard_migration.py`

RED parte de 0057 sin una revisión posterior: no existe auditoría y los estados ambiguos avanzan.
GREEN migra la base limpia a 0058, compara el conjunto de `user_roles` antes/después, verifica el
snapshot auditado y prueba replay único y downgrade bloqueado. La regresión productiva modifica la
sucursal canónica a `SUC06` y separa los timestamps de sucursal, almacén y cuenta; debe avanzar sin
mutar la única asignación Cajero y auditar `approved_canonical_state_verified`. Casos separados
aceptan para SUC06 las dos grafías exactas confirmadas `Almacén La Primavera|Almacen La Primavera`,
mantienen la huella limpia limitada a la grafía acentuada y rechazan cualquier otro nombre de
almacén. También preparan en 0048 una cuenta con dos roles que
0049 reemplaza, una sucursal de coincidencia parcial y
una asignación actual adicional; cada upgrade debe fallar antes de escribir, permanecer en 0057 y
conservar el estado observado. PostgreSQL aislado repite huella limpia, no-mutación, auditoría y
forward-only en CI usando exclusivamente `SEED0058_TEST_POSTGRES_URL` sobre una base local
`seed0058_*`; la restauración candidata cubre el camino SUC06 antes de producción.

### TDD-TC-144 Máquina de estado de impresión

Given un trabajo FAILED
When retry idempotente, claim, ack alterado y ack válido se ejecutan
Then transita FAILED a QUEUED a CLAIMED a PRINTED sólo por el ack válido y conserva cada intento.
También cubre pull por scope persistido, CLAIMED a FAILED con rollback/replay y rechazo de retry
con clave nueva mientras exista intento activo.
Dos sesiones concurrentes sólo crean un intento activo y conservan el contador. La creación del job
incluye intento inicial QUEUED en la misma transacción. Un claim vencido sólo pasa a FAILED mediante
reconciliación scoped y explícita, sin reenqueue; PostgreSQL valida locking e índice de pull compuesto.

### TDD-TC-145 Gate sensible no filtra el secreto detectado

Given fixtures temporales con base, backup, clave simulada y fixture sintético permitido
When se ejecuta el scanner en dos órdenes de filesystem
Then produce el mismo conjunto ordenado de clases/paths, falla por los tres prohibidos y nunca
incluye su contenido.
Incluye PEM/OpenSSH sin asignación, credencial en fuente de test, sidecars WAL/SHM/journal y dumps o
exportes SQL; sólo pasa un fixture declarado por path, hash y procedencia exactos.

### TDD-TC-166 Autoridades separadas de pedido

Given líneas conocidas con modificadores/extras y un pedido ACCEPTED
When cotización y creación usan el mismo payload, se confirma pago, KDS completa y fulfillment opera
Then cotización y total persistido coinciden en centavos, pago conserva estado, KDS llega a READY y
los comandos terminales exigen permiso, scope, estado, CAS e idempotencia sin cierre implícito.
Un guard AST adicional exige que no exista `create_public_online_order` y que el cuerpo de
`POST /public/orders` conserve exclusivamente la denegación `public_order_unavailable` 503. Las
regresiones de teléfono, captura sin turno y reserva/producción ejercen sólo
`create_public_order_intent` + `accept_public_order_intent`, nunca el escritor retirado.

## TDD-TS-090 Cortesía, proveedores, compras y reimpresión autoritativas

Pruebas backend/dominio:

- reautenticación real de Supervisor y autorización persistida de un uso/TTL/actor/sucursal/hash de
  carrito; no aceptar PIN ni autorización local;
- subtotal, ajuste y total derivados en Python, pago por total exacto y rollback de ajuste/evento;
- `suppliers.create` y `purchase_presentations.create` separados de `catalog.manage`;
- alta atómica de proveedor, contacto y términos; duplicidad y branch ajena sin filas parciales;
- compra de al menos dos líneas con `Decimal`, idempotencia, recepciones, costo promedio, retiro cash
  y cancelación compensatoria completa;
- reimpresión crea trabajo real, auditado y no presenta `PRINTED` antes del agente.

Pruebas frontend/E2E:

- Cajero, Supervisor y actor de otra sucursal ejercen casos positivos y negativos reales;
- el modal de cortesía limpia credencial, no calcula el total y no cambia UI ante error;
- proveedor recién creado conserva términos y presentación; compra renderiza dos líneas;
- reimpresión muestra Encolado/referencia, resultado incierto y error sin éxito falso;
- typecheck/build y QA visual 1440x900 y 1000x800 para vacío, carga, datos, denegación y error.

### TDD-TC-146 Cortesía backend y pago reconciliado

Given subtotal 15000, autorización válida y total solicitado 12000
When se aplica y se confirma pago
Then Python persiste ajuste -3000 y pago 12000; token inválido/reusado deja total 15000.

### TDD-TC-147 UI no acepta PIN simulado ni diverge del backend

Given el modal abierto y una cadena local de cuatro caracteres
When la API rechaza o queda incierta
Then no cambia subtotal/total, conserva la venta y no emite mensaje de éxito.

### TDD-TC-148 Proveedor y términos atómicos por permiso específico

Given Supervisor con suppliers.create sin catalog.manage
When crea proveedor, contacto y términos, y se inyecta fallo en cada escritura
Then el caso normal confirma todo y cada fallo o actor Cajero/branch ajena confirma nada.

### TDD-TC-149 Presentación y compra de dos líneas exactas

Given dos presentaciones con conversiones Decimal y pago cash
When se confirma dos veces con la misma clave
Then totales, cantidades base y costo promedio coinciden con el oráculo Python y existen dos
recepciones, un documento y un retiro.

### TDD-TC-150 Cancelación compensa compra completa

Given la compra de TDD-TC-149 confirmada
When se cancela y se repite el comando
Then cada recepción tiene una reversa, el retiro una compensación y nada original se edita o duplica.

### TDD-TC-151 Reimpresión real con resultado incierto

Given un pedido imprimible
When el POS reintenta tras timeout con la misma clave
Then existe un solo intento consultable y la UI no muestra Impreso hasta ack válido.

## TDD-TS-091 Ingreso y aceptación de pedido público

Pruebas frontera/dominio:

- JSON Schema estricto, límites, clave pública activa, rechazo de UUID/total/precio/turno/actor;
- precios y totales desde catálogo vigente en Python; entradas aleatorias se contrastan contra un
  oráculo Python con centavos enteros y `Decimal`, incluyendo límites y redondeo explícito;
- command log por clave/hash, replay estable, conflicto y recuperación tras timeout;
- rate limiter Redis y fallback fail-closed de escritura; logs/métricas sin PII;
- persistencia de intent no toca `cash_shifts`, `payments`, reservas ni tareas;
- aceptación autenticada llama al servicio canónico y crea exactamente un pedido/reserva/tareas/
  eventos/outbox; carrera accept/accept produce un solo resultado;
- WhatsApp se sustituye por fake adapter y nunca condiciona commit ni usa número hardcodeado.

Pruebas mobile-web/E2E:

- build y script de tests entran a CI;
- éxito real limpia carrito; 4xx, 5xx, timeout y respuesta inválida conservan carrito/clave;
- estado incierto consulta referencia y no fabrica folio;
- QA visual móvil 360x800 y 390x844: catálogo, carrito, enviando, pendiente, error y reintento.

### TDD-TC-152 Sucursal y total sólo desde backend

- Archivo: `apps/api/tests/test_public_order_intents.py::test_public_order_intent_requires_idempotency_key_and_strict_body`

Given catálogo público conocido y payload con branch_id/precio/total manipulados
When se envía por una public_key válida
Then campos extra se rechazan; sin ellos Python deriva sucursal y total exactos.

### TDD-TC-153 Persistencia idempotente y recuperación de timeout

- Archivo: `apps/api/tests/test_public_order_intents.py::test_post_commit_failure_recovers_the_same_intent_by_idempotency_key`

Given una clave nueva y un fallo de respuesta después del commit
When el cliente consulta y reintenta con la misma clave
Then recupera una sola referencia PENDING_REVIEW y no duplica líneas ni command result.
La prueba instala `public_order_after_commit_hook` que eleva después del commit, lo retira y
reintenta la misma clave para verificar la recuperación de la única intención/referencia.

### TDD-TC-154 Frontend conserva carrito ante cualquier no-éxito

Given un carrito no vacío
When fetch rechaza, expira, devuelve 4xx/5xx o JSON inválido
Then carrito y clave permanecen, no hay folio aleatorio y el usuario puede consultar/reintentar.

### TDD-TC-155 Esquema, límites, rate y redacción

- Archivo: `apps/api/tests/test_public_order_intents.py::test_public_capture_fails_closed_without_rate_limiter_or_configuration`

Given casos inválidos de BDD-SC-372 y datos personales marcadores
When se procesan en paralelo
Then todos fallan sin filas parciales y ninguna salida de log/métrica contiene los marcadores.

### TDD-TC-156 Captura pública no toca caja ni producción

- Archivo: `apps/api/tests/test_public_order_intents.py::test_public_capture_never_mutates_operational_cash_or_production`
- Archivo: `apps/api/tests/test_public_order_intents.py::test_legacy_public_order_write_is_always_fail_closed`

Given cero turnos abiertos y uno cerrado histórico
When se persiste una intención
Then huellas y conteos de turnos/pagos/reservas/tareas no cambian y el intent no referencia turno.
La ruta heredada se prueba con el flag apagado y encendido: en ambos casos devuelve el mismo 503
estable y conserva sin cambios pedidos, turnos, pagos, producción y movimientos de inventario.

### TDD-TC-157 Aceptación canónica concurrente

- Archivo: `apps/api/tests/test_public_order_intents.py::test_authenticated_acceptance_creates_canonical_order_once_without_cash_shift`

Given una intención PENDING_REVIEW
When se acepta con versión e Idempotency-Key válidas
Then la prueba SQLite focal verifica un pedido enlazado, reserva, tareas y outbox una vez.
La carrera de dos sesiones PostgreSQL es un gate opt-in real con
`MOBORD001_TEST_POSTGRES_URL`; CI preaprovisiona una base `mobord001_*` en 0050, ejecuta
la migración forward-only 0051 y prueba con dos sesiones que sólo una transición CAS terminal gana.
La prueba SQLite focal verifica por separado que los efectos canónicos se materializan una vez.

### TDD-TC-210 Contención canónica de archivos estáticos

- Archivo: `apps/api/tests/test_static_file_containment.py`

Given raíces estáticas sintéticas separadas para Admin y POS
When una solicitud Admin intenta atravesar hacia POS con `..` codificado o mediante symlink
Then devuelve 404 y nunca entrega el marcador externo; assets internos y fallback SPA válidos siguen
disponibles dentro de la raíz solicitada.

### TDD-TC-169 Reserva de estados terminales de intención pública

- Archivo: `apps/api/tests/test_public_order_intents.py::test_authenticated_rejection_is_idempotent_and_has_no_operational_effects`

Given una intención pendiente y un actor autorizado
When se rechaza y se repite el comando
Then queda REJECTED una sola vez, sin efectos operativos y sin exponer el motivo públicamente.
`EXPIRED` permanece reservado sin comando, TTL ni scheduler.

La regresión `test_old_public_intents_remain_in_history_without_read_side_effects` ejecuta
cuentas y conteo con intenciones de 25 horas, compara el registro completo y captura DML.
Se exige cero escrituras y estado histórico original para PENDING_REVIEW, REJECTED y EXPIRED.

### TDD-TC-987 Historial público limitado y autorizado

- Archivos: `apps/api/tests/test_public_order_intents.py::test_public_intent_history_is_bounded_and_paginated_with_stable_ties`,
  `apps/api/tests/test_order_history.py`, `tests/frontend/test_mobile_order_history.mjs`.
- Comprobar mezcla de orígenes, empates, filtros, separación entre tenants, cursor inválido,
  límite por página y renovación del alcance; SQLite y PostgreSQL cuando está configurado.
- Ejecutar el handler real del monitor: cargar más, conservar profundidad al refrescar y
  descartar respuestas de otra sucursal; sin reescribir la clasificación en el test.

### TDD-TC-170 Selecciones y límite seudonimizado

- Archivos: `apps/api/tests/test_public_order_intents.py::test_public_intent_uses_canonical_selections_and_direct_client_signal`
  y `apps/api/tests/test_public_order_rate_limit.py`

Given selecciones vigentes y una señal directa de cliente
When se captura una intención
Then Python calcula el snapshot y Redis recibe sólo clave y HMAC, nunca PII.

## TDD-TS-092 Integración y publicación de PCO-008/008R

PCO-008P importa primero ADR-028/029 y reconstruye quirúrgicamente su diff sobre la head vigente; no
aplica a ciegas archivos en conflicto ni amplía la allowlist `cash.movement.create.v1`. Como la base
ocupó los rangos reservados, el mapeo aprobado por colisión es `TDD-TC-129..136` a
`TDD-TC-171..178`, más `TDD-TC-179..181` para replay, checkout y cobro idempotentes.

### TDD-TC-158 Trasplante PCO-008 sin regresión de remediaciones

Given la head con SEC-001, OPS-WAVE-001R y MOB-ORD-001 verdes
When se integra PCO-008/008R y se ejecutan sus suites SQLite/PostgreSQL/gateway/Windows
Then TDD-TC-171..181 y TDD-TC-141..170 permanecen verdes, CI incluye edge-gateway y ninguna ruta
operacional vuelve a quedar anónima.

## Gates y evidencia mínima

1. Guardar salida RED focal antes de runtime; un test de texto no sustituye comportamiento.
2. GREEN focal de dominio/API/contrato/frontend por paquete.
3. Migración `head -> nueva -> head -> nueva` en SQLite y PostgreSQL aislado cuando aplique.
4. PostgreSQL usa sólo `SEC001_TEST_POSTGRES_URL`, `OPSWAVE001R_TEST_POSTGRES_URL`,
   `MOBORD001_TEST_POSTGRES_URL` o `PCO008_TEST_POSTGRES_URL`, con base de prefijo equivalente;
   SEC-001 omite visiblemente si falta y rechaza antes de conectar una URL que no sea PostgreSQL
   con base `sec001_*`.
   ausencia se reporta omitida, nunca verde. Prohibido `DATABASE_URL`.
5. Ruff, typecheck/build de cada app cambiada, pruebas mobile y edge explícitas en CI.
6. QA visual autenticada/pública según paquete, arquitectura/trazabilidad y `git diff --check`.
7. Suite completa una vez en CI del PR; localmente focales y diagnóstico proporcional.
8. Terra entrega evidencia exacta y Sol reejecuta una selección independiente; R3 no cierra por
   avance parcial, skips no explicados o sólo CI histórica.
