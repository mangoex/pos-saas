# BDD - Hub de Integraciones y Conector Uber Eats Marketplace

## BDD-FEAT-096 Hub de Integraciones y Configuración en Backoffice

```gherkin
@PRD-FR-640 @PRD-FR-732 @integrations @admin
Feature: Administración centralizada de credenciales y mapeo de Uber Eats

  @BDD-SC-459
  Scenario: Guardar configuración de Uber Eats y generar URL de Webhook
    Given el administrador corporativo accede al Hub de Integraciones
    When ingresa Client ID "client_123", Client Secret "sec_456", Webhook Secret "whsec_789" y entorno "sandbox"
    Then el sistema almacena la configuración de forma persistente y segura
    And expone la URL oficial de webhook para registro en Uber Developer Dashboard
    And permite activar o pausar el conector globalmente

  @BDD-SC-460
  Scenario: Asociar Store UUID de Uber a sucursal Kiwi
    Given existe la sucursal Kiwi "Sucursal Principal"
    And existe una configuración activa de Uber Eats
    When el administrador asocia el Store UUID "d0e94168-bf1b-49cb-a49b-02df1ff9b68e" a "Sucursal Principal"
    Then los webhooks y órdenes asociadas a ese Store UUID se enrutan exclusivamente a "Sucursal Principal"

  @BDD-SC-461
  Scenario: Consulta de bitácora y monitor de webhooks
    Given se han recibido eventos de webhook de Uber Eats
    When el administrador consulta el monitor de integraciones
    Then visualiza la lista cronológica con timestamp, tipo de evento, estado de procesamiento y respuesta
```

## BDD-FEAT-097 Ingestión Segura e Idempotente de Órdenes Uber Eats

```gherkin
@PRD-FR-641 @PRD-FR-647 @PRD-FR-732 @webhooks @security
Feature: Recepción y normalización de pedidos de Uber Eats

  @BDD-SC-462
  Scenario: Validar firma criptográfica HMAC-SHA256
    Given un webhook entrante en "/v1/integrations/uber-eats/webhook"
    When el encabezado "X-Uber-Signature" contiene un HMAC válido calculado con el Webhook Secret
    Then el servidor acepta la solicitud y responde con HTTP 200 OK
    And registra el evento en "integration_webhook_logs"

  @BDD-SC-463
  Scenario: Rechazar webhook sin firma o con firma manipulada
    Given un webhook entrante con firma "X-Uber-Signature" incorrecta
    When el validador de seguridad procesa la firma
    Then rechaza la llamada con HTTP 401 Unauthorized
    And no crea órdenes ni despacha eventos operativos

  @BDD-SC-464
  Scenario: Idempotencia en reintentos de webhooks
    Given una notificación de orden de Uber Eats con ID "uber_ord_999" ya fue procesada
    When Uber Eats reintenta la misma notificación con el mismo payload
    Then el sistema responde HTTP 200 OK
    And no duplica el pedido, ni las comandas ni los consumos de inventario
```

## BDD-FEAT-098 Gestión Operativa de Pedidos Uber Eats en POS

```gherkin
@PRD-FR-733 @pos @orders @uber_eats
Feature: Visualización y control de pedidos Uber Eats en Punto de Venta

  @BDD-SC-465
  Scenario: Visualizar comandas de Uber Eats en la vista dedicada de POS
    Given un cajero está en el POS de "Sucursal Principal"
    And existen 2 pedidos de Uber Eats (1 en preparación y 1 listo para repartidor)
    When el cajero hace clic en "Uber Eats" en el menú lateral debajo de "Pedidos"
    Then visualiza las tarjetas de los pedidos con su folio Uber (ej. #U101), comensal y artículos
    And puede cambiar el estado a "Listo para entrega" notificando a la API de Uber
```
