# BDD - Proveedores y presentaciones de compra

## BDD-FEAT-036 Proveedores centrales y conversiones por presentación

```gherkin
@PRD-FR-591 @PRD-FR-592 @suppliers
Feature: Administrar proveedores y contactos operativos

  @BDD-SC-075
  Scenario: Registrar proveedor con contactos distintos
    Given el administrador opera el catálogo central
    When registra un proveedor y contactos para pedidos, facturación y cobranza
    Then conserva cada contacto por separado
    And puede marcar responsables principales por función
    And registra auditoría de las altas

  @BDD-SC-076
  Scenario: Habilitar proveedor en una sucursal
    Given existe un proveedor central
    When el administrador lo habilita para una sucursal con tiempo de entrega particular
    Then otras sucursales no heredan silenciosamente esa condición particular
```

## BDD-FEAT-037 Presentaciones y precio informativo

```gherkin
@PRD-FR-561 @PRD-FR-562 @PRD-FR-593 @PRD-FR-594 @purchasing
Feature: Convertir presentaciones de compra a unidad base

  @BDD-SC-077
  Scenario: Registrar bolsa de azúcar de diez kilogramos
    Given azúcar usa kilogramo como unidad base
    When se registra una bolsa con contenido aprovechable de 10 kg y precio neto de 280 pesos
    Then la presentación informa 28 pesos por kilogramo
    And conserva el precio en su historial
    And no genera movimiento ni cambia costo promedio de inventario

  @BDD-SC-078
  Scenario: Rechazar conversión inválida
    Given existe un artículo medido en masa
    When se intenta usar una unidad base incompatible sin equivalencia autorizada
    Then el sistema rechaza la presentación
```
