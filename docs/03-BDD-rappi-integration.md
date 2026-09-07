# BDD - Hub de Integraciones y Conector Rappi Restaurante

## BDD-FEAT-103 Hub de Integraciones y Configuración de Rappi en Backoffice

```gherkin
@PRD-FR-640 @PRD-FR-732 @integrations @admin @rappi
Feature: Administración centralizada de credenciales y mapeo de Rappi Restaurante

  @BDD-SC-476
  Scenario: Guardar configuración de Rappi como borrador
    Given el administrador corporativo accede al Hub de Integraciones
    When ingresa Client ID "rappi_client_123", Client Secret "rappi_sec_456", Webhook Secret "rappi_whsec_789" y entorno "sandbox"
    Then el sistema almacena la configuración de forma persistente y segura por organización
    And no expone los secretos ni declara una URL registrada con Rappi
    And deja el conector pendiente de validación

  @BDD-SC-477
  Scenario: Asociar Store ID de Rappi a sucursal Kiwi
    Given existe la sucursal Kiwi "Sucursal Principal"
    And existe una configuración pendiente de validación de Rappi
    When el administrador asocia el Store ID "rappi_store_guadalajara_01" a "Sucursal Principal"
    Then el mapeo queda disponible sólo como preparación de la validación posterior

  @BDD-SC-478
  Scenario: Estado de una configuración pendiente de Rappi
    Given existe una configuración de Rappi guardada
    When el administrador consulta el monitor de integraciones para Rappi
    Then visualiza que requiere validación de partner antes de recibir eventos
```

## BDD-FEAT-104 Configuración pendiente de validación de Rappi

```gherkin
@PRD-FR-641 @PRD-FR-647 @PRD-FR-732 @webhooks @security @rappi
Feature: Preparar datos de Rappi sin declarar una integración activa

  @BDD-SC-479
  Scenario: Guardar configuración de Rappi sin conectarla
    Given un administrador autorizado de una organización
    When guarda Client ID, Client Secret, Webhook Secret, ambiente y mapeos de sucursal
    Then los datos quedan asociados únicamente a su organización
    And los secretos no se devuelven al navegador
    And el estado permanece "Pendiente de validación"

  @BDD-SC-480
  Scenario: Mostrar configuración guardada sin exponer secretos
    Given una configuración de Rappi previamente guardada
    When el administrador vuelve al Hub de Integraciones
    Then ve campos de secreto vacíos y un indicador de secreto guardado
    And no ve el estado "Conectado" ni "Confirmado"

  @BDD-SC-481
  Scenario: Guardar un mapeo de sucursal como preparación
    Given una sucursal propia y un identificador externo capturado por el administrador
    When guarda el mapeo de Rappi
    Then el mapeo queda asociado a su organización
    And permanece pendiente de validación de partner
```

## BDD-FEAT-105 Flujo operativo Rappi diferido

```gherkin
@PRD-FR-733 @pos @orders @rappi
Feature: No presentar una simulación como integración certificada

  @BDD-SC-482
  Scenario: Mantener la recepción de pedidos fuera del borrador
    Given un administrador abre la configuración pendiente de Rappi
    When revisa las acciones disponibles
    Then no se presenta como un canal conectado ni como una recepción activa

  @BDD-SC-483
  Scenario: Posponer simulación de partner hasta validar contrato
    Given el administrador está en la pestaña de Rappi en el Hub de Integraciones
    When guarda los datos de configuración
    Then no ejecuta una simulación ni confirma conectividad con Rappi
```
