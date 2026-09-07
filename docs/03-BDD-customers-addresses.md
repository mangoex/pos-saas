# BDD - Clientes, teléfonos y direcciones

## BDD-FEAT-035 Directorio de clientes del POS

```gherkin
@PRD-FR-524 @PRD-FR-531 @PRD-FR-532 @PRD-FR-533 @PRD-FR-534 @customers
Feature: Identificar clientes y conservar su domicilio histórico

  @BDD-SC-069
  Scenario: Registrar cliente con varios teléfonos
    Given el cajero opera una sucursal autorizada
    When registra un cliente con dos teléfonos mexicanos
    Then el cliente conserva un ID interno
    And cada teléfono conserva valor capturado y normalizado
    And una coincidencia de teléfono no fusiona clientes automáticamente

  @BDD-SC-070
  Scenario: Registrar varios domicilios
    Given existe un cliente
    When el cajero registra Casa, Oficina y Escuela
    Then las tres direcciones permanecen activas bajo el mismo cliente
    And una puede marcarse como predeterminada

  @BDD-SC-071
  Scenario: Pedido a domicilio conserva snapshot
    Given un cliente tiene una dirección Casa
    When el cajero crea un pedido a domicilio usando Casa
    Then el pedido referencia al cliente
    And guarda una copia histórica de cliente y dirección
    When Casa se modifica posteriormente
    Then el pedido anterior conserva el snapshot original
    And el POS muestra el nuevo domicilio solamente para pedidos posteriores

  @BDD-SC-072
  Scenario: Rechazar dirección ajena al cliente
    Given existen dos clientes con direcciones distintas
    When el cajero intenta crear un pedido para uno usando la dirección del otro
    Then el sistema rechaza el pedido
    And no crea snapshot ni movimiento operativo parcial

  @BDD-SC-073
  Scenario: Conservar datos fiscales separados
    Given existe un cliente con domicilios de entrega
    When el cajero registra razon social, RFC, regimen y codigo postal fiscal
    Then los datos fiscales quedan en un perfil separado
    And no reemplazan ningun domicilio de entrega

  @BDD-SC-074
  Scenario: Repetir pedido usa reglas vigentes
    Given existe un pedido histórico de un cliente
    When el cajero solicita repetirlo
    Then el sistema crea una orden nueva
    And vuelve a validar disponibilidad, precio y receta vigente de cada producto
    And para domicilio vuelve a resolver la dirección activa
    And no copia silenciosamente el total histórico
```
