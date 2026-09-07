# BDD - Estructura organizacional y roles POS

## BDD-FEAT-034 Unidad de negocio y perfiles operativos

```gherkin
@PRD-FR-505 @PRD-FR-509 @organization @security
Feature: Organizar sucursales y separar capacidades del POS

  @BDD-SC-193
  Scenario: Crear unidad de negocio y asignar sucursal
    Given existe una razon social del Grupo Kiwi
    When el administrador crea una unidad de negocio de tipo restaurante
    And crea una sucursal dentro de esa unidad
    Then la sucursal conserva la unidad de negocio y la razon social compatibles
    And mantiene un solo almacen operativo
    And ambas altas producen auditoria

  @BDD-SC-067
  Scenario: Supervisor opera funciones sensibles de su sucursal
    Given existe un usuario con rol Supervisor de sucursal
    When inicia sesion
    Then recibe permisos de POS, compras, retiros, inventario, merma, envio de traspasos y conteos
    And esos permisos solo aplican a su sucursal asignada
    And no recibe permiso de administracion corporativa

  @BDD-SC-068
  Scenario: Receptor y auditor conservan acceso limitado
    Given existe un usuario Receptor de traspaso en una sucursal
    Then puede consultar inventario y confirmar recepciones
    And no puede enviar traspasos ni ajustar inventario
    Given existe un usuario Auditor
    Then puede consultar operacion y auditoria
    And no recibe permisos de mutacion
```
