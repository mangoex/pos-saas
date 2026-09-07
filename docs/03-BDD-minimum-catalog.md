# BDD - Catalogo minimo

## BDD-FEAT-019 Catalogo inicial para POS

```gherkin
@PRD-FR-510 @PRD-FR-512 @PRD-FR-514 @PRD-FR-515 @catalog @phase0
Feature: Catalogo minimo versionado

  @BDD-SC-026
  Scenario: Consultar productos semilla disponibles
    Given las migraciones de catalogo fueron ejecutadas
    And existe la Sucursal Piloto
    When el sistema consulta el catalogo del POS
    Then recibe productos activos con categoria
    And recibe precio vigente en centavos
    And recibe disponibilidad por sucursal
```

