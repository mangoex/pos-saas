# TDD-TS-290 Guardado móvil de producto y modificadores

Regresión focal: `apps/api/tests/test_mobile_product_modifiers.py` y
`tests/frontend/test_mobile_product_modifiers.mjs`. Cubrir cargo/gratis y cantidades, creación,
edición, recuperación de grupo vacío/archivado, identidad estable, snapshots históricos, rechazo de
precio inválido y revisión vieja, rollback con fallo inyectado, permiso y tenant ajeno, grupos
avanzados intactos, carga fallida y carrera de respuestas. PostgreSQL verifica bloqueo concurrente;
SQLite verifica contratos, rollback y concurrencia con base en archivo. El gate de PostgreSQL
es `test_mobile_product_modifiers_postgres.py`, usa SAAS_TEST_POSTGRES_URL local ya configurada
en CI y un esquema desechable único. Incluye rollback y dos escritores con la misma revisión. Typecheck admin y lint/typecheck Python focales.

QA visual del modal móvil: carga/error, multilinea, guardar y archivar; conservar texto ante error.
La suite CI es autoritativa para los gates configurados. No presentar canary ni despliegue como
ejecutados por pruebas locales. Evidencia exacta y límites se registran en el cierre de este paquete.
