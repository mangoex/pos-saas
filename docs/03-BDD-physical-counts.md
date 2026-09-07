# BDD - Conteo físico y conciliación

## BDD-FEAT-045 Fotografía y captura ciega

```gherkin
@PRD-FR-568 @inventory @counts
Feature: Capturar inventario físico

  @BDD-SC-105
  Scenario: Abrir una fotografía sin mover inventario
    Given una sucursal tiene artículos inventariables activos
    When el supervisor abre una sesión de conteo
    Then congela cantidad teórica, costo y valor por artículo
    And queda en estado counting
    And no genera movimientos

  @BDD-SC-106
  Scenario: Captura ciega
    Given una sesión está en counting
    When el supervisor consulta y captura cantidades físicas
    Then la interfaz no muestra existencia teórica ni diferencia
    And cada captura conserva usuario y fecha

  @BDD-SC-107
  Scenario: Enviar conteo incompleto
    Given falta capturar al menos una línea
    When se intenta enviar a revisión
    Then el sistema lo rechaza sin calcular ajustes

@PRD-FR-568 @inventory @reconciliation
Feature: Revisar y autorizar diferencias

  @BDD-SC-108
  Scenario: Ajustar contra ledger vigente
    Given la fotografía registró 10 unidades teóricas
    And se contaron 8 unidades físicas
    And después de abrir ocurrió una salida legítima de 1 unidad
    When se aprueba el conteo
    Then el reporte conserva diferencia de fotografía igual a -2
    And genera COUNT_ADJUSTMENT por -1 contra la existencia vigente
    And no sobrescribe la salida intermedia

  @BDD-SC-109
  Scenario: Aprobar y cerrar idempotentemente
    Given un conteo enviado contiene diferencias positivas y negativas
    When el supervisor lo aprueba con idempotency key
    Then crea un movimiento por cada ajuste no cero una sola vez
    And conserva costo, actor y documento de origen
    When cierra la sesión
    Then el reporte queda inmutable y separado de mermas
```
