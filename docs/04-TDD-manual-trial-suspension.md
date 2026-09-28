# TDD â€” Casos de Prueba para SuspensiÃ³n Manual de PerÃ­odo de Prueba (Trial)

## TDD-TS-297
VerificaciÃ³n de no-expiraciÃ³n automÃ¡tica de organizaciones en perÃ­odo de prueba y validaciÃ³n de suspensiÃ³n exclusivamente manual por superadministrador.

### Casos de prueba:
### TDD-TC-970
ComprobaciÃ³n de que una organizaciÃ³n cuya fecha de trial ya venciÃ³ (`trial_ends_at < now`) conserva acceso completo a sus endpoints autenticados (`/branches`, `/catalog/products`, `/organization/profile`) y `access_block_reason` permanece en `None` (`apps/api/tests/test_manual_trial_suspension.py`).
### TDD-TC-971
ComprobaciÃ³n de que el menÃº digital pÃºblico (`/api/v1/public/storefront-context` vÃ­a host wildcard y `/api/v1/public/branches/{key}/catalog`) permanece accesible (200 OK) aÃºn tras vencer los 14 dÃ­as iniciales (`apps/api/tests/test_manual_trial_suspension.py`).
### TDD-TC-972
ComprobaciÃ³n de que la suspensiÃ³n manual por superadministrador (`subscription_status="suspended"`) bloquea de inmediato las llamadas autenticadas con 403 `tenant_suspended`, el storefront directo con 403 `storefront_unavailable` y el catÃ¡logo pÃºblico por clave con 404 (`apps/api/tests/test_manual_trial_suspension.py`, `apps/api/tests/test_saas_superadmin.py`).

Autofacturación: `test_self_invoice_respects_manual_suspension_after_trial` verifica consulta y emisión simulada tras vencer trial, y cero llamadas al proveedor tras suspensión manual. Las fechas de validez fiscal del ticket permanecen independientes.
