# TDD-TS-294 — Eliminación segura de categoría

BDD-SC-948..952: prueba HTTP real para flag/permiso, categoría vacía y con productos,
aislamiento por IDs/organización, estados archivados, no-op repetido y conservación
de filas e históricos. Falla inyectada de auditoría con rollback. PostgreSQL real en
schema desechable para concurrencia contra alta/edición y serialización; SQLite focal.
Frontend verifica confirmación/cancelación, pendiente/error/invalidation y ubicación;
typecheck/build admin y QA móvil. Regresiones focales catálogo/modificadores/presentación.
Auditoría independiente R3 registra evidencia y riesgos residuales en cierre único.

Ejecutables: apps/api/tests/test_category_delete.py y test_category_delete_postgres.py;
este último requiere SAAS_TEST_POSTGRES_URL apuntando exclusivamente a PostgreSQL de QA
y crea/migra/elimina un schema aislado por escenario. Regresión de importación en
test_legacy_import.py; el fixture usa una categoría nueva porque BEBIDAS del seed está
archivada. Casos de Excel y legacy rechazan reactivación incluso con distintas mayúsculas.

QA interactiva reproducible: node tests/browser/category-delete-fixture.mjs, abrir
http://127.0.0.1:4176/qa-category a 390x844. Editar Cafe: botón debajo de Guardar,
Cancelar conserva catálogo, confirmar deja Otra y su producto. Editar Error QA provoca
409 y conserva el editor/error. Nueva categoría y Editar portada no ofrecen eliminar.
Fixture conecta el componente real a respuestas sintéticas en memoria; no demuestra
integración desplegada. Pruebas HTTP y PostgreSQL anteriores cubren el servidor real.
