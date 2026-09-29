# SDD — Fronteras de integración y CRM, remediación 2026-09-28

PRD-FR-003 conserva autoridad: los identificadores recibidos no otorgan alcance.
Las mutaciones marketplace autorizan actor, permiso y sucursal antes de llamar al servicio.
El servicio comprueba organización/sucursal activas y pertenencia tanto al guardar mapping como
al resolver el destino de un webhook; una asociación histórica inválida se rechaza antes de I/O.
Trial transcurrido no equivale a suspensión.

La disponibilidad Uber sólo encola destinos activos y pertenecientes al tenant, incluyendo producto
y mapping de ítem. Al reclamar un job existente se revalida el destino exacto antes de liberar la
transacción y realizar I/O. Sucursal/mapping/producto revocados producen FAILED con razón acotada,
nunca CONFIRMED sin envío. La autorización tiene su punto de decisión en el claim: una desactivación
posterior puede ocurrir entre el commit y el inicio de HTTP, o durante la petición. El job ya
autorizado puede salir en ambos casos; no se garantiza cancelación instantánea tras el claim.

Una nueva FK compuesta de `channel_store_mappings(organization_id, branch_id)` referencia
`branches(organization_id, id)`, cuyo índice único ya existe. La migración nueva comprueba
asociaciones inválidas y se detiene sin alterar datos; no reescribe migraciones históricas.
Downgrade retira únicamente la guarda nueva, conservando filas; exige retirar tráfico que dependa
de esa garantía antes de ejecutarlo. SQLite y PostgreSQL deben verificar upgrade/downgrade.

CRM resuelve siempre el alcance con la guarda canónica aunque se omita `branch_id`; la consulta
global requiere permiso de alcance organizacional. Un rol de sucursal utiliza la sucursal autorizada
por la guarda o recibe denegación. El mismo alcance limita clientes, pedidos, importes y contadores.
No se introduce una fórmula financiera nueva ni se mueve cálculo de dinero al frontend.

### Catálogo usado al cotizar y capturar pedidos

El resolutor compartido `_get_available_product` vincula la sucursal activa al tenant del
producto y exige que categoría y versión de precio pertenezcan al mismo tenant antes de
resolver ID, SKU o nombre. La ausencia de una fila de disponibilidad por sucursal sólo
significa disponible para un producto de esa organización; no habilita productos ajenos.
Conserva precio en centavos y los aliases existentes dentro del tenant. Una referencia ajena
se rechaza antes de construir recetas/snapshots o persistir intención, pedido e inventario.
Los productos exclusivos de sucursal exigen `source_branch_id` igual a la sucursal de la
operación, conforme a la misma frontera que usa el catálogo público; pertenecer al tenant
no concede acceso a un catálogo local de otra sucursal.

### CRM: lectura agregada con costo de consultas acotado

La segmentación obtiene una fila agregada por cliente en una sola consulta SQL. Clientes y
pedidos se filtran explícitamente por organización y, cuando corresponde, por sucursal antes
de agregarse. Un `LEFT JOIN` conserva los clientes sin pedidos. `COUNT`, `SUM` de centavos
enteros y `MAX(created_at)` sustituyen la lectura de todos los pedidos por cada cliente;
Python conserva la clasificación, normalización UTC, ordenación y límites de presentación
vigentes (15 elementos por segmento, contadores sobre todo el conjunto autorizado).
No se introduce paginación ni nuevos estados o umbrales de segmentación. El número de consultas
no crece con el número de clientes; el trabajo SQL y la memoria aún dependen del volumen
autorizado. La evaluación de índices se basa en `EXPLAIN` y un conjunto sintético reproducible,
sin añadir índices o migraciones por intuición.

Preguntas operativas de esta lectura: ¿crece el número de consultas con los clientes?, ¿cuánto
tarda el agregado en el volumen ensayado? Las pruebas cuentan sentencias y registran duración
y plan SQL en evidencia local, sin nombres, teléfonos ni contenido de clientes reales. Esa
medición sintética no se presenta como capacidad o latencia productiva.

Preguntas operativas: ¿se rechazó un scope ajeno antes de persistir?, ¿el resolver rechazó un mapping
inválido antes de procesar el evento? La auditoría de autorización existente registra razón,
actor y correlación; errores del resolver usan códigos acotados sin payloads o secretos.
WhatsApp permanece aplazado; este cambio no habilita proveedor, notificaciones ni configuración.

### Consulta del turno para movimientos de caja

El alias `/cash-shifts/current` conserva las capacidades alternativas ya contratadas:
`cash.shift.read`, `cash.movement.read`, `cash.movement.withdraw` o `cash.movement.deposit`.
Un servicio específico resuelve actor y sucursal mediante `authorize_cash_movement_scope`
antes de consultar el turno. No aplica después una segunda exigencia exclusiva de
`cash.shift.read`. La ruta canónica `/cash/shifts/current` conserva su permiso de lectura
de turno y su reconciliación automática; el alias no agrega ese efecto. Ambas rechazan
actores revocados o sucursales fuera del alcance. No cambia dinero, persistencia ni estados.
La elección de permiso candidato consulta grants persistidos de la sucursal y no autoriza
por sí misma: la guarda canónica revalida estado del actor/tenant, pertenencia y permiso.
No se prueban alternativas mediante denegaciones auditadas, pues éstas hacen commit y un
rollback posterior no las deshace. Una consulta permitida no agrega denegaciones falsas;
un rechazo final conserva una sola `authorization.denied`, sin borrar auditoría histórica.

El agotado temporal modifica `branch_product_availability`, no la habilitación administrativa
de `channel_product_mappings`. Desactivar el mapping impediría enviar precisamente el agotado
y cambiaría otras sucursales al reutilizar un mapping organizacional. El outbox conserva el
destino habilitado y transmite la disponibilidad solicitada sólo para las sucursales autorizadas.
