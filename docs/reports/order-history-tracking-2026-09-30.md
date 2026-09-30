# Historial y seguimiento de pedidos: evidencia local

Fecha: 2026-09-30. Riesgo R3 por integridad histórica y aislamiento de sucursal.
Base: `5ae82274ea397a40db5a1daa84cdea96f64f8379` (`main`, actualizado desde origin).
Rama local: `codex/fix-order-history-tracking`, en el worktree `saas-completed-fixes`.
El checkout original y sus 170 archivos modificados/no rastreados se preservaron.

## Resultado y autoridad

El historial conserva intenciones antiguas; listar y contar ya no expira registros.
Se preserva `EXPIRED` en el detalle y se bloquean controles de aceptación y cobro para ese estado.
La paginación conjunta es acotada y distingue pedidos/intenciones en empates. El monitor conserva
las páginas solicitadas y descarta respuestas de otra sucursal. El tracker detiene estados
terminales, evita requests solapados y descarta respuestas tras desmontarse o cambiar de sucursal.

Se restauró la autoridad funcional existente: no se activó un cambio de PRD. Se actualizaron SDD,
BDD-SC-390/987/988, TDD y sus relaciones en la matriz, sin elevar estados históricos de evidencia.
No hay migración, compensación, edición de movimientos históricos ni nuevos logs sensibles.

## Afirmaciones R3 e intento de refutación

| Afirmación | Evidencia e intento de refutación | Resultado y límite |
| --- | --- | --- |
| Una lectura no altera historia | Captura SQL y comparación integral de registros antiguos PENDING_REVIEW, REJECTED y EXPIRED; consultar listado, conteo y detalle | Regresión verde; el RED inicial detectó la escritura anterior. No repara expiraciones ya guardadas. |
| La paginación no omite empates ni cruza autoridad | Mismo timestamp e ID en ambas tablas, límite 1, filtros/cursor incompatibles, otro tenant/sucursal y folio público | SQLite verde; comparación de SQL compilado SQLite/PostgreSQL en auditoría. PostgreSQL real pendiente. |
| Un resultado tardío no contamina otra sucursal ni continúa después del cleanup | Promesas diferidas, cambio A→B, terminal junto a otro pedido activo y request lento | Harnesses verdes; no representan pérdida de red ni carga productiva. |
| EXPIRED no ofrece aceptación/cobro | Render de componente real y revisión visual con respuestas sintéticas; RED adicional detectó selector de cobro sobrante | Regresión verde y selector oculto; revisión independiente confirmó la guardia exclusiva EXPIRED. |

## Verificación

- Backend focal: **58 passed, 2 skipped**, con dos advertencias preexistentes Starlette/httpx.
  Comando: `python -m pytest apps/api/tests/test_order_history.py apps/api/tests/test_public_order_intents.py apps/api/tests/test_order_reopen_workflow.py apps/api/tests/test_order_reopen_contracts.py apps/api/tests/test_dine_in_configuration.py tests/integration/test_order_ready_flow.py tests/architecture/test_traceability.py -q`.
  Se usó el Python del `.venv` del checkout original y código del worktree limpio.
- Frontend: `pnpm test:frontend-semantic` terminó con exit 0. Las nueve regresiones nuevas están
  incluidas en ese script; tras el ajuste visual final se repitieron focalmente: **9/9 verdes**.
- TypeScript admin/mobile: `pnpm --filter @restaurantos/admin-web typecheck` y
  `pnpm --filter @restaurantos/mobile-web typecheck`, verdes.
- Preparación para publicación Git: `pnpm --filter @restaurantos/admin-web build` y
  `pnpm --filter @restaurantos/mobile-web build`, ambos exit 0, incluida generación PWA.
  Administración conserva una advertencia de chunk superior a 500 kB.
- Ruff en operaciones y pruebas Python afectadas; mypy de `restaurant_os/operations.py`, verdes.
- `python scripts/repository_policy.py .` y `git diff --check`, verdes.
- QA Playwright de componentes reales con API sintética de sólo lectura: historial y detalle
  en 390×844; detalle en 1280×900; tracker EXPIRED en 390×844. Evidencia local en `output/playwright/`.
- Auditoría Sol independiente R3 cerrada sin hallazgos bloqueantes; confirmó aislamiento,
  ausencia de DML en lecturas, cursor portátil y el ajuste final del modal.

La política del repositorio falló inicialmente por el hash desactualizado del fixture sintético
`apps/api/tests/test_saas_superadmin.py`, modificado previamente en origin. Tras revisar íntegramente
su uso de TestClient/SQLite efímero, se renovó sólo el hash exacto de su entrada existente. No se
añadieron exclusiones, silenciamientos ni cambios al scanner o al fixture.

## Límites y publicación

Los dos casos PostgreSQL se omitieron por ausencia de instancia configurada. No se corrió la suite
Python completa ni un canary; el alcance se verificó con regresiones focales y builds de los dos
frontends afectados. La QA visual usa datos sintéticos, no una API productiva. Al cierre técnico
inicial no había evidencia de CI ni publicación Git para este diff. El usuario autorizó después
commit, integración en main y push; sus hashes y confirmación remota se informan en el cierre Git.
CI sólo se dispara por pull_request o workflow_dispatch, no por un push directo a main.
No se realizó despliegue ni operación de datos/configuración productivos.
La reversión del paquete es por código; no requiere migración ni compensación de datos.
