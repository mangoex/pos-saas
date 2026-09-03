# BDD: Consolidación y Simplificación del Panel de Administración (Versión Lite)

## Contexto y Alcance

En la versión Lite de RestaurantOS:
1. No se requiere costeo gramo por gramo ni explosión factorial de subrecetas en cocina. El catálogo opera con productos directos, categorías y modificadores/adiciones para agilidad de comanda.
2. No se requiere la suite de importaciones masivas de historial legacy (específica de migraciones ERP de cadenas grandes).
3. Los Conceptos de Caja son un control financiero de efectivo, por lo que pertenecen al núcleo de "Cajas y Reportes", no a "Sucursales y Canales".
4. La recepción omnicanal de pedidos de plataformas de delivery (Uber Eats, DiDi Food, Rappi, Tienda Web) es una funcionalidad de alto valor para el POS y KDS, y debe desacoplarse del timbrado fiscal ante el SAT (Facturapi CFDI 4.0).

---

## BDD-FEAT-LITE-001: Catálogo y Menú Lite sin Recetas Complejas

### BDD-SC-LITE-001: El Hub de Catálogo no expone recetas complejas
Given el usuario administrador abre el panel de administración
When accede al Hub de "Catálogo y Menú" (`/catalog`)
Then visualiza tarjetas para Productos, Categorías, Comentarios/Notas, Ingredientes Extra y Opciones previas
And la tarjeta de "Recetas" (fórmulas y explosión de insumos) no está presente en el menú de catálogo.

---

## BDD-FEAT-LITE-002: Administración y Accesos Limpia de Migraciones Legacy

### BDD-SC-LITE-002: El Hub de Accesos excluye importaciones masivas de migración
Given el usuario administrador accede a "Equipo y Cajeros / Administración y Accesos" (`/admin-access-hub`)
When consulta las opciones disponibles
Then visualiza tarjetas para Usuarios y Cuentas, Roles y Permisos, y Directorio de Clientes
And la tarjeta de "Importaciones Masivas" de historial legacy queda excluida de la vista operativa.

---

## BDD-FEAT-LITE-003: Reubicación Ergonómica de Conceptos de Caja a Cajas y Reportes

### BDD-SC-LITE-003: Conceptos de caja reside en Cajas y Reportes
Given el usuario con permisos de gestión de caja navega por el panel de administración
When accede al Hub de "Cajas y Reportes" (`/reports-hub`)
Then visualiza la tarjeta de "Conceptos de Caja" para definir motivos autorizados de ingresos y egresos de efectivo
And en la subnavegación (`CategorySubNav`), el enlace a "Conceptos de Caja" se encuentra dentro del grupo de "Cajas y Reportes".

### BDD-SC-LITE-004: Sucursales no incluye Conceptos de Caja
Given el usuario accede al Hub de "Sucursales y Canales" (`/branches-hub`)
When revisa las opciones operativas
Then no visualiza la tarjeta de "Conceptos de Caja" en esta sección.

---

## BDD-FEAT-LITE-004: Desacoplamiento de Canales de Delivery y Facturación Fiscal

### BDD-SC-LITE-005: Canales de Delivery enfocado en recepción de pedidos omnicanal
Given el usuario administrador consulta "Sucursales y Canales" (`/branches-hub`)
When visualiza las opciones de integración
Then encuentra una tarjeta dedicada a "Canales de Delivery (Uber Eats, DiDi, Rappi)" orientada a la recepción automática de comandas en POS y KDS
And encuentra una tarjeta dedicada a "Facturación Electrónica (SAT CFDI 4.0)" para timbrado con Facturapi.

### BDD-SC-LITE-006: Navegación directa hacia Facturación Fiscal y Delivery Hub
Given el usuario hace clic en "Facturación Electrónica" o "Canales de Delivery"
When el sistema abre la vista correspondiente
Then el usuario puede configurar de forma independiente las credenciales de delivery o los sellos digitales del SAT sin mezclar flujos.
