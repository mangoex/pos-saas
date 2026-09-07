# BDD - Identificación telefónica de clientes en el POS

## BDD-FEAT-056 Buscar o registrar un cliente por teléfono durante el checkout

```gherkin
@PRD-FR-531 @PRD-FR-695 @PRD-FR-698 @pos @customers
Feature: El checkout identifica al cliente por teléfono y permite registrarlo si no existe

  @BDD-SC-163
  Scenario: Un teléfono incompleto no ejecuta una búsqueda
    Given un cajero en el modal de finalizar venta
    When captura menos de diez dígitos en Teléfono del cliente
    Then el POS explica que debe completar el número
    And no consulta el directorio de clientes

  @BDD-SC-164
  Scenario: Un teléfono exacto muestra cada cliente coincidente con su nombre
    Given dos clientes distintos que comparten un teléfono normalizado
    When el cajero captura el teléfono completo
    Then el POS consulta por phone y la sucursal canónica
    And muestra ambos nombres como opciones separadas
    And muestra cuántos domicilios activos tiene cada cliente

  @BDD-SC-165
  Scenario: Un teléfono inexistente permite registrar al cliente sin perder la venta
    Given un teléfono válido sin coincidencias en la sucursal
    When el cajero captura el nombre y confirma el alta
    Then el POS crea al cliente con el teléfono como primario
    And conserva el carrito, tipo de pedido y total
    And selecciona al cliente creado

  @BDD-SC-166
  Scenario: El modal de entrega muestra y permite agregar domicilios
    Given un cliente seleccionado en el checkout
    When el cajero elige A domicilio dentro del modal
    Then ve todos los domicilios activos con alias y dirección legible
    And puede seleccionar uno existente
    And puede agregar y seleccionar un domicilio nuevo

  @BDD-SC-167
  Scenario: Una clave heredada no se interpreta como teléfono
    Given una importación que sólo declara CLAVE, NOMBRE y DIRECCION
    When el sistema materializa al cliente
    Then conserva la clave como evidencia de origen
    And no crea un customer_phone a partir de CLAVE
```
