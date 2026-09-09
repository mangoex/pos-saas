# Plantilla Easypanel

## Servicios iniciales

- `restaurant-os-api`: FastAPI central.
- `restaurant-os-worker`: jobs, outbox/inbox y tareas programadas.
- `postgres`: PostgreSQL 16 con volumen dedicado.
- `redis`: Redis 7 para coordinacion no durable.
- `backup-job`: respaldo automatizado fuera de la VPS.

## Variables requeridas

- `RESTAURANTOS_ENVIRONMENT`
- `RESTAURANTOS_SERVICE_NAME`
- `RESTAURANTOS_PUBLIC_BASE_URL`
- `RESTAURANTOS_PLATFORM_HOSTS`
- `RESTAURANTOS_STOREFRONT_WILDCARD_DOMAIN` (opcional; sólo el dominio base, sin `*`)
- `DATABASE_URL`
- `REDIS_URL`
- `SECRET_KEY`
- `LOG_LEVEL`

Los secretos se configuran en Easypanel, nunca en el repositorio.

## Health checks

- API live: `/health/live`
- API ready: `/health/ready`
- API version: `/health/version`

## Rollback

Cada despliegue debe conservar:

- imagen anterior,
- migracion aplicada,
- procedimiento de restauracion,
- evidencia de health check.
