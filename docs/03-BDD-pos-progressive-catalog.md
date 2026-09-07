# BDD - Catálogo POS progresivo

## BDD-FEAT-094 POS-UX-003 navegación progresiva y modificadores por pestaña

```gherkin
@PRD-FR-729 @PRD-FR-713 @pos @ux
Feature: Capturar productos POS por etapas progresivas

  @BDD-SC-425
  Scenario: El menú fijo reinicia la selección transitoria
    Given el Cajero avanzó a una categoría, tamaño y producto
    When selecciona ALIMENTOS, BEBIDAS, OTROS, FAVORITOS o TODO
    Then el menú fijo permanece visible
    And vuelve a la etapa de categorías del grupo elegido, excepto Favoritos que abre productos directamente
    And el carrito y la búsqueda permanecen intactos

  @BDD-SC-426
  Scenario: La categoría con selector previo ocupa la etapa actual
    Given Ensaladas requiere Tamaño
    When el Cajero abre Ensaladas
    Then ve Tamaño antes de productos concretos
    And Ensaladas queda como contexto compacto que puede cambiar

  @BDD-SC-427
  Scenario: Una opción válida muestra sólo los productos concretos
    Given el Cajero eligió Chica en Ensaladas
    When avanza el flujo
    Then la zona central muestra productos concretos de Chica
    And categoría y tamaño siguen disponibles para regresar sin mostrarse como cuadrículas paralelas

  @BDD-SC-428
  Scenario: El compositor muestra sólo el grupo modificador activo
    Given un producto tiene grupos de complementos
    When el Cajero abre su compositor
    Then ve pestañas grandes de todos los grupos
    And sólo ve las opciones de la pestaña activa
    And cada pestaña comunica Obligatorio u Opcional y sus límites actuales

  @BDD-SC-429
  Scenario: Agregar respeta mínimos existentes y retorna a productos
    Given un grupo obligatorio aún no cumple su mínimo
    When el Cajero abre el compositor
    Then Agregar al pedido permanece deshabilitado
    When cumple los mínimos de todos los grupos y agrega
    Then retorna a los productos de la misma categoría y opción
    And el carrito conserva la nueva línea

  @BDD-SC-430
  Scenario: Producto sin modificadores entra directamente al carrito
    Given un producto concreto no tiene grupos modificadores
    When el Cajero lo selecciona
    Then se agrega directamente al carrito
    And el flujo permanece en productos
```
