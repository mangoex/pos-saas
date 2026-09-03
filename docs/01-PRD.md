# PRD — Product Requirements Document: POS-SaaS
## Micro-POS de Alto Impacto para Restaurantes

---

## 1. Propósito y Visión del Producto

**POS-SaaS** es una plataforma en la nube (SaaS Multi-tenant) diseñada específicamente para micro y pequeños negocios gastronómicos en México y Latinoamérica:
- Taquerías y carritos de tacos
- Cafeterías y barras de café
- Dark kitchens y cocinas fantasma
- Fondas y cocinas económicas
- Pizzerías de barrio
- Food trucks y snacks

El producto erradica por completo la pesada burocracia, configuraciones complejas y costos prohibitivos de los ERPs gastronómicos tradicionales. Ofrece una solución autoservicio con **onboarding garantizado en 5 minutos** y planes accesibles (**$349 - $599 MXN / mes**), resolviendo de manera quirúrgica los 5 dolores críticos del restaurantero independiente:

1. **POS Táctil Ultrarrápido:** Cobro en mostrador/mesas, división de cuentas, propinas, turnos y cortes de caja (X y Z) para evitar fugas de efectivo.
2. **Delivery Hub Unificado:** Recepción e inyección de pedidos de Uber Eats, DiDi Food y Rappi en una sola pantalla/comanda, con botón maestro (Kill-Switch) para apagar platillos agotados en todas las apps.
3. **Autofacturación 1-Click (CFDI 4.0 SAT):** Generación automática de código QR y URL corta en el ticket para que el comensal facture solo desde su celular en 1 minuto.
4. **Menú Web con Pedidos por WhatsApp:** Canal directo propio sin comisiones del 30%, con fotos, modificadores y carrito que genera el pedido formateado.
5. **Backoffice Ultraligero y Multi-tenant:** Registro de cuenta autoservicio, catálogo con variantes/modificadores, precios diferenciados por canal (salón vs delivery) y reportes diarios al WhatsApp o correo del dueño.

---

## 2. Objetivos de Negocio y Métricas de Éxito

1. **Tiempo de Cobro en Mostrador / Mesas:** Reducir la captura y cobro a menos de **15 segundos** por transacción.
2. **Onboarding Autoservicio:** Lograr que un negocio se registre, configure su primer menú y emita su primer ticket en menos de **5 minutos**.
3. **Cero Fugas de Efectivo:** Garantizar cuadre al 100% de cajas mediante arqueos a ciegas, turnos auditables y cortes X/Z inmutables.
4. **Cero Pedidos Perdidos de Delivery:** Unificar pedidos de Uber Eats, DiDi y Rappi en un solo flujo, reduciendo cancelaciones por saturación de pantallas a **0%**.
5. **Autofacturación Desatendida:** Reducir a **0 minutos** el tiempo que el personal de caja dedica a generar facturas fiscales, trasladando la captura al comensal mediante código QR.
6. **Canal Directo Rentable:** Facilitar ventas directas sin comisiones del 30% a través de un menú web móvil optimizado que convierte directo a WhatsApp.

---

## 3. Usuarios y Roles Simplificados

### PRD-ROLE-001 Dueño / Administrador del SaaS (Owner)
Propietario de la cuenta del restaurante. Realiza el registro autoservicio (Sign up), gestiona su suscripción, configura la sucursal, catálogo de productos con precios por canal, vincula sus sellos de facturación CFDI (FacturAPI) y recibe los reportes ejecutivos diarios de ventas.

### PRD-ROLE-002 Gerente / Encargado de Sucursal (Supervisor)
Supervisa la operación diaria de la sucursal. Gestiona la apertura y cierre de turnos de caja, aprueba cancelaciones, cortes Z y descuentos excepcionales, y opera el botón maestro de disponibilidad (Kill-Switch) de platillos agotados en delivery.

### PRD-ROLE-003 Cajero / Mesero
Opera el POS táctil para toma rápida de comandas en mostrador o mesas, registra pagos en efectivo, tarjeta o transferencias, aplica propinas, divide cuentas y genera su corte X/Z al terminar turno.

### PRD-ROLE-004 Operador de Cocina (KDS / Comandas)
Visualiza los pedidos en pantalla KDS de cocina o recibe la comanda impresa automáticamente en la estación de preparación. Marca órdenes listas para entrega o despacho.

### PRD-ROLE-005 Comensal / Cliente Digital
Escanea el código QR de mesa o ticket, consulta el menú web móvil, envía pedidos para recoger/domicilio a WhatsApp, o genera su factura CFDI 4.0 escaneando el QR del ticket desde su teléfono móvil.

---

## 4. Requisitos Funcionales de POS-SaaS (`PRD-FR-xxx`)

### 4.1 Multi-Tenancy, Aprovisionamiento y Onboarding en 5 Minutos

- `PRD-FR-001`: **Sign Up Público Autoservicio**: Cualquier usuario debe poder registrarse en la plataforma mediante formulario público (nombre del negocio, correo, contraseña y teléfono), sin requerir intervención manual ni agentes de ventas.
- `PRD-FR-002`: **Aprovisionamiento Atómico de Tenant**: Al completarse el registro, el sistema debe aprovisionar de forma transaccional y atómica:
  1. Organización (`organization_id`).
  2. Sucursal principal predeterminada con zona horaria adecuada.
  3. Almacén base vinculado.
  4. Roles y permisos predeterminados (`Owner`, `Supervisor`, `Cajero`).
  5. Usuario Administrador (Owner) con sesión autenticada lista para operar.
- `PRD-FR-003`: **Aislamiento Multi-Tenant Estricto**: Todo dato, catálogo, usuario, pedido, turno y factura debe pertenecer estrictamente a su `organization_id`. Todas las consultas y mutaciones de la API deben forzar el filtro por organización. Queda estrictamente prohibida cualquier fuga de información entre tenants.
- `PRD-FR-004`: **Wizard de Onboarding en 3 Pasos (5 Minutos)**:
  - *Paso 1:* Confirmación de datos del negocio (nombre, logo opcional, tipo de comida).
  - *Paso 2:* Carga de catálogo express: Opción de precargar plantilla temática (Taquería, Cafetería, Pizzería, Hamburguesería) o capturar productos iniciales de forma rápida.
  - *Paso 3:* Configuración básica de caja e impresión, habilitando de inmediato la terminal de cobro.
- `PRD-FR-005`: **Gestión de Planes y Suscripción**: Manejo de suscripción autoservicio ($349 MXN Básico / $599 MXN Pro) con soporte para período de prueba (Trial 7 días), estado activo, aviso de pago vencido y suspensión automática.

### 4.2 Catálogo Ágil y Precios Diferenciados por Canal

- `PRD-FR-010`: **Catálogo Simplificado de Productos**: Administración de categorías, productos, descripción corta, fotos optimizadas, código rápido y visibilidad en menú digital.
- `PRD-FR-011`: **Precios Diferenciados por Canal (Salón vs Delivery)**: Cada producto debe soportar:
  - `price_dine_in`: Precio base para mostrador y consumo en salón.
  - `price_delivery`: Precio para canales de entrega (Uber Eats, DiDi Food, Rappi), permitiendo absorber comisiones de las plataformas sin mermar margen.
- `PRD-FR-012`: **Variantes y Modificadores**:
  - Definición de variantes (ej. Tamaño: Chico, Mediano, Grande).
  - Grupos de modificadores obligatorios (ej. Término de la carne) y opcionales con costo adicional (ej. Queso extra +$15 MXN, Tocino +$20 MXN).
- `PRD-FR-013`: **Kill-Switch y Agotados por Canal**: El operador puede marcar un producto como agotado temporalmente en una sucursal, desactivándolo de inmediato en el POS, Menú Web y plataformas de delivery.

### 4.3 POS Táctil Ultrarrápido y Operación Mostrador/Mesas

- `PRD-FR-020`: **Interfaz Táctil Optimizada**: Diseñada con tokens CSS nativos de alto contraste para tablets económicas (Android/iPad) y monitores touch. Navegación por pestañas de categoría, barra de búsqueda en tiempo real y selector de cantidades rápido.
- `PRD-FR-021`: **Captura Dinámica de Comandas**:
  - Selección de producto en un toque.
  - Apertura de modal táctil solo si el producto requiere modificadores obligatorios; si no, adición directa al ticket en 1 clic.
  - Notas de comanda por platillo (ej. "Sin cebolla", "Salsa aparte").
- `PRD-FR-022`: **Modalidades de Venta**: Soporte para Venta en Mostrador (Rápida / Para Llevar), Mesas / Comedor (con nombre de mesa o identificador) y Pedido para Recoger.
- `PRD-FR-023`: **División de Cuentas (Split Bill)**:
  - División en partes iguales (N cuentas con el total prorrateado exacto en centavos).
  - División por artículos (asignación de productos específicos a cada comensal).
- `PRD-FR-024`: **Propinas Integradas**: Captura ágil de propinas con botones rápidos de porcentaje sugerido (10%, 15%, 20%) o monto libre, registradas por separado para cuadre contable.
- `PRD-FR-025`: **Cobro Multiforma de Pago**: Registro de Efectivo (con calculadora de cambio automática), Tarjeta de Débito/Crédito (referencia bancaria opcional), Transferencia SPEI y pagos mixtos (ej. mitad efectivo, mitad tarjeta).
- `PRD-FR-026`: **Inmutabilidad y Auditoría de Pagos**: Todo pago confirmado es inmutable en base de datos. Anulaciones o cancelaciones de tickets cobran con registro de motivo y requieren PIN de autorización de supervisor.
- `PRD-FR-027`: **Impresión Térmica Desatendida**: Emisión automática de comanda a cocina y ticket para el cliente en impresoras térmicas de 58mm y 80mm vía ESC/POS o diálogo de impresión ligero, conteniendo código QR de autofacturación.
- `PRD-FR-028`: **Resiliencia y Modo Offline**: Soporte de cobro local continuo hasta por 2 horas en caso de caída de internet, almacenando tickets y pagos en SQLite local y sincronizando en segundo plano al reconectar.

### 4.4 Control de Caja y Cortes de Turno (X y Z)

- `PRD-FR-030`: **Apertura de Turno con Fondo Inicial**: Apertura obligatoria de turno ingresando el monto del fondo fijo en caja antes de registrar la primera venta.
- `PRD-FR-031`: **Movimientos de Turno (Entradas y Retiros)**: Registro de gastos menores (ej. compra de hielo urgente) y retiros parciales de efectivo con motivo auditable y firma de recepción.
- `PRD-FR-032`: **Corte X (Corte Parcial Informativo)**: Consulta en cualquier momento del turno de las ventas acumuladas por forma de pago sin cerrar el turno.
- `PRD-FR-033`: **Corte Z (Cierre Ciego y Cuadre de Turno)**:
  - El cajero ingresa el conteo físico de billetes y monedas (arqueo a ciegas sin mostrar el esperado del sistema para evitar manipulaciones).
  - El sistema calcula diferencia (sobrante o faltante).
  - Congela el turno, emite el ticket físico de Corte Z inmutable y bloquea la caja.
- `PRD-FR-034`: **Notificación Inmediata al Propietario**: Al emitirse el Corte Z, el sistema genera automáticamente un extracto y lo envía por WhatsApp o email al dueño con el total vendido, método de pago y diferencia de caja.

### 4.5 Delivery Hub Unificado & Kill-Switch Global

- `PRD-FR-040`: **Bandeja Centralizada de Delivery**: Recepción directa de pedidos provenientes de Uber Eats, DiDi Food y Rappi en una sola pantalla unificada de comandas en el POS.
- `PRD-FR-041`: **Inyección Automática a Cocina**: Los pedidos aceptados de las apps se imprimen o proyectan en KDS con el mismo formato que los pedidos locales, indicando nombre de la app, número de orden y repartidor.
- `PRD-FR-042`: **Idempotencia de Webhooks de Plataformas**: Recepción robusta de eventos de pedidos de delivery con `idempotency_key`, preservando el payload original de la plataforma y garantizando cero duplicados.
- `PRD-FR-043`: **Kill-Switch Global de Platillos (1 Clic)**: Botón maestro en POS/Backoffice que permite marcar un platillo como agotado y transmite la actualización en batch a las APIs de Uber Eats, DiDi Food y Rappi en simultáneo.

### 4.6 Autofacturación 1-Click (CFDI 4.0 SAT)

- `PRD-FR-050`: **Token Único y Código QR en Ticket**: Cada ticket emitido en POS genera un `invoice_token` criptográfico seguro impreso en el ticket junto con un código QR y URL corta (`https://pos.midominio.com/f/{token}`).
- `PRD-FR-051`: **Portal Comensal Móvil de Autofacturación**: El cliente escanea el QR desde su smartphone y accede a una interfaz ultraligera donde visualiza el desglose de su consumo e introduce:
  - RFC
  - Nombre o Razón Social
  - Código Postal fiscal
  - Régimen Fiscal SAT
  - Uso de CFDI
  - Correo electrónico para recepción
- `PRD-FR-052`: **Timbrado CFDI 4.0 Automatizado (FacturAPI / PAC)**: Validación con el catálogo SAT y timbrado oficial inmediato mediante integración con FacturAPI / PAC autorizado.
- `PRD-FR-053`: **Descarga y Envío Automático**: En menos de 5 segundos tras pulsar "Facturar", la pantalla ofrece los botones de descarga de PDF y XML, enviando copias al correo del cliente.
- `PRD-FR-054`: **Factura Global Automatizada**: Consolidación automática de los tickets no autofacturados del período para generar el CFDI 4.0 global al público en general.

### 4.7 Menú Web y Pedidos Directos por WhatsApp

- `PRD-FR-060`: **Menú Digital Responsivo (PWA)**: Catálogo digital público y atractivo disponible en URL única por restaurante (`https://menu.pos-saas.com/{slug}`), compatible con smartphones y códigos QR en mesas.
- `PRD-FR-061`: **Personalización de Platillos en Menú Web**: El comensal puede elegir opciones, modificadores y extras con recálculo dinámico de precio.
- `PRD-FR-062`: **Carrito y Checkout para WhatsApp**: Carrito interactivo con selección de tipo de entrega (Para recoger en sucursal o A domicilio con dirección) y notas especiales.
- `PRD-FR-063`: **Generación de Pedido Formateado a WhatsApp**: Al finalizar el pedido, el sistema genera la orden en estado pendiente en el POS y abre automáticamente WhatsApp con un mensaje estructurado y listo para enviar al número del restaurante:
  ```text
  🌮 *Nuevo Pedido #1024 - Taquería El Paisa*
  Cliente: Juan Pérez (55-1234-5678)
  Tipo: Para Llevar (Recoger 8:30 PM)

  1x Orden Tacos Pastor ($95.00)
     - Con piña, salsa verde aparte
  1x Coca-Cola 600ml ($35.00)

  *Total: $130.00 MXN*
  Pago: Efectivo ($200)
  ```

### 4.8 Backoffice Ultraligero y Reportes Ejecutivos

- `PRD-FR-070`: **Dashboard Ejecutivo Resumido**: Métricas claras sin saturación: Ventas brutas hoy, Ticket promedio, Comparativa vs semana anterior, Top 5 platillos más vendidos y Distribución de pagos.
- `PRD-FR-071`: **Gestión de Personal con PIN de 4 Dígitos**: Alta ágil de cajeros y supervisores con asignación de PIN de 4 dígitos para cambio rápido de usuario en el POS físico.
- `PRD-FR-072`: **Reporte Automatizado al Dueño**: Configuración de envío nocturno del resumen de caja y ventas por WhatsApp o correo electrónico.

---

## 5. Módulos Podados y Fuera de Alcance para MVP (ERP Complejo)

Para garantizar la simplicidad, autoservicio y entrega ágil, se excluyen explícitamente del MVP los módulos del ERP maduro previo:
- `PRD-OOS-001`: Costeo gramo a gramo y recetas/subrecetas multinivel.
- `PRD-OOS-002`: Producción interna de lotes de elaborados (salsas industriales, panadería).
- `PRD-OOS-003`: Múltiples almacenes y traspasos inter-bodega.
- `PRD-OOS-004`: Cuentas por pagar, compras a crédito e importación de XML CFDI de proveedores.
- `PRD-OOS-005`: Despacho geográfico con optimización de rutas para flotillas de repartidores propios.

---

## 6. Requisitos No Funcionales (NFR)

- `PRD-NFR-001 Rendimiento Táctil`: El POS debe responder a interacciones táctiles en < 100 ms.
- `PRD-NFR-002 Aislamiento Multi-Tenant`: Garantía absoluta de aislamiento de datos a nivel de base de datos (`organization_id` en todas las capas).
- `PRD-NFR-003 Disponibilidad Cloud`: Uptime del 99.9% para la API central y el portal de autofacturación.
- `PRD-NFR-004 Continuidad Offline`: El POS debe tolerar hasta 2 horas de trabajo sin internet localmente.
- `PRD-NFR-005 Timbrado Fiscal Rápido`: Generación y respuesta de timbrado CFDI 4.0 en < 5 segundos.
- `PRD-NFR-006 Responsive & WCAG`: Interfaces diseñadas para tablets de bajo costo y celulares bajo estándar WCAG 2.1 AA.
