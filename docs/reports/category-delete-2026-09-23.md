# CAT-DELETE-001 — Evidencia local, 2026-09-23

R3, base main 078a09d. PRD-FR-010, BDD-SC-948..952 y TDD-TS-294.
Botón debajo de Guardar en editor móvil; confirmación explícita de categoría y productos.
El catálogo es organizacional: afecta todas las sucursales del mismo restaurante.
Archivado transaccional, sin migración ni borrado de referencias históricas.

## Evidencia y refutaciones

| Afirmación | Evidencia / intento de refutación | Resultado / riesgo residual |
| --- | --- | --- |
| Sólo afecta productos de esa categoría y organización | DELETE HTTP, categoría ajena con mismo nombre, actor sin permiso, comparación de otras filas | 9 pruebas focales aprobadas; no ejecutado sobre datos reales |
| Conserva historia y es atómico/idempotente | Pedido existente conserva líneas/total/estado; precios conservados; repetición produce una auditoría; falla inyectada de auditoría revierte cambios | Aprobado; recuperación administrativa compensatoria fuera del alcance, no hay botón Deshacer |
| No quedan productos vendibles por carreras o formularios viejos | PostgreSQL real con migraciones en schema desechable: delete vs create, create vs delete, move vs delete; PUT/DELETE obsoletos rechazados | 3 pruebas PostgreSQL aprobadas; bloqueo por organización serializa escrituras de catálogo, carga masiva no medida |
| Importar no revive productos eliminados | Excel sintético con categoría/producto archived, legacy con variantes de nombre; regresión de importación idempotente | Guardas y pruebas aprobadas; nombres archivados siguen reservados, incluidas variantes de mayúsculas |
| UI no elimina sin confirmación y preserva errores | Navegador a 390x844 con componente real y backend sintético: cancelar, confirmar, error409, nueva categoría y portada | Verificado; no sustituye prueba del despliegue con API real |

## Gates

- `pytest apps/api/tests/test_category_delete.py -q`: 9 passed.
- `SAAS_TEST_POSTGRES_URL` local + `pytest apps/api/tests/test_category_delete_postgres.py apps/api/tests/test_legacy_import.py -q`: 6 passed (3 + 3).
- Regresión focal inicial: eliminación, presentación de categorías y modificadores móviles: 60 passed; ampliación posterior de eliminación: 9 passed.
- Semánticas frontend: admin-category-options, admin-modifier-option-creation y mobile-product-modifiers aprobadas.
- Admin typecheck/build aprobados; advertencia existente de bundle mayor de 500 kB.
- Ruff focal y `git diff --check` aprobados.
- Mypy focal (`--follow-imports=silent --no-incremental`) en cinco módulos: 39 errores previos en operations/api/real_catalog_loader; comparación con versiones HEAD mediante shadow files arroja los mismos 39 diagnósticos. Ningún diagnóstico nuevo; el gate absoluto no está verde. category_deletion y legacy_import sin errores propios.
- Trazabilidad global: 3 failed, 5 passed; fallos previos PRD-FR-740 sin definición y duplicados BDD-SC-819..822/TDD-TC-259..262. No se silencian ni se modifican pruebas.
- Auditoría independiente Sol: cerrados hallazgos de reactivación por importador y reserva de nombres; sin bloqueantes nuevos. Auditor repitió 9 pruebas focales y 3 PostgreSQL, todas aprobadas.

Evidencia registrada antes de publicación; CI y despliegue no certificados aquí.
El usuario autorizó commit, integración en main y push después del cierre local.
No se ejecutaron comandos
sobre datos productivos. Canary pendiente antes de certificar comportamiento productivo;
usar categoría sintética vacía y otra con producto sintético sin ventas, comprobar que
otra categoría permanece y que existe `category.deleted` con actor/IDs correctos.
No hace falta nueva migración; rollback de código no restaura categorías archivadas.
