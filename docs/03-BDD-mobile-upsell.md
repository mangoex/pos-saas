# BDD - Venta cruzada determinista en el pedido móvil

## BDD-FEAT-107 Sugerencias complementarias antes del checkout

```gherkin
@PRD-FR-736 @mobile-web @catalog
Feature: Sugerencias seguras para el carrito móvil

  @BDD-SC-484
  Scenario: Recomendar bebidas disponibles para un carrito de alimentos
    Given un carrito contiene un alimento cuya estación canónica es cocina
    And existen bebidas compradas con ese alimento en al menos dos pedidos no cancelados
    When mobile-web solicita sugerencias para la sucursal seleccionada
    Then el sistema devuelve hasta cuatro bebidas disponibles de esa sucursal
    And excluye los productos que ya están en el carrito
    And ordena primero la mayor coocurrencia con desempate determinista

  @BDD-SC-485
  Scenario: No clasificar un alimento por una subcadena de su nombre
    Given un producto llamado "Baguette integral" pertenece a cocina
    When el sistema clasifica el carrito
    Then el producto se considera alimento aunque su nombre contenga "te"
    And sólo admite bebidas como complemento

  @BDD-SC-486
  Scenario: Excluir un complemento no disponible en la sucursal
    Given una bebida tiene mayor coocurrencia histórica
    And la bebida está deshabilitada en la sucursal seleccionada
    When el sistema calcula las sugerencias
    Then no devuelve esa bebida
    And sólo usa candidatos del catálogo efectivo de la sucursal

  @BDD-SC-487
  Scenario: Fallar sin afectar el checkout
    Given el carrito cambia de productos o de sucursal
    When el recomendador responde vacío, inválido o no está disponible
    Then mobile-web elimina las sugerencias anteriores
    And no fabrica recomendaciones genéricas
    And el comensal puede continuar el checkout sin cambios en carrito ni total

  @BDD-SC-488
  Scenario: Aislar recomendaciones administrativas por tenant y sucursal
    Given un actor tiene customers.read en una sucursal de su organización
    And existe otra organización con clientes, productos, pedidos y una sucursal distinta
    When el actor solicita recomendaciones o segmentos CRM
    Then las consultas usan únicamente la organización del actor
    And una sucursal de la otra organización se rechaza antes de consultar datos
    And una recomendación sin precio vigente no se devuelve
```
