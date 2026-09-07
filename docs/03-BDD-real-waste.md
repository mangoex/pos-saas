# BDD - Merma real auditable

## BDD-FEAT-043 Captura y autorización de merma

```gherkin
@PRD-FR-571 @PRD-FR-572 @inventory @waste
Feature: Capturar merma real clasificada

  @BDD-SC-095
  Scenario: Guardar borrador sin descontar inventario
    Given existe un motivo activo Derrame
    When el supervisor captura una merma de 2 litros con etapa y observaciones
    Then el documento queda en borrador
    And no se crea movimiento ni cambia la existencia

  @BDD-SC-096
  Scenario: Rechazar motivo inactivo o cantidad inválida
    Given un motivo de merma está inactivo
    When se intenta usarlo en una captura
    Then el sistema rechaza el documento
    And no modifica inventario

@PRD-FR-573 @PRD-FR-575 @inventory @waste
Feature: Confirmar merma idempotente

  @BDD-SC-097
  Scenario: Confirmar con costo y actor
    Given existe inventario suficiente y costo promedio vigente
    And una merma está en borrador
    When un supervisor autorizado la confirma con idempotency key
    Then se crea una salida WASTE_REAL una sola vez
    And conserva costo unitario, costo total, capturista y autorizador
    And disminuye existencia física y estado de costo

  @BDD-SC-098
  Scenario: Rechazar merma mayor a la existencia
    Given la cantidad de la merma supera la existencia física
    When el supervisor intenta confirmarla
    Then se rechaza sin efectos parciales

@PRD-FR-574 @PRD-FR-575 @inventory @waste
Feature: Corregir mediante compensación

  @BDD-SC-099
  Scenario: Revertir merma confirmada
    Given una merma confirmada tiene un movimiento WASTE_REAL
    When un supervisor la revierte con motivo e idempotency key
    Then se crea WASTE_REVERSAL referenciado al movimiento original
    And se restaura la cantidad sin borrar la salida original
    And un reintento no duplica la reversa
```
