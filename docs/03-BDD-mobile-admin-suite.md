# BDD - Suite Móvil de Administración y Puesta en Marcha Rápida

## BDD-FEAT-109 Suite Móvil de Administración y Puesta en Marcha Rápida

```gherkin
@PRD-FR-738 @mobile_admin @cash_shifts @catalog @branch_settings
Feature: Suite Móvil de Administración y Puesta en Marcha Rápida en admin-web

  @BDD-SC-493
  Scenario: Navegación inferior y alternancia fluida de pestañas en shell móvil de administración
    Given un usuario administrador autenticado accediendo a "admin-web" desde un dispositivo móvil
    When carga el panel principal en "/" o "/orders-mobile"
    Then el sistema presenta la barra de navegación inferior fija con cuatro opciones: "Pedidos", "Caja", "Menú" y "Sucursal"
    And permite alternar entre cada pestaña sin recargar la página ni perder el contexto de la sucursal activa

  @BDD-SC-494
  Scenario: Apertura, consulta y cierre operativo de turno de caja desde dispositivo móvil
    Given un usuario administrador en la pestaña de "Caja" sin turno abierto en la sucursal
    When ingresa un fondo inicial de "$500.00" y pulsa "Abrir Turno de Caja"
    Then el sistema registra la apertura de turno mediante "POST /cash/shifts/open"
    And actualiza la interfaz mostrando el turno activo, fondo inicial y resumen financiero
    And permite registrar movimientos de efectivo y ejecutar el cierre operativo con confirmación

  @BDD-SC-495
  Scenario: Alternancia rápida de disponibilidad y alta ágil de producto con imagen en catálogo móvil
    Given un usuario administrador en la pestaña de "Menú"
    When conmuta el interruptor de disponibilidad de un producto de "Disponible" a "Agotado"
    Then el sistema actualiza inmediatamente el estado del producto mediante "PUT /catalog/products/{id}"
    And al crear o editar un platillo permite asignar precio, categoría, estación e imagen por cámara, galería o preset

  @BDD-SC-496
  Scenario: Consulta y compartición de enlace de menú digital y configuración operativa de sucursal móvil
    Given un usuario administrador en la pestaña de "Sucursal"
    When consulta los enlaces y canales digitales del restaurante
    Then el sistema muestra el enlace al menú digital público con opciones para copiar, abrir y compartir por WhatsApp
    And permite activar o desactivar la recepción de pedidos por WhatsApp y alternar reversiblemente a la vista de escritorio
```
