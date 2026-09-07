# BDD - Bootstrap de datos base

## BDD-FEAT-018 Datos operativos iniciales

```gherkin
@PRD-FR-501 @PRD-FR-502 @PRD-FR-503 @PRD-FR-505 @PRD-FR-507 @platform @phase0
Feature: Bootstrap de organizacion y sucursal

  @BDD-SC-025
  Scenario: Consultar datos base despues de migrar
    Given las migraciones de Postgres fueron ejecutadas
    When el usuario abre Admin
    Then el sistema muestra la organizacion Kiwi Restaurante
    And muestra la Sucursal Piloto
    And muestra el almacen formal de la sucursal
    And conserva un evento de auditoria del bootstrap
```

