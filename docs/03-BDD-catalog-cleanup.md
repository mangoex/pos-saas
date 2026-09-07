# BDD - Depuración y catálogo corporativo compartido

## BDD-FEAT-061 Depurar catálogos heredados sin romper historia

```gherkin
@PRD-FR-691 @PRD-FR-692 @PRD-FR-696 @PRD-FR-702 @catalog @migration
Feature: Normalizar productos, categorías e insumos heredados

  @BDD-SC-196
  Scenario: Retirar insumos con SKU no numérico
    Given existen insumos con SKU `1001` y `INS-ACE`
    When se aplica la depuración DATA-003
    Then `1001` queda activo y corporativo
    And `INS-ACE` queda archivado y no aparece en el catálogo operativo
    And ningún movimiento, existencia o costo histórico se modifica

  @BDD-SC-197
  Scenario: Retirar categorías que no están en mayúsculas
    Given existen las categorías `AGUAS` y `Bebidas`
    When se aplica la depuración DATA-003
    Then `AGUAS` permanece activa
    And `Bebidas` queda archivada y no aparece en el catálogo operativo
    And un producto conservado se reasigna primero a su categoría mayúscula equivalente

  @BDD-SC-198
  Scenario: Normalizar o retirar productos por SKU y nombre
    Given existen un producto `'01001` llamado `AGUA DE FRESA` y registros con SKU no numérico o nombre no mayúsculo
    When se aplica la depuración DATA-003
    Then el producto válido conserva `01001` como texto, incluidos sus ceros iniciales
    And queda activo y con alcance corporativo
    And los demás quedan archivados y no aparecen en el catálogo operativo

  @BDD-SC-199
  Scenario: Clasificar estaciones sin inventar datos
    Given existen productos válidos de AGUAS, comida y empaque
    When se aplica la política de estaciones
    Then aguas, jugos, licuados, bebidas, smoothies y extractos usan `drinks`
    And bolsas, empaques y servicios a domicilio usan `packing`
    And los demás productos usan `kitchen`

  @BDD-SC-200
  Scenario: Compartir catálogo entre sucursales
    Given un producto e insumo válidos importados desde Constitución
    And otra sucursal tenía una excepción local de producto
    When termina la depuración
    Then producto, categoría e insumo aparecen en ambas sucursales
    And la excepción previa se retira para heredar disponibilidad central
    And las existencias y almacenes continúan separados por sucursal

  @BDD-SC-201
  Scenario: Conservar productos sin precio fuera del cobro
    Given un producto válido con estación y estado activo pero sin precio vigente positivo
    When un administrador y un cajero consultan el catálogo
    Then el administrador puede revisar el producto
    But el POS no lo ofrece para cobrar ni inventa un precio

  @BDD-SC-202
  Scenario: Revertir y auditar la depuración
    Given la migración registró los valores previos y su resumen
    When se ejecuta downgrade a `0026_ingredient_variations`
    Then se restauran SKU, estado, alcance, categoría, estación y excepciones locales
    And no se reescriben movimientos, pedidos, pagos, costos ni snapshots
    And el endpoint de estado sólo entrega conteos a un actor con `catalog.manage`
```
