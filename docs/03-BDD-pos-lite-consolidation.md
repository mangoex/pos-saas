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

### BDD-SC-POS-003: Exclusión de producción, traspasos y conteos físicos
Given un usuario supervisor o administrador accede al Hub de "Administración de sucursal" en el POS
When examina las tarjetas operativas disponibles
Then no se presentan tarjetas para Producción de lotes (`/administration/production`), Traspasos (`/administration/transfers`) ni Conteos físicos (`/administration/counts`).

### BDD-SC-POS-004: Foco en disponibilidad, compras de caja, mermas y monitoreo
Given el supervisor accede al Hub de "Administración de sucursal"
When revisa las opciones autorizadas
Then dispone de Monitor de ventas, Disponibilidad de Menú, Mermas operativas, Compras de caja chica, Directorio de proveedores y Checador de asistencia.
