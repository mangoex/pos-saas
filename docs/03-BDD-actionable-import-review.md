# BDD - Revisión accionable de importaciones

## BDD-FEAT-054 Conciliación guiada de datos heredados

```gherkin
@PRD-FR-692 @PRD-FR-693 @PRD-FR-696 @import @admin
Feature: Comprender y resolver los pendientes de una importación

  @BDD-SC-152
  Scenario: La bandeja separa pendientes por tipo
    Given un lote con presentaciones, productos y recetas en revisión
    When el administrador abre la importación
    Then ve el total independiente de cada tipo
    And puede cambiar de tipo sin recorrer primero los registros de otro tipo

  @BDD-SC-153
  Scenario: Cada pendiente identifica el dato y la acción requerida
    Given un registro heredado en revisión
    When aparece en la bandeja
    Then muestra nombre, clave de origen y motivo en lenguaje operativo
    And la pantalla explica los pasos y el catálogo canónico donde debe completarse

  @BDD-SC-154
  Scenario: Un producto se localiza sin activación automática
    Given un producto heredado sin estación
    When el administrador elige Configurar producto
    Then el catálogo de Productos abre filtrado por su SKU
    And el producto permanece no vendible hasta que se asigne estación y se active explícitamente

  @BDD-SC-155
  Scenario: La revisión permanece paginada
    Given más de cien pendientes del mismo tipo
    When el administrador navega la bandeja
    Then la API devuelve sólo la página solicitada y su total
    And la interfaz permite avanzar y volver sin cargar el lote completo
```
