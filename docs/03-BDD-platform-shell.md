# BDD - Platform Shell

## BDD-FEAT-017 Consola inicial de plataforma

```gherkin
@PRD-NFR-509 @PRD-NFR-510 @PRD-NFR-511 @platform @phase0
Feature: Shell operativo inicial

  @BDD-SC-024
  Scenario: Ver la consola inicial desplegada
    Given la API esta desplegada en Easypanel
    And PostgreSQL y Redis estan configurados
    When el usuario abre la raiz publica del servicio
    Then ve la consola inicial de RestaurantOS
    And la consola muestra el estado de Postgres y Redis
    And ofrece accesos a Admin, POS, KDS y documentacion API

  @BDD-SC-192
  Scenario: El contenedor no bloquea el arranque por migraciones
    Given la API se despliega desde el Dockerfile de produccion
    When el contenedor inicia en Easypanel
    Then el proceso principal abre Uvicorn directamente
    And las migraciones Alembic se ejecutan como paso operativo separado
    And ninguna variable de entorno puede reactivar Alembic dentro del proceso web
    And un error de base de datos debe reflejarse en `/health/ready`, no en un 502 por proceso caido
```
