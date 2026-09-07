# BDD - Mejoras de UX en Administrador de Modificadores

```gherkin
@PRD-FR-595 @PRD-FR-596 @modifiers-ui @admin
Feature: Mejoras de usabilidad en la administración de modificadores

  @BDD-SC-441
  Scenario: Mostrar y capturar precios en formato moneda (MXN)
    Given un modificador tiene un precio adicional guardado en centavos (ej. 2200)
    When el administrador visualiza la opción en la interfaz de modificadores
    Then el precio se muestra formateado en pesos como "$22.00"
    And al editar el precio, el administrador ingresa un valor decimal (ej. "25.50")
    And el sistema lo convierte y guarda internamente como centavos (2550)

  @BDD-SC-442
  Scenario: Edición inline de grupos y opciones
    Given un grupo de modificadores existente con opciones
    When el administrador selecciona editar el nombre de un grupo o una opción
    Then la interfaz cambia a modo edición en la misma línea (inline) sin abrir modales adicionales
    And los cambios se guardan al perder el foco o presionar la tecla Enter
    And se actualiza la vista inmediatamente

  @BDD-SC-443
  Scenario: Vista previa del efecto del modificador sobre la receta
    Given un producto con una receta configurada y un modificador que altera inventario
    When el administrador selecciona la opción de previsualizar el modificador
    Then el sistema muestra un panel con el impacto simulado sobre la receta
    And resalta visualmente qué componentes se agregan, cambian de cantidad o se eliminan
    And refleja cómo se verá la instrucción para cocina

  @BDD-SC-444
  Scenario: Clonación de grupos de modificadores entre productos
    Given un producto origen tiene un grupo de modificadores configurado (ej. "Término de la carne")
    And existe un producto destino en el catálogo
    When el administrador selecciona clonar el grupo hacia el producto destino
    Then se crea una copia exacta del grupo, sus reglas de cardinalidad y sus opciones
    And los cambios futuros en el grupo clonado son independientes del grupo original

  @BDD-SC-445
  Scenario: Reordenamiento visual de opciones y grupos (Drag & Drop)
    Given un producto tiene múltiples grupos de modificadores, cada uno con varias opciones
    When el administrador arrastra y suelta un grupo a una nueva posición
    Then el sistema actualiza el orden de visualización de los grupos
    When el administrador arrastra una opción dentro de un grupo a otra posición
    Then el sistema actualiza el orden específico de las opciones
    And el nuevo orden se conserva de forma persistente para las interfaces de venta (POS)
```
