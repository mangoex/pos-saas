# BDD — remediación previa a piloto

**Estado:** diseño R3 aprobado el 2026-08-19 para implementación/pruebas aisladas por Terra y
auditoría posterior de Sol.
**Paquetes:** `SEC-001`, `OPS-WAVE-001R`, `MOB-ORD-001` y publicación `PCO-008P`.

## BDD-FEAT-081 Frontera operacional y repositorio seguros

@PRD-FR-721 @PRD-FR-722 @PRD-NFR-506 @PRD-NFR-526 @security @printing
Feature: Denegar operación sin autoridad y excluir artefactos sensibles

  @BDD-SC-355
  Scenario Outline: Ruta operacional anónima falla cerrada
    Given no existe identidad humana ni credencial de dispositivo válida
    When se invoca <operacion>
    Then la API responde denegación estable
    And no siembra datos, cambia tareas, acepta comandos ni altera trabajos de impresión
    And registra sólo metadatos técnicos redactados
    And no existe un shell HTML legacy capaz de invocar esas rutas fuera de las SPAs autenticadas

    Examples:
      | operacion                         |
      | sembrar menú                      |
      | sembrar sucursales                |
      | transicionar una tarea KDS        |
      | sincronizar un comando            |
      | listar trabajos de impresión      |
      | reintentar un trabajo de impresión|

  @BDD-SC-356
  Scenario: Semilla interna es explícita, idempotente y no pública
    Given un operador autorizado selecciona una organización y entorno no productivo
    And el manifest versionado declara organización, topología de sucursales y catálogo/menu
    When ejecuta el comando interno en dry-run y después lo confirma
    Then valida IDs, referencias, orden, centavos y cantidades Decimal antes de escribir
    And crea razón social, unidad, sucursales, almacenes, categorías, unidades, insumos, productos,
      precios, disponibilidad y recetas del conjunto explícito una sola vez
    And el replay devuelve el mismo resultado sin duplicados
    And dry-run no crea tablas, filas ni auditoría y exige una base previamente migrada
    And la auditoría organizacional conserva branch_id nulo y el actor explícito
    And un fallo en cualquier handler revierte todo el manifest
    And los scripts legacy se niegan a sembrar directamente, incluidos ventas y mocks aleatorios
    And ninguna ruta HTTP expone esa capacidad

  @BDD-SC-357
  Scenario: Dispositivo sólo opera su capacidad y sucursal
    Given credenciales válidas en dos sucursales y un humano sin `kds.tasks.operate`
    And una credencial sintética con ownership inconsistente o scope inactivo
    And gateways válidos en organizaciones, sucursales o dispositivos distintos
    When KDS B opera, intenta observar A, el humano opera KDS y los gateways reutilizan una clave
    Then el backend responde device_scope_denied
    And el dispositivo sólo observa y modifica la sucursal B derivada de su credencial
    And el humano queda denegado aunque conserve `orders.create`
    And un humano con permisos granulares sólo observa y opera su sucursal explícitamente autorizada
    And `orders.create` no sustituye `sync.events.read`
    And la credencial inconsistente o inactiva queda denegada al emitirse o resolverse
    And no revela si existen recursos en la otra sucursal
    And replay sync queda ligado a organización, sucursal y dispositivo autenticados
    And la descarga entrega todos los eventos remotos pendientes de la organización/sucursal
      persistida, aunque otro gateway de la misma sucursal haya originado el comando
    And un envelope ausente, malformado o ajeno falla sin escritura ni error 500
    And la denegación queda auditada sin material de credencial

  @BDD-SC-358
  Scenario: CI bloquea bases, respaldos y secretos sin exponerlos
    Given un cambio agrega una base local, backup o firma sensible fuera de la allowlist sintética
    When se ejecuta el gate de política del repositorio
    Then el gate falla e identifica sólo archivo y clase de hallazgo
    And no imprime valores, hashes, sales, correos ni filas operativas
    And un fixture sintético permitido continúa verificándose por contenido y procedencia
    And detecta PEM u OpenSSH, credenciales en tests, sidecars SQLite y dumps o exportes SQL

  @PRD-FR-715 @PRD-NFR-524
  @BDD-SC-454
  Scenario: Revisión posterior contiene la semilla destructiva 0049 sin inventar roles
    Given 0049 ya forma parte de la historia y no guardó las asignaciones que eliminó
    When 0058 encuentra la huella limpia exacta o el estado SUC06 aprobado de La Primavera
    And existe una única asignación Cajero para esa sucursal e identidades canónicas exactas
    And la huella limpia conserva "Almacén La Primavera" y sólo SUC06 admite además "Almacen La Primavera"
    Then conserva exactamente esa asignación y registra su snapshot en auditoría
    And distingue la huella limpia del estado canónico aprobado en la decisión auditada
    And no crea, elimina, sustituye ni amplía ningún rol o alcance
    When la sucursal sólo coincide parcialmente, el código no fue aprobado, el almacén usa otra grafía, la identidad difiere o hay otra asignación
    Then el upgrade se detiene en 0057 antes de escribir auditoría o cambiar autoridad
    And exige reconciliación humana contra respaldo o evidencia anterior mediante compensación separada
    And no permite downgrade, stamp, fallback al primer rol ni reconstrucción automática

  @BDD-SC-359
  Scenario: Reintentar impresión no equivale a imprimir
    Given un trabajo FAILED con historial de intentos
    When un actor autorizado solicita reintento con la misma clave idempotente
    Then queda un único intento QUEUED enlazado al trabajo
    And dos retries concurrentes no crean dos intentos activos ni pierden el contador
    And un trabajo nuevo ya contiene su intento inicial QUEUED y es visible al pull scoped
    And el trabajo no queda PRINTED hasta el acuse válido del agente
    And replay idéntico devuelve el mismo intento sin duplicarlo

  @BDD-SC-360
  Scenario: Acuse inválido no completa trabajo
    Given un intento CLAIMED por un agente autorizado
    When otro dispositivo, otra sucursal o un payload alterado informa éxito
    Then el backend responde print_ack_required o device_scope_denied
    And conserva el trabajo sin completar y sin escritura parcial

    And una credencial print.agent vigente sólo hace pull de intentos QUEUED de su sucursal
    And tras claim puede informar un código técnico permitido, dejando FAILED y habilitando el siguiente retry
    And un claim cuyo lease vence sólo se recupera mediante reconciliación scoped a FAILED
    And la recuperación nunca crea un segundo intento ni declara salida física

  @BDD-SC-380
  Scenario: Cotización, producción, pago y fulfillment conservan autoridades separadas
    Given un carrito autenticado con modificadores y extras y un pedido aceptado
    When el POS solicita cotización, confirma pago, KDS completa producción y operación entrega
    Then Python calcula la misma cotización que persistirá la creación
    And confirmar pago no altera el estado operativo del pedido
    And KDS conduce el pedido hasta READY mediante transiciones con compare-and-swap
    And sólo comandos fulfillment idempotentes, scoped y auditados pueden entregar y cerrar

## BDD-FEAT-082 Reparación de operaciones POS existentes

@PRD-FR-705 @PRD-FR-706 @PRD-FR-707 @PRD-FR-722 @PRD-NFR-519 @PRD-NFR-527
Feature: Sustituir simulaciones por operaciones backend autoritativas

  @BDD-SC-361
  Scenario: Cortesía se autoriza y persiste en backend
    Given un pedido no pagado y un Supervisor elegible de la misma sucursal
    When el Cajero solicita una cortesía con justificación y el Supervisor se reautentica
    Then el backend emite y consume una autorización de un solo uso
    And Python conserva subtotal, calcula el ajuste append-only y devuelve total cobrable
    And el POS muestra exactamente ese DTO y el pago exige el total resultante

  @BDD-SC-362
  Scenario: PIN simulado, token reutilizado o API fallida no cambian el total
    Given una cadena local de cuatro caracteres o una autorización inválida
    When el navegador intenta aplicar la cortesía
    Then el backend rechaza sin enumerar credenciales
    And no crea ajuste, evento, auditoría de éxito ni total divergente
    And el POS conserva el pedido y muestra el error sin simular aceptación

  @BDD-SC-363
  Scenario: Supervisor crea proveedor, contacto y términos de sucursal atómicamente
    Given un Supervisor con suppliers.create en su sucursal asignada
    When registra un proveedor único, contacto opcional y términos locales válidos
    Then proveedor corporativo, contacto, términos y auditoría se confirman juntos
    And el proveedor queda disponible para comprar sólo en la sucursal habilitada
    And un fallo o duplicado deja cero filas parciales

  @BDD-SC-364
  Scenario: Permisos específicos no se sustituyen por catalog.manage
    Given un Supervisor sin catalog.manage pero con suppliers.create y purchase_presentations.create
    When crea un proveedor y una presentación dentro de su alcance
    Then ambas operaciones son aceptadas
    And un Cajero o un Supervisor de otra sucursal recibe permission_denied o branch_scope_denied
    And ocultar o mostrar el botón no modifica la decisión backend

  @BDD-SC-365
  Scenario: Compra multi-línea usa cantidades y totales exactos de Python
    Given un Supervisor, un turno abierto y dos presentaciones válidas
    When confirma una compra cash con cantidades, descuentos e impuestos decimales
    Then Python calcula subtotal, descuento, impuesto, total, cantidad base y costo promedio exactos
    And crea una recepción por línea, un retiro enlazado y un documento una sola vez
    And el navegador no puede imponer totales ni conversiones

  @BDD-SC-366
  Scenario: Cancelar compra compensa todo sin borrar historia
    Given una compra confirmada con dos recepciones y un retiro cash
    When un actor autorizado la cancela idempotentemente
    Then crea una reversa por recepción y el movimiento compensatorio enlazado
    And documento, recepciones y retiro originales permanecen inmutables
    And una falla inyectada revierte la cancelación completa

  @BDD-SC-367
  Scenario: Reimpresión desde historial encola un trabajo real
    Given un pedido imprimible y un actor autorizado de la sucursal
    When pulsa Reimprimir dos veces durante un resultado incierto con la misma clave
    Then existe un único intento de impresión persistido y auditable
    And la UI informa Encolado con su referencia, no Impreso
    And una falla de API conserva la acción disponible y no muestra éxito

## BDD-FEAT-083 Pedidos web públicos gobernados

@PRD-FR-723 @PRD-FR-724 @PRD-NFR-527 @PRD-NFR-528 @public-orders @mobile-web
Feature: Capturar y aceptar un pedido público sin inventar autoridad

  @BDD-SC-368
  Scenario: Clave pública resuelve sucursal sin aceptar UUID interno
    Given una clave pública activa configurada para una sucursal
    When un cliente consulta catálogo y envía una intención válida
    Then el backend deriva organización y sucursal desde la clave
    And rechaza branch_id, precio, total, estado, turno o actor enviados por el cliente
    And la respuesta no expone UUID internos

  @BDD-SC-369
  Scenario: Éxito se muestra sólo después de persistir la intención
    Given productos públicos vigentes y una escritura dentro de límites
    When el backend confirma transaccionalmente la intención
    Then devuelve referencia pública, versión, total calculado y PENDING_REVIEW
    And el móvil limpia el carrito sólo después de recibir esa respuesta
    And no presenta un folio operativo antes de aceptar la intención

  @BDD-SC-370
  Scenario: Replay idéntico no duplica intención y payload distinto entra en conflicto
    Given una intención persistida con una Idempotency-Key
    When se repite el mismo payload
    Then devuelve la misma referencia y resultado
    When la misma clave se usa con otra cantidad, producto o dato de entrega
    Then responde idempotency_conflict sin crear otra intención

  @BDD-SC-371
  Scenario: Timeout o rechazo conserva carrito y clave
    Given el cliente envía una intención y no obtiene resultado autoritativo
    When ocurre timeout, error de red o rechazo de API
    Then el móvil no fabrica folio ni éxito y conserva el carrito
    And reutiliza la misma clave para consultar o reintentar
    And sólo limpia al recuperar un resultado persistido compatible

  @BDD-SC-372
  Scenario Outline: Entrada pública inválida falla sin estado parcial
    Given una intención con <problema>
    When se valida en la frontera y el dominio
    Then se rechaza con código estable y cero intención parcial
    And logs y métricas no contienen PII ni el payload completo

    Examples:
      | problema                                  |
      | producto inexistente o no disponible      |
      | cantidad cero, negativa o sobre el límite |
      | campo extra o payload sobredimensionado   |
      | límite de frecuencia agotado              |
      | control de frecuencia no verificable      |

  @BDD-SC-373
  Scenario: Captura pública nunca crea ni selecciona turno y la ruta heredada permanece cerrada
    Given no existe turno de caja abierto en la sucursal
    When se persiste una intención pública válida
    Then la intención queda PENDING_REVIEW sin cash_shift_id ni pago
    And no se abre, reutiliza ni asigna turno a ningún usuario
    When se intenta escribir directamente en la ruta pública heredada con el flag apagado o encendido
    Then responde public_order_unavailable
    And no crea pedido, turno, pago, producción ni movimiento de inventario

  @BDD-SC-374
  Scenario: Aceptación autenticada reutiliza el dominio canónico
    Given una intención PENDING_REVIEW y un actor con orders.create en la sucursal
    When la acepta con versión e Idempotency-Key válidas
    Then se crea exactamente un pedido con snapshots, reservas, tareas, eventos y outbox canónicos
    And la intención queda ACCEPTED enlazada al pedido
    And replay idéntico devuelve el mismo pedido sin duplicar inventario ni producción

  @BDD-SC-375
  Scenario: Actor ajeno o intención obsoleta no crea pedido
    Given una intención ya resuelta, expirada o de otra sucursal
    When un actor intenta aceptarla
    Then responde public_order_transition_invalid o branch_scope_denied
    And no crea pedido, reserva, tarea, evento ni turno

  @PRD-NFR-506
  @BDD-SC-452
  Scenario: Cada SPA queda contenida en su raíz estática canónica
    Given una ruta estática con segmentos ascendentes codificados o un enlace simbólico externo
    When se solicita bajo Admin, POS, KDS o Mobile
    Then el servidor responde 404 sin leer contenido fuera de la raíz de esa aplicación
    And una ruta interna inexistente conserva únicamente el fallback de su propia SPA

  @BDD-SC-376
  Scenario: WhatsApp es una proyección posterior y configurable
    Given una intención ya persistida y una integración configurada para la sucursal
    When el adaptador de WhatsApp falla
    Then la intención conserva su estado y referencia autoritativos
    And el fallo queda reintentable sin número hardcodeado ni duplicar la intención
    And los datos personales se envían sólo al adaptador aprobado y no a logs

  @BDD-SC-389
  Scenario: Rechazo terminal autenticado no crea efectos operativos
    Given una intención PENDING_REVIEW
    When un actor con orders.create y alcance de sucursal la rechaza con versión, motivo e Idempotency-Key
    Then queda REJECTED de forma terminal y auditable
    And replay idéntico devuelve la misma decisión
    And no crea pedido, pago, reserva, tarea, evento ni outbox
    And la consulta pública no expone el motivo interno

  @BDD-SC-390
  Scenario: Expiración automática queda fuera hasta una decisión explícita
    Given una intención PENDING_REVIEW
    When no existe TTL, scheduler ni orden de operación aprobada
    Then no hay transición automática a EXPIRED ni efecto operacional

  @BDD-SC-391
  Scenario: Selecciones públicas son valuadas sólo por el pricer canónico
    Given una línea pública con modificadores, comentarios o extras permitidos por catálogo
    When se captura la intención
    Then Python deriva importes y snapshots sin aceptar precio o total del cliente

  @BDD-SC-392
  Scenario: Límite público combina clave y señal seudonimizada
    Given una escritura con señal de cliente disponible en la conexión directa
    When Redis verifica el presupuesto
    Then usa clave pública y HMAC de la señal sin almacenar ni registrar PII
    And falla cerrada si señal, secreto o Redis no pueden verificarse

## Regla PCO-008P

`PCO-008P` no agrega escenarios de negocio nuevos. La base vigente ya ocupó el rango que el plan
había reservado; por eso el trasplante registra el mapeo no ambiguo `BDD-SC-343..350` del paquete
local a `BDD-SC-393..400` y asigna `BDD-SC-401..403` a replay, checkout y cobro idempotentes.
Debe probar además que `BDD-SC-355..376` y `BDD-SC-380` permanecen verdes.
