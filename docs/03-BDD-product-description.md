# BDD-FEAT-195 — Descripción editable del producto

```gherkin
@PRD-FR-010
Feature: Personalizar la descripción del menú
  @BDD-SC-953
  Scenario: Editar la propuesta existente
    Given un producto con descripción guardada
    When abro Editar Platillo
    Then el cuadro Descripción del producto muestra ese texto editable
    When lo amplío y guardo
    Then al reabrir y consultar el menú se conserva el nuevo texto
    And precio y modificadores permanecen iguales
  @BDD-SC-954
  Scenario: Vacío, omisión y entradas inválidas
    Given un producto existente
    When guardo una descripción vacía
    Then su descripción queda vacía
    And omitir el campo en otra edición conserva el texto
    And texto de más de 360 caracteres o tipos inválidos se rechazan sin cambios
```
