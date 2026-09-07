# BDD - Asignación de repartidor desde el POS

## BDD-FEAT-071 Repartidor de la sucursal para pedidos a domicilio

```gherkin
@PRD-FR-711 @pos @delivery @drivers
Feature: Cajero asigna un repartidor al pedido a domicilio

  @BDD-SC-243
  Scenario: Cobro conserva el tipo seleccionado previamente
    Given un Cajero que seleccionó A domicilio en la cuenta
    When abre Cobrar pedido
    Then el modal no vuelve a mostrar controles de tipo de pedido
    And conserva cliente y domicilio seleccionados

  @BDD-SC-244
  Scenario: Selector muestra únicamente repartidores disponibles de la sucursal
    Given un pedido a domicilio en la sucursal Centro
    And existen repartidores activos e inactivos en varias sucursales
    When el Cajero selecciona Asignar repartidor
    Then sólo ve repartidores activos de Centro
    And puede seleccionar uno antes de guardar

  @BDD-SC-245
  Scenario: Otro tipo de pedido no presenta asignación
    Given un pedido En sucursal o Para llevar
    When el Cajero abre Cobrar pedido
    Then no aparece Asignar repartidor
    And enviar driver_id para ese pedido es rechazado

  @BDD-SC-246
  Scenario: Crear pedido registra la asignación completa
    Given un pedido a domicilio con cliente, domicilio y repartidor válido
    When el Cajero guarda el pedido
    Then pedido y asignación se crean en una sola transacción
    And la asignación congela repartidor, pedido, cliente, domicilio, total, moneda y cantidades
    And se crean evento de pedido y auditoría de asignación

  @BDD-SC-247
  Scenario: Administrador consulta historial por repartidor
    Given un repartidor con pedidos asignados
    When el Administrador abre su historial
    Then ve folio, cliente, importe, líneas, unidades, estado y fecha de cada pedido
    And desactivar el repartidor no elimina asignaciones anteriores
```
