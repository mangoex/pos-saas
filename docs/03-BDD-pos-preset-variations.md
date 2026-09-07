# BDD - Variaciones preestablecidas del POS

> Especificación histórica hasta `0027_catalog_cleanup`. Conserva los escenarios que protegen
> lectura y compatibilidad de datos anteriores. Para escrituras nuevas y aceptación vigente de
> `PRD-FR-699`, gobierna `BDD-FEAT-062` en `03-BDD-pos-order-operations-wave.md`.

## BDD-FEAT-057 Variaciones y cambios por producto

```gherkin
@PRD-FR-699 @pos @modifiers @catalog
Feature: Notas preestablecidas de variación o cambio

  @BDD-SC-168
  Scenario: Crear Sin cebolla como nota preestablecida
    Given un administrador corporativo con catalog.manage
    When crea Sin cebolla para un producto
    Then la opción usa preset_instruction, precio cero y sin efecto de inventario
    And pertenece al grupo opcional Variaciones y cambios

  @BDD-SC-169
  Scenario: El servidor conserva invariantes de una nota
    Given un administrador intenta crear una nota ya existente con espacios y mayúsculas distintas
    Or envía precio o efecto de inventario en el payload
    Then el duplicado normalizado se rechaza
    And una nota válida conserva precio cero, cantidades cero e inventario sin efecto
    And un display_order malformado se rechaza sin respuesta 500 ni cambio de datos

  @BDD-SC-194
  Scenario: Un grupo avanzado homónimo no se transforma en grupo de presets
    Given un producto tiene un grupo obligatorio Variaciones y cambios con una instrucción libre
    When el administrador intenta crear una nota preestablecida
    Then recibe variation_group_conflict
    And el grupo, su cardinalidad y la instrucción libre permanecen intactos

  @BDD-SC-170
  Scenario: La excepción del supervisor sólo afecta su sucursal
    Given dos sucursales autorizadas con una nota central activa
    When el supervisor de la sucursal A la marca No disponible
    Then A no la recibe en modificadores efectivos
    And B la conserva por herencia central
    When el supervisor marca Heredar
    Then se elimina sólo la excepción de A

  @BDD-SC-171
  Scenario: El cajero elige varias notas en una sola línea
    Given un producto con Sin cebolla y Sin lechuga disponibles
    When el cajero toca ambas tarjetas y agrega el producto
    Then se crea una sola línea con ambas notas
    And las tarjetas usan aria-pressed sin input para preset_instruction

  @BDD-SC-172
  Scenario: El pedido congela la nota sin cambiar importes ni consumo
    Given una nota preestablecida activa
    When se crea un pedido y después se archiva la nota
    Then la línea y el snapshot conservan kitchen_text histórico
    And total, modifier_total_cents y componentes son iguales al producto base
    And texto enviado por cliente no sustituye la nota congelada

  @BDD-SC-173
  Scenario: Cocina y comanda reciben las notas seleccionadas
    Given un pedido con una nota preestablecida
    When se crea su tarea KDS y el print job de cocina
    Then el read model de KDS expone kitchen_text
    And el payload de comanda incluye selected_modifiers por línea sin datos personales

  @BDD-SC-174
  Scenario: Las capacidades administrativas permanecen separadas
    Given un Cajero y un Supervisor de sucursal autenticados
    When el Cajero intenta administrar notas o abrir su ruta administrativa
    Then recibe acceso denegado
    When el Supervisor intenta crear una nota central o cambiar otra sucursal
    Then recibe permission_denied
```
