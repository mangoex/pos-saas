# BDD - Gate frontend de integración continua

## BDD-FEAT-048 Gate de CI para Admin, POS y KDS

```gherkin
@PRD-NFR-516 @ci @frontend
Feature: Validar frontend en integración continua

  @BDD-SC-115
  Scenario: Gate frontend bloquea integraciones fallidas
    Given un cambio afecta Admin, POS, KDS o un paquete TypeScript compartido
    When GitHub Actions valida el cambio
    Then instala dependencias usando el lockfile congelado
    And ejecuta el typecheck del monorepo
    And construye Admin, POS y KDS para producción
    And una falla impide que el gate termine correctamente
```
