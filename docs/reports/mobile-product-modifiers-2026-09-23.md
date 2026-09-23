# Corrección del editor móvil de producto — evidencia local

Base: `c231982`. Riesgo R3. Backend y cierre: agente principal; frontend: Luna;
auditoría independiente con contexto fresco: Sol. La verificación se realizó antes de publicar.
Posteriormente el usuario autorizó commit, integración y push para hacer él mismo el redeploy;
despliegue y cambios productivos no forman parte de esta publicación.

El editor anterior enviaba `surcharge`, no aceptado por el dominio, después de guardar producto y
grupo por separado. La corrección sigue PRD-FR-010/061 y los suplementos SDD/BDD/TDD del editor.
No requiere migración. El grupo vacío de un intento fallido se recupera al volver a guardar.

## Evidencia

- RED backend: `test_price_free_option_order_snapshot_and_history` falló por GET inexistente (404)
  antes de implementar el nuevo contrato. RED frontend: helper inexistente, antes de implementarlo.
- `python -m pytest apps/api/tests/test_mobile_product_modifiers.py
  apps/api/tests/test_mobile_product_modifiers_postgres.py apps/api/tests/test_saas_modifier_scope.py -q`:
  **30 passed, 2 skipped**. Los skips son PostgreSQL sin SAAS_TEST_POSTGRES_URL local; CI ya configura
  esa variable y recogerá ambos tests. SQLite en archivo sí ejercitó escritores concurrentes.
- `python -m pytest apps/api/tests/test_platform_api.py -k 'modifier or product' -q`:
  **14 passed, 69 deselected**.
- `pnpm test:mobile-product-modifiers`: pasó, incluido ahora en `test:frontend-semantic` de CI.
- `node tests/frontend/test_mobile_web_order_flow.mjs`: **15 passed**;
  `test_mobile_order_modifier_labels.mjs` y `test_admin_modifier_option_creation.mjs`: pasaron.
- `pnpm --filter @restaurantos/admin-web typecheck`: pasó.
- Antes de publicar: `pnpm --filter @restaurantos/admin-web build` pasó, incluida generación PWA;
  Vite conservó la advertencia no bloqueante de bundle superior a 500 kB.
- Ruff sobre `simple_modifiers.py`, `operations.py`, `api.py` y los dos nuevos tests Python: pasó.
- Mypy del nuevo `simple_modifiers.py` con `--follow-imports=silent`: pasó.
- `git diff --check`: pasó.
- QA navegador con API y tenant sintéticos locales, anchos 390 y 360: editor visible con papelera
  abajo a la derecha, rechazo de `Leche de avena, diez` conservando texto, guardado de cuatro opciones,
  reapertura con nombres/precios persistidos, Shift+Enter para agregar Canela gratuita, y archivo
  del producto mostrando Agotado. Se verificó el estado de carga y bloqueo durante guardado.
  El clic del diálogo nativo de archivo reportó timeout de la herramienta; el estado posterior
  confirmó que el producto quedó archivado. No se afirma un E2E concurrente en navegador.

## Auditoría R3: afirmaciones, refutación y límites

| Afirmación | Evidencia e intento de refutación | Resultado y riesgo residual |
| --- | --- | --- |
| Producto y opciones se guardan juntos | Fallo inyectado en INSERT de opción después de escribir producto; comparar producto, versiones, grupos, opciones y auditoría | Rollback completo en SQLite; réplica PostgreSQL preparada, pendiente de ejecución |
| Los precios son autoritativos y exactos | Base 4500 + opción 1000 + opción gratuita; cantidad 1/2; precio enviado por cliente manipulado; negativos, bool, texto y fracciones | Totales 5500/11000; rechazos sin cambios parciales; no se infieren consumos por nombre |
| No se sobrescribe una edición concurrente silenciosamente | Sol reprodujo pérdida de precio por cambio sólo de precio y por lista vieja con revisión nueva; regresiones de revisión, snapshot y payload de campos editados; dos escritores SQLite | Correcciones verificadas, un ganador y un conflicto; bloqueos PostgreSQL pendientes de CI |
| Se preservan alcance e historia | Tenant ajeno, grupo avanzado, override por sucursal, nombre no representable, quitar/reactivar, comparación de snapshots históricos | Rechazo o preservación; IDs estables; proyección pública y snapshot conservan tipo modifier, no comentario |

Sol cerró la revisión final sin hallazgos bloqueantes dentro del alcance. Se corrigieron también sus
hallazgos de distintivo promocional nulo y controles que impedían guardar precios como 12.99.

## Gates generales preexistentes y pendientes

- Trazabilidad: **3 fallos, 5 pases** en HEAD original, reproducidos en una extracción limpia antes
  del cambio: matriz referencia PRD-FR-740 ausente y duplicados BDD-SC-819..822/TDD-TC-259..262
  entre las suites móviles. La corrección no agrega IDs duplicados ni oculta esos fallos.
- Mypy de operations/api: **37 errores preexistentes** en HEAD, fuera del cambio. El nuevo módulo
  está limpio. No se agregaron silenciamientos, exclusiones ni tests desactivados.
- No se ejecutó CI remoto ni suite completa local. La verificación fue dirigida; la suite aplicable
  completa corresponde al CI configurado. No se presenta el paquete como release con todos los
  gates verdes mientras sigan pendientes PostgreSQL/CI y los gates generales anteriores.
- Canary autorizado posterior: abrir producto afectado, guardar opciones, reabrir y verificar pedido
  de prueba con base 45 + extra 10 = 55 y opción gratuita; observar auditoría y códigos de error.
  Cualquier venta de prueba debe corregirse por compensación normal, nunca editando historia.
- Despliegue debe incluir API y admin juntos: el editor nuevo requiere el GET y payload nuevos.
  Los clientes anteriores siguen omitiendo el campo opcional; los datos usan el esquema existente.
