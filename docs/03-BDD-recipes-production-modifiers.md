# BDD - Recetas, elaborados y consumo versionado

## BDD-FEAT-040 Receta con merma y costo por sucursal

```gherkin
@PRD-FR-582 @PRD-FR-584 @PRD-FR-588 @recipes
Feature: Versionar receta y calcular cantidad bruta

  @BDD-SC-084
  Scenario: Aguacate con merma estándar
    Given una receta requiere 100 g netos de aguacate
    And la merma estándar es 20 por ciento
    When se activa la receta
    Then conserva 125 g como cantidad bruta
    And el costo usa 125 g al costo promedio de la sucursal
    And no crea una salida adicional por la merma estándar

  @BDD-SC-085
  Scenario: Pedido conserva receta y costo
    Given un producto tiene una receta activa
    When el cajero acepta un pedido
    Then la línea guarda un snapshot de versión, componentes y costos
    When se activa otra versión
    Then el pedido anterior conserva su snapshot original
```

## BDD-FEAT-041 Producción de elaborado sin doble consumo

```gherkin
@PRD-FR-580 @PRD-FR-581 @PRD-FR-585 @PRD-FR-587 @production
Feature: Producir y vender elaborados

  @BDD-SC-086
  Scenario: Producir aderezo por lote
    Given aderezo tiene una receta de producción con materias primas
    When el supervisor confirma un lote
    Then se consumen las materias primas una vez
    And entra existencia de aderezo
    And su costo resulta del costo real consumido dividido entre rendimiento real

  @BDD-SC-087
  Scenario: Venta consume elaborado
    Given un lote de aderezo ya consumió sus materias primas
    And un producto vendido usa aderezo como componente
    When se prepara el producto
    Then la venta consume aderezo
    And no vuelve a consumir las materias primas del lote

  @BDD-SC-088
  Scenario: Rechazar ciclo de elaborados
    Given elaborado A depende de elaborado B
    When se intenta activar una receta donde B depende de A
    Then el sistema rechaza el ciclo
    And conserva las versiones activas anteriores
```

## BDD-FEAT-042 Modificadores con precio, cocina e inventario

```gherkin
@PRD-FR-595 @PRD-FR-597 @modifiers
Feature: Validar grupos de modificadores

  @BDD-SC-089
  Scenario: Rechazar selección obligatoria incompleta
    Given un producto exige elegir una opción de cocción
    When el cajero acepta la línea sin selección
    Then el sistema rechaza el pedido con el grupo faltante

  @BDD-SC-090
  Scenario: Rechazar más opciones que el máximo
    Given un grupo permite como máximo dos extras
    When el cajero selecciona tres opciones
    Then el sistema rechaza la línea sin crear reservas

@PRD-FR-596 @PRD-FR-598 @modifiers @inventory
Feature: Aplicar efecto de inventario

  @BDD-SC-091
  Scenario: Quitar un ingrediente
    Given la receta contiene aguacate
    When el cajero elige Sin aguacate
    Then el snapshot final no contiene consumo de aguacate
    And cocina recibe el texto Sin aguacate

  @BDD-SC-092
  Scenario: Sustituir un ingrediente
    Given la receta contiene aderezo original
    When el cajero elige sustituir por aderezo picante
    Then el snapshot elimina la cantidad configurada del original
    And agrega la cantidad configurada del picante

  @BDD-SC-093
  Scenario: Instrucción libre no cambia inventario
    Given el cajero escribe cortar por la mitad
    When se acepta el pedido
    Then cocina recibe la instrucción
    And los componentes finales son iguales a la receta base

@PRD-FR-597 @PRD-FR-599 @modifiers @orders
Feature: Congelar precio y catálogo efectivo

  @BDD-SC-094
  Scenario: Precio adicional calculado por backend
    Given Aguacate extra cuesta 20 pesos en la sucursal
    When se aceptan dos unidades con esa opción
    Then el backend agrega 40 pesos a la línea
    And congela el precio y consumo aplicados
    When cambia el precio del catálogo
    Then el pedido anterior conserva sus importes

  @BDD-SC-419
  Scenario: Dar de alta una opción con precio adicional desde Administración
    Given un administrador captura una opción ordinaria con precio adicional de 22.00 MXN
    When guarda la nueva opción
    Then la interfaz envía price_delta_cents como el entero exacto 2200
    And espera la confirmación del servidor antes de cerrar el formulario
    And el catálogo recargado muestra la opción con su precio
    But si el servidor rechaza el alta el formulario permanece abierto con los datos capturados
    And muestra el error sin presentar el alta como exitosa

  @BDD-SC-404
  Scenario: Editar un modificador sólo cambia ventas futuras
    Given existe un pedido aceptado con una opción de modificador
    When un administrador edita nombre, cantidad, precio o texto de la opción
    Then el catálogo efectivo muestra la configuración nueva
    And el pedido anterior conserva nombre, cantidad, precio y consumo congelados

  @BDD-SC-405
  Scenario: Retirar modificadores sin destruir historia ni cardinalidad
    Given un grupo y sus opciones pertenecen al catálogo ordinario de modificadores
    When un administrador elimina una opción o el grupo
    Then el sistema los archiva y dejan de estar disponibles en ventas futuras
    And los pedidos anteriores conservan sus snapshots
    But si retirar una opción deja menos opciones que el mínimo del grupo la operación falla completa
    And comentarios e ingredientes adicionales sólo pueden modificarse desde su catálogo canónico
    And una opción deshabilitada en la sucursal permanece visible en la administración central
    And una organización no puede crear opciones dentro de grupos de otra organización
```
