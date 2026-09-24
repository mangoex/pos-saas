# TDD — Casos de Prueba para Suspensión Manual de Período de Prueba (Trial)

## Suite: TDD-TS-297
Verificación de no-expiración automática de organizaciones en período de prueba y validación de suspensión exclusivamente manual por superadministrador.

### Casos de prueba:
- **TDD-TC-970**: Comprobación de que una organización cuya fecha de trial ya venció (`trial_ends_at < now`) conserva acceso completo a sus endpoints autenticados (`/branches`, `/catalog/products`, `/organization/profile`) y `access_block_reason` permanece en `None` (`apps/api/tests/test_manual_trial_suspension.py`).
- **TDD-TC-971**: Comprobación de que el menú digital público (`/api/v1/public/storefront-context` vía host wildcard y `/api/v1/public/branches/{key}/catalog`) permanece accesible (200 OK) aún tras vencer los 14 días iniciales (`apps/api/tests/test_manual_trial_suspension.py`).
- **TDD-TC-972**: Comprobación de que la suspensión manual por superadministrador (`subscription_status="suspended"`) bloquea de inmediato las llamadas autenticadas con 403 `tenant_suspended`, el storefront directo con 403 `storefront_unavailable` y el catálogo público por clave con 404 (`apps/api/tests/test_manual_trial_suspension.py`, `apps/api/tests/test_saas_superadmin.py`).
