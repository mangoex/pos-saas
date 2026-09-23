# BDD-FEAT-194 — Eliminar categoría del catálogo móvil

```gherkin
@PRD-FR-010 @catalog
Feature: Eliminar una categoría junto con sus productos
  @BDD-SC-948
  Scenario: Confirmar la eliminación
    Given una categoría con productos activos e inactivos
    When el administrador pulsa Eliminar categoría y confirma
    Then desaparecen esa categoría y sus productos del catálogo
    And las demás categorías y productos permanecen iguales
    And sus pedidos históricos permanecen y queda auditoría
  @BDD-SC-949
  Scenario: Cancelar o fallar
    Given el editor de categoría abierto
    When cancelo la confirmación o falla la solicitud
    Then no se presenta éxito ni se cierra el editor
    And cancelar no envía una eliminación
  @BDD-SC-950
  Scenario: Proteger el alcance
    Given una categoría ajena o un actor sin permiso
    When solicita eliminar categoría y productos
    Then la operación se rechaza sin modificar datos
  @BDD-SC-951
  Scenario: Repeticiones y formularios viejos
    Given una categoría eliminada
    When se repite la eliminación o se intenta guardar un formulario anterior
    Then no se duplican efectos ni se reactivan productos o categorías archivados
  @BDD-SC-952
  Scenario: Operación atómica y concurrencia
    Given una alta o edición de producto concurrente con la eliminación
    When se resuelven las transacciones
    Then no queda un producto vendible dentro de la categoría archivada
    And una falla de auditoría revierte el archivado completo
```
