# BDD-FEAT-190 Editor móvil de producto y modificadores

```gherkin
@PRD-FR-010 @PRD-FR-061
Feature: Guardar modificadores comerciales sin cambios parciales
  @BDD-SC-890
  Scenario: Cargo y opción gratuita se conservan como modificadores
    Given Café Latte con precio de 45 pesos
    When el administrador guarda Leche de avena, 10 y Sin azúcar sin precio
    Then seleccionar ambos produce 55 pesos por unidad
    And las opciones son modificadores y no comentarios del pedido
  @BDD-SC-891
  Scenario: Validación y fallo conservan el estado anterior
    Given un producto con opciones existentes
    When el precio es inválido o falla la persistencia de una opción
    Then no cambia el producto ni el precio ni las opciones ni la auditoría
  @BDD-SC-892
  Scenario: Edición y reintento preservan identidad e historia
    Given el grupo Extras vacío de un guardado anterior fallido
    When se guardan, retiran y vuelven a agregar opciones
    Then se reutilizan grupo y opciones sin duplicados
    And los pedidos previos conservan su snapshot
    And una revisión obsoleta se rechaza sin sobrescribir
  @BDD-SC-893
  Scenario: Editor respeta el alcance del catálogo
    Given grupos avanzados y productos de otro restaurante
    When se usa el editor simplificado
    Then sólo modifica Extras compatible de su restaurante
    And una carga fallida bloquea el guardado
    And una respuesta atrasada no sobrescribe otro borrador
```
