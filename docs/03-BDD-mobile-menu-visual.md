# BDD-FEAT-192 Menú visual y paleta de sucursal

```gherkin
@PRD-FR-061 @mobile-web
Feature: Explorar el menú conservando sus funciones y colores configurados
  @BDD-SC-940
  Scenario: La sucursal gobierna el acento
    Given una sucursal con paleta naranja, verde, azul o tinto
    When abro su menú incluso con la apariencia legacy dark
    Then botones y acentos usan la paleta de sucursal
    And un valor desconocido usa naranja

  @BDD-SC-941
  Scenario: Explorar desde la nueva cabecera
    Given categorías y productos del catálogo vigente
    When busco, cambio categoría o pulso Ver menú
    Then se conservan los filtros y el acceso al listado
    And puedo cambiar sucursal y actualizar mi ubicación

  @BDD-SC-942
  Scenario: Comprar desde las tarjetas verticales
    Given un producto con modificadores disponibles
    When uso su botón más o abro la personalización
    Then se conservan el agregado rápido y las opciones obligatorias
    And puedo editar el producto desde el carrito sin perder el checkout

  @BDD-SC-943
  Scenario: Usar el menú en pantalla pequeña
    Given una pantalla de 360 píxeles
    When exploro el menú con teclado o tacto
    Then nombres, precios y acciones son legibles sin desbordar la página
    And Menú, Dictar, Favoritos y Carrito permanecen accesibles
```
