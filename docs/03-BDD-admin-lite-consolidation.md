# BDD: Consolidación y Simplificación del Panel de Administración (Versión Lite)

## Contexto y Alcance

En la versión Lite de RestaurantOS:
1. No se requiere costeo gramo por gramo ni explosión factorial de subrecetas en cocina. El catálogo opera con productos directos, categorías y modificadores/adiciones para agilidad de comanda.
2. No se requiere la suite de importaciones masivas de historial legacy (específica de migraciones ERP de cadenas grandes).
3. Los Conceptos de Caja son un control financiero de efectivo, por lo que pertenecen al núcleo de "Cajas y Reportes", no a "Sucursales y Canales".
4. La recepción omnicanal de pedidos de plataformas de delivery (Uber Eats, DiDi Food, Rappi, Tienda Web) es una funcionalidad de alto valor para el POS y KDS, y debe desacoplarse del timbrado fiscal ante el SAT (Facturapi CFDI 4.0).

---

## BDD-FEAT-LITE-001: Catálogo y Menú Lite sin Recetas Complejas ni Selectores Redundantes

### BDD-SC-LITE-001: El Hub de Catálogo no expone recetas complejas ni selector previo redundante
Given el usuario administrador abre el panel de administración
When accede al Hub de "Catálogo y Menú" (`/catalog`)
Then visualiza tarjetas para Productos, Categorías, Comentarios/Notas y Adicionales y Modificadores
And la tarjeta de "Recetas" (fórmulas y explosión de insumos) no está presente
And la tarjeta de "Opciones previas" (selector previo de categoría) no está presente en la navegación principal.

### BDD-SC-LITE-007: Modificadores y Adicionales desvinculados de insumos y almacén
Given el usuario administrador entra a la gestión de "Adicionales y Modificadores" (`/ingredient-extras`)
When crea o edita un adicional (ej. "Extra Queso", "Salsa Especial")
Then el formulario únicamente solicita Nombre, Precio de Venta (MXN), Estación de preparación y Orden
And no requiere vincular un insumo del almacén (`/inventory/items`) ni capturar obligatoriamente cantidades decimales
And el adicional queda listo para seleccionarse de inmediato en la toma de comandas del POS y Menú Web.

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

---

## BDD-FEAT-LITE-005: Exclusión de Mermas y Desperdicios en Plan Lite SaaS

### BDD-SC-LITE-008: Cajas y Reportes no expone Mermas y Desperdicios
Given el usuario administrador accede al Hub de "Cajas y Reportes" (`/reports-hub`)
When consulta los reportes disponibles
Then no visualiza la tarjeta de "Mermas y Desperdicios" ni el enlace en la subnavegación
And la vista prioriza el monitoreo de ventas, cortes de caja y conciliación diaria.

### BDD-SC-LITE-009: Protección de rutas excluidas para Mermas
Given un usuario intenta acceder a `/admin/waste` o `/admin/inventory/waste`
When el sistema procesa la ruta en la aplicación Admin Web
Then se muestra el componente de módulo comercial excluido indicando que el control de mermas e inventario detallado pertenece a planes superiores.

---

## BDD-FEAT-LITE-006: Confirmación y Envío de Pedidos por WhatsApp en Menú Móvil

### BDD-SC-LITE-011: Generación y despacho de comanda detallada por WhatsApp al confirmar en móvil
Given una sucursal con teléfono de contacto y la casilla "Habilitar confirmación y envío de pedidos por WhatsApp" activa
And un cliente en navegador web móvil que completa un pedido con adicionales, notas y modalidad elegida
When confirma el pedido desde el carrito de compra
Then el sistema registra la orden en la base de datos conservando su folio para auditoría
And genera el enlace de WhatsApp estructurado con folio, modalidad (comer aquí, llevar o a domicilio), cliente, adicionales desglosados con precio y total
And en navegadores móviles abre automáticamente la aplicación de WhatsApp y muestra el botón de reintento en el modal de éxito.

### BDD-SC-LITE-012: Configuración de envío por WhatsApp en sucursal
Given el usuario administrador edita o crea una sucursal en el panel de administración
When consulta los campos de contacto
Then visualiza la casilla "Habilitar confirmación y envío de pedidos por WhatsApp"
And al desmarcarla, el menú móvil registra pedidos directamente en el sistema sin forzar la apertura de WhatsApp.

---

## BDD-FEAT-LITE-007: Monitor de Pedidos Móvil para mimenu.onl/admin

### BDD-SC-LITE-013: Detección de dispositivo móvil y despliegue del monitor de comandas
Given un encargado o cocinero que ingresa a mimenu.onl/admin desde un smartphone o pantalla táctil pequeña (viewport < 768px)
When se carga la pantalla principal del panel de administración
Then el sistema detecta el dispositivo móvil y presenta de forma directa la relación de pedidos activos en lugar del panel de escritorio complejo
And muestra cada orden con folio, tiempo transcurrido, modalidad (comer aquí con mesa, llevar o domicilio), cliente, total y estado
And ofrece un selector accesible para alternar entre el "Monitor de Pedidos" y el "Panel Completo de Administración".

### BDD-SC-LITE-014: Apertura de detalle de comanda interactivo al tocar un pedido
Given la lista de pedidos en el monitor móvil
When el usuario toca una tarjeta de pedido
Then se abre un modal de detalle con la información completa del cliente, teléfono con enlace directo a WhatsApp y llamada, y modalidad de entrega
And se despliega cada producto con su cantidad, precio, notas y lista de ingredientes adicionales o modificadores seleccionados
And cada instrucción seleccionada muestra su texto operativo (por ejemplo, "Sin azúcar", "Con todo" o "Sin picante") tanto antes como después de aceptar el pedido
And ninguna selección válida se representa únicamente mediante el signo "+" o mediante una etiqueta vacía
And las notas libres del producto permanecen visibles por separado de los modificadores y comentarios predefinidos
And se presentan botones de acción rápida para avanzar el estado de preparación (Iniciar Preparación, Marcar Listo, Entregado) o contactar al comensal por WhatsApp.

### BDD-SC-LITE-015: Flujo de pestañas Activos -> Listos -> Todos en el monitor móvil
Given el monitor de comandas en la aplicación web móvil del administrador
When se recibe un nuevo pedido con estado por aceptar
Then se muestra en la columna "Activos" y en "Todos"
And al pulsar "Aceptar Pedido" dentro del detalle, el pedido abandona "Activos" y pasa inmediatamente a "Listos"
And la interfaz posiciona al usuario en la pestaña "Listos" para dar seguimiento a la preparación
And el pedido nunca se traslada directamente a finalizado sin haber pasado por la columna "Listos"
And al abrir el pedido desde "Listos", se ofrece la acción "Listo para Entregar" para finalizar la comanda
And al pulsar "Listo para Entregar", el pedido sale de "Listos" y permanece registrado únicamente en "Todos".
