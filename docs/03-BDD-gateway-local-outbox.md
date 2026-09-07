# BDD - Gateway local y outbox SQLite

## BDD-FEAT-028 Outbox local del gateway

```gherkin
@PRD-FR-680 @PRD-FR-682 @PRD-FR-684 @PRD-FR-687 @offline @phase1
Feature: Persistencia local de comandos offline

  @BDD-SC-041
  Scenario: Guardar comando local antes de sincronizar
    Given la sucursal opera mediante gateway local
    And la conexion con la nube puede estar interrumpida
    When el POS envia un depósito o retiro manual con grant offline vigente
    Then el gateway deriva actor y alcance del grant y valida cash.movement.create.v1
    And persiste comando, hash y payload canónico en SQLite WAL
    And lo deja PENDING_SYNC en outbox
    And usa la clave idempotente para evitar duplicados locales
    But cualquier otro tipo, campo adicional o payload vacío falla cerrado

  @BDD-SC-042
  Scenario: Marcar comando local como confirmado
    Given existe un comando PENDING_SYNC en outbox
    When la nube confirma el comando con checkpoint
    Then el gateway marca el comando como confirmado
    And conserva el checkpoint confirmado
    And ya no lo lista como pendiente

  @BDD-SC-401
  Scenario: Replay local conserva contrato y alcance completos
    Given existe un comando local válido con clave idempotente
    When se repite con todos sus campos inmutables idénticos
    Then el gateway devuelve la misma fila sin duplicarla
    And si los replays idénticos llegan concurrentemente ninguno recibe una excepción SQL
    When se cambia organización, sucursal, dispositivo, actor, tipo o payload
    Then el gateway rechaza idempotency_conflict sin reutilizar la fila previa
    And un sobre fuera de command-envelope.schema.json se rechaza antes de persistir
    And correlación, causación, campos adicionales o un payload vacío se rechazan
```
