# BDD - Catálogo administrativo de repartidores

## BDD-FEAT-070 Repartidores propios por sucursal

```gherkin
@PRD-FR-710 @drivers @admin @delivery
Feature: Administrador mantiene el catálogo de repartidores propios

  @BDD-SC-239
  Scenario: Administrador registra un repartidor completo
    Given un Administrador corporativo y una sucursal activa
    When captura nombre, licencia, placas, teléfono, domicilio y persona de contacto
    Then el repartidor queda activo y asignado a la sucursal
    And el listado muestra el nombre de la sucursal
    And la auditoría registra el alta sin copiar teléfono ni domicilio

  @BDD-SC-240
  Scenario: Catálogo rechaza datos incompletos o sucursal inválida
    Given un Administrador corporativo
    When intenta guardar un campo requerido vacío o una sucursal inexistente o inactiva
    Then el comando falla atómicamente
    And no crea ni modifica un repartidor

  @BDD-SC-241
  Scenario: Administrador edita y reasigna un repartidor
    Given un repartidor existente y dos sucursales activas de la organización
    When el Administrador modifica sus datos o sucursal asignada
    Then el catálogo refleja los valores vigentes
    And la auditoría conserva únicamente la sucursal y los nombres de campos modificados

  @BDD-SC-242
  Scenario: Desactivar repartidor preserva el registro
    Given un repartidor activo
    When el Administrador selecciona Desactivar
    Then el estado cambia a inactivo sin eliminar la fila
    And un actor sin admin.manage no puede consultar ni modificar el catálogo
```
