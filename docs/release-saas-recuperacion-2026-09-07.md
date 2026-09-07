# Release SaaS recuperado: preparación operativa

Rama de integración: codex/saas-recovery-integration. Base publicada cee907b. Este documento prepara una operación; no autoriza ni registra despliegue.

## Antes de producción

1. Confirmar origen Git/rama/imagen exactos de pos-saas y que el dominio SaaS enruta a ese servicio. Verificar host PostgreSQL real: captura pos-postgres, respuesta previa pos-saas; no ejecutar migración hasta resolverlo. Redis/volúmenes/credenciales deben ser propios del SaaS.
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
