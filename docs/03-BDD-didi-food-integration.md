# BDD - Hub de Integraciones y Conector DiDi Food Marketplace

## BDD-FEAT-099 Hub de Integraciones y Configuración de DiDi Food en Backoffice

```gherkin
@PRD-FR-640 @PRD-FR-732 @integrations @admin @didi_food
Feature: Administración centralizada de credenciales y mapeo de DiDi Food

  @BDD-SC-466
  Scenario: Guardar configuración de DiDi Food y generar URL de Webhook
    Given el administrador corporativo accede al Hub de Integraciones
    When ingresa App ID "didi_app_123", App Secret "didi_sec_456", Webhook Secret "didi_whsec_789" y entorno "sandbox"
    Then el sistema almacena la configuración de forma persistente y segura
    And expone la URL oficial de webhook para registro en DiDi Food Open Platform
    And permite activar o pausar el conector globalmente

  @BDD-SC-467
  Scenario: Asociar Shop ID de DiDi Food a sucursal Kiwi
    Given existe la sucursal Kiwi "Sucursal Principal"
    And existe una configuración activa de DiDi Food
    When el administrador asocia el Shop ID "didi_shop_guadalajara_01" a "Sucursal Principal"
    Then los webhooks y órdenes asociadas a ese Shop ID se enrutan exclusivamente a "Sucursal Principal"

  @BDD-SC-468
  Scenario: Consulta de bitácora y monitor de webhooks DiDi Food
    Given se han recibido eventos de webhook de DiDi Food
    When el administrador consulta el monitor de integraciones para DiDi Food
    Then visualiza la lista cronológica con timestamp, tipo de evento, estado de procesamiento y respuesta
```

## BDD-FEAT-100 Ingestión Segura e Idempotente de Órdenes DiDi Food

```gherkin
@PRD-FR-641 @PRD-FR-647 @PRD-FR-732 @webhooks @security @didi_food
Feature: Recepción y normalización de pedidos de DiDi Food

  @BDD-SC-469
  Scenario: Validar firma criptográfica HMAC-SHA256 en webhooks de DiDi Food
    Given un webhook entrante en "/v1/integrations/didi-food/webhook"
    When el encabezado de firma contiene un HMAC válido calculado con el Webhook Secret
    Then el servidor acepta la solicitud y responde con HTTP 200 OK
    And registra el evento en "integration_webhook_logs"

  @BDD-SC-470
  Scenario: Rechazar webhook de DiDi Food sin firma o con firma manipulada
    Given un webhook entrante a DiDi Food con firma incorrecta o ausente
    When el validador de seguridad procesa la firma
    Then rechaza la llamada con HTTP 401 Unauthorized
    And no crea órdenes ni despacha eventos operativos

  @BDD-SC-471
  Scenario: Idempotencia en reintentos de webhooks de DiDi Food
    Given una notificación de orden de DiDi Food con ID "didi_ord_999" ya fue procesada
    When DiDi Food reintenta la misma notificación con el mismo payload
    Then el sistema responde HTTP 200 OK con estado already_processed
    And no duplica el pedido, ni las comandas ni los consumos de inventario
```

## BDD-FEAT-101 Gestión Operativa de Pedidos DiDi Food en POS

```gherkin
@PRD-FR-733 @pos @orders @didi_food
Feature: Visualización y control de pedidos DiDi Food en Punto de Venta

  @BDD-SC-472
  Scenario: Visualizar comandas de DiDi Food en la terminal POS
    Given un cajero está en el POS de "Sucursal Principal"
    And existen pedidos activos de DiDi Food
    When el cajero consulta los pedidos de canales externos
    Then visualiza las tarjetas de los pedidos con su folio DiDi (ej. #D101), comensal y artículos
    And puede cambiar el estado operativo notificando la actualización
```
