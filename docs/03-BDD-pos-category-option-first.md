# BDD - Selección previa de opción por categoría

## BDD-FEAT-074 POS-CAT-004 selector obligatorio antes del producto

```gherkin
@PRD-FR-713 @PRD-NFR-504 @PRD-NFR-510 @PRD-NFR-512 @PRD-NFR-516 @PRD-NFR-517 @PRD-NFR-518 @pos @catalog
Feature: Seleccionar una opción de categoría antes del producto

  @BDD-SC-255
  Scenario: Categoría configurada muestra opciones antes de productos
    Given Ensaladas tiene el grupo requerido Tamaño
    When el Cajero abre Ensaladas
    Then ve Tamaño y sus opciones disponibles antes de cualquier producto

  @BDD-SC-256
  Scenario: Un valor filtra sólo productos vendibles asignados
    Given Chica tiene productos concretos elegibles en la sucursal
    When el Cajero selecciona Chica
    Then sólo ve esos productos concretos

  @BDD-SC-257
  Scenario: Elegir opción no agrega carrito
    Given el carrito contiene una línea existente
    When el Cajero selecciona Mediana
    Then el carrito no cambia

  @BDD-SC-258
  Scenario: Categoría sin selector conserva flujo
    Given Bebidas no tiene grupo activo
    When el Cajero la abre
    Then ve directamente la cuadrícula actual de productos

  @BDD-SC-259
  Scenario: Cambiar categoría u opción limpia sólo personalización transitoria
    Given hay complementos abiertos y un carrito existente
    When cambia la categoría o la opción
    Then los complementos transitorios se cierran
    And el carrito permanece intacto

  @BDD-SC-260
  Scenario: Sucursal, disponibilidad y precio gobiernan valores
    Given un valor no tiene productos activos, disponibles y con precio vigente positivo
    When POS consulta el catálogo de la sucursal
    Then el valor no aparece

  @BDD-SC-261
  Scenario: Producto sin asignación falla cerrado y sigue visible en Administración
    Given una categoría con grupo activo y un producto vendible sin asignación válida
    When POS proyecta el catálogo
    Then no publica ese producto
    And Administración corporativa lo muestra como incompleto
    And permite editar explícitamente la opción asignada o reasignar el producto

  @BDD-SC-262
  Scenario: Error de proyección no hace fallback inseguro
    Given falla la proyección del selector
    When POS carga la categoría
    Then muestra un error recuperable con Reintentar
    And no muestra todos los productos como fallback
    And un selector activo sin valores visibles muestra un estado vacío recuperable

  @BDD-SC-263
  Scenario: Backend cobra y congela producto concreto
    Given el Cajero seleccionó Chica y añadió un producto concreto
    When crea un pedido con turno abierto
    Then envía sólo el product_id concreto
    And backend recalcula precio, total y snapshot
```

## Compatibilidad técnica de migraciones

`PRD-NFR-517` exige que el adaptador Alembic acepte una URL SQLAlchemy percent-encoded sin alterar
el valor que recibirá el driver. Es una garantía técnica de arranque de migración, no un selector ni
una regla de negocio POS.

```gherkin
@PRD-NFR-517 @alembic
@BDD-SC-264
Scenario: URL percent-encoded se conserva a través de ConfigParser
  Given una URL SQLAlchemy con escapes %xx de socket o credenciales
  When Alembic la almacena mediante ConfigParser
  Then el driver recupera exactamente el URL lógico original
  And no se imprime la URL ni sus credenciales
```
