# BDD - Suite Móvil de Administración y Puesta en Marcha Rápida

## BDD-FEAT-109 Suite Móvil de Administración y Puesta en Marcha Rápida

```gherkin
@PRD-FR-738 @mobile_admin @cash_shifts @catalog @branch_settings
Feature: Suite Móvil de Administración y Puesta en Marcha Rápida en admin-web

  @BDD-SC-497
  Scenario: Navegación inferior y alternancia fluida de pestañas en shell móvil de administración
    Given un usuario administrador autenticado accediendo a "admin-web" desde un dispositivo móvil
    When carga el panel principal en "/" o "/orders-mobile"
    Then el sistema presenta la barra de navegación inferior fija con cuatro opciones: "Pedidos", "Caja", "Menú" y "Sucursal"
    And permite alternar entre cada pestaña sin recargar la página ni perder el contexto de la sucursal activa

  @BDD-SC-498
  Scenario: Apertura, consulta y cierre operativo de turno de caja desde dispositivo móvil
    Given un usuario administrador en la pestaña de "Caja" sin turno abierto en la sucursal
    When ingresa un fondo inicial de "$500.00" y pulsa "Abrir Turno de Caja"
    Then el sistema registra la apertura de turno mediante "POST /cash/shifts/open"
    And actualiza la interfaz mostrando el turno activo, fondo inicial y resumen financiero
    And permite registrar movimientos de efectivo con una referencia de evidencia real y ejecutar el cierre operativo con confirmación
    And un reintento tras resultado incierto conserva la misma "Idempotency-Key" mientras el payload no cambie

  @BDD-SC-499
  Scenario: Alternancia rápida de disponibilidad y alta ágil de producto con imagen en catálogo móvil
    Given un usuario administrador en la pestaña de "Menú"
    When conmuta el interruptor de disponibilidad de un producto de "Disponible" a "Agotado"
    Then el sistema actualiza inmediatamente el estado del producto mediante "PUT /catalog/products/{id}"
    And al crear o editar un platillo permite asignar precio, categoría, estación e imagen por cámara, galería o preset

  @BDD-SC-500
  Scenario: Consulta y compartición de enlace de menú digital y configuración operativa de sucursal móvil
    Given un usuario administrador en la pestaña de "Sucursal"
    When consulta los enlaces y canales digitales del restaurante
    Then el sistema muestra el enlace al menú digital público con opciones para copiar, abrir y compartir por WhatsApp
  @BDD-SC-502
  Scenario: Cobro y entrega integrada de pedidos desde el monitor móvil de comandas
    Given un usuario administrador en el monitor móvil de pedidos con una comanda en estado "Listos"
    And la comanda tiene cobro pendiente con un total positivo
    When selecciona el método de pago ("Efectivo", "Tarjeta" o "Transferencia") y confirma la entrega
    Then el sistema registra el pago mediante "POST /orders/{id}/payments" asociado al turno de caja abierto
    And transiciona la comanda a entregada mediante "POST /orders/{id}/fulfillment/deliver"
    And la venta queda reflejada inmediatamente en los reportes contables y corte de caja
    And si la comanda ya estaba entregada pero con pago pendiente, permite confirmar el cobro directamente sin requerir una terminal POS de escritorio

  @BDD-SC-815
  Scenario: Una intención pública nueva alerta una sola vez desde cualquier pestaña móvil
    Given un administrador autenticado con alcance a la sucursal activa y admin-web abierta
    And el coordinador ya estableció una línea base sin reproducir sonido
    When se persiste una nueva intención pública PENDING_REVIEW en esa sucursal
    Then se muestra una alerta visual y se reproduce una sola alarma si el audio está activo
    And si varias novedades llegan en la misma reconciliación se reproduce una secuencia por lote y el badge conserva la cantidad exacta hasta confirmación humana
    And la detección continúa aunque el administrador navegue por Caja, Menú o Sucursal

  @BDD-SC-816
  Scenario: Identidad estable evita pedidos perdidos o alarmas duplicadas
    Given dos intenciones nuevas comparten created_at o llegan respuestas de consulta fuera de orden
    When el coordinador reconcilia las novedades
    Then identifica cada intención por created_at e id
    And no pierde ninguna ni vuelve a alertar una intención ya observada

  @BDD-SC-817
  Scenario: Cambio de sucursal crea una línea base silenciosa y aislada
    Given el administrador cambia de una sucursal autorizada a otra
    When se carga por primera vez la lista de la nueva sucursal
    Then no suenan pedidos históricos de ninguna de las dos sucursales
    And sólo las novedades posteriores de la sucursal activa pueden alertar

  @BDD-SC-818
  Scenario: El estado de audio refleja la capacidad real del navegador
    Given el navegador suspende o rechaza AudioContext
    When el administrador activa o recupera la alarma
    Then la interfaz no declara Alarma lista hasta confirmar estado running
    And conserva una alerta visual y una acción explícita de reactivación
```
