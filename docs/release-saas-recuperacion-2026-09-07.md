# Release SaaS recuperado: preparación operativa

Rama de integración: codex/saas-recovery-integration. Base publicada cee907b. Este documento prepara una operación; no autoriza ni registra despliegue.

## Antes de producción

1. Origen, dominio y PostgreSQL verificados abajo mediante EasyPanel y consultas de sólo lectura. Confirmar SHA de imagen durante el corte y corregir Redis con su credencial propia; no desplegar con el host genérico redis.
2. Registrar SHA y `alembic current`; la nueva cadena conserva0069 publicada y añade0070..0080. No aplicar el antiguo árbol local ni revertir0069, que elimina slug.
3. Backup consistente PostgreSQL y volúmenes; ensayar restauración fuera de producción. Inventariar slugs actuales, sucursales sin historial de keys, keys revocadas y trials sin fecha. No publicar listados con datos de clientes.
4. Preflight de duplicados pedidos externos por organización/proveedor/ID, identidad pública ambigua y conflictos de slugs.0080 rechaza duplicados antesDDL; reconciliación de datos requiere decisión auditada separada.
5. Migración0070 conserva slugs emitidos, genera identidad sólo donde falta, emite key inicial sólo cuando sucursal no tiene historial de claves; nunca revive revoked. Trials con fecha pasan a trialing; legacy sin fecha conserva estado, sin inventar duración ni cobro. Revisar conteo de nuevas keys y su adopción explícitamente antes de migrar.
6. Configurar bandera explícita de pedidos públicos y Redis/secretos de producción. Docker declara la bandera en imagen; EasyPanel debe mostrar el valor efectivo, no depender de detección por STATIC_DIR/DATABASE_URL. Provisión superadmin por CLI con credencial única; revisar cuenta heredada y rotación de credenciales con autorización.
7. Iniciar trabajador `restaurant_os.uber_availability_worker` con la misma imagen y base/Redis del SaaS. API registra pending_confirmation; no afirmar sincronización Uber sólo por guardar configuración.
8. Desplegar y migrar sólo tras autorización del usuario; observar errores por correlation_id y pending/retry. Canary con dos restaurantes sintéticos/consentidos: registro, plan/trial, wizard reanudado, menú/QR, producto propio, pedido web→POS→KDS y reintento sin duplicar. Nunca enviar pedidos reales a proveedores sin canary acordado.

## Reversión

Antes de rollback, drenar workers y preservar inbox/outbox/comandos fiscales pendientes. Las migraciones aditivas conservan identidades y hechos: no eliminar filas, pagos ni estados fiscales. Si existen eventos posteriores al corte, restaurar backup requiere compensación/reconciliación antes de reabrir tráfico; una imagen anterior no demuestra compatibilidad de esquema. Validar rollback en copia. Mantener0069 como mínimo compatible para URL pública; no regresar a0068.

## EasyPanel

Kiwi Pro y POS-SaaS pueden vivir en una VPS con servicios/datos independientes. Proyectos separados reducen errores operativos; mover servicios no corrige el aislamiento de tenant. No es necesario un contenedor/proyecto por restaurante. La separación de VPS depende de capacidad y disponibilidad.

## Límites del cierre local

Git y pruebas locales/CI no prueban el SHA publicado. `/health/version` observado originalmente devolvió commit unknown. Registrar SHA completo como metadato y contrastar imagen real. DiDi/Rappi permanecen configuraciones pendientes; una cuenta aprobada no equivale a contrato implementado y certificado.

La imagen infra/docker/api.Dockerfile ejecuta entrypoint.sh y éste corre `alembic upgrade head` antes de Uvicorn. Por ello un redeploy de esa imagen también ejecutaría las migraciones: ambos pasos necesitan autorización productiva conjunta y preflight previo. El Dockerfile raíz tiene un arranque diferente; confirmar cuál utiliza EasyPanel.

## Verificación efectiva de EasyPanel, 7 septiembre 2026

- Servicio `paperclip/pos-saas`, Git `https://github.com/mangoex/pos-saas`, rama `main`, contexto `/`, archivo `infra/docker/api.Dockerfile`. El redeploy de esta imagen ejecuta migraciones automáticamente.
- Dominios `paperclip-pos-saas.yroec7.easypanel.host`, `posrestaurant.yroec7.easypanel.host` y `pos.humanio.digital` apuntan a `http://paperclip_pos-saas:8000/`.
- Proceso: `DATABASE_URL` apunta a `paperclip_pos-postgres:5432`; consulta read-only confirma base `postgres`, esquema `public`, revisión `0069_add_slug_to_organizations_and_branches`. Hay credencial configurada y no fue registrada en este reporte.
- Error confirmado: `REDIS_URL` tiene host `redis:6379/0` sin credencial; DNS devuelve gaierror y PING ConnectionError. `paperclip_pos-redis` sí resuelve y devuelve AuthenticationError sin contraseña. Cambio productivo propuesto: URL al host `paperclip_pos-redis`, puerto6379, base0, con la credencial existente de ese servicio, codificada correctamente. No se aplicó.
- Bandera `RESTAURANTOS_PUBLIC_ORDER_INTENTS_ENABLED=true` y entorno production confirmados. No se observó un servicio worker de disponibilidad en el listado del proyecto; provisionar el worker del release bajo autorización.
- La pantalla de almacenamiento de la aplicación no lista montajes ni backups de volumen. Esto no prueba ausencia de persistencia en los servicios PostgreSQL/Redis, cuyos volúmenes deben incluirse en el backup del corte.
- Preflight SQL read-only:0 organizaciones sin slug;1 sucursal activa sin historial de claves (0070 emitiría una clave inicial);0 claves revoked;0 trials con fecha para normalizar;2 trials legacy active sin fecha que la migración conserva;0 grupos duplicados de pedidos externos. Repetir los conteos inmediatamente antes del corte.
- Compartir el proyecto paperclip no mezcla automáticamente los datos: aplicación y PostgreSQL SaaS están separados de los servicios Kiwi. El fallo de resolución de menú era de aplicación; Redis es un segundo problema real de configuración. Proyectos separados siguen siendo una mejora operativa, no un prerrequisito de aislamiento por restaurante.

Sólo se consultaron configuración, DNS, PING y SELECT en transacción read-only. No se cambió entorno, no hubo reinicio, despliegue, migración ni escritura de datos productivos.

La pantalla Copias de seguridad de pos-postgres informa que no hay copias de base de datos en este momento. No se concluye que no existan respaldos externos; antes del corte debe generarse y comprobarse uno consistente y restaurable.
