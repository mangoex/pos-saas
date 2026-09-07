# BDD - Capacidad de identificadores de revisión Alembic

## BDD-FEAT-049 Ampliar la columna version_num antes de revisiones largas

```gherkin
@PRD-NFR-517 @db @migrations
Feature: Migrar la cadena sin truncar identificadores de revisión

  @BDD-SC-116
  Scenario: La migración puente amplía version_num y permite avanzar hasta el head
    Given una base PostgreSQL está en 0013_pos_cash_rbac_permissions
    And alembic_version.version_num admite 32 caracteres
    When el operador ejecuta alembic upgrade head
    Then una migración puente amplía version_num a 128 caracteres
    And Alembic aplica 0014 hasta 0023 en una sola cadena
    And la base termina en 0023_physical_counts
    And no se modifica información de negocio

  @BDD-SC-117
  Scenario: Downgrade reduce version_num cuando la revisión actual cabe
    Given una base PostgreSQL está en 0014_legacy_caja_role_permissions
    And version_num ya fue ampliada a 128 caracteres
    When el operador ejecuta alembic downgrade 0013_pos_cash_rbac_permissions
    Then la migración puente reduce version_num a 32 caracteres
    And la base termina en 0013_pos_cash_rbac_permissions
    And la cadena permanece válida y sin ramas
```
