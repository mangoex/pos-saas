# Enlaces y dominios de restaurantes — R3

Base: 08639f2. Autorización: «Adelante» al diseño de enlaces, alias y dominios con
activación supervisada. Implementación y PR; configurar dominios/DNS/TLS reales y
migrar producción requiere el gate GOV-REL-001 de este paquete.

Secuencia: contrato → regresiones → persistencia/API → pantalla → revisión Sol → CI.
Se conserva el trabajo original de Sol y los informes locales de la recuperación.

Decisión: el slug canónico es inmutable. Un alias preferido nuevo no elimina los
anteriores. El dominio propio redirige su raíz al menú canónico en el mismo origen;
Admin/POS/KDS siguen en sus rutas actuales y requieren sesión de esa organización.
No se crean servicios ni bases por cliente. Inicialmente EasyPanel/TLS se configura
manualmente; un superadministrador confirma esta operación y revalida TXT al activar.

Operación: ¿qué dominios esperan DNS/TLS? listado con estado y fecha; ¿por qué falló
una verificación? código estable y evento de auditoría sin TXT; ¿quién activó o
desactivó? auditoría por organización y actor. La baja conserva la reserva del nombre,
no permite su apropiación automática por otra organización.

Validación: API dos tenants, alias históricos/colisiones, Host/token/clave contradictorios,
TXT incorrecto/timeout, activación por administrador de restaurante rechazada;
migración PostgreSQL y downgrade protegido con historial, UI semántica/build/QA visual.
La revisión adversarial y resultados exactos se registran al cierre aquí.

## Evidencia y revisión

- RED: endpoint `/saas/links` devolvió 404 antes de implementar (1 fallo esperado).
- Local: 46 pruebas de dominios/registro/superadmin; 30 de
  dominios/storefront/wizard/trazabilidad en la fase anterior; 6 de wizard/health.
- PostgreSQL 16.15 local: roundtrip 0080→0081→0080→0081 vacío, concurrencia entre
  dos restaurantes por dominio/alias y alias contra código de sucursal; downgrade con
  reservas rechaza y conserva datos. Canary de migraciones anterior también pasó.
- Typecheck y build Admin aprobados; tres contratos frontend de recuperación/enlaces
  aprobados. Mypy de los cuatro módulos nuevos sin errores; Ruff focal aprobado.
- QA navegador local con datos sintéticos: inicio de sesión, cuatro accesos, alias
  actualizado conservando URL permanente, solicitud dominio e instrucciones TXT/CNAME.
  Escritorio y móvil 390×844; se añadió viewport y navegación compacta en estas pantallas.
- Revisión Sol independiente: dos hallazgos corregidos, dos regresiones independientes
  aprobadas; sin blockers restantes. CI y publicación se registran en el PR.

Afirmación: un alias impreso no se invalida por otro tenant. Evidencia/refutación:
alta/rename de sucursal y generador de slug forzado al alias, más carrera PostgreSQL.
Resultado: un ganador o 409, URL histórica 200. La misma exclusión advisory por nombre
se aplica a todos los asignadores de slug y escrituras de código dinámico. SQLite se
verifica funcionalmente; la concurrencia productiva corresponde a PostgreSQL.

Afirmación: Host no concede acceso a otro tenant. Refutación: token, login, slug y clave
POST de otro tenant; añadir dominio activo al CSV de plataforma. Resultado: 403/404;
ninguna operación cruzada. Health está exento y no entrega datos de restaurantes.

## Activación operativa (pendiente de autorización productiva)

1. Respaldar PostgreSQL, desplegar el paquete revisado y migrar a 0081.
2. Configurar `RESTAURANTOS_PUBLIC_BASE_URL=https://pos.humanio.digital` y
   `RESTAURANTOS_PLATFORM_HOSTS=pos.humanio.digital,paperclip-pos-saas.yroec7.easypanel.host,posrestaurant.yroec7.easypanel.host`.
   Conservar todos los hosts compartidos reales; no agregar dominios de clientes al CSV.
   No vaciar este ajuste mientras existan dominios registrados en el proxy.
3. Propietario solicita el hostname en Admin → Enlaces y dominio. Publica CNAME al
   destino indicado y TXT en el nombre completo independiente. El panel DNS puede pedir
   sólo la parte relativa a su zona. Para dominio raíz usar A a la IP vigente o soporte
   de flattening del proveedor; no sustituir registros existentes sin revisar su propósito.
4. Verificar DNS. El token TXT es persistente para una reserva que nunca se recicla;
   es una prueba pública de propiedad, no una credencial de sesión. Cada activación
   vuelve a consultarlo; no se escriben tokens en auditoría. No hay expiración o rotación
   automáticas en esta versión. El cliente debe conservar el TXT.
5. Operador agrega hostname al servicio pos-saas de EasyPanel, destino HTTP interno
   puerto 8000, HTTPS/certificado; comprueba certificado y `/health/live`. El menú puede
   responder 404 hasta activarlo, deliberadamente. No crear otro servicio/base por cliente.
6. Superadmin abre `/admin/superadmin/domains`, confirma ruta/TLS y activa. La API
   revalida TXT y sólo permite un dominio activo por organización. Comprobar raíz→menú,
   instalación móvil, login del tenant y rechazo del segundo tenant antes de entregarlo.
7. Para desactivar, usar el comando auditado y retirar ruta/DNS. La reserva permanece.
   Rollback de código conserva el esquema aditivo; antes retirar dominios del proxy.
   Downgrade físico se bloquea si hay historia: requiere exportación y plan separado,
   nunca eliminar reservas para forzar una reversión.

Límites: sin dominio real aportado, no hay certificación DNS/TLS de cliente. Activación
supervisada manual, sin automatización de EasyPanel ni monitor periódico de certificados.
El adaptador DoH falla cerrado, respuesta máx.64KB y timeout4s. El QR reutiliza el
proveedor externo existente para generar la imagen a partir del enlace público.
