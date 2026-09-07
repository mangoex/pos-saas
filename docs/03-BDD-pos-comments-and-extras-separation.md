# BDD - Separación de comentarios e ingredientes adicionales

> Especificación histórica de superficies hasta `0027_catalog_cleanup`. La separación semántica se
> conserva, pero alcance y selección vigentes se definen en `BDD-FEAT-062` y `BDD-FEAT-063`.

## BDD-FEAT-059 Comentarios del pedido e ingredientes adicionales

```gherkin
@PRD-FR-699 @PRD-FR-700 @PRD-FR-701 @pos @catalog @inventory
Feature: Separar semántica de comentarios y adicionales

  @BDD-SC-185
  Scenario: Administración ofrece rutas separadas
    Given un administrador corporativo autenticado
    When abre el catálogo
    Then ve Comentarios del pedido e Ingredientes adicionales como rutas distintas
    And ninguna ruta usa tabs para mezclar ambos catálogos

  @BDD-SC-186
  Scenario: Sin lechuga es un comentario sin inventario
    Given Sin lechuga creado como comentario del pedido
    When el cajero lo selecciona y confirma una venta
    Then usa preset_instruction con precio cero e inventory_effect false
    And KDS e impresión muestran kitchen_text sin reserva, consumo ni costo

  @BDD-SC-187
  Scenario: Extra de aguacate ejecuta inventario exacto
    Given Porción extra de aguacate con insumo y cantidad Decimal
    When se vende con el adicional
    Then congela componente y costo teórico con el costo promedio vigente
    And reserva y consumo usan la cantidad exacta configurada

  @BDD-SC-188
  Scenario: El cargo del adicional es explícito
    Given un adicional sin cargo y otro con cargo explícito
    When se venden
    Then el primero no cambia el total y el segundo lo cambia exactamente
    And ningún precio se deriva del costo promedio

  @BDD-SC-189
  Scenario: Retiro heredado no participa en ventas nuevas
    Given una opción remove histórica ligada a ingredient_variations
    When el POS lee modificadores o un cliente envía manualmente su option_id
    Then no aparece en el POS y el payload falla con ingredient_extra_add_only
    And el pedido histórico con su snapshot, KDS e impresión sigue legible

  @BDD-SC-190
  Scenario: Supervisor administra disponibilidades separadas
    Given un Supervisor de sucursal y un Cajero
    When el Supervisor ajusta la disponibilidad de un comentario y de un adicional
    Then sólo cambia su sucursal canónica y sólo las opciones add de adicionales
    And el Cajero no puede ver rutas administrativas

  @BDD-SC-191
  Scenario: Modal POS separa comentarios y adicionales
    Given un producto con comentarios y adicionales efectivos
    When el cajero abre la personalización, cancela o confirma
    Then ve los encabezados Comentarios del pedido e Ingredientes adicionales separados
    And cancelar no cambia el carrito y confirmar conserva snapshots y kitchen_text
    And cambiar destinos, cantidad o cargo después del preview exige solicitar otro preview antes
      de relacionar el adicional
```
