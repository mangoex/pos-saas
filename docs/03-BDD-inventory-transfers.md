# BDD - Traspasos entre sucursales

## BDD-FEAT-044 Envío e inventario en tránsito

```gherkin
@PRD-FR-576 @PRD-FR-577 @inventory @transfers
Feature: Enviar inventario entre sucursales

  @BDD-SC-100
  Scenario: Borrador no afecta existencias
    Given origen y destino son sucursales distintas
    When el supervisor captura un traspaso de 10 kg
    Then queda en borrador
    And no crea movimientos en ninguna sucursal

  @BDD-SC-101
  Scenario: Enviar una sola vez
    Given el origen tiene existencia suficiente
    And el traspaso está en borrador
    When el supervisor confirma el envío con idempotency key
    Then se crea TRANSFER_OUT por 10 kg al costo promedio de origen
    And quedan 10 kg y su costo en tránsito
    And un reintento no duplica la salida

  @BDD-SC-102
  Scenario: Rechazar envío sin existencia
    Given una línea supera la existencia física de origen
    When se intenta enviar
    Then se rechaza todo el documento sin efectos parciales

@PRD-FR-578 @PRD-FR-579 @inventory @transfers
Feature: Recibir inventario en destino

  @BDD-SC-103
  Scenario: Recepción completa
    Given un traspaso enviado conserva costo de origen
    When el receptor confirma toda la cantidad en destino
    Then se crea TRANSFER_IN por la cantidad enviada
    And el documento queda recibido
    And el destino actualiza su costo promedio sin registrar una compra

  @BDD-SC-104
  Scenario: Recepción con diferencia
    Given se enviaron 10 kg
    When el receptor confirma 9.5 kg y documenta 0.5 kg dañados
    Then destino recibe únicamente 9.5 kg
    And el documento queda recibido con diferencia
    And conserva cantidad, costo y motivo de la diferencia
    And un reintento no duplica la entrada
```
