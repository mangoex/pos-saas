# BDD - Pago, corte e impresion simulada

## BDD-FEAT-024 Pago basico

```gherkin
@PRD-FR-525 @PRD-FR-553 @PRD-FR-554 @payments @phase1
Feature: Cobro basico de pedido local

  @BDD-SC-032
  Scenario: Cobrar en efectivo un pedido aceptado
    Given existe un turno de caja abierto
    And existe un pedido aceptado con total calculado
    When el cajero registra un pago en efectivo por el total exacto
    Then el sistema confirma el pago
    And conserva el estado operativo del pedido
    And registra el evento de pago sin simular entrega o cierre
    And conserva el pago como registro inmutable

  @BDD-SC-033
  Scenario: Rechazar pago por importe distinto al total
    Given existe un pedido aceptado con total calculado
    When el cajero registra un pago por un importe diferente al total
    Then el sistema rechaza el pago
    And conserva el pedido sin transición operativa

  @BDD-SC-230
  Scenario Outline: Elegir la forma de pago antes de confirmar el cobro
    Given existe un pedido aceptado con total calculado
    When el cajero abre Pagar
    Then debe elegir una forma de pago antes de confirmar
    When elige <forma> y confirma el total exacto
    Then el pago se conserva con el método <registro>

    Examples:
      | forma         | registro    |
      | efectivo      | cash        |
      | débito        | debit_card  |
      | crédito       | credit_card |
      | transferencia | transfer    |

  @BDD-SC-403
  Scenario: Reintentar un cobro sin duplicar efectos financieros
    Given el POS conserva la intención y la clave idempotente del cobro
    When la misma confirmación se envía dos veces o se reintenta tras respuesta incierta
    Then ambas respuestas identifican el mismo pago confirmado
    And existe un solo snapshot, evento, par de trabajos de impresión y auditoría de confirmación
    When la clave se reutiliza con otro pedido, actor, caja, método o importe
    Then el sistema rechaza payment_idempotency_conflict sin escritura adicional
```

## BDD-FEAT-025 Corte de caja

```gherkin
@PRD-FR-550 @PRD-FR-556 @PRD-FR-557 @cash @phase1
Feature: Corte final de caja

  @BDD-SC-034
  Scenario: Cerrar caja con resumen de ventas y efectivo
    Given existe un turno de caja abierto
    And existen pedidos cobrados en efectivo durante el turno
    When el cajero registra el efectivo contado y cierra caja
    Then el sistema calcula ventas del turno
    And calcula efectivo esperado
    And calcula diferencia contra efectivo contado
    And crea un corte final
    And registra auditoria del corte
```

## BDD-FEAT-026 Impresion simulada

```gherkin
@PRD-FR-546 @PRD-FR-547 @PRD-FR-548 @printing @phase1
Feature: Cola de impresion simulada

  @BDD-SC-035
  Scenario: Generar ticket y comanda al cobrar pedido
    Given existe un pedido cobrado
    When el sistema confirma el pago
    Then crea trabajos de impresion simulados para ticket y comanda
    And conserva payload, destino y estado de cada trabajo

  @BDD-SC-036
  Scenario: Reintentar impresion simulada
    Given existe un trabajo de impresion pendiente
    When el operador solicita reintento manual
    Then el sistema incrementa los intentos
    And marca el trabajo como impreso en la simulacion
    And registra auditoria del reintento
```
