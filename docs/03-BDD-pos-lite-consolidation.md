# BDD: Consolidación y Control de Roles en Terminal POS (Versión Lite)

## Contexto y Alcance

En la terminal de Punto de Venta (POS):
1. **Rol Cajero**: Es un operador enfocado en venta rápida, cobro, pedidos, clientes y registro de asistencia. No debe tener acceso al módulo de "Administración de sucursal".
2. **Rol Supervisor / Administrador**: Tiene acceso a la gestión operativa de la sucursal (disponibilidad de productos agotados, compras de caja chica, mermas de cocina, monitoreo de ventas y asistencia).
3. **Depuración de Herencias ERP**: En una terminal de cobro gastronómica Lite no se capturan lotes industriales de producción (`/production`), traspasos inter-almacenes (`/transfers`), conteos físicos periódicos (`/counts`) ni reportes históricos de insumos pasados (`/historical-reports`).

---

## BDD-FEAT-POS-001: Restricción Estricta del Menú Administración en POS

### BDD-SC-POS-001: Cajero sin acceso a menú de administración
Given un usuario con rol exclusivo de Cajero ha iniciado sesión en el POS
When visualiza la barra lateral de navegación
Then visualiza Punto de Venta, Clientes, Pedidos, Canales Delivery, Facturación y Checador
And el elemento de navegación "Administración" no está disponible ni visible en la barra lateral.

### BDD-SC-POS-002: Supervisor y Administrador acceden a administración de sucursal
Given un usuario con permiso `branch.admin.access` o `admin.manage` inicia sesión en el POS
When consulta la barra lateral de navegación
Then visualiza el acceso directo a "Administración".

---

## BDD-FEAT-POS-002: Depuración de Tarjetas ERP en Hub de Administración de Sucursal

### BDD-SC-POS-003: Exclusión de producción, traspasos, conteos físicos e inventario de almacén
Given un usuario supervisor o administrador accede al Hub de "Administración de sucursal" en el POS
When examina las tarjetas operativas disponibles
Then no se presentan tarjetas para Producción de lotes (`/administration/production`), Traspasos (`/administration/transfers`), Conteos físicos (`/administration/counts`), Reportes históricos (`/historical-reports`), ni opciones fragmentadas de comentarios/ingredientes o inventario de almacén.

### BDD-SC-POS-004: Foco en 6 tarjetas operativas y distinción de checador
Given el supervisor o administrador accede al Hub de "Administración de sucursal"
When revisa las opciones operativas autorizadas
Then dispone exactamente de 6 tarjetas:
  1. Reporte de Asistencia (auditoría de horas y checadas, distinguiéndose de la acción de checar del sidebar)
  2. Monitor de ventas (desbloqueado para supervisores y administradores)
  3. Disponibilidad de Menú (activar/apagar platillos e insumos agotados 86)
  4. Proveedores locales
  5. Compras de caja chica
  6. Mermas operativas.
