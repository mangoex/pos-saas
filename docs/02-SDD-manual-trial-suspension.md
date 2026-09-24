# SDD — Política de Suspensión Manual de Período de Prueba (Trial)

## Contexto y Problema

Previamente, al cumplirse los 14 días iniciales de prueba (`trial_ends_at <= now()`), el sistema ejecutaba bloqueos automáticos en cascada:
1. `public_storefront.py` denegaba con 403 `storefront_unavailable` el acceso al menú digital y contexto del restaurante.
2. `operations.py` (`_trial_access_expired`) arrojaba 403 `tenant_trial_expired` en llamadas autenticadas (sucursales, usuarios, catálogo).
3. `api.py` (`_resolve_active_public_order_key`) invalidaba la clave pública del menú arrojando 404 `public_branch_not_found`.
4. El perfil de la organización (`GET /api/v1/organization/profile`) establecía `access_block_reason = "tenant_trial_expired"`.

Esto provocaba la falsa impresión de que los datos del negocio (como `https://marimba.mimenu.onl`) se habían eliminado o borrado, cuando en realidad la base de datos conservaba íntegra toda la información pero el acceso quedaba interrumpido automáticamente.

La regla de negocio definida por dirección establece que **no se suspende el servicio automáticamente por transcurso de tiempo**. La suspensión debe ser **única y deliberadamente manual** por parte de un superadministrador.

## Decisiones Técnicas y Arquitectura

1. **Eliminación de la Expiración Automática en Runtime (`operations.py`):**
   - La función interna `_trial_access_expired(subscription_status, trial_ends_at)` retorna incondicionalmente `False`.
   - En `get_organization_profile`, `access_block_reason` se asigna exclusivamente como `"tenant_suspended"` cuando `subscription_status == "suspended"` o `status == "suspended"`. Se retira la rama que asignaba `"tenant_trial_expired"` basada en días restantes.

2. **Acceso al Menú Digital y Storefront Público (`public_storefront.py`):**
   - La resolución del storefront público (`resolve_storefront`) evalúa únicamente que `org["status"] == "active"` y `org["subscription_status"] != "suspended"`.
   - Se removió la condición restrictiva `(org["subscription_status"] == "trialing" and (trial_end is None or trial_end <= now))`.
   - Si una sucursal tiene más de 14 días en estado `trialing`, su menú digital (`https://{slug}.mimenu.onl`) continúa plenamente visible y operativo.

3. **Resolución de Claves Públicas de Pedido (`api.py`):**
   - En `_resolve_active_public_order_key`, se eliminó el bloqueo que evaluaba `trial_ends_at <= now()`.
   - Los catálogos públicos (`/api/v1/public/branches/{key}/catalog`) y generación de pedidos operan sin interrupción a menos que la organización o sucursal sea suspendida manualmente.

4. **Integraciones Salientes (`integrations/service.py`):**
   - `_outbound_permitted` permite comunicación en organizaciones con suscripción `trialing` sin importar la fecha, denegando únicamente si el estado de suscripción es `suspended`.

5. **Mecanismo Exclusivo de Suspensión:**
   - La suspensión sólo se activa mediante intervención explícita de un superadministrador mediante `subscription_status="suspended"` o `status="suspended"` en la tabla `organizations`.

## Invariantes Preservadas

- Inmutabilidad de datos históricos: ninguna información de catálogo, pedidos, turnos o sucursales se destruye.
- Multi-tenancy estricto: la seguridad y el aislamiento entre organizaciones permanecen intactos.
- Coherencia defensiva en subdominios: las peticiones con host wildcard para organizaciones suspendidas retornan 404 `domain_unavailable` para no exponer metadatos de ciclo de vida a escaneos externos, mientras que el endpoint directo retorna 403 `storefront_unavailable`.
