# TDD — POS-CASH-OPS-001 estrategia de verificación

**Estado:** PCO-001 ejecutó autorización, bootstrap/transición y migración de partes de `TDD-TS-077`,
`TDD-TC-073`, `TDD-TS-084` y `TDD-TS-087` en SQLite y PostgreSQL aislado. PCO-002 ejecutó y Sol
auditó el subconjunto de catálogo de `TDD-TS-078` mediante `TDD-TC-084` en SQLite y PostgreSQL
aislado. PCO-003 está autorizado para ejecutar el resto de `TDD-TS-078`, `TDD-TC-074`,
`TDD-TC-079` y `TDD-TC-085..088`. PCO-004 y PCO-005 ya ejecutaron cierre operativo y reapertura de
pedido; PCO-006 define corte por usuario, mientras reportes PCO-007 y offline PCO-008 siguen en
incrementos posteriores.

## TDD-TS-077 Autorización y perfiles acumulativos

Dominio y API comprueban herencia positiva/negativa proyectada por permisos, actor ausente, rol visible
alterado, branch `NULL` legacy, sucursal u organización ajena, escalación a Dueño y preservación de
especialidades. Un rol branch-scoped con `admin.manage` debe ser rechazado en toda operación
corporativa incluso si está asignado a la sucursal por defecto; un rol organization-scoped con el
mismo permiso conserva la capacidad. PCO-001 no ejecuta flujos futuros de movimientos/cortes/reportes
ni frontend/E2E.

## TDD-TC-073 Ningún perfil inferior escala por UI o payload

Given un Cajero y un payload que nombra a Dueño o cambia branch_id
When llama un comando de corte, receta, reporte o caja superior
Then Python rechaza por permiso o alcance y audita la denegación sin mutación.

## TDD-TS-078 Ledger de depósitos, retiros y efectivo esperado

Pruebas Python con centavos y `Decimal` cubren concepto, turno abierto, referencia/evidencia, idempotencia igual/distinta, compensación, fórmula de efectivo esperado y compra cash enlazada. Integración PostgreSQL/SQLite comprueba índices únicos, concurrencia y auditoría. El contrato prueba que el navegador no puede fijar esperado ni diferencia.

## TDD-TC-074 Reintento no duplica efectivo esperado

Given fondo, pago cash y retiro con una idempotency key
When el comando se reintenta y después se intenta con payload distinto
Then el primer reintento devuelve el original y el segundo devuelve idempotency_conflict.

## TDD-TS-079 Cuentas, detalle histórico y solicitud de reapertura

API/contrato cubre filtros, cursor, folio/cliente, alcance, snapshots y solicitud sin mutación. Seguridad
prueba que pagado/cerrado/producción iniciada no se enmienda, solicitud de Cajero jefe+ y autorización
de Dueño para aprobar/rechazar en PCO-005A. PCO-005B sustituye únicamente el gate `/apply` por una
corrección enlazada y compensatoria según TC-101..112; edición directa permanece bloqueada. E2E cubre
lista, detalle, plan servidor, confirmación Dueño, resultado aplicado y ausencia de éxito optimista.

## TDD-TC-075 Reapertura no altera un pedido no elegible

Given pedido pagado con producción iniciada y una solicitud válida
When se registra solicitud y se intenta aplicarla
Then sólo existe solicitud auditable y pago, reservas, consumo, corte y versión permanecen iguales.

## TDD-TC-096 Consulta de cuentas y cursor ligado a filtros

API real cubre alcance, intervalo UTC semiabierto, turno, caja, servicio, folio/cliente, límite y
cursor opaco. Cambiar filtros con el mismo cursor falla `order_accounts_cursor_invalid`; el detalle
de pago confirmado se compara contra snapshots aunque cambie el catálogo vigente.

## TDD-TC-097 Solicitud conserva la huella histórica

Capturar antes y después pedido, revisiones de líneas, pagos, inventario, tareas, cierres, cortes y
snapshots. Crear y repetir una solicitud debe cambiar únicamente tablas de workflow, auditoría y
métrica permitidas; la huella protegida permanece idéntica.

## TDD-TC-098 Idempotencia y concurrencia de solicitud activa

Replay idéntico devuelve el mismo ID; key/payload distinto falla. Dos transacciones concurrentes
sobre el mismo pedido dejan una sola solicitud `REQUESTED|APPROVED` y ningún comando parcial. SQLite
y PostgreSQL aislado se reportan como gates separados.

## TDD-TC-099 Autorización decisión transición y versión

Cajero jefe solicita sólo dentro de alcance; únicamente Dueño lista y decide. Aprobar/rechazar exige
motivo e idempotency key, respeta terminales y falla `order_version_conflict` sin decidir si cambió
la versión snapshot.

## TDD-TC-100 Aplicación denegada y observabilidad redactada

`/apply` sobre `APPROVED` devuelve `order_reopen_policy_pending`; solicitud e historia conservan la
misma huella. Logs, auditoría, métricas y DTOs no contienen motivo libre completo, evidencia, cliente
ni idempotency key.

## TDD-TC-101 Contrato estricto y respuesta redactada de apply

Validar JSON Schema de comando/respuesta: `Idempotency-Key`, versión, líneas, disposiciones,
liquidación y `register_id` nullable; para delta cash exigir caja no vacía y derivar el turno por
sucursal+caja. Rechazar extras, `cash_shift_id`, totales/actor/organización afirmados por cliente,
importes no enteros, IDs ajenos y evidencia vacía cuando aplica. La respuesta no contiene motivo libre, evidencia,
cliente ni idempotency key y conserva códigos de error estables.

## TDD-TC-102 Delta financiero calculado únicamente en Python

Con snapshots reproducibles probar delta positivo, negativo y cero, borde de un centavo, cantidad
múltiple y modificadores. `corrected_total_cents - original_paid_cents` produce exactamente
`CHARGE`, `REFUND(abs)` o ninguna fila. TypeScript no contiene fórmula de total o delta.

## TDD-TC-103 Pago snapshot turno y corte originales permanecen inmutables

Capturar huella de pedido, pago, snapshot de venta/líneas, turno, cierre, corte y asociaciones antes
de aplicar. Después de CHARGE y REFUND sólo aparecen corrección y ajuste enlazados; las filas y hashes
originales son iguales y la diferencia pertenece al turno actual.

## TDD-TC-104 Matriz de estados y disposiciones productivas

Para `PENDING`, reducir cancela tarea y libera reserva diferencial; agregar crea snapshot/reserva/tarea.
Para `IN_PROGRESS`, cualquier cantidad afectada falla sin escritura. Para `COMPLETED`, reducción sin
disposición falla; `waste` conserva consumo y `recovery` crea movimiento positivo exacto.

## TDD-TC-105 Inventario deriva cantidades de snapshots con Decimal

Sembrar conversiones fraccionarias y receta vigente distinta. La parte histórica usa exclusivamente
el snapshot congelado; la adición captura receta vigente nueva. Sumas usan `Decimal`, unidades
incompatibles o snapshot incompleto fallan y no dejan movimientos parciales.

## TDD-TC-106 Dueño scope y negativos de perfiles

Dueño de la organización aplica en cualquier sucursal propia. Cajero, Cajero jefe, Líder, Supervisor
y Administrador reciben denegación; actor cross-org y sucursal fuera de alcance fallan antes de
replay. UI oculta la acción sin sustituir la autorización backend.

## TDD-TC-107 Idempotencia versión y concurrencia SQLite

Replay idéntico devuelve IDs/respuesta estables después de reautorizar. Key con plan, actor u objetivo
distinto falla. Versión divergente conserva `APPROVED`. Dos sesiones con claves diferentes dejan una
corrección y cero ajustes duplicados; SQLite prueba invariantes e índices, no claims de row locking.

## TDD-TC-108 Concurrencia locks e índices PostgreSQL aislado

Con `PCO005B_TEST_POSTGRES_URL` y base `pco005b_*`, ejecutar carreras apply/apply, apply/cierre cash y
apply/cambio de versión. Exactamente un comando gana cada frontera, constraints son los esperados y
no hay deadlock persistente. Rechazar `DATABASE_URL`, nombres productivos y host remoto sin opt-in.

## TDD-TC-109 Rollback tras cada escritura sensible

Inyectar fallo después de corrección, líneas, ajuste financiero, cash movement, inventario, tareas,
eventos y auditoría. Cada caso revierte toda escritura y conserva solicitud `APPROVED`; un reintento
posterior válido puede aplicar exactamente una vez.

## TDD-TC-110 Migración aditiva y downgrade bloqueado con historia

Probar `0039 -> nueva -> 0039 -> nueva` en base vacía SQLite/PostgreSQL, tablas, checks, FKs, índices y
unicidad. Tras sembrar corrección/ajuste, downgrade falla con mensaje explícito y conserva todas las
filas; no se usa `stamp` ni se borra historia.

## TDD-TC-111 UI Dueño semántica y visual

Prueba semántica verifica permiso, carga de solicitud, plan calculado por API, disposiciones
condicionales, clave reintentable, confirmación y refresco. TypeScript estricto y build pasan. QA
visual real cubre 1440x900 y 1000x800 en loading, plan, validación, enviando, aplicado, conflicto y
error, con foco/teclado, español, contraste y sin overflow anidado.

## TDD-TC-112 Reconciliación de reportes efectivo cierre y corte

Comparar monitor, drill-down, efectivo esperado, resumen de cierre y corte antes/después. La venta
original permanece en su periodo; CHARGE/REFUND cash aparece una vez en el turno actual, no cash no
afecta efectivo, y una operación de corte finalizado nunca queda elegible para otro corte.

## TDD-TC-113 Cajero y periodo canónicos del turno

La apertura persiste `cashier_user_id`; crear corte deriva y compara organización, sucursal, caja,
turno, cajero y `[opened_at, closed_at)`. Payload alterado y turno legacy con cero o más de un actor
de apertura fallan antes de escribir. La migración sólo backfillea una fuente inequívoca.

## TDD-TC-114 Matriz de permisos y alcance

API real cubre positivos Líder, Supervisor, Administrador y Dueño, y negativos Cajero, Cajero jefe,
branch NULL, sucursal ajena, actor inactivo/cross-org y rol visible adulterado. La denegación deja
huella financiera idéntica y auditoría redactada.

## TDD-TC-115 Contrato estricto y fórmula Python

JSON Schema acepta únicamente alcance, contado entero no negativo y versión donde corresponde.
Rechaza esperado, diferencia, tolerancia, operaciones, actor, estado y extras. Python congela fondo,
pagos cash y movimientos confirmados y prueba borde de un centavo, depósito, retiro, compensación y
tipo/estado desconocido fail-closed; TypeScript no contiene la fórmula.

## TDD-TC-116 Idempotencia versión y rollback

Crear, contar, finalizar y decidir reapertura reautorizan replay, devuelven la misma respuesta para
hash idéntico y fallan conflicto para key/payload/actor/objetivo distinto. Inyección después de cada
escritura sensible deja cero cortes, asociaciones, comandos, solicitudes, compensaciones o auditorías
parciales y permite un reintento válido único.

## TDD-TC-117 Locks y unicidad PostgreSQL

Con `PCO006_TEST_POSTGRES_URL` y base `pco006_*`, carreras finalize/finalize, finalize/movimiento y
finalize/reapertura producen un ganador determinista, sin deadlock persistente ni doble asociación.
Un periodo parcialmente solapado no evade la unicidad por operación. SQLite prueba constraints, no
row locking. El harness rechaza `DATABASE_URL`, nombres no aislados y host remoto sin opt-in.

## TDD-TC-118 Historial cursor y snapshot inmutable

Lista/detalle prueban filtros, límite `1..100`, cursor ligado al hash, scope y redacción. Cambiar
usuario, zona, pago o movimiento después de FINALIZED no cambia el DTO; evidencia, motivo completo,
hash e Idempotency-Key nunca salen.

## TDD-TC-119 Reapertura y compensación append-only

Una solicitud activa por corte conserva contado propuesto, motivo/evidencia opacos y versión. Sólo
Dueño solicita/decide/compensa. Aprobar, rechazar y compensar respetan terminales; la compensación
calcula diferencia corregida y delta con esperado/tolerancia originales, no toca ledger ni libera
asociaciones.

## TDD-TC-120 Migración reversible y QA POS

SQLite y PostgreSQL aislado prueban `0040 -> 0041 -> 0040 -> 0041`, esquema, backfill inequívoco,
índices y downgrade vacío. Con cualquier historia PCO-006, downgrade falla sin borrar. Prueba
semántica, TypeScript y build cubren selección de turno elegible, captura/confirmación, loading,
COUNTED, FINALIZED, conflicto y error. QA visual real cubre 1440x900 y 1000x800, foco, teclado,
español, contraste y contención sin éxito optimista.

## TDD-TS-080 Turno operativo y monitor de ventas

Dominio/API cubre apertura y cierre idempotentes, `OPEN -> CLOSING -> OPERATIVELY_CLOSED`, actor,
auditoría, rollback y resumen congelado. Verifica esquema estricto: el cierre canónico sólo acepta
objeto vacío y el alias legacy sólo sucursal/caja; contado, esperado, diferencia, actor, estado y
extras fallan sin cierre ni corte. Carreras cierre-movimiento, cierre-compra y cierre-pago se ejecutan
en SQLite y PostgreSQL: exactamente uno gana el guard y el resumen nunca cambia después de confirmar.

Migración prueba `0037 -> 0038 -> 0037 -> 0038`, preflight de familias legacy, huella de turnos,
pagos, pedidos y líneas, índices/constraints y downgrade bloqueado con cierre, comando o snapshot
capturado. Contrato prueba JSON Schema estricto para comandos/respuestas, enteros de centavos,
timestamps UTC y ausencia de claves/PII.

Reportes siembra dos sucursales, cajas, turnos de cobro, servicios, familias y órdenes multifamilia
con snapshots conocidos e incompletos. Prueba intervalo `[from_utc,to_utc)`, scope, facetas, conteo
distinct por pedido, suma por línea sin doble conteo, conocidos/faltantes, cursor estable y drill-down
con filtros idénticos. Cambiar categoría, producto u orden después del pago no altera el resultado.
Python es la única implementación de sumas; TypeScript sólo construye filtros y presenta el DTO.

Frontend cubre estados `loading|open|closed|submitting|error`, clave idempotente reintentable, cierre
por ID, resumen congelado, ruta `/sales-monitor` guardada por `reports.sales.read`, loading/error/
vacío/datos/drill-down y ausencia de estación, impresión, Excel/descarga o nota de consumo. QA visual
real cubre español, teclado/foco, sin éxito antes de confirmación y contención a 1440x900 y 1000x800.

## TDD-TC-076 Cierre operativo conserva corte pendiente

Given turno abierto con efectivo esperado distinto de cero
When Cajero jefe lo cierra operativamente
Then no se crea user_cash_cut ni diferencia ficticia y el resumen conserva sus operaciones.

## TDD-TC-090 Pago diferido y cierre tienen una sola frontera transaccional

Given un pedido pendiente, una caja con turno OPEN y dos transacciones coordinadas
When una confirma el pago y otra cierra operativamente
Then pago ganador queda asociado al turno de cobro e incluido en el cierre
And cierre ganador provoca cash_shift_not_open sin payment, sales snapshot, eventos ni cambio de orden.

## TDD-TC-091 Monitor reconcilia snapshots sin inventar faltantes

Given dos pedidos con varias familias, uno capturado y otro legacy con impuesto desconocido
When se filtra por periodo, turno, familia y servicio y se pagina el drill-down
Then cada pedido se cuenta una vez, los centavos de líneas coincidentes reconcilian
And tax devuelve known_cents más unknown_operation_count y conserva legacy_catalog_backfill.

## TDD-TC-092 Monitor y lista de turnos validan frontera UTC y paginación

Given una sucursal autorizada con zona IANA y más resultados que el límite solicitado
When la UI convierte una vez el día local y API recibe consultas HTTP de turno, monitor y drill-down
Then los timestamps de respuesta son RFC3339 UTC, los cursores son estables y no se repite ni omite fila
And fecha sin zona, cursor mal formado o límite fuera de 1..100 falla con su código de negocio.

## TDD-TC-093 Preflight de moneda conserva verdad histórica

Given pagos y pedidos legacy con moneda vacía, no ISO-3 o distinta tras normalizar mayúsculas
When Alembic intenta subir 0037 a 0038
Then aborta antes de insertar un snapshot de operación
And un caso MXN/MXN válido conserva la moneda del pedido y del pago sin inferencia.

## TDD-TC-094 Observabilidad PCO-004 no revela datos sensibles

Given apertura, cierre, conflicto del guard y consulta con operaciones incompletas
When el servicio emite sus métricas estructuradas
Then registra resultado, sucursal y código de rechazo cuando aplique
And no registra idempotency key, hash, filtros completos, líneas, cliente ni payload.

## TDD-TC-095 Backfill de servicio acepta sólo el alias legado probado

Given pagos CONFIRMED legacy con order_type takeaway y con un tipo desconocido separado
When SQLite y PostgreSQL aislado aplican 0037 a 0038
Then takeaway conserva orders.order_type y produce service_type_snapshot takeout
And el tipo desconocido aborta antes de crear cualquier snapshot
And crear pedidos actuales mantiene validación estricta de dine-in, takeout o delivery.

## TDD-TS-081 Corte por usuario, exactitud y concurrencia

Dominio cubre tupla canónica derivada del turno, operaciones incluidas una sola vez,
contado/esperado/diferencia en centavos, reporte inmutable y reapertura compensatoria. Integración
PostgreSQL y SQLite cubre lock, unicidad, solicitudes concurrentes, reintentos, rollback y migración.
Contrato y frontend prueban que React sólo presenta cálculo Python. E2E cubre captura real de contado.

## TDD-TC-077 Dos cortes concurrentes no duplican operaciones

Given dos transacciones para el mismo cajero, caja, turno y periodo
When ambas finalizan
Then una confirma y la otra falla de forma determinista sin segunda asociación de operaciones.

## TDD-TS-082 Venta por insumos y reportes con historia congelada

Unitarias Python cubren agregación `Decimal`, unidades, periodos, recetas/snapshots distintos,
correcciones y datos incompletos fail-closed. API cubre alcance Supervisor/Administrador/Dueño,
receta versionada e idempotente, gastos canónicos, cursores y redacción. El contrato impide que
TypeScript calcule fórmulas. SQLite prueba semántica/migración y PostgreSQL aislado prueba
concurrencia e índices sin usar `DATABASE_URL`.

## TDD-TC-078 Receta actual no reescribe venta histórica

Given una línea aceptada con snapshot de receta versión uno
When se publica receta versión dos y se consulta el periodo anterior
Then el reporte usa sólo versión uno y expone la procedencia.

## TDD-TC-121 Receta exige permiso y alcance canónico

API y dominio prueban Supervisor/Administrador en sucursal asignada, Dueño en sucursal y corporativo,
y negativos Cajero/Líder, actor ausente, branch `NULL`, sucursal ajena, organización cruzada, nombre
de rol/correo adulterado y permiso ordinario sin authority grant. GET y PUT revalidan alcance; una
denegación no retira receta activa ni confirma command/auditoría de éxito.

## TDD-TC-122 Versionado estricto idempotente y concurrente

Contrato rechaza extras, versión/costo/bruto/actor/organización afirmados, componente duplicado,
cantidad o rendimiento no Decimal positivo y unidad incompatible. Replay idéntico reautoriza y
devuelve misma receta; key con actor/producto/alcance/payload distinto falla. `expected_active_recipe_id`
obsoleto y dos publicaciones concurrentes dejan una versión activa por alcance, historia anterior
retirada y cero command parcial. PostgreSQL prueba locks y SQLite sólo invariantes transaccionales.
El publicador manual de catálogo prueba huella del manifiesto, dry-run exacto, baseline incompleto
fail-closed, ambiente, actor y autoridad organizacional, preferencia de unidad canónica, replay y rollback
transaccional de todas las tablas afectadas, ausencia de productos, precios e insumos pendientes y
unidad de componente igual a la base del insumo; fixture con `06002` versiones 1..4, 11 componentes
activos y `recipe_version_commands` confirma que no borra ni reescribe historia.
También cubre el lote reducido exacto de 307 recetas elegibles y 1,395 componentes: 306 recetas y
1,386 componentes insertados, `06002` con sus nueve componentes fuente preservada, y replay de 306.
Verifica que `11057`, `24001..24007` y `001026..001028` aparezcan
en el reporte/auditoría como pendientes, que no se creen producto, precio, insumo, receta ni categoría
de menú, y que cualquier preexistencia de esos SKU detenga el publicador antes de escribir.

## TDD-TC-123 Proyección de insumos usa venta y receta congeladas

Fixtures con dos pagos confirmados, una orden no pagada y versiones de receta diferentes verifican
que sólo `sales_operation_snapshots` dentro de `[start,end)` participan. Python toma el total ya
congelado de cada componente en `order_line_consumption_snapshots` sin volver a escalarlo por línea,
agrega por `item_id,unit_id`, serializa Decimal como texto y
conserva IDs/versiones de procedencia. Cambiar recetas, catálogo o costo actuales no cambia el hash
del resultado histórico.

## TDD-TC-124 Unidades incompletas y correcciones no inventan cantidades

Snapshot sin unidad/identidad/cantidad válida incrementa incompletos o falla
`historical_snapshot_missing` según su operación y jamás aporta cero. Dos unidades incompatibles del
mismo insumo producen grupos separados. Una corrección aplicada atribuye reducción escalada al
`applied_at` y adición al snapshot nuevo; el periodo original no cambia y el intervalo combinado
reconcilia. Disposición `WASTE|RECOVERY` no altera el agregado de venta.

## TDD-TC-125 Gasto canónico evita compra y retiro duplicados

Compra confirmada cash/no cash produce una fila `purchase` con subtotal, descuento, impuesto y total
en centavos; el withdrawal `PURCHASE` enlazado no agrega otra. Cancelación crea evento inverso en
`cancelled_at`. Retiro manual confirmado produce `cash_movement` y su compensación el inverso;
depósitos ordinarios, purchase cancellation cash, order correction e inventario se excluyen. Impuesto
desconocido permanece `NULL` con contador, sin inferir IVA ni redondear en TypeScript.

## TDD-TC-126 Periodo alcance cursor y consolidado son estrictos

API prueba UTC aware semiabierto, límite `1..100`, orden/cursor estable y cursor ligado a reporte,
periodo, sucursal y filtros. Supervisor/Administrador requieren sucursal asignada; Dueño puede omitirla
para consolidar sólo su organización. Fecha ingenua/invertida, límite, cursor o sucursal inválidos
fallan con código estable. La UI convierte un día local con la zona IANA de la sucursal exactamente
una vez, incluido cambio de fecha UTC.

## TDD-TC-127 Frontend por capacidad y QA visual

Prueba semántica confirma navegación/pestañas por `recipes.manage`,
`reports.ingredient_sales.read` y `reports.expenses.read`; catálogo no autorizado oculta mutaciones
ajenas sin usar la UI como autoridad. Estados carga, vacío, datos, incompleto, error y reintento se
presentan en español. TypeScript estricto y builds pasan. QA visual real cubre 1440x900 y 1000x800,
foco/teclado, tablas contenidas y ausencia de fórmula monetaria o Decimal de dominio en React.

## TDD-TC-128 Migración observabilidad y plan PostgreSQL

SQLite y PostgreSQL aislado validan `0041 -> 0042 -> 0041 -> 0042`, una head, command table, FKs,
unicidad e índices. Downgrade vacío pasa y con command de receta falla conservando filas. PostgreSQL
usa únicamente `PCO007_TEST_POSTGRES_URL` con base `pco007_*` y verifica `EXPLAIN` sin exigir tiempos
frágiles. Métricas/logs de éxito, incompleto y denegación incluyen IDs técnicos/resultado/código y no
incluyen componentes, razones, filtros completos, importes individuales, tokens, keys ni PII.

## TDD-TC-079 Compra cash y compensación no duplican esperado

Given fondo 10000, pago 5000, depósito 1000, retiro 2000 y compra cash WITHDRAWAL 3000
When se calcula esperado y después se compensa la compra con DEPOSIT 3000
Then los resultados son 11000 y 14000 centavos y cada movimiento participa exactamente una vez.

## TDD-TC-085 Movimiento manual exige autoridad, turno, concepto y evidencia

Matriz por permiso prueba Cajero retiro/no depósito, Cajero jefe depósito/retiro y Dueño compensación;
actor ausente, branch ajena/NULL, caja sin turno `OPEN`, importe cero/negativo, concepto
archivado/futuro/incompatible, referencia vacía y evidencia vacía fallan sin movimiento, comando de
éxito ni cambio de esperado. API rechaza actor, organización, shift, snapshot, signo o esperado
afirmados por cliente.

## TDD-TC-086 Replay y concurrencia no duplican ledger

SQLite con dos sesiones y PostgreSQL aislado ejecutan dos comandos iguales/concurrentes: una fila y un
resultado estable. Cambiar actor, sucursal, caja, tipo, concepto, importe, referencia, evidencias o
objetivo bajo la misma key devuelve `idempotency_conflict`. La colisión se recupera en transacción
nueva y nunca confirma escrituras pendientes del llamador.

## TDD-TC-087 Compensación es exacta, opuesta, única e inmutable

Dueño compensa un retiro con depósito del mismo importe, motivo y evidencia; original y compensación
permanecen. Se rechaza monto/tipo enviados por cliente, doble compensación concurrente, compensar una
compensación, original ajeno/no confirmado o turno cerrado. Cada rechazo conserva el ledger y audita
sin confirmar otra escritura pendiente.

## TDD-TC-088 Migración compatible y lectura histórica

SQLite y PostgreSQL aislado validan `0036 -> 0037 -> 0036 -> 0037`, una sola head, columnas/tablas/
índices y huella exacta de filas legacy. Downgrade con comandos o campos PCO-003 bloquea sin perder
historia. Lectura filtrada/cursor incluye snapshots nuevos y proyecta `withdrawal|cash_reversal`
legacy sin reescribirlos.

## TDD-TC-089 Compensación productiva desde el POS converge ledger y efectivo esperado

Backend/API/contrato prueban `compensation_state` y `compensated_by_movement_id` para original
elegible, compensado, compensación, turno cerrado y fila legacy, incluida autorización negativa y
revalidación concurrente. Frontend prueba que sólo Dueño ve `Compensar`, que el request contiene
exclusivamente `reason` y `evidence_refs`, conserva Idempotency-Key durante error no confirmado y no
permite editar importe/tipo/vínculo. Una máquina de estado probada abre una fila, conserva su clave
ante error incierto, y al cancelar o elegir otra descarta target, clave y campos; durante envío no
admite abandono. Tras creación y compensación se vuelve a ejecutar GET ledger y
se muestra `current_summary`; original y compensación quedan visibles con efecto neto cero. E2E
productivo controlado usa un concepto QA archivado después, un turno OPEN autorizado y evidencia no
sensible; comprueba auditoría y conteos antes/después sin borrar historia.
La prueba frontend cubre además una tabla exhaustiva y cerrada para traducir tipos (`deposit`,
`withdrawal`, `cash_reversal`) y estados (`eligible`, `compensated`, `compensation`, `ineligible`) a
español de México; un valor desconocido usa una etiqueta neutra y nunca se presenta como código interno.

## TDD-TC-080 Corte parcialmente solapado rechaza operación ya asociada

Given un corte FINALIZED que contiene una operación del turno uno
When el primer corte se reabre/compensa conforme a PCO-006 y se finaliza otro corte parcialmente solapado que intenta asociarla
Then falla cash_cut_already_finalized y un corte del turno dos no puede usarla.

## TDD-TC-081 Invariante de grant organizacional y mapeo append-only

SQLite prueba dos filas `reversed` históricas para el mismo usuario/perfil y rechaza dos
`pending|mapped` activos. Dominio prueba que `admin.manage` legacy no cambia scope, borra ni reemplaza
permisos de un rol con `organization_all_permissions`; el actor con el grant puede renombrarlo sin
perder autorización dinámica. También prueba que `access.organization.all_branches` como permiso
ordinario no concede permisos futuros ni crea el grant. PostgreSQL aislado valida una autoridad Dueño,
dos asignaciones exactas y un mapping histórico revertido sin mapping activo.

## TDD-TS-088 Bootstrap y transición explícita de perfiles

Dominio SQLite prueba bootstrap con los dos correos configurados, organización/actor/procedencia
explícitos, usuarios preexistentes/activos con rol legacy preservado, atomicidad, replay estable, conflicto y ausencia sin cuentas
nuevas. Prueba dry-run sin PII, creación `PENDING`, aplicación aditiva, reversión `REVERSED`, snapshot,
idempotencia, segundo ciclo histórico, conflicto concurrente, replay de carrera con payload distinto,
stale legacy por ausencia o sucursal distinta y destino reasignado. Prueba además que una denegación,
incluido actor cross-org existente, revierte escritura ajena antes de persistir su auditoría en la
organización objetivo, y que organización inexistente/inactiva falla antes de autoridad/auditoría sin
violar FK. PostgreSQL aislado ejecuta upgrade/downgrade/re-upgrade, bootstrap exacto/replay y el ciclo
dry-run/PENDING/MAPPED/REVERSED/replay con fixture determinista. No equivale a bootstrap ni E2E sobre
usuarios o datos productivos.

## TDD-TC-082 Bootstrap no tiene escalación general

Given usuarios preexistentes, una organización explícita y los dos correos autorizados
When se intenta variar correo, organización, actor, procedencia o dejar una asignación parcial
Then el comando falla sin asignaciones nuevas y conserva auditoría de rechazo cuando aplica.

## TDD-TC-083 Reversión sólo retira la asignación creada por el mapping

Given un mapping aplicado que conservó una especialidad existente
When se revierte con su key y actor autorizado
Then se retira únicamente el perfil destino agregado, snapshot y filas históricas permanecen y un
reintento devuelve el estado `REVERSED`. Si la fila destino ya no coincide exactamente con la sucursal
registrada por el mapping, el caso falla y no modifica el estado.

## TDD-TC-084 Catálogo efectivo versionado e idempotente

Given una identidad de concepto publicada en versión uno y un actor con permisos persistidos
When crea, versiona o archiva con `Idempotency-Key`
Then el replay idéntico no duplica filas, un payload distinto falla `idempotency_conflict`, el código
no cambia, la lectura por fecha/tipo devuelve sólo la versión efectiva y el archivo conserva toda la
historia. SQLite y PostgreSQL aislado prueban `0035 -> 0036 -> 0035 -> 0036`; el downgrade se bloquea
si existe historia de conceptos.
Frontend fija `TZ=America/Mazatlan` y prueba que un instante UTC se presenta con sus componentes
locales en `datetime-local`, tanto al crear como al iniciar una nueva versión, y que el payload vuelve
al ISO UTC equivalente sin sumar dos veces el desfase. También cubre el cruce de fecha UTC/local.

## TDD-TS-083 Offline, outbox/inbox e idempotencia de caja

Integración gateway SQLite/PostgreSQL cubre persistencia local, actor/alcance, reintento, reconexión, inbox duplicado, denegación remota, lag y estado visible. Recuperación verifica que no exista éxito final local ni compensación automática por conflicto.

### TDD-TC-168 Compensación manual con autoridad persistida de Dueño

- Archivo: `apps/api/tests/test_cash_ledger.py::test_compensation_requires_persisted_owner_authority_not_only_permission`
- Un actor con `cash.movement.compensate` sin grant `organization_all_permissions` recibe
  `permission_denied` y no agrega movimiento; el Dueño persistido conserva la compensación
  append-only y el resumen Python exacto en centavos.

## TDD-TS-084 Migraciones y downgrade reversibles

Alembic PostgreSQL y SQLite debe cubrir upgrade desde head, una head, downgrade y re-upgrade, roles
semilla, Administrador corporativo y especialidades. Debe rechazar downgrade si hay user_role de perfil,
mapping o grant externo, y permitirlo sólo tras reversión controlada sin borrar datos confirmados.
PCO-001 ejecuta SQLite y PostgreSQL aislado para perfiles; los modelos de caja posteriores siguen sólo
definidos.

### TDD-TC-211 Reparación forward-only de grants agregados por 0047

- Archivo: `apps/api/tests/test_canonical_roles_repair_migration.py`

SQLite migra una base vacía hasta la head y verifica que los cinco perfiles de sucursal conservan
exactamente la matriz acumulativa de `0035`, mientras Dueño conserva scope organizacional y su grant
persistido sin usuarios nuevos. Casos de preflight alteran un permiso requerido o agregan un homónimo
cross-org antes de aplicar la revisión: el upgrade falla, conserva la revisión previa y no hace
cambios parciales. El downgrade de la reparación queda bloqueado por ser una corrección de datos
forward-only. PostgreSQL aislado repite preflight, upgrade y evidencia antes/después en CI.

## TDD-TS-085 Contratos, frontend y E2E por perfil

Validar JSON Schema versionado de endpoints, errores y serialización de centavos/Decimal. E2E por los seis perfiles cubre navegación autorizada/denegada, sucursal, movimientos, cuentas, monitor, corte y reportes. QA visual cubre escritorio/reducido, foco, teclado, contraste y estados vacío/carga/error.

## TDD-TS-086 Seguridad y observabilidad R3

Verificar step-up según política aprobada, rate limit, auditoría append-only de éxito/denegación, redacción de secreto/PII, correlation id, métricas y trazas. Regresión confirma que UI, logs y eventos no son fuente de autorización ni cálculo financiero.

## TDD-TS-087 Threat model, reversión y contratos de iteración 2

Prueba simulaciones de escalación, branch tampering, replay, autorización offline vencida, doble corte, evidencia/PII, modificación histórica y downgrade. Verifica aprobación humana antes de R3, fallo/reversión controlados, compatibilidad por fases y que rollback de aplicación, downgrade de esquema y compensación de negocio son procedimientos distintos.

## TDD-TC-171 Outbox local transaccional e idempotente

SQLite WAL prueba persistencia antes de `PENDING_SYNC`, hash/replay, conflicto por key o command ID,
migración local versionada y preservación tras reabrir la base.

## TDD-TC-172 Autenticación doble y bindings fail-closed

API prueba credencial técnica y grant Ed25519 válidos, ausentes, alterados, revocados, expirados y
ligados a otro actor/scope. Ningún negativo crea dominio ni persiste grant o secreto.

## TDD-TC-173 Reconciliación atómica reutiliza PCO-003

La ruta online y sync comparten el núcleo transaccional. Fallos después de movimiento, command log,
inbox, evento o auditoría dejan cero parcial; el esperado sigue siendo autoridad Python.

## TDD-TC-174 Replay, intención y autoridad obsoleta

Replay idéntico devuelve movimiento/checkpoint originales. Intención distinta, actor inactivo,
permiso revocado, turno cerrado o concepto no efectivo produce conflicto sin efecto financiero.

## TDD-TC-175 Recuperación local y clasificación de errores

Reloj y transportes falsos prueban `PENDING_SYNC -> SYNCING -> CONFIRMED|CONFLICT`, recuperación de
reinicio y backoff determinista sin red real ni `sleep`.

## TDD-TC-176 Checkpoint concurrente por sucursal

PostgreSQL aislado usa `PCO008_TEST_POSTGRES_URL`, sesiones independientes y base local `pco008_*`;
verifica fila bloqueada, secuencia por sucursal, replay y rollback. Nunca lee `DATABASE_URL`.

## TDD-TC-177 Contrato y UX POS offline

JSON Schema rechaza extras/tipos/valores fuera de allowlist. Contrato frontend y QA visual verifican
misma intención, estados españoles y ausencia de cálculo financiero o acciones offline adicionales.

## TDD-TC-178 Migraciones, downgrade, redacción y límites

Alembic `0044 -> 0045 -> 0044 -> 0045` preserva sync legacy, mantiene una head y bloquea downgrade
con historia. Configuración prueba origen POS exacto, normalización IPv4/IPv6 y TLS obligatorio fuera de
loopback, además de config/paths absolutos confinados al runtime root, archivo técnico regular con
permisos privados, rutas distintas por valor e inode, symlinks/hardlinks rechazados, sustitución
tardía fail-closed y modos POSIX privados de root/SQLite/log. Logging prueba rotación de 5 MiB por
tres respaldos, exclusión de handlers duplicados, restauración de nivel aun ante fallo de cierre y
apagado que libera transporte/logging y desactiva readiness aunque falle la recuperación. Una falla
de composición posterior a crear el cliente/handler verifica rollback de ambos. Escaneo y
logs omiten credenciales, grants, referencias completas y PII.

## Cobertura directa PRD y BDD

| Suite/caso | PRD/NFR | BDD principal |
|---|---|---|
| TDD-TS-077, TDD-TC-073, TDD-TC-081, TDD-TS-088, TDD-TC-082, TDD-TC-083 | PRD-FR-715, NFR-020, NFR-024 | BDD-SC-270/271/277/298/299/300 ejecutados parcialmente por autorización/transición; 272..276/293 proyectados o negativos de ruta existente |
| TDD-TS-078, TDD-TC-074, TDD-TC-079, TDD-TC-084..088 | PRD-FR-716, NFR-020, NFR-021, NFR-024 | BDD-SC-278..280, 294, 296, 301..305; PCO-002 ejecuta catálogo y PCO-003 ejecuta ledger/compensación/esperado |
| TDD-TS-079, TDD-TC-075, TDD-TC-096..100 | PRD-FR-717 | BDD-SC-281..283, BDD-SC-312..316 |
| TDD-TS-080, TDD-TC-076, TDD-TC-090..095 | PRD-FR-708, PRD-FR-718 | BDD-SC-284, 285, 292, 307..311 |
| TDD-TS-081, TDD-TC-077, TDD-TC-080, TDD-TC-113..120 | PRD-FR-719, NFR-020, NFR-021, NFR-024 | BDD-SC-286, 287, 295, 327..334 |
| TDD-TS-082, TDD-TC-078, TDD-TC-121..128 | PRD-FR-720, NFR-002/016/018/020/021/023 | BDD-SC-275/276/288/297/335..342 |
| TDD-TS-083 | PRD-FR-716, NFR-022 | BDD-SC-289 |
| TDD-TC-168 | PRD-FR-716, NFR-021 | BDD-SC-280 |
| TDD-TS-084 | PRD-FR-715, NFR-024 | BDD-SC-290 |
| TDD-TS-085 | PRD-FR-715..220 | BDD-SC-270..297 definido; no ejecutado en PCO-001 |
| TDD-TS-086, TDD-TS-087 | NFR-020..024 | BDD-SC-271, 289..297 |

## Comandos previstos — estado `defined`, no ejecutados

```bash
python -m pytest apps/api/tests -q
PCO002_TEST_POSTGRES_URL=postgresql+psycopg://localhost:PORT/pco002_test python -m pytest apps/api/tests/test_cash_concepts_postgres.py -q
python -m pytest tests/architecture/test_traceability.py -q
python -m ruff check apps/api tests
pnpm typecheck
pnpm --filter @restaurantos/pos-web test
pnpm --filter @restaurantos/pos-web build
git diff --check
```

Antes de implementación se añadirán comandos de integración PostgreSQL, SQLite gateway y Playwright; los nombres, fixtures, conteos y resultados permanecen pendientes hasta existir las pruebas.
