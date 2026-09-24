# BDD — Suspensión Manual de Período de Prueba (Trial)

## Feature: Permanencia del Servicio tras Vencimiento del Período de Prueba

Como dueño de restaurante o administrador del sistema
Quiero que el servicio, catálogo y menú digital sigan funcionando activamente aún después de cumplirse los 14 días de prueba
Para que la suspensión del servicio sea deliberada y manual, evitando afectaciones no deseadas a los negocios

### Escenario: BDD-SC-970 Acceso operativo y catálogo de tenant con prueba transcurrida
- **Dado** una organización registrada en la plataforma con estado de suscripción `trialing`
- **Y** cuya fecha `trial_ends_at` se encuentra en el pasado (más de 14 días desde el registro)
- **Cuando** el usuario consulta su perfil (`GET /api/v1/organization/profile`) o el listado de sucursales (`GET /api/v1/branches`)
- **Entonces** la respuesta es exitosa (código HTTP 200)
- **Y** `access_block_reason` es `None` (sin bloqueo automático).

### Escenario: BDD-SC-971 Menú digital público accesible tras transcurrir los 14 días
- **Dado** una organización en estado `trialing` con fecha de prueba en el pasado
- **Cuando** un comensal ingresa al menú digital a través de su subdominio (`https://marimba.mimenu.onl`)
- **O** consulta el catálogo público mediante su clave (`GET /api/v1/public/branches/{public_key}/catalog`)
- **Entonces** el storefront responde exitosamente (código HTTP 200)
- **Y** el comensal puede visualizar los platillos y realizar pedidos sin error `storefront_unavailable`.

### Escenario: BDD-SC-972 Suspensión explícita por superadministrador
- **Dado** una organización cuyo estado es modificado manualmente por un superadministrador a `subscription_status = "suspended"`
- **Cuando** el usuario intenta operar en la plataforma
- **Entonces** las peticiones autenticadas son rechazadas con código HTTP 403 y código de error `tenant_suspended`
- **Y** las peticiones al storefront directo son denegadas con código HTTP 403 `storefront_unavailable`
- **Y** las peticiones al dominio wildcard responden 404 `domain_unavailable` sin exponer detalles internos.
