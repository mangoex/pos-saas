# BDD — POS-CASH-OPS-001 caja, cuentas, corte y perfiles

**Estado:** decisiones `OPEN-011..017` resueltas el 2026-08-10 y conservadas como trazabilidad.
PCO-001 ejecuta la semilla/proyección de permisos de `BDD-SC-270`, la asignación y denegación de
alcance de `BDD-SC-271`, la autoridad persistida/cross-org de `BDD-SC-277`, y la migración SQLite de
`BDD-SC-290`. En `BDD-SC-272..276`, `291` y `293` sólo ejecuta las denegaciones o permisos base que
ya tienen ruta; los flujos de movimientos, corte, conceptos, receta, reportes y reapertura permanecen
definidos/proyectados para sus PCO posteriores. PCO-002 ejecuta `BDD-SC-296`, `BDD-SC-301` y la
precondición de catálogo de `BDD-SC-278`. PCO-003 fue autorizado para completar `BDD-SC-278..280`,
`BDD-SC-294` y los escenarios específicos `BDD-SC-302..305`; no ejecuta offline ni PCO-004+.

## BDD-FEAT-076 Perfiles acumulativos y alcance

```gherkin
@rbac
Feature: Autorizar capacidades acumulativas por permisos persistidos

  @PRD-FR-715
  @BDD-SC-270
  Scenario: La jerarquía concede sólo las capacidades acumuladas
    Given usuarios Cajero, Cajero jefe, Líder, Supervisor, Administrador y Dueño con permisos semilla
    When cada usuario consulta su proyección de capacidades para su sucursal canónica
    Then cada nivel conserva las capacidades de los niveles inferiores
    And ningún nivel inferior recibe una capacidad del nivel superior
    And la respuesta no depende del texto visible del rol

  @PRD-FR-715 @PRD-NFR-520
  @BDD-SC-271
  Scenario: Una sucursal no asignada se deniega por defecto
    Given un Supervisor con asignación branch-scoped `NULL` legacy o asignado únicamente a Sucursal Centro
    When solicita inventario, caja o reporte de Sucursal Norte
    Then el backend responde branch_scope_denied o permission_denied sin datos ni mutación
    And registra authorization.denied con actor, recurso y correlation id
    When un administrador intenta crear una asignación branch-scoped sin sucursal
    Then el backend responde branch_assignment_required sin escritura
    Given un rol branch-scoped recibe `admin.manage` por configuración personalizada o historia legacy
    When intenta consultar o mutar usuarios, roles, permisos u otro catálogo corporativo
    Then el backend responde permission_denied aunque la asignación corresponda a la sucursal por defecto
    And sólo un rol organization-scoped puede ejercer `admin.manage`

  @PRD-FR-715
  @BDD-SC-272
  Scenario: Cajero vende y registra retiro sin manejar caja
    Given un Cajero con turno abierto en su sucursal asignada
    When crea y cobra un pedido y registra un retiro manual válido
    Then las operaciones quedan auditadas y el retiro se incorpora una vez al efectivo esperado
    When intenta abrir/cerrar turno, depositar, comprar, registrar merma o crear corte por usuario
    Then cada comando se rechaza por permiso sin escritura parcial

  @PRD-FR-715
  @BDD-SC-273
  Scenario: Cajero jefe maneja caja y operación pero no acciones de Líder
    Given un Cajero jefe con sucursal y turno autorizados
    When abre o cierra operativamente turno, deposita, enmienda pedido elegible, compra y registra merma
    Then cada acción usa permisos granulares y auditoría append-only
    When intenta cancelar pedido o crear corte por usuario
    Then el backend responde permission_denied

  @PRD-FR-715
  @BDD-SC-274
  Scenario: Líder cancela y corta por usuario sin modificar recetas
    Given un Líder autorizado y un corte con alcance válido
    When cancela un pedido elegible y solicita el corte por usuario
    Then ambas acciones guardan actor, alcance e idempotency key
    When intenta editar una receta
    Then el backend lo deniega

  @PRD-FR-715 @PRD-FR-720
  @BDD-SC-275
  Scenario: Supervisor consulta insumos e inventario y administra receta dentro de alcance
    Given un Supervisor asignado a una sucursal
    When consulta venta por insumos, inventario y reporte de merma y modifica una receta autorizada
    Then sólo recibe datos y efectos de su alcance y cada acción sensible se audita
    And la venta por insumos usa snapshots históricos de receta

  @PRD-FR-715 @PRD-FR-720
  @BDD-SC-276
  Scenario: Administrador consulta reportes de ventas y gastos sólo dentro de alcance asignado
    Given un Administrador con sucursales asignadas
    When consulta reportes de ventas y gastos
    Then el backend agrega únicamente las sucursales autorizadas
    And no concede acceso organizacional total por el nombre Administrador

  @PRD-FR-715
  @BDD-SC-277
  Scenario: Dueño opera consolidado de todas las sucursales
    Given un Dueño con todos los permisos persistidos vigentes de su organización y access.organization.all_branches
    When consulta un reporte consolidado, administra un catálogo corporativo y ejecuta una capacidad especializada autorizada
    Then recibe únicamente datos de la organización y puede consultar todas sus sucursales
    And cada autorización se resuelve en backend sin wildcard enviado por cliente
    When intenta consultar o mutar una segunda organización
    Then recibe branch_scope_denied o permission_denied sin escritura parcial
```

## BDD-FEAT-077 Movimientos y consulta de cuentas

```gherkin
@cash
Feature: Registrar efectivo y revisar cuentas históricas

  @PRD-FR-716
  @BDD-SC-278
  Scenario: Movimiento directo de caja con concepto libre o snapshot opcional
    Given un turno abierto en la terminal de caja
    When un actor autorizado registra un retiro o depósito con importe positivo y concepto en texto libre
    Then se crea un movimiento append-only con el motivo indicado sin exigir catálogo corporativo previo
    And si se proporciona un concepto versionado opcional, se preserva su snapshot para compatibilidad

  @PRD-FR-716 @PRD-NFR-521
  @BDD-SC-279
  Scenario: Efectivo esperado usa pagos y movimientos exactamente una vez
    Given un turno con fondo de 10000, pago cash de 5000, depósito de 1000, retiro manual de 2000 y compra cash de 3000
    When el backend calcula efectivo esperado
    Then devuelve 11000 centavos usando cada cash_movement una sola vez
    And la compra es un WITHDRAWAL source_type PURCHASE y no se resta en otro término
    And un reintento con la misma clave no agrega un segundo movimiento

  @PRD-FR-716 @PRD-NFR-521
  @BDD-SC-280
  Scenario: Sólo un Dueño con concesión persistida compensa sin borrar historia
    Given un retiro confirmado con error de concepto o importe
    And un Dueño con la concesión persistida organization_all_permissions y cash.movement.compensate
    When el Dueño registra su compensación referenciada
    Then permanecen visibles original, compensación, actores y motivo
    And no se puede editar ni eliminar el retiro original
    When un actor tiene sólo cash.movement.compensate sin la concesión persistida de Dueño
    Then recibe permission_denied y no se agrega movimiento alguno

  @PRD-FR-717
  @BDD-SC-281
  Scenario: Consultar cuentas por filtros y abrir detalle snapshot
    Given cuentas de venta directa y domicilio en varias cajas, turnos y fechas
    When un actor autorizado filtra por turno, día, caja, sucursal y servicio o busca folio/cliente
    Then sólo recibe el conjunto dentro de alcance
    And el detalle muestra líneas, cantidades, productos, pago y snapshots históricos

  @PRD-FR-717
  @BDD-SC-282
  Scenario: Pedido pagado o con producción iniciada no se reabre
    Given un pedido pagado, cerrado o con tarea fuera de PENDING
    When cualquier perfil solicita editarlo o aplicarle reapertura directa
    Then el backend devuelve order_reopen_not_eligible o order_reopen_policy_pending
    And no toca pago, reservas, consumo, corte ni eventos existentes

  @PRD-FR-717
  @BDD-SC-283
  Scenario: Reapertura es sólo una solicitud hasta decisión de Dueño
    Given la política aprobada asigna orders.reopen.request a Cajero jefe o superior
    And existe un pedido consultable y motivo/evidencia válidos
    When el actor crea la solicitud auditada
    Then se crea una solicitud auditable sin cambiar el pedido
    And sólo Dueño puede aprobar o rechazar en PCO-005A
    And la aplicación permanece cerrada hasta PCO-005B

  @PRD-FR-717
  @BDD-SC-312
  Scenario: Consultar cuentas usa alcance cursor y snapshots históricos
    Given pedidos de varias sucursales turnos cajas servicios y fechas
    When un actor consulta cuentas con filtros UTC y un cursor ligado a esos filtros
    Then el backend devuelve sólo su alcance con orden estable
    And un pago confirmado se presenta desde snapshots sin consultar catálogo vigente

  @PRD-FR-717
  @BDD-SC-313
  Scenario: Solicitar reapertura no muta historia protegida
    Given un pedido pagado cerrado o con producción iniciada
    And un Cajero jefe autorizado proporciona motivo evidencia e idempotency key válidos
    When crea una solicitud de reapertura
    Then recibe estado REQUESTED y el replay devuelve la misma solicitud
    And pedido líneas pagos inventario producción cierres y snapshots conservan la misma huella

  @PRD-FR-717
  @BDD-SC-314
  Scenario: Sólo existe una solicitud activa y la clave no cambia de significado
    Given dos comandos concurrentes para el mismo pedido protegido
    When intentan crear solicitudes activas con claves distintas
    Then sólo una solicitud queda REQUESTED
    And la otra falla order_reopen_request_active sin escritura parcial
    And reutilizar una clave con otro payload falla idempotency_conflict

  @PRD-FR-717
  @BDD-SC-315
  Scenario: Sólo Dueño decide una solicitud con versión estable
    Given una solicitud REQUESTED dentro del alcance organizacional
    When un actor sin orders.reopen.authorize intenta decidirla
    Then recibe actor_not_authorized y la solicitud no cambia
    When Dueño aprueba o rechaza con la misma versión y comando idempotente
    Then la decisión y su replay son estables y auditables
    But si la versión cambió responde order_version_conflict y conserva REQUESTED

  @PRD-FR-717
  @BDD-SC-316
  Scenario: La aplicación compensatoria permanece cerrada en PCO-005A
    Given una solicitud APPROVED por Dueño
    When Dueño intenta aplicarla
    Then el backend responde order_reopen_policy_pending
    And no cambia solicitud pedido pago inventario producción cierre ni snapshots

  @PRD-FR-717
  @BDD-SC-317
  Scenario: Aplicar una corrección de delta cero conserva la cuenta original
    Given una solicitud APPROVED con pago confirmado y producción PENDING
    And Dueño propone una imagen corregida con el mismo total
    When aplica el plan con versión e idempotency key vigentes
    Then crea una corrección APPLIED sin ajuste financiero
    And pedido pago snapshot turno cierre y corte originales conservan la misma huella

  @PRD-FR-717
  @BDD-SC-318
  Scenario: Un aumento crea un cargo actual sin mover el pago original
    Given una solicitud APPROVED y un turno OPEN autorizado
    And la imagen corregida supera en 3000 centavos el pago original
    When Dueño aplica el plan con método cash y register_id cuya caja tiene un turno OPEN
    Then crea un CHARGE enlazado de 3000 y un DEPOSIT de caja actual una sola vez
    And el pago y la asociación histórica a turno o corte no cambian

  @PRD-FR-717
  @BDD-SC-319
  Scenario: Una disminución crea reembolso compensatorio verificable
    Given una solicitud APPROVED cuya imagen corregida reduce 2000 centavos
    When Dueño aplica cash con register_id y turno OPEN derivado o un método no cash con evidencia válida
    Then crea un REFUND enlazado de 2000
    And cash crea un WITHDRAWAL actual mientras tarjeta o transferencia conserva evidencia manual
    But sin register_id o turno cash derivable o evidencia no cash falla sin escritura

  @PRD-FR-717
  @BDD-SC-320
  Scenario: Producción pendiente libera y agrega sólo las cantidades diferenciales
    Given una solicitud APPROVED con tareas PENDING y snapshots de consumo completos
    When la corrección reduce una línea y agrega otra
    Then cancela la tarea reducida y libera sólo su reserva diferencial
    And crea snapshot reserva y tarea PENDING para la adición

  @PRD-FR-717
  @BDD-SC-321
  Scenario: Producción iniciada bloquea y producción terminada exige disposición
    Given una solicitud APPROVED que reduce una cantidad ya producida
    When la tarea está IN_PROGRESS
    Then responde production_in_progress sin escritura
    When la tarea está COMPLETED y falta waste o recovery
    Then responde production_disposition_required sin escritura
    But con waste conserva consumo y con recovery crea movimiento positivo enlazado

  @PRD-FR-717
  @BDD-SC-322
  Scenario: Plan versión o clave conflictivos no dejan aplicación parcial
    Given una solicitud APPROVED y un plan canónico
    When cambia la versión o faltan líneas disposiciones liquidación o snapshots requeridos
    Then devuelve el error estable correspondiente y conserva APPROVED
    And reutilizar la idempotency key con otro plan devuelve idempotency_conflict

  @PRD-FR-717
  @BDD-SC-323
  Scenario: Sólo Dueño autorizado dentro de la organización aplica
    Given una solicitud APPROVED de una sucursal válida
    When intenta aplicar un perfil no Dueño un actor de otra organización o fuera de alcance
    Then recibe actor_not_authorized o branch_scope_denied
    And no se crea corrección ajuste movimiento tarea evento ni command log completado

  @PRD-FR-717
  @BDD-SC-324
  Scenario: Aplicaciones concurrentes producen una sola corrección
    Given una solicitud APPROVED y dos comandos concurrentes con claves distintas
    When ambos intentan aplicar el mismo plan
    Then exactamente uno crea la corrección y cambia la solicitud a APPLIED
    And el otro falla por transición o unicidad sin duplicar compensaciones
    And el replay de la clave ganadora devuelve la misma respuesta después de reautorizar

  @PRD-FR-717
  @BDD-SC-325
  Scenario: Reportes separan corrección actual de la venta histórica
    Given una venta original incluida en un turno o corte histórico
    When se aplica una corrección con diferencia financiera
    Then el monitor histórico conserva la operación original sin cambios
    And la diferencia aparece como corrección del periodo y turno en que se ejecutó
    And ningún corte finalizado libera ni reasigna su operación original

  @PRD-FR-717
  @BDD-SC-326
  Scenario: Un fallo interno revierte toda la aplicación
    Given una solicitud APPROVED y un plan válido
    When ocurre un fallo después de cualquier escritura sensible antes del commit
    Then la solicitud permanece APPROVED
    And no persiste corrección línea ajuste movimiento tarea evento auditoría parcial ni respuesta
```

## BDD-FEAT-078 Turnos, monitor y corte por usuario

```gherkin
@cash @reports
Feature: Separar cierre operativo de corte final y monitorear ventas

  @PRD-FR-718
  @BDD-SC-284
  Scenario: Cierre operativo no fabrica un corte final
    Given un turno abierto con operaciones confirmadas
    When un Cajero jefe autorizado lo cierra operativamente
    Then se congela el resumen y actor del cierre
    And el turno queda OPERATIVELY_CLOSED en la misma transacción
    And no se envía efectivo contado, esperado o diferencia
    And no se crea cash_shift_cut ni UserCashCut
    And un replay idéntico devuelve el mismo cierre sin duplicarlo

  @PRD-FR-718
  @BDD-SC-285
  Scenario: Monitor de ventas filtra y baja a operaciones trazables
    Given ventas con familias, servicios, impuestos y cortesías en distintos turnos
    When un actor autorizado filtra fecha, turno, familia y tipo de servicio
    Then ve importes en centavos, conteos distintos, impuestos, descuentos y cortesías calculados por Python desde snapshots
    And cada indicador separa el monto conocido del número de operaciones sin dato canónico
    And cada indicador permite drill-down con los mismos filtros a operaciones dentro de su alcance

  @PRD-FR-708 @PRD-FR-718
  @BDD-SC-307
  Scenario: Pago y cierre compiten por el mismo turno operativo
    Given un pedido pendiente y un turno OPEN en la caja donde se intenta cobrar
    When pago y cierre operativo se ejecutan concurrentemente
    Then si el pago gana queda confirmado, asociado al turno de cobro e incluido en el resumen congelado
    But si el cierre gana el pago falla cash_shift_not_open sin pago, eventos ni cierre del pedido
    And ningún resultado exitoso cambia después del cierre

  @PRD-FR-718
  @BDD-SC-308
  Scenario: El monitor no inventa historia financiera o de familia
    Given operaciones legacy con familia completada desde catálogo y un impuesto sin fuente canónica
    When un Administrador consulta el monitor y abre el drill-down
    Then la familia indica legacy_catalog_backfill y el impuesto reporta la operación como desconocida
    And no se consulta la familia viva ni se calcula IVA o cortesía por diferencia

  @PRD-FR-718
  @BDD-SC-309
  Scenario: El monitor fija zona, periodo y cursores antes de consultar
    Given un perfil con una sucursal autorizada y zona IANA válida
    When la UI convierte su día local a límites UTC y consulta el monitor o el drill-down
    Then el backend acepta sólo un intervalo con zona, semiabierto y creciente
    And turno y drill-down paginan con límite de 1 a 100 y una tupla estable con timestamp UTC
    And un límite, cursor o fecha ingenua inválida falla sin una página parcial

  @PRD-FR-718
  @BDD-SC-310
  Scenario: La migración no inventa moneda histórica
    Given un pago legacy cuya moneda falta, no tiene tres letras o difiere de la moneda de su pedido
    When se intenta aplicar la revisión 0038
    Then el preflight falla antes de crear snapshots de ventas ambiguos
    And la operación se corrige por un procedimiento auditado, no mediante edición destructiva

  @PRD-FR-718
  @BDD-SC-311
  Scenario: El alias histórico takeaway se proyecta sin reescribir el pedido
    Given un pago CONFIRMED cuyo pedido legado conserva exactamente order_type takeaway
    When se aplica la revisión 0038
    Then el snapshot registra service_type_snapshot takeout y el pedido conserva takeaway
    And las rutas nuevas siguen aceptando sólo dine-in, takeout o delivery
    But cualquier otro tipo legado bloquea el preflight antes de crear snapshots

  @PRD-FR-719 @PRD-NFR-521
  @BDD-SC-286
  Scenario: Corte por usuario calcula contado, esperado y diferencia
    Given un Líder con alcance explícito de cajero, caja, turno y periodo aprobado
    When captura efectivo contado y confirma el corte con idempotency key
    Then el backend calcula esperado, diferencia y tolerancia en centavos
    And crea reporte inmutable con actor, autorizador y operaciones incluidas

  @PRD-FR-719 @PRD-NFR-521
  @BDD-SC-287
  Scenario: Corte duplicado o concurrente no doble contabiliza
    Given dos solicitudes simultáneas para la misma tupla de corte
    When ambas intentan finalizar
    Then sólo una adquiere el lock y finaliza
    And la otra recibe cash_cut_in_progress o cash_cut_already_finalized sin duplicar operaciones

  @PRD-FR-719 @PRD-NFR-520 @PRD-NFR-521
  @BDD-SC-327
  Scenario: El cajero del corte se deriva del turno y no del navegador
    Given un turno cerrado operativamente con un único actor de apertura persistido
    When un Líder crea un corte indicando turno, caja, cajero y periodo
    Then el backend acepta sólo el cajero responsable y el periodo exacto del turno cerrado
    And un cajero, caja, sucursal, organización o periodo afirmado que no coincide falla sin borrador
    But un turno legado sin actor de apertura inequívoco falla cash_cut_cashier_unknown

  @PRD-FR-719 @PRD-NFR-520
  @BDD-SC-328
  Scenario: Sólo Líder o superior dentro de alcance finaliza
    Given un corte COUNTED de una sucursal asignada
    When Cajero o Cajero jefe intenta finalizar, o un Líder cambia a una sucursal ajena
    Then la autorización falla cerrado y genera auditoría de denegación
    And el corte, turno, operaciones y asociaciones permanecen iguales

  @PRD-FR-719 @PRD-NFR-521
  @BDD-SC-329
  Scenario: El navegador no fija efectivo esperado ni diferencia
    Given un corte DRAFT sobre un turno OPERATIVELY_CLOSED
    When el Líder captura contado y finaliza
    Then Python deriva fondo, pagos cash y movimientos confirmados del turno
    And calcula diferencia como contado menos esperado con tolerancia cero
    And rechaza esperado, diferencia, tolerancia, operaciones, actor o estado enviados por cliente

  @PRD-FR-719 @PRD-NFR-521
  @BDD-SC-330
  Scenario: Replay conflicto de versión y fallo interno son atómicos
    Given un corte DRAFT o COUNTED y una Idempotency-Key
    When se repite el mismo comando, se cambia su payload o falla una escritura antes del commit
    Then el replay idéntico devuelve la respuesta almacenada
    And el payload distinto o versión obsoleta falla sin mutación
    And el fallo interno no deja corte, asociación, comando o auditoría parcial

  @PRD-FR-719 @PRD-NFR-520
  @BDD-SC-331
  Scenario: Historial y detalle conservan snapshot y redacción
    Given cortes de dos sucursales y estados distintos
    When un actor autorizado filtra por sucursal, caja, cajero, turno, estado y periodo
    Then recibe cursor estable, snapshot financiero y operaciones sólo dentro de su alcance
    And no recibe Idempotency-Key, hash, evidencia ni motivo libre completo
    And cambiar pagos, movimientos, usuarios o zona después no reescribe un corte finalizado

  @PRD-FR-719 @PRD-NFR-520 @PRD-NFR-521
  @BDD-SC-332
  Scenario: Sólo Dueño decide una reapertura con imagen exacta
    Given un corte FINALIZED
    When un Dueño solicita contado corregido con motivo y evidencia y después aprueba o rechaza
    Then una sola solicitud activa conserva la imagen propuesta y transita de forma idempotente
    And perfiles inferiores, otra organización, cambio de payload o estado terminal fallan sin decidir

  @PRD-FR-719 @PRD-NFR-521
  @BDD-SC-333
  Scenario: Compensar un corte no libera ni reescribe operaciones
    Given una solicitud APPROVED sobre un corte FINALIZED
    When Dueño compensa con la misma imagen aprobada
    Then Python crea un artefacto enlazado con contado y diferencia corregidos y delta exacto
    And no modifica corte, pago, movimiento, turno, cierre ni asociación originales
    And ninguna operación original vuelve a ser elegible para otro corte

  @PRD-FR-719 @PRD-NFR-521 @PRD-NFR-524
  @BDD-SC-334
  Scenario: UTC zona y downgrade fallan cerrado ante historia ambigua
    Given una sucursal con zona IANA y un turno que cruza cambio de fecha local
    When se crea y consulta el corte
    Then el periodo se almacena UTC semiabierto y se presenta en la zona snapshot
    And un timestamp ingenuo o periodo distinto al cierre falla cash_cut_period_invalid
    When existe cualquier historia PCO-006 y se intenta downgrade
    Then la migración se detiene sin borrar corte, comando, asociación, solicitud ni compensación

  @PRD-FR-718
  @BDD-SC-292
  Scenario: Candidatos visuales del video no se convierten en requisitos silenciosos
    Given la pantalla de monitor propuesta
    When no existe decisión para estación, impresora, Excel o nota de consumo
    Then no se publica un contrato ni permiso para esos controles
    And el plan los conserva como pendientes de producto
```

## BDD-FEAT-079 Reportes históricos, offline y transición

```gherkin
@offline
Feature: Derivar reportes y sincronizar sin reemplazar autoridad central

  @PRD-FR-720 @PRD-NFR-521
  @BDD-SC-288
  Scenario: Venta por insumos conserva receta aplicada históricamente
    Given dos pedidos equivalentes aceptados con versiones distintas de receta
    When un Supervisor consulta venta por insumo de ambos periodos
    Then Python agrega Decimal desde los snapshots aplicados
    And editar la receta actual no cambia ningún resultado histórico

  @PRD-FR-716 @PRD-NFR-522
  @BDD-SC-289
  Scenario: Movimiento offline se revalida y no declara éxito final antes de nube
    Given un gateway SQLite sin conexión y un comando de caja con actor e idempotency key
    When lo persiste en outbox y después recupera conectividad
    Then PostgreSQL revalida actor, permiso, alcance, turno e idempotencia en inbox
    And una denegación se muestra como conflicto pendiente sin crear compensación automática

  @PRD-FR-715 @PRD-NFR-524
  @BDD-SC-290
  Scenario: Migración de roles semilla es reversible y conserva especialidades
    Given Administrador corporativo, un perfil Cajero legacy y roles especializados existentes
    When se ejecuta el upgrade propuesto y luego downgrade en bases PostgreSQL y SQLite
    Then bloquea downgrade si existen asignaciones, mappings o grants externos no revertidos
    And sólo tras revertirlas controladamente baja sin borrar datos confirmados
    And conserva asignaciones, permisos efectivos, auditoría y roles especializados
    And no convierte Administrador corporativo en Dueño sin mapeo individual aprobado

  @PRD-FR-715 @PRD-NFR-520 @PRD-NFR-523
  @BDD-SC-291
  Scenario: Acciones R3 y denegaciones son auditables y observables
    Given una acción de efectivo, cancelación, reapertura, merma, receta o corte
    When se autoriza o se deniega
    Then registra actor, alcance, resultado, UTC y correlation id sin secretos
    And emite métrica estructurada del resultado
```

## BDD-FEAT-080 Invariantes de auditoría iteración 2

```gherkin
@cash @security @reports
Feature: Cerrar ambigüedades contables y de autorización

  @PRD-FR-715 @PRD-NFR-520
  @BDD-SC-293
  Scenario: Dueño ejerce permisos corporativos persistidos y no cruza organización
    Given un Dueño de Organización A con admin.manage, catalog.manage y un permiso especializado persistidos
    When administra catálogo corporativo y consulta una capacidad especializada de Organización A
    Then ambas acciones son autorizadas por permisos almacenados en backend
    When reutiliza su token o payload contra Organización B
    Then es rechazado sin que access.organization.all_branches conceda cruce organizacional
    And un Administrador corporativo sin esa concesión no puede asignarse ni asignar Dueño

  @PRD-FR-715 @PRD-NFR-520
  @BDD-SC-298
  Scenario: La concesión de autoridad de organización conserva su invariante
    Given un rol con organization_all_permissions y un Administrador corporativo legacy
    When el Administrador intenta cambiar su scope, borrarlo o reemplazar sus permisos
    Then recibe un error estable auditado y el grant conserva scope organization y autoridad dinámica
    When un actor con la misma autoridad renombra el rol
    Then el nombre cambia sin alterar la autorización persistida
    And un rol organizacional con access.organization.all_branches ordinario no obtiene permisos futuros

  @PRD-FR-715 @PRD-NFR-520 @PRD-NFR-524
  @BDD-SC-299
  Scenario: Bootstrap explícito asigna sólo los dos Dueños iniciales configurados
    Given usuarios preexistentes y activos aniacuestas@gmail.com y mangoex@gmail.com de una organización explícita
    And ambos conservan Administrador corporativo legacy antes y después del bootstrap
    And un actor operacional de esa organización y una procedencia de mantenimiento válida
    When ejecuta bootstrap_initial_owners con exactamente esos dos correos
    Then asigna atómicamente el único rol con organization_all_permissions y audita actor/procedencia
    And no crea cuenta, contraseña, rol, organización ni asignación para un correo diferente
    When se repite el mismo comando
    Then devuelve already_bootstrapped sin agregar asignaciones
    When falta un usuario, hay parcialidad, otra organización o un Dueño externo
    Then falla cerrado sin asignación parcial
    And revierte una escritura ajena pendiente antes de persistir sólo la auditoría de denegación

  @PRD-FR-715 @PRD-NFR-520 @PRD-NFR-524
  @BDD-SC-300
  Scenario: Mapeo explícito preserva especialidades y permite reversión auditable
    Given un Dueño solicita dry-run sin PII para un usuario legacy y un perfil destino válido
    When crea PENDING con snapshot, scope, procedencia e idempotency key y después lo aplica
    Then MAPPED agrega sólo el perfil destino y conserva roles especializados
    When reintenta cada etapa con la misma key
    Then recibe el resultado estable sin otra mutación
    And un replay que llega tras colisión de inserción compara roles, sucursal y procedencia antes de responder
    And si el rol legacy desaparece o cambia de sucursal antes de aplicar, falla auditado sin asignar destino
    When revierte el mapping
    Then restaura el snapshot, marca REVERSED y conserva toda la historia/auditoría
    And si el destino fue retirado y reasignado en otra sucursal, falla auditado sin borrarlo ni marcar REVERSED
    And un actor existente de otra organización es denegado, revierte escritura ajena pendiente y deja authorization.denied en la organización objetivo
    And una organización inexistente o inactiva falla con profile_transition_organization_invalid sin mapping ni auditoría
    And un nuevo ciclo sólo puede crear otro PENDING después de REVERSED, sin borrar el ciclo previo
    And dos mappings pending o mapped para la misma pareja se rechazan

  @PRD-FR-716 @PRD-NFR-521
  @BDD-SC-294
  Scenario: Compensación de compra cash conserva signo e importe una sola vez
    Given una compra cash confirmada crea WITHDRAWAL de 3000 con source_type PURCHASE
    When Dueño compensa ese movimiento con motivo válido
    Then crea DEPOSIT de 3000 con compensates_movement_id y amount positivo
    And el esperado cambia de 11000 a 14000 sin contar la compra o compensación dos veces

  @PRD-FR-716 @PRD-NFR-520
  @BDD-SC-302
  Scenario: Permiso, turno y evidencia gobiernan cada movimiento manual
    Given un Cajero y un Cajero jefe con sucursal canónica y caja configurada
    When Cajero registra un retiro durante turno OPEN con concepto efectivo, centavos positivos, referencia y evidencia
    Then se crea un único withdrawal auditado y recibe el efectivo esperado calculado por Python
    When Cajero intenta depositar o cualquiera intenta operar sin turno OPEN, referencia, evidencia o concepto compatible
    Then falla permission_denied, cash_shift_not_open, cash_reference_required, cash_evidence_required o cash_concept_invalid sin movimiento ni comando completado
    When Cajero jefe registra un depósito válido
    Then se crea un único deposit dentro de su sucursal autorizada

  @PRD-FR-716 @PRD-NFR-521
  @BDD-SC-303
  Scenario: Idempotencia de movimiento compara actor y payload completo
    Given un comando manual confirmado con Idempotency-Key
    When el mismo actor repite sucursal, caja, tipo, concepto, centavos, referencia y evidencias
    Then recibe el resultado persistido sin recalcularlo ni insertar otra fila
    When cambia actor, campo, orden canónico de evidencia u objetivo usando la misma clave
    Then falla idempotency_conflict sin escritura parcial

  @PRD-FR-716 @PRD-NFR-520
  @BDD-SC-304
  Scenario: Consulta de ledger respeta alcance y conserva snapshots
    Given movimientos manuales, compras legacy y compensaciones en dos sucursales
    When un actor con cash.movement.read filtra por sucursal, caja, turno, fecha y tipo
    Then recibe sólo filas autorizadas en orden estable con cursor y snapshot histórico disponible
    And no recibe command hash, Idempotency-Key ni evidencias de otra organización

  @PRD-FR-716 @PRD-NFR-521
  @BDD-SC-305
  Scenario: Compra cash y cancelación usan el mismo ledger compatible
    Given una compra cash confirmada durante turno OPEN
    When se confirma y luego se cancela con inventario reversible y el turno todavía OPEN
    Then existe un withdrawal PURCHASE y un deposit compensatorio exacto enlazado
    And ambos participan una vez en el efectivo esperado sin término adicional de compra
    When se reintenta confirmación o cancelación
    Then no aparece otro movimiento
    And las filas legacy withdrawal y cash_reversal conservan su proyección histórica

  @PRD-FR-719 @PRD-NFR-521
  @BDD-SC-295
  Scenario: Cortes parcialmente solapados y dos turnos no comparten operaciones
    Given un cajero con dos turnos y operaciones distintas en cada uno
    And un corte FINALIZED ya incluye una operación del primer turno
    When se intenta finalizar un segundo corte con periodo parcialmente solapado que la incluye
    Then falla cash_cut_already_finalized aunque su period_start y period_end sean distintos
    And un corte del segundo turno sólo puede incluir operaciones de ese turno
    When el primer corte se reabre y se compensa conforme a PCO-006
    Then la operación original conserva su asociación histórica y no puede entrar al segundo corte

  @PRD-FR-716 @PRD-NFR-520 @PRD-NFR-521
  @BDD-SC-306
  Scenario: Dueño compensa desde el ledger POS y la vista converge sin recarga manual
    Given un movimiento manual confirmado durante turno OPEN y una sesión Dueño con cash.movement.compensate
    When el Dueño abre Compensar desde esa fila, captura motivo y evidencia y confirma
    Then el navegador no envía importe, tipo, concepto, sucursal, turno ni actor
    And el backend crea una sola fila opuesta exacta enlazada y devuelve current_summary autoritativo
    And el POS vuelve a consultar el ledger y muestra original como compensated y nueva fila como compensation
    And el efectivo esperado visible vuelve al valor anterior al movimiento sin recarga manual
    And los tipos y estados visibles usan etiquetas cerradas en español de México sin exponer enums internos
    When un actor sin cash.movement.compensate consulta el mismo ledger
    Then ve los estados y vínculos permitidos pero no la acción Compensar
    When la red falla antes de confirmar la respuesta
    Then no muestra éxito y reintenta la misma intención con la misma Idempotency-Key
    When cancela esa intención y abre Compensar en otra fila elegible
    Then descarta clave, motivo y evidencia de la fila anterior y la nueva intención comienza vacía
    And durante un envío no permite cancelar ni cambiar de fila

  @PRD-FR-716
  @BDD-SC-296
  Scenario: Operador sólo puede seleccionar conceptos efectivos publicados
    Given un Cajero abre depósito o retiro con turno autorizado
    When consulta conceptos efectivos para tipo y fecha
    Then sólo recibe conceptos vigentes compatibles desde backend
    When envía texto libre, código inventado o concepto archivado
    Then el comando falla cash_concept_invalid sin crear movimiento

  @PRD-FR-716
  @BDD-SC-301
  Scenario: Dueño versiona y archiva conceptos sin borrar historia
    Given un Dueño con cash.concept.manage y un concepto retiro publicado en versión uno
    And su navegador opera en America/Mazatlan a las 16:30 locales
    When abre el formulario para crear o versionar un concepto
    Then Vigente desde muestra 16:30 locales y no la hora UTC reinterpretada como local
    And al publicar el comando envía el instante ISO UTC equivalente una sola vez
    When publica una versión dos con vigencia futura usando Idempotency-Key
    Then la fecha anterior sigue resolviendo versión uno y la fecha vigente resuelve versión dos
    And el replay idéntico devuelve el mismo resultado sin agregar otra versión
    When reutiliza la clave con payload diferente o intenta cambiar el código
    Then falla idempotency_conflict o cash_concept_code_immutable sin escritura parcial
    When archiva el concepto
    Then desaparece de la lectura efectiva pero identidad y ambas versiones siguen en historia

  @PRD-FR-720 @PRD-NFR-521
  @BDD-SC-297
  Scenario: Reportes no mezclan unidades ni doble cuentan gasto enlazado
    Given una venta con snapshots convertibles y otra sin conversión histórica válida
    And una compra con retiro cash enlazado por source_id
    When se consulta venta por insumo y gastos
    Then agrega sólo cantidades de unidad base compatibles y marca o rechaza la línea incompleta
    And presenta una sola fila de gasto para compra y retiro enlazados

  @PRD-FR-720 @PRD-NFR-520 @PRD-NFR-521
  @BDD-SC-335
  Scenario: Supervisor versiona receta sólo para su sucursal
    Given un Supervisor asignado a la sucursal A con recipes.manage
    And existe una receta corporativa activa para el producto
    When crea con Idempotency-Key una versión para la sucursal A y la receta activa esperada
    Then Python valida Decimal, unidad y componentes y crea una nueva versión de sucursal
    And la receta corporativa y la receta efectiva de la sucursal B permanecen intactas
    When intenta usar la sucursal B o alcance corporativo
    Then falla permission_denied o recipe_corporate_scope_denied sin retirar receta alguna

  @PRD-FR-720 @PRD-NFR-520 @PRD-NFR-521
  @BDD-SC-336
  Scenario: Dueño administra receta corporativa sin confiar en nombre o correo
    Given un actor con la concesión persistida organization_all_permissions
    When crea una versión corporativa con alcance nulo y versión esperada
    Then la versión queda disponible como fallback de las sucursales sin excepción local
    And una excepción local existente conserva prioridad sólo en su sucursal
    When otro actor afirma ser Dueño por payload, correo, is_superadmin o permiso ordinario
    Then el backend lo deniega sin mutación

  @PRD-FR-720 @PRD-NFR-502 @PRD-NFR-521
  @BDD-SC-337
  Scenario: Versión de receta es idempotente y rechaza editor obsoleto
    Given dos editores cargaron la misma receta activa
    When ambos publican versiones distintas o reutilizan una misma Idempotency-Key
    Then un solo comando compatible confirma y el otro falla recipe_version_conflict o idempotency_conflict
    And no existen dos recetas activas para el mismo producto y alcance
    And ventas ya confirmadas conservan sus snapshots y resultado histórico
    And un publicador manual no modifica ninguna versión ni command ya existentes
    And exige recipes.manage y autoridad organizacional persistida al actor activo
    And falla cerrado antes de escribir si el baseline activo o la historia esperada difieren
    And reporta como pendientes 11057, 24001..24007 y los insumos 001026..001028
    And no crea para ellos producto, precio, insumo, receta ni categoría de menú
    And falla cerrado si alguno de esos SKU pendientes ya existe en el catálogo

  @PRD-FR-720 @PRD-NFR-521
  @BDD-SC-338
  Scenario: Venta por insumos usa sólo snapshots de ventas confirmadas
    Given ventas confirmadas con líneas y recetas versión uno y dos en el mismo periodo
    And existe otra orden sin pago confirmado
    When un Supervisor consulta venta por insumos de su sucursal
    Then Python agrega cantidades Decimal por item_id y unit_id desde cada snapshot aplicado
    And expone receta, versión y operaciones conocidas sin consultar la receta vigente
    And la orden sin venta confirmada no participa

  @PRD-FR-720 @PRD-NFR-521
  @BDD-SC-339
  Scenario: Correcciones se atribuyen como delta sin mover la venta original
    Given una venta confirmada y una corrección aplicada en otro día operativo
    When la corrección reduce una línea histórica y agrega otra con receta nueva
    Then el periodo original conserva la venta confirmada original
    And el periodo de aplicación contiene el delta negativo escalado del snapshot original y la adición nueva
    And waste o recovery no cambia por sí mismo la cantidad vendida
    When se consulta el intervalo combinado
    Then el total por insumo reconcilia la imagen corregida sin reescribir historia

  @PRD-FR-720 @PRD-NFR-521
  @BDD-SC-340
  Scenario: Reporte de gastos conserva una fuente canónica y reversas
    Given una compra cash confirmada con subtotal, descuento, impuesto y retiro enlazado
    And un retiro manual confirmado con una compensación posterior
    When un Administrador consulta ambos días operativos
    Then la compra y su retiro producen una sola fuente purchase con impuestos separados
    And la cancelación o compensación aparece como evento inverso en su fecha sin borrar el original
    And depósitos ordinarios, movimientos de inventario y ajustes de pedido no se clasifican como gasto
    And un retiro sin impuesto canónico marca impuesto desconocido sin inferir IVA

  @PRD-FR-720 @PRD-NFR-520
  @BDD-SC-341
  Scenario: Periodo alcance y cursor de reportes fallan cerrados
    Given reportes en dos sucursales y actores Supervisor, Administrador y Dueño
    When Supervisor o Administrador consulta una sucursal asignada con periodo UTC y cursor ligado a filtros
    Then recibe sólo esa sucursal y paginación estable
    When omite sucursal, cambia filtros bajo el cursor o envía periodo ingenuo o límite inválido
    Then falla branch_scope_denied, report_cursor_invalid o report_period_invalid
    When Dueño omite sucursal
    Then recibe el consolidado de su organización y nunca datos de otra organización

  @PRD-FR-720 @PRD-NFR-516 @PRD-NFR-518 @PRD-NFR-523
  @BDD-SC-342
  Scenario: UI presenta reportes autoritativos y receta sin fórmulas cliente
    Given una sesión con capacidades de receta, insumos o gastos
    When abre la superficie correspondiente en ancho de escritorio o reducido
    Then sólo ve pestañas y acciones autorizadas con estados carga, vacío, datos, incompleto y error en español
    And React convierte una vez el día local y presenta cantidades e importes recibidos sin recalcularlos
    And la API registra resultado y alcance sin componentes, razones libres, filtros completos ni PII

  @PRD-FR-716 @PRD-NFR-502 @PRD-NFR-522
  @BDD-SC-393
  Scenario: Gateway persiste la intención antes de responder pendiente
    Given un grant offline vigente ligado al actor, gateway y sucursal
    When registra un depósito o retiro manual válido sin nube
    Then SQLite confirma sobre, payload canónico y hash en WAL antes de responder PENDING_SYNC
    And replay idéntico conserva command_id e idempotency_key
    And cambiar la intención con la misma identidad falla idempotency_conflict

  @PRD-FR-716 @PRD-NFR-520 @PRD-NFR-522
  @BDD-SC-394
  Scenario: Gateway y grant no aceptan autoridad afirmada por el cliente
    Given credencial gateway activa y grant Ed25519 de máximo dos horas
    When firma, capability, ventana y bindings coinciden
    Then la nube inicia revalidación central
    When falta autoridad, está revocada o se altera un binding
    Then falla cerrado sin movimiento, evento ni checkpoint confirmado

  @PRD-FR-716 @PRD-NFR-502 @PRD-NFR-521 @PRD-NFR-522
  @BDD-SC-395
  Scenario: Reconciliación confirma caja e inbox atómicamente
    Given un comando local todavía autorizado en PostgreSQL
    When la nube lo reconcilia
    Then revalida actor, permiso, alcance, turno OPEN y concepto efectivo
    And confirma juntos movimiento, command log, inbox, evento, auditoría y checkpoint
    And un fallo inyectado deja cero escritura parcial

  @PRD-FR-716 @PRD-NFR-520 @PRD-NFR-522
  @BDD-SC-396
  Scenario: Autoridad obsoleta produce conflicto visible
    Given un comando aceptado durante desconexión
    When actor, permiso, sucursal, turno o concepto dejan de ser válidos
    Then no crea movimiento ni compensación y persiste conflicto redactado
    And el gateway deja de reintentarlo automáticamente

  @PRD-FR-716 @PRD-NFR-502 @PRD-NFR-522
  @BDD-SC-397
  Scenario: Transporte incierto y reinicio conservan una intención
    Given un comando SYNCING cuya respuesta se pierde
    When el gateway reinicia o encuentra timeout DNS conexión o 5xx
    Then restaura PENDING_SYNC con backoff y el mismo key, hash, actor y payload
    And replay central recupera una confirmación previa sin duplicar

  @PRD-NFR-502 @PRD-NFR-522
  @BDD-SC-398
  Scenario: Checkpoint permanece único bajo concurrencia
    Given comandos concurrentes de una sucursal y otra sucursal distinta
    When PostgreSQL los reconcilia en sesiones independientes
    Then asigna checkpoints únicos crecientes por organización y sucursal mediante fila bloqueada

  @PRD-FR-716 @PRD-NFR-516 @PRD-NFR-518 @PRD-NFR-522
  @BDD-SC-399
  Scenario: POS distingue pendiente confirmado conflicto y gateway ausente
    Given movimientos locales en cada estado
    When abre Movimientos de caja
    Then ve un único estado en español y explicación segura
    And React no calcula efectivo definitivo ni ofrece otras acciones offline

  @PRD-NFR-522 @PRD-NFR-523 @PRD-NFR-524
  @BDD-SC-400
  Scenario: Migración y telemetría conservan historia y secretos
    Given sync legacy, outbox local y checkpoints
    When se migra o intenta downgrade con historia PCO-008
    Then upgrade preserva filas y una sola head mientras downgrade falla cerrado
    And logs y respuestas omiten credencial, grant, evidencia y PII
    And el origen POS se normaliza incluso para IPv6 y exige HTTPS fuera de loopback sin wildcard path ni credenciales
    And config y archivos runtime son distintos por ruta e inode sin symlinks ni hardlinks
    And root y archivos sensibles son privados y se revalidan al abrirse
    And el log redactado rota con límite finito sin handlers duplicados
    And shutdown deja readiness falso y libera recursos aunque falle la recuperación del outbox
    And una composición fallida cierra cliente HTTP y logging ya creados
```
