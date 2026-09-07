# BDD - Ingredientes adicionales relacionados con productos

> Especificación histórica hasta `0027_catalog_cleanup`. Para ventas nuevas sin relación previa
> producto-adicional gobierna `BDD-FEAT-063` en `03-BDD-pos-order-operations-wave.md`.
>
> Norma POS-VAR-003: BDD-FEAT-058 conserva sus IDs y la compatibilidad de esquema 0026, pero
> sustituye Con/Sin por ingredientes adicionales ADD-only en ventas y configuración nuevas.
> Cualquier remove materializado antes de esta regla es legado histórico, no una acción seleccionable.

## BDD-FEAT-058 Catálogo reutilizable de ingredientes adicionales

```gherkin
@PRD-FR-700 @pos @modifiers @inventory @catalog
Feature: Ingredientes adicionales relacionados con productos

  @BDD-SC-175
  Scenario: Admin crea Aguacate como ingrediente adicional normalizado
    Given un administrador corporativo con catalog.manage y el insumo Aguacate
    When crea la definición del adicional con etiqueta Porción extra de aguacate
    Then la etiqueta y la unidad base quedan visibles sin crear una segunda definición canónica

  @BDD-SC-176
  Scenario: Preview expande productos y categorías actuales sin duplicarlos
    Given una selección de dos productos y una categoría con productos activos actuales
    When el administrador solicita preview del adicional de aguacate
    Then el preview colapsa duplicados e identifica producto, SKU, categoría y compatibilidad
    When confirma sólo los compatibles
    Then persiste exclusivamente los productos activos existentes en ese momento

  @BDD-SC-177
  Scenario: Un intento de retiro no aplica parcialmente
    Given una selección de productos para un ingrediente adicional
    When el cliente envía allow_remove verdadero
    Then recibe ingredient_extra_add_only
    And ninguna asignación ni opción se crea parcialmente

  @BDD-SC-178
  Scenario: Un adicional agrega Decimal y costo promedio al snapshot
    Given una sucursal con costo promedio vigente de aguacate
    When el cajero selecciona Porción extra de aguacate con cantidad Decimal configurada
    Then el snapshot, reserva y consumo incluyen esa cantidad exacta
    And el costo teórico usa el costo promedio vigente de la sucursal

  @BDD-SC-179
  Scenario: Adicional de azúcar sin cargo conserva venta y aumenta consumo interno
    Given Porción extra de azúcar configurada sin cargo
    When se vende un café con ese adicional
    Then el total de venta no cambia
    And consumo y costo teórico incluyen la azúcar configurada

  @BDD-SC-180
  Scenario: Cargo explícito no usa costo promedio como precio
    Given Porción extra de aguacate tiene un price_delta_cents explícito
    When se vende una línea con cantidad dos
    Then el backend suma ese cargo por cantidad de línea
    And no deriva el precio del costo promedio contable
    And la UI convierte el importe MXN exacto a price_delta_cents sin redondearlo

  @BDD-SC-181
  Scenario: Un retiro heredado no puede usarse en ventas nuevas
    Given una opción remove materializada por POS-VAR-002 antes de la separación
    When un cliente envía uno o varios option_id de retiro manipulando el payload
    Then el backend responde ingredient_extra_add_only
    And no crea snapshot, reserva, consumo ni pedido parcial

  @BDD-SC-182
  Scenario: Supervisor modifica sólo disponibilidad ADD en su sucursal
    Given dos sucursales con un adicional de aguacate heredado
    When el Supervisor de una sucursal marca el adicional como No disponible
    Then la otra sucursal conserva el estado heredado
    And el Supervisor no puede configurar retiro, insumo, cantidad ni precio

  @BDD-SC-183
  Scenario: Archivar o desvincular conserva pedidos históricos
    Given un pedido previo con ingrediente adicional, snapshot, costo y kitchen_text
    When el administrador archiva o desvincula la relación
    Then las ventas nuevas no reciben la opción
    And el pedido previo conserva su snapshot, costo, texto KDS e impresión

  @BDD-SC-184
  Scenario: Catálogo muestra y gestiona relaciones según permiso
    Given un administrador, un Supervisor y un Cajero autenticados
    When el administrador abre un ingrediente adicional
    Then ve productos relacionados y puede agregar, editar o desvincular relaciones ADD
    And el Supervisor sólo gestiona disponibilidad ADD en su sucursal
    And el Cajero no puede abrir ninguna ruta administrativa
```
