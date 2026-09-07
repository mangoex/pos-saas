# BDD - Sincronizacion minima nube-gateway

## BDD-FEAT-027 Confirmacion idempotente de comando local

```gherkin
@PRD-FR-680 @PRD-FR-684 @PRD-FR-685 @PRD-FR-686 @PRD-FR-687 @sync @phase1
Feature: Sincronizar comando local con nube

  @BDD-SC-037
  Scenario: Confirmar comando local pendiente una sola vez
    Given existe un comando local pendiente de sincronizacion
    When el gateway envia el comando a la API central
    Then la nube registra el comando recibido
    And asigna un checkpoint de sucursal
    And devuelve un evento de confirmacion
    And conserva auditoria de la sincronizacion

  @BDD-SC-038
  Scenario: Reintentar comando ya confirmado
    Given la nube ya confirmo un comando con la misma clave idempotente
    When el gateway reintenta el envio del mismo comando
    Then la nube devuelve la confirmacion original
    And no crea un segundo checkpoint
    And no duplica el evento confirmado

  @BDD-SC-039
  Scenario: Descargar eventos posteriores al ultimo checkpoint
    Given existen eventos de sincronizacion confirmados
    When el gateway solicita eventos posteriores a su ultimo checkpoint
    Then la nube devuelve solo eventos pendientes
    And mantiene el orden ascendente de checkpoint

  @BDD-SC-040
  Scenario: Consultar estado de sincronizacion de la sucursal
    Given existen comandos confirmados para una sucursal
    When el operador consulta el estado de sincronizacion
    Then el sistema muestra el ultimo checkpoint
    And muestra conteos de comandos y eventos sincronizados
    And conserva la sucursal consultada
```
