# TDD: Consolidación y Control de Roles en Terminal POS (Versión Lite)

## Cobertura y Estrategia de Verificación

Suite de verificación semántica y estructural del frontend POS para roles y tarjetas operativas.

- **Suite**: `TDD-TS-POS-001`
- **Fichero de prueba**: `tests/frontend/test_pos_lite_consolidation.mjs`

---

### Casos de Prueba

#### TDD-TC-POS-001: Guarda de visibilidad de Administración en PosLayout
- **Requisito**: BDD-SC-POS-001, BDD-SC-POS-002
- **Verificación**: `PosLayout.tsx` restringe el elemento de navegación "Administración" a `branch.admin.access` o `admin.manage`, asegurando que permisos secundarios como `cash.user_cut.read` o `recipes.manage` no abran la puerta administrativa a cajeros.

#### TDD-TC-POS-002: Exclusión de tarjetas ERP en AdminHub
- **Requisito**: BDD-SC-POS-003, BDD-SC-POS-004
- **Verificación**:
  1. `AdminHub.tsx` no incluye tarjetas con enlaces hacia:
     - `/administration/production`
     - `/administration/transfers`
     - `/administration/counts`
     - `/historical-reports`
  2. `AdminHub.tsx` conserva las tarjetas operativas clave:
     - `/sales-monitor`
     - `/administration/products`
     - `/administration/waste`
     - `/administration/purchases`
     - `/administration/suppliers`
     - `/administration/attendance`
