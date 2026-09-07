# Recuperación SaaS R3

Base GitHub cee907b; fuente local 109c672 con cambios sin publicar preservada. Backup verificado: ../pos-saas-backups/sol-working-tree-20260907-075357.zip (824 archivos, SHA256 8c4b0652006d40ebf62d1f442165d85fdfc3ff9cb5eb52d83879ea42a4d73c2a). No incluye dependencias regenerables; conserva archivos versionados, trabajo no ignorado y .env raíz/API si existen.

Paquetes: seguridad/tenant; identidad/migraciones; frontend/onboarding; integración idempotente; gates/revisión independiente. Terra frontend e integraciones trabajan en directorios disjuntos; principal reconcilia API/modelo/migración; Sol audita al cierre. No despliegue, configuración ni migración productivos autorizados.

Preguntas operativas: ¿qué tenant/actor resolvió la petición?, ¿por qué falló alta o checkout?, ¿qué evento externo quedó confirmado o pendiente de reintento?, ¿qué SHA/esquema atiende el dominio? Logs deben responder con códigos/correlación sin payloads personales ni credenciales.

Evidencia y afirmaciones R3 se registrarán aquí por paquete. Los 735 passed históricos no certifican esta rama.

## Decisiones confirmadas

La matriz publicada no corresponde al PRD SaaS (baseline cee907b: test_traceability 1 failed,7 passed). Se recupera la separación de IDs históricos +500 ya realizada localmente para no atribuir pruebas ERP a requisitos SaaS. Las ampliaciones fiscales de seguridad se mantienen como paquete separado porque la ruta autofactura continúa expuesta y depende de los comandos durables; no añaden un requisito fiscal al onboarding ni nuevas funciones comerciales.

R3 revisión: contraejemplo tenant pre-0066 con trial/active/NULL bloquearía por normalización indiscriminada. Corrección: sólo normalizar trials con fecha emitida; legacy sin fecha conserva estado y requiere decisión comercial explícita, no regalar ni recortar prueba automáticamente. Regresión de migración cubre ambos registros y conserva slug/clave.

## Evidencia del ciclo R3

- RED supervisor/kill-switch: 2 fallos funcionales sobre cee907b; recuperación de guardas validada en paquete50passed (storefront, public intents, caja y autofactura).
- RED boundaries:4fallos demostraron flag implícito/SQL público; GREEN4passed tras configuración explícita y código/correlation_id saneados.
- Registro/wizard/migraciones:17passed con PostgreSQL16 y rollback compatible0069; identidad SQLite conserva slug/keys y trials legacy. QR/registro remoto preservados con aliases de plan normalizados a starter_349/pro_599 y contraseña8 mínima.
- Revisión Sol independiente: cinco hallazgos cerrados (legacy trial NULL, clave revoked, eventos ignorados lease zombie, políticas autofactura y excepción pública). Autofactura7passed; inbox/lease PG+noorder12passed; DiDi/Rappi/config/outbox17passed. Payloads sintéticos, sin llamadas a proveedores productivos.
- Frontend semántico completo aprobado; typecheck admin/mobile/POS y builds afectados aprobados por Terra. QA visual en navegador detectó nombres de plan y avance de menú pendiente: no se confunde semántica de fuentes con E2E.
- Arquitectura148casos:144passed inicialmente; cuatro expectativas reconciliadas con tarjetas de modificadores y entrypoint real. Focales31passed y27passed después, sin exclusiones.
- Mypy baseline cee907b128errores; integración79, sin diagnósticos nuevos comparando archivo/mensaje. No es green global ni se añadieron ignores. Ruff apps/api+tests aprobado.
- Datos sintéticos de pruebas y servicios CI/Compose: procedencia y hashes exactos actualizados conforme al gate existente; ninguna excepción de runtime ni prueba desactivada. Se retiraron17type-ignore de la fixture superadmin usando estado de test de FastAPI.
- Se encontraron tres sesiones locales QA del4septiembre con transacciones/bloqueos abiertos durante casi3días; se cerraron sólo esos pids en PGloopback55432/base saas_remediation_qa después de verificarlos. Ninguna conexión productiva intervenida.

- QA navegador aislado confirmó negocio→menú persistido→QR→caja CAJA-QA-03→completar y recarga sin wizard. Cierre móvil recupera imágenes propias/artwork neutro; elimina nutrición inferida, preferencias de sucursal globales y código muerto de selección por nombre. Acepta ruta publicada /menu/{slug} y muestra error/reintento de catálogo. Regresión de fotos RED→GREEN y12pruebas móviles aprobadas.

- QA real /menu/bistro-wizard-final-qa-54605d/ detectó assets relativos y pantalla vacía con diagonal final. Base Vite /menu/ corregida; recarga muestra título propio y tres productos del catálogo sintético, sin fotos heredadas. CI inicial baae9a8: frontend completo, Docker e integridad aprobados; revisión de dependencias bloqueada por Dependency graph no disponible/habilitado en GitHub (no vulnerabilidad detectada). No se desactiva el gate.
