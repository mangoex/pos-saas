# TDD: Consolidación y Simplificación del Panel de Administración (Versión Lite)

## Cobertura y Estrategia de Verificación

Suite de verificación semántica y estructural de componentes UI para la versión Lite.

- **Suite**: `TDD-TS-LITE-001`
- **Fichero de prueba**: `tests/frontend/test_admin_lite_consolidation.mjs`

---

### Casos de Prueba

#### TDD-TC-LITE-001: Exclusión de Recetas en CatalogHub
- **Requisito**: BDD-SC-LITE-001
- **Verificación**: `CatalogHub.tsx` no incluye tarjeta de `/recipes`, enfocándose exclusivamente en Productos, Categorías y Modificadores de menú.

#### TDD-TC-LITE-002: Exclusión de Importaciones Masivas en AdminAccessHub
- **Requisito**: BDD-SC-LITE-002
- **Verificación**: `AdminAccessHub.tsx` no incluye tarjeta de `/imports`.

#### TDD-TC-LITE-003: Reubicación de Conceptos de Caja en ReportsHub y CategorySubNav
- **Requisito**: BDD-SC-LITE-003, BDD-SC-LITE-004
- **Verificación**:
  1. `BranchesHub.tsx` no exporta tarjeta de `/cash-concepts`.
  2. `ReportsHub.tsx` contiene tarjeta de `/cash-concepts` sujeta a permisos de caja.
  3. `CategorySubNav.tsx` incluye `/cash-concepts` en la lista de items de `/reports-hub` y no en `/branches-hub`.
  4. `AdminLayout.tsx` asocia `/cash-concepts` a `matchingPrefixes` de `/reports-hub`.

#### TDD-TC-LITE-004: Desacoplamiento de Canales de Delivery e Invoicing
- **Requisito**: BDD-SC-LITE-005, BDD-SC-LITE-006
- **Verificación**:
  1. `BranchesHub.tsx` cuenta con tarjeta dedicada a "Canales de Delivery (Uber Eats, DiDi Food, Rappi)" apuntando a `/integrations`.
  2. `BranchesHub.tsx` cuenta con tarjeta dedicada a "Facturación Electrónica (SAT CFDI 4.0)" apuntando a `/invoicing` (o `/integrations?provider=FACTURAPI`).
  3. `App.tsx` registra ruta protegida hacia la gestión de facturación fiscal.
