# BDD - Auto-Registro de Clientes en Pedidos y Trazabilidad de Satisfacción

## BDD-FEAT-108 Auto-Registro de Clientes y Trazabilidad de Calificaciones

```gherkin
@PRD-FR-737 @customers @auto_registration @reviews
Feature: Auto-registro de clientes en pedidos y trazabilidad de satisfacción en panel de administración

  @BDD-SC-489
  Scenario: Auto-registro de cliente al aceptar pedido de tienda móvil pública
    Given un pedido público entrante con teléfono "6671234567" y nombre "Carlos Beltrán"
    When el restaurante acepta el pedido mediante "accept_public_order_intent"
    Then el sistema crea un nuevo cliente en "customers" con nombre "Carlos Beltrán" y sucursal de origen
    And registra el teléfono normalizado "+526671234567" en "customer_phones"
    And la orden creada tiene "customer_id" asociado al nuevo cliente

  @BDD-SC-490
  Scenario: Vinculación automática de cliente recurrente en POS
    Given un cliente previamente registrado con teléfono "+526671234567"
    When se realiza una venta en POS enviando teléfono "6671234567" y nombre "Carlos Beltrán"
    Then el sistema vincula la venta al cliente existente sin duplicar registros en "customers"
    And incrementa el conteo de pedidos del cliente

  @BDD-SC-491
  Scenario: Captura incondicional de calificación y comentario privado
    Given un pedido completado por el cliente con folio "ORD-9901"
    When el cliente califica con 3 estrellas y envía el comentario "Faltaron aderezos"
    Then el sistema almacena el feedback en "customer_feedbacks" vinculado a su "customer_id"
    And registra el rating de 3 estrellas y el texto del comentario

  @BDD-SC-493
  Scenario: Vinculación de feedback emitido antes de la aceptación del pedido móvil
    Given una intención de pedido móvil en revisión con referencia "REF-7701" y teléfono "6689998877"
    When el comensal califica inmediatamente con 5 estrellas antes de que el restaurante acepte
    And posteriormente el restaurante acepta el pedido generando el folio operativo
    Then el feedback queda vinculado al nuevo cliente creado
    And el directorio de clientes refleja la calificación de 5 estrellas en su promedio

  @BDD-SC-494
  Scenario: Actualización idempotente y aislada de comentario privado en feedback
    Given un comensal que selecciona 2 estrellas para una referencia persistida y su teléfono coincidente
    When posteriormente envía el comentario privado "El pedido tardó demasiado" con la misma referencia y teléfono
    Then el sistema actualiza la retroalimentación existente sin generar registros duplicados
    And el cliente conserva una sola calificación de 2 estrellas con su comentario asociado
    But una solicitud con `customer_id`, referencia ajena, sucursal distinta o teléfono no coincidente se rechaza sin crear ni modificar feedback
    And los resúmenes administrativos excluyen feedback de otra organización aunque exista una asociación histórica inválida

  @BDD-SC-492
  Scenario: Consulta de promedio de satisfacción en directorio administrativo
    Given un cliente con dos calificaciones registradas de 5 y 3 estrellas
    When el administrador consulta el directorio de clientes en "/customers"
    Then el cliente incluye un promedio de 4.0 estrellas y conteo de 2 calificaciones
    And en la interfaz web se muestra la insignia de calificación y el acceso a su historial de comentarios
```
