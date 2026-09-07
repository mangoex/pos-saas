# BDD - Presentación de tarjetas de producto POS

## BDD-FEAT-075 POS-UX-002 tarjetas de producto sin fotografía

```gherkin
@PRD-FR-714 @PRD-NFR-510 @PRD-NFR-516 @PRD-NFR-518 @pos @ux
Feature: Presentar con claridad las tarjetas de producto concreto sin fotografía

  @BDD-SC-265
  Scenario: Producto concreto sin foto usa fallback compacto y nombre mayor
    Given un producto concreto con image_url nulo, ausente, vacío o sólo espacios
    When el Cajero ve su tarjeta en la cuadrícula del POS
    Then la tarjeta usa el fallback visual de 52 px con el icono existente de 32 px
    And su nombre se presenta a 14 px, peso 700 y line-height 1.25 sin elipsis ni recorte
    And el precio conserva formatMxnCents y su estilo actual

  @BDD-SC-266
  Scenario: Producto concreto con foto conserva imagen y texto alternativo
    Given un producto concreto con image_url no vacío
    When el Cajero ve su tarjeta en la cuadrícula del POS
    Then conserva el contenedor visual de 72 px
    And conserva img con alt del nombre y object-fit contain
    And el elemento img nunca excede ni se superpone fuera de su contenedor de 72 px
    And no recibe la jerarquía tipográfica especial del fallback

  @BDD-SC-267
  Scenario: Selector previo Chica Grande no hereda estilos de producto sin foto
    Given Ensaladas requiere seleccionar Tamaño antes del producto concreto
    When el Cajero abre Ensaladas sin haber elegido una opción
    Then las tarjetas Chica y Grande conservan su icono de 48 px y apariencia actual
    And elegir una opción no agrega una línea al carrito

  @BDD-SC-268
  Scenario: Nombre largo envuelve sin tapar precio en ambos grids
    Given un producto concreto sin fotografía y con un nombre largo
    When el Cajero ve la cuadrícula de escritorio y el breakpoint de hasta 1120 px
    Then el nombre puede envolver hasta tres líneas dentro de la tarjeta
    And no se solapa con el precio ni desborda la tarjeta

  @BDD-SC-269
  Scenario: El ajuste visual no altera la venta del producto concreto
    Given el Cajero eligió una opción previa sin modificar el carrito
    When toca un producto concreto y después lo retira
    Then el producto continúa llamando selectProduct
    And el carrito cambia sólo al elegir el producto y termina vacío tras retirarlo
    And precio y complementos conservan sus contratos actuales
```
