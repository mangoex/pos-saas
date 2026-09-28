# TDD — Regresiones de fronteras multitenant

## TDD-TS-298 Integridad de mappings y alcance CRM

- `apps/api/tests/test_saas_integration_mapping_scope.py`: HTTP por Uber/DiDi/Rappi,
  cambio de mapping, sucursal ajena/inactiva/inexistente, actor revocado, control positivo propio;
  servicio y resolución con datos históricos, integridad compuesta y migración reversible.
- `apps/api/tests/test_saas_crm_branch_scope.py`: permiso limitado a sucursal, parámetro omitido,
  propia/ajena y owner organizacional. Un rol organizacional sin el permiso no amplía otro rol.
- Gates: SQLite con FK activas y PostgreSQL desechable; API lint/typecheck focal; revisión Sol R3.
- `apps/api/tests/test_saas_crm_aggregation.py`: reloj fijo, umbrales de 14/30 días y
  3 pedidos/50 000 centavos, clientes sin pedidos, exclusión de cancelados conforme al contrato
  vigente, total superior a 32 bits, aislamiento de cada relación y dos sucursales.
  Aumentar clientes de 1 a 201 conserva una consulta, con resultados y contadores completos;
  ejecutar en SQLite y PostgreSQL. La latencia se registra sin un umbral frágil dependiente del
  equipo. Inspeccionar el plan SQL antes de decidir un índice adicional.

La afirmación es rechazo previo a efectos. La refutación usa IDs válidos de otro tenant, omisión de
parámetros y escrituras SQL directas, no sólo UUIDs inexistentes. La evidencia RED/GREEN y los gates
pendientes se registran en el cierre del paquete, sin presentar diseño como prueba ejecutada.

- Regresión kill-switch integrado: agotado y restauración conservan habilitación del mapping,
  sólo generan outbox para la sucursal objetivo y no reactivan un mapping revocado.
- `test_public_pickup_schedule.py`: regresión encontrada en captura con horario válido:
  producto de otro tenant debe rechazarse por el resolutor compartido antes de snapshots o
  escrituras. SQLite/PostgreSQL comprueban el caso negativo y aceptación propia, incluida
  conservación del snapshot temporal. ID, SKU y nombre conservan resolución sólo local.
