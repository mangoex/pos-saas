# PRD — Product Requirements Document: POS-SaaS

## Personalización visual del menú

- `PRD-FR-086`: El administrador de catálogo puede guardar, reemplazar o retirar una
  liga de imagen por categoría y editar nombre e imagen de la portada maestra del menú.
  La portada inicia como «Todos», sigue mostrando todos los productos y no es una
  categoría asignable a productos. Los cambios pertenecen exclusivamente al restaurante.

## Enlaces personalizados

- `PRD-FR-084`: El administrador consulta/copia accesos Admin, POS, KDS y menú/QR de
  su restaurante; puede reservar un alias público preferido conservando URLs anteriores.
- `PRD-FR-085`: El administrador solicita un dominio propio y verifica control mediante
  TXT. Sólo el superadministrador activa tras verificar DNS y confirmar HTTPS/enrutamiento.
  El dominio nunca cambia la autoridad de la sesión ni sirve datos de otro restaurante.
- `PRD-FR-087`: Cuando la plataforma configura un dominio wildcard compartido, cada
  restaurante obtiene accesos `https://{slug}.dominio/`, `/admin/`, `/pos/` y `/kds/`
  sin alta DNS individual. El host resuelve exactamente el slug o alias reservado, nunca
  concede autoridad por sí mismo y falla cerrado para nombres desconocidos, ambiguos,
  reservados, restaurantes no disponibles o datos de otra organización. Las URLs
  históricas por ruta y los dominios propios activos continúan funcionando.
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

El producto erradica por completo la pesada burocracia, configuraciones complejas y costos prohibitivos de los ERPs gastronómicos tradicionales. Ofrece una solución autoservicio con **objetivo de onboarding en 5 minutos** y planes accesibles (**$349 - $599 MXN / mes**), resolviendo de manera quirúrgica los 5 dolores críticos del restaurantero independiente:

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
- `PRD-FR-005`: **Gestión de Planes y Suscripción**: Manejo de suscripción autoservicio ($349 MXN Básico / $599 MXN Pro) con soporte para período de prueba (Trial 14 días), estado activo, aviso de pago vencido y suspensión automática.

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

**Alcance de la entrega actual, indicado por el usuario el 4 de septiembre de 2026:**
Uber conserva el flujo operativo de recepción probado. DiDi Food y Rappi quedan preparados
para capturar y guardar configuración por restaurante, con una experiencia similar a Uber;
el usuario completará y validará esas integraciones después. Guardar datos no demuestra conexión
ni entrega de pedidos ni sincronización remota. Sus estados distinguen pendiente de configuración,
pendiente de validación y error; no se presenta como confirmada una operación externa no ejecutada.
La implementación y certificación real de ambos proveedores se difiere de esta entrega.


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

### 4.9 Pago y Suscripción (Paquete Lite)

- `PRD-FR-090`: **Custom Checkout Mercado Pago**: El pago del paquete Lite ($349 MXN) se procesa nativamente en el Backoffice sin redirección. Falla si hay fuga de contexto (redirección externa a Mercado Pago).
- `PRD-FR-091`: **Suscripción Preapproval**: Mercado Pago gestiona la recurrencia mensual. La plataforma consume webhooks idempotentes para actualizar la vigencia de la sucursal de forma inmutable.

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

## 7. Cierre SaaS A01–A12 (contrato de septiembre 2026)

Los objetivos anteriores son requisitos, no certificaciones de implementación. El paquete de cierre completo incluye:

- `PRD-FR-080`: Autoridad superadmin persistida, aprovisionamiento administrativo auditable y soporte con actor real, actor efectivo y tenant destino; jamás autoridad por correo ni bootstrap desde login público.
- `PRD-FR-081`: Identidad pública exacta del restaurante, estado local y PWA aislados; slug inválido o ambiguo falla explícitamente sin catálogo sustituto.
- `PRD-FR-082`: Importaciones y toda administración validan actor, organización y sucursal de destino antes de efectos.
- `PRD-FR-083`: Primera venta ligera sin recetas, compras ni costeo de insumos; módulos ERP excluidos del producto, preservando historia y compensaciones.
- `PRD-NFR-007`: Release exige evidencia diferenciada local/PostgreSQL/CI/Git/despliegue/canary; verificar aislamiento de infraestructura Kiwi y SaaS, backups restaurables y reversión antes de habilitación comercial.

La prueba dura exactamente 14 días desde alta confirmada, calculados en UTC por servidor; al alcanzar el vencimiento se bloquean operaciones comerciales incluso con sesión vigente. Elegir plan no acredita pago. Suspensión revoca acceso operativo; permanecen disponibles autenticación, consulta de estado y gestión de suscripción autorizada. Activación pagada requiere confirmación verificable del canal contratado o autorización administrativa auditada, sin inventar proveedor de cobro.

## 8. Registro de requisitos históricos ERP (fuera del alcance comercial SaaS)

La versión previa reutilizó identificadores para significados diferentes. Se conserva aquí su relación documental con prefijo numérico 500: antiguo FR001 pasa a FR501, NFR001 a NFR501. Estos registros describen contratos históricos conservados para mantenimiento/regresión, no capacidades prometidas del SaaS ni validación de implementación actual. Las referencias SDD históricas requieren consultar la revisión histórica; no se interpretan como secciones del SDD SaaS actual. Los estados históricos se conservan en matriz con esta salvedad.

- `PRD-FR-501`: Registro histórico de PRD-FR-001 — Organization module. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-502`: Registro histórico de PRD-FR-002 — Organization module. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-503`: Registro histórico de PRD-FR-003 — Organization module. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-504`: Registro histórico de PRD-FR-004 — Inventory module. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-505`: Registro histórico de PRD-FR-005 — RBAC scoped authorization. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-506`: Registro histórico de PRD-FR-006 — Devices, registers, stations, printers. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-507`: Registro histórico de PRD-FR-007 — Audit events append-only. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-508`: Registro histórico de PRD-FR-008 — Configuration inheritance. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-509`: Registro histórico de PRD-FR-009 — Business unit hierarchy. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-510`: Registro histórico de PRD-FR-010 — Catalog module. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-511`: Registro histórico de PRD-FR-011 — Station-aware products. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-512`: Registro histórico de PRD-FR-012 — Shared menu by channel. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-513`: Registro histórico de PRD-FR-013 — Sale schedules. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-514`: Registro histórico de PRD-FR-014 — Branch stockouts. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-515`: Registro histórico de PRD-FR-015 — Price versioning. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-516`: Registro histórico de PRD-FR-016 — External product mappings. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-517`: Registro histórico de PRD-FR-017 — Canonical catalog consistency. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-518`: Registro histórico de PRD-FR-018 — POS administrative hub. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-519`: Registro histórico de PRD-FR-019 — Canonical branch context. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-520`: Registro histórico de PRD-FR-020 — Orders module. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-521`: Registro histórico de PRD-FR-021 — Channel adapters. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-522`: Registro histórico de PRD-FR-022 — Integration idempotency. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-523`: Registro histórico de PRD-FR-023 — Original payload retention. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-524`: Registro histórico de PRD-FR-024 — Customer/address/channel data. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-525`: Registro histórico de PRD-FR-025 — Order totals and payments. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-526`: Registro histórico de PRD-FR-026 — Historical catalog snapshots. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-527`: Registro histórico de PRD-FR-027 — Order events/state machine. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-528`: Registro histórico de PRD-FR-028 — Cancellation rules. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-529`: Registro histórico de PRD-FR-029 — Notes by order/product/station. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-530`: Registro histórico de PRD-FR-030 — Offline-safe folios. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-531`: Registro histórico de PRD-FR-031 — Customer identity and phones. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-532`: Registro histórico de PRD-FR-032 — Unlimited customer addresses. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-533`: Registro histórico de PRD-FR-033 — Separate customer tax profile. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-534`: Registro histórico de PRD-FR-034 — Customer and address snapshots. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-535`: Registro histórico de PRD-FR-035 — Repeat order with current rules. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-540`: Registro histórico de PRD-FR-040 — Production tasks. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-541`: Registro histórico de PRD-FR-041 — Station model. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-542`: Registro histórico de PRD-FR-042 — Timing, priority and delays. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-543`: Registro histórico de PRD-FR-043 — Production state machine. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-544`: Registro histórico de PRD-FR-044 — Authorized reopen/reprint. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-545`: Registro histórico de PRD-FR-045 — Incidents and stockouts. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-546`: Registro histórico de PRD-FR-046 — Print service. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-547`: Registro histórico de PRD-FR-047 — Printer routing. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-548`: Registro histórico de PRD-FR-048 — Print audit trail. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-550`: Registro histórico de PRD-FR-050 — Cash shifts. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-551`: Registro histórico de PRD-FR-051 — Opening cash fund. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-552`: Registro histórico de PRD-FR-052 — Cash movements. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-553`: Registro histórico de PRD-FR-053 — Payment methods. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-554`: Registro histórico de PRD-FR-054 — Immutable payments. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-555`: Registro histórico de PRD-FR-055 — Partial close. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-556`: Registro histórico de PRD-FR-056 — Cash count differences. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-557`: Registro histórico de PRD-FR-057 — Final close. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-558`: Registro histórico de PRD-FR-058 — Reopen evidence and audit. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-559`: Registro histórico de PRD-FR-059 — Driver cash settlement. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-560`: Registro histórico de PRD-FR-060 — Inventory ledger. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-561`: Registro histórico de PRD-FR-061 — Units by process. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-562`: Registro histórico de PRD-FR-062 — Exact conversions. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-563`: Registro histórico de PRD-FR-063 — Inventory reservation. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-564`: Registro histórico de PRD-FR-064 — Consumption. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-565`: Registro histórico de PRD-FR-065 — Release reservation. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-566`: Registro histórico de PRD-FR-066 — Post-production cancellation. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-567`: Registro histórico de PRD-FR-067 — Lots and expirations. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-568`: Registro histórico de PRD-FR-068 — Counts and authorized adjustments. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-569`: Registro histórico de PRD-FR-069 — Transfers. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-570`: Registro histórico de PRD-FR-070 — Kardex and theoretical stock. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-571`: Registro histórico de PRD-FR-071 — Classified real waste. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-572`: Registro histórico de PRD-FR-072 — Configurable waste reasons. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-573`: Registro histórico de PRD-FR-073 — Authorized idempotent waste confirmation. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-574`: Registro histórico de PRD-FR-074 — Immutable waste compensation. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-575`: Registro histórico de PRD-FR-075 — Waste costing and reconciliation. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-576`: Registro histórico de PRD-FR-076 — Transfer document and states. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-577`: Registro histórico de PRD-FR-077 — Authorized idempotent transfer out. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-578`: Registro histórico de PRD-FR-078 — Explicit destination receipt. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-579`: Registro histórico de PRD-FR-079 — Transfer differences and costing. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-580`: Registro histórico de PRD-FR-080 — Recursive recipes. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-581`: Registro histórico de PRD-FR-081 — Cycle detection. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-582`: Registro histórico de PRD-FR-082 — Recipe versioning. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-583`: Registro histórico de PRD-FR-083 — Yield. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-584`: Registro histórico de PRD-FR-084 — Planned and real waste. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-585`: Registro histórico de PRD-FR-085 — Batch production. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-586`: Registro histórico de PRD-FR-086 — Lot traceability. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-587`: Registro histórico de PRD-FR-087 — Real batch cost. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-588`: Registro histórico de PRD-FR-088 — Theoretical product cost. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-589`: Registro histórico de PRD-FR-089 — Weighted average cost. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-590`: Registro histórico de PRD-FR-090 — Standard cost. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-591`: Registro histórico de PRD-FR-091 — Central suppliers. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-592`: Registro histórico de PRD-FR-092 — Supplier contacts and branch terms. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-593`: Registro histórico de PRD-FR-093 — Purchase presentations. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-594`: Registro histórico de PRD-FR-094 — Informational presentation prices. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-595`: Registro histórico de PRD-FR-095 — Modifier groups and cardinality. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-596`: Registro histórico de PRD-FR-096 — Modifier inventory effects, kitchen text and exact administrative surcharge capture. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-597`: Registro histórico de PRD-FR-097 — Effective modifier snapshot. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-598`: Registro histórico de PRD-FR-098 — Modified reservation and consumption. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-599`: Registro histórico de PRD-FR-099 — Backend modifier pricing. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-600`: Registro histórico de PRD-FR-100 — Direct receipts. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-601`: Registro histórico de PRD-FR-101 — Supplier presentation and lot. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-602`: Registro histórico de PRD-FR-102 — XML import. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-603`: Registro histórico de PRD-FR-103 — XML duplicate. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-604`: Registro histórico de PRD-FR-104 — Supplier mappings. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-605`: Registro histórico de PRD-FR-105 — Accounts payable. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-606`: Registro histórico de PRD-FR-106 — AP payments and balances. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-607`: Registro histórico de PRD-FR-107 — XML evidence retention. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-608`: Registro histórico de PRD-FR-108 — Direct purchase and cash reconciliation. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-609`: Registro histórico de PRD-FR-109 — Receipt-driven weighted average cost. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-610`: Registro histórico de PRD-FR-110 — Purchase idempotency and compensations. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-611`: Registro histórico de PRD-FR-111 — Base inventory cost policy. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-620`: Registro histórico de PRD-FR-120 — Delivery zones. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-621`: Registro histórico de PRD-FR-121 — Geocoding. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-622`: Registro histórico de PRD-FR-122 — Distance and ETA. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-623`: Registro histórico de PRD-FR-123 — Route optimization. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-624`: Registro histórico de PRD-FR-124 — Multi-order driver routes. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-625`: Registro histórico de PRD-FR-125 — Delivery windows. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-626`: Registro histórico de PRD-FR-126 — Manual route override. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-627`: Registro histórico de PRD-FR-127 — Manual dispatch fallback. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-628`: Registro histórico de PRD-FR-128 — Delivery state registration. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-629`: Registro histórico de PRD-FR-129 — Driver settlement. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-640`: Registro histórico de PRD-FR-140 — Versioned APIs. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-641`: Registro histórico de PRD-FR-141 — Idempotent webhooks. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-642`: Registro histórico de PRD-FR-142 — Integration health/errors. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-643`: Registro histórico de PRD-FR-143 — Safe retries. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-644`: Registro histórico de PRD-FR-144 — Pause branch in channels. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-645`: Registro histórico de PRD-FR-145 — Chatbot system queries. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-646`: Registro histórico de PRD-FR-146 — Chatbot no invention. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-647`: Registro histórico de PRD-FR-147 — External adapters. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-660`: Registro histórico de PRD-FR-160 — Individual export. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-661`: Registro histórico de PRD-FR-161 — Global export. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-662`: Registro histórico de PRD-FR-162 — Legal entity separation. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-663`: Registro histórico de PRD-FR-163 — Export canonical data. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-664`: Registro histórico de PRD-FR-164 — Export deduplication. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-665`: Registro histórico de PRD-FR-165 — Re-export. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-666`: Registro histórico de PRD-FR-166 — CONTPAQi adapters. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-667`: Registro histórico de PRD-FR-167 — Export history and reconciliation. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-680`: Registro histórico de PRD-FR-180 — Edge gateway; PCO-008 local para caja manual. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-681`: Registro histórico de PRD-FR-181 — Local coordination. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-682`: Registro histórico de PRD-FR-182 — Two-hour offline. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-683`: Registro histórico de PRD-FR-183 — Several offline registers. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-684`: Registro histórico de PRD-FR-184 — Outbox, inbox, idempotency; PCO-008 cash manual. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-685`: Registro histórico de PRD-FR-185 — Reconciliation allowlisted de caja manual. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-686`: Registro histórico de PRD-FR-186 — Sync status POS PCO-008. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-687`: Registro histórico de PRD-FR-187 — No duplicate/loss. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-688`: Registro histórico de PRD-FR-188 — Local KDS and printing. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-689`: Registro histórico de PRD-FR-189 — External continuity. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-690`: Registro histórico de PRD-FR-190 — Idempotent legacy import batches. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-691`: Registro histórico de PRD-FR-191 — Organization catalog with branch operations. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-692`: Registro histórico de PRD-FR-192 — Deterministic station or product review. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-693`: Registro histórico de PRD-FR-193 — Incomplete presentation and recipe review. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-694`: Registro histórico de PRD-FR-194 — Legacy cost is non-operational reference. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-695`: Registro histórico de PRD-FR-195 — Paginated branch customer directory. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-696`: Registro histórico de PRD-FR-196 — Corporate catalog and local availability adjustments. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-697`: Registro histórico de PRD-FR-197 — Import retry and audit. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-698`: Registro histórico de PRD-FR-198 — Phone-first POS customer registration. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-699`: Registro histórico de PRD-FR-199 — Organization-wide order comments assigned through expandable operational categories and stable `category_id` subcategory checkboxes, with independent catalog/error loading, current-preview confirmation, visible cart text and reversible 0028 state restoration. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-700`: Registro histórico de PRD-FR-200 — Universal add-only extras with complete canonical configuration, exact 1..99 POS portions and no sale through historical option IDs. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-701`: Registro histórico de PRD-FR-201 — Separate canonical comments and extras; legacy product-assignment endpoints are read-only in new configuration. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-702`: Registro histórico de PRD-FR-202 — Reversible legacy catalog cleanup. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-703`: Registro histórico de PRD-FR-203 — Single product grid and removable POS cart lines. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-704`: Registro histórico de PRD-FR-204 — Pedidos detail, exact active-branch PENDING notification, selected-order edit routing, snapshot-backed cart restoration and versioned amendment. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-705`: Registro histórico de PRD-FR-205 — Supervisor-authorized courtesy adjustments; auditoría 2026-08-19 detectó UI simulada sin autoridad backend. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-706`: Registro histórico de PRD-FR-206 — Branch-originated supplier creation; contrato/permiso/atomicidad implementados. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-707`: Registro histórico de PRD-FR-207 — Branch multi-line direct purchases; implementado con cobertura de alcance y cancelación. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-708`: Registro histórico de PRD-FR-208 — Deferred payment confirmation attributed to the OPEN collection shift under the shared cash guard. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-709`: Registro histórico de PRD-FR-209 — POS-only navigation, inventory under Administration, four category-first operational groups and local product-specific Favorites that open directly to concrete products. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-710`: Registro histórico de PRD-FR-210 — Audited corporate driver catalog assigned by branch. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-711`: Registro histórico de PRD-FR-211 — Branch-scoped POS driver assignment with immutable delivery history. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-712`: Registro histórico de PRD-FR-212 — POS attendance clock with six-character organization-unique staff identifiers, atomic administrator self-edit recovery, branch-local daily pairing and scoped report. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-713`: Registro histórico de PRD-FR-213 — Required single-select category option before concrete POS product, explicit editable assignment, branch projection, corporate catalog.manage administration and fail-closed incomplete coverage. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-714`: Registro histórico de PRD-FR-214 — Compact fallback and legible name only for concrete POS products without a usable photograph; photographed products and category preselector preserve current behavior. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-729`: Registro histórico de PRD-FR-229 — Progressive POS catalog stages, persistent menu reset with direct-product Favorites exception, compact previous context and modifier-group tabs without changing catalog, pricing, cart or order authority. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-715`: Registro histórico de PRD-FR-215 — Perfiles persistidos, autorización branch/org, bootstrap/mapping gobernados y contención forward-only de 0049 sin inferir autoridad; PCO-002+ conserva sus paquetes propios. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-716`: Registro histórico de PRD-FR-216 — PCO-002/003 más PCO-008P para caja manual offline; publicación pendiente de CI/PR. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-717`: Registro histórico de PRD-FR-217 — Account consultation plus implemented PCO-005A request/decision and PCO-005B linked compensating correction. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-718`: Registro histórico de PRD-FR-218 — PCO-004 operational shift lifecycle and snapshot-backed traceable sales monitor. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-719`: Registro histórico de PRD-FR-219 — PCO-006 implementado y auditado localmente: cajero/turno canónicos, snapshot Python exacto, asociaciones exclusivas y reapertura compensatoria; PostgreSQL CI y QA visual permanecen como gates de cierre. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-720`: Registro histórico de PRD-FR-220 — Branch/corporate recipe versioning, historical ingredient sales and canonical scoped expense reports. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-721`: Registro histórico de PRD-FR-221 — SDD §39.1/39.3, ADR-030 aprobada: scanner y guards focales implementados; el cierre transversal de rutas default-deny, KDS, sync y seed sigue pendiente de evidencia completa. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-722`: Registro histórico de PRD-FR-222 — SDD §39.1/39.3: impresión verificable; cotización Python compartida; pago, KDS y fulfillment como autoridades separadas. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-723`: Registro histórico de PRD-FR-223 — SDD §39.2, ADR-031: intención pública idempotente, terminal y validada en Python; rechazo autorizado sin efectos y expiración reservada. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-724`: Registro histórico de PRD-FR-224 — SDD §39.2/39.3: aceptación autenticada por dominio compartido, reserva de inventario atómica, sin turno público fantasma. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-725`: Registro histórico de PRD-FR-225 — Generación automática de conciliación diaria de sucursal (corte Z extendido, desglose multicanal y balance sobrante/faltante). Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-726`: Registro histórico de PRD-FR-226 — Consolidado multi-sucursal diario/mensual, estado de auditoría y exportación a Excel (.xlsx formato Kiwi). Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-727`: Registro histórico de PRD-FR-227 — Autoservicio web móvil y captura de pedidos públicos con intención canónica; la captura no toca caja y la UI sólo confirma una referencia persistida. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-728`: Registro histórico de PRD-FR-228 — SDD §41, ADR-032/033: diálogo asistido con OpenRouter redactado, preguntas canónicas y borrador sin autoridad de pedido. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-730`: Registro histórico de PRD-FR-230 — SDD §43, ADR-034: asistente Admin implementado con QA visual sintético y gate PostgreSQL de CI; proveedor real, ejecución CI y staging pendientes. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-731`: Registro histórico de PRD-FR-231 — SDD §44: portada estática aislada, selección móvil sólo en `/`, variantes no cacheables y recursos contenidos. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-732`: Registro histórico de PRD-FR-232 — SDD §5.12: Hub de Integraciones desacoplado, configuración segura y adaptadores Uber Eats / DiDi Food / Rappi con validación HMAC e idempotencia. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-733`: Registro histórico de PRD-FR-233 — SDD §5.12: Monitor y gestión de pedidos Uber Eats / DiDi Food / Rappi en terminal POS con control de estados y despacho. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-734`: Registro histórico de PRD-FR-234 — Configuración multi-sucursal de enlace directo de Google Reviews en Administrador y exposición pública. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-735`: Registro histórico de PRD-FR-235 — Smart Rating de satisfacción en confirmación de pedido y retención de feedback privado. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-736`: Registro histórico de PRD-FR-236 — SDD §45: venta cruzada determinista, complementaria y acotada al catálogo efectivo de la sucursal, sin autoridad sobre checkout. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-FR-737`: Auto-registro y vinculación de clientes por pedido (POS y App Móvil) y trazabilidad de calificaciones promedio y comentarios en directorio de clientes del Administrador. El feedback público deriva identidad, organización y sucursal de un pedido o intención persistida cuya referencia y teléfono coinciden; el cliente público no puede elegir `customer_id`, sobrescribir feedback ajeno ni contaminar otra organización.
- `PRD-FR-738`: Suite Móvil de Administración y Puesta en Marcha Rápida en admin-web (Bottom Navigation Bar, Monitor de Pedidos con cobro y entrega integrada, Gestión de Turno de Caja, Catálogo Ágil y Disponibilidad con IA/Fotos, Configuración de Sucursal y Enlaces Compartibles). Al marcar un pedido como listo o entregado desde el monitor móvil, el sistema permite registrar y confirmar el cobro con el método de pago seleccionado contra el turno de caja abierto, asegurando que la venta compute en cortes y reportes. Los comandos de caja conservan la misma `Idempotency-Key` al reintentar un resultado incierto para el mismo payload y los movimientos manuales exigen una referencia de evidencia capturada por el operador; nunca se inventa una evidencia fija.
- `PRD-NFR-501`: Registro histórico de PRD-NFR-001 — Offline-first gateway. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-NFR-502`: Registro histórico de PRD-NFR-002 — Idempotency and command log; PCO-008P publicado sólo tras CI/PR. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-NFR-503`: Registro histórico de PRD-NFR-003 — Performance envelope. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-NFR-504`: Registro histórico de PRD-NFR-004 — Local latency. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-NFR-505`: Registro histórico de PRD-NFR-005 — Cloud latency. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-NFR-506`: Registro histórico de PRD-NFR-006 — Security. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-NFR-507`: Registro histórico de PRD-NFR-007 — Auditability. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-NFR-508`: Registro histórico de PRD-NFR-008 — Recovery. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-NFR-509`: Registro histórico de PRD-NFR-009 — Observability. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-NFR-510`: Registro histórico de PRD-NFR-010 — Maintainability and pull-request quality ratchet. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-NFR-511`: Registro histórico de PRD-NFR-011 — Portability. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-NFR-512`: Registro histórico de PRD-NFR-012 — Exact arithmetic. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-NFR-513`: Registro histórico de PRD-NFR-013 — Future multi-company. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-NFR-514`: Registro histórico de PRD-NFR-014 — Privacy. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-NFR-515`: Registro histórico de PRD-NFR-015 — Gateway compatibility. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-NFR-516`: Registro histórico de PRD-NFR-016 — Frontend CI quality gate. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-NFR-517`: Registro histórico de PRD-NFR-017 — Alembic revision capacity and percent-safe ConfigParser adapter. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-NFR-518`: Registro histórico de PRD-NFR-018 — Operational localization. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-NFR-519`: Registro histórico de PRD-NFR-019 — Step-up supervisor authorization. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-NFR-520`: Registro histórico de PRD-NFR-020 — PCO-001 aporta autorización acumulativa; PCO-006 implementa actor, permiso, alcance, Dueño exclusivo y respuestas redactadas con auditoría. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-NFR-521`: Registro histórico de PRD-NFR-021 — Cálculo financiero exacto y append-only implementado para ledger y corte PCO-006; concurrencia PostgreSQL queda como gate CI. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-NFR-522`: Registro histórico de PRD-NFR-022 — Offline outbox/inbox y reautorización; PostgreSQL PCO-008P pendiente de CI. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-NFR-523`: Registro histórico de PRD-NFR-023 — Cash security audit and observability; publicación PCO-008P pendiente de CI. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-NFR-524`: Registro histórico de PRD-NFR-024 — PCO-001/006 conservan historia; 0058 contiene 0049 sin reconstrucción automática, acepta SUC06 sólo por decisión explícita con identidad y asignación canónicas, y deja cualquier divergencia a reconciliación humana; la huella limpia tiene oráculo PostgreSQL/CI histórico y el camino SUC06 queda condicionado al snapshot PostgreSQL y CI del hotfix. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-NFR-525`: Registro histórico de PRD-NFR-025 — Implemented PCO-005B atomic idempotent compensating correction with Python authority, locking, rollback and redaction. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-NFR-526`: Registro histórico de PRD-NFR-026 — SDD §39.1: política de repositorio, fixtures sintéticos y contención separada. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-NFR-527`: Registro histórico de PRD-NFR-027 — SDD §39.1/39.2: éxito sólo por respuesta persistida y recuperación idempotente. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-NFR-528`: Registro histórico de PRD-NFR-028 — SDD §39.2: esquema, límites, rate limiting y PII redactada en escritura pública. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-NFR-529`: Registro histórico de PRD-NFR-029 — SDD §41, ADR-032/033: OpenRouter sólo en backend, PII redactada, salida estricta y autoridad Python intacta. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.
- `PRD-NFR-530`: Registro histórico de PRD-NFR-030 — SDD §43, ADR-034: frontera backend default-off, contexto mínimo, logs redactados y autoridad Python probados sin red real. Su alcance y evidencia se conservan en BDD/TDD históricos; no añade alcance comercial.

## Aclaración de alcance aprobada: recuperación SaaS 2026-09-07

PRD-FR-001..005 y PRD-FR-003 gobiernan registro con plan/prueba de 14 días, onboarding persistido y aislamiento por organización. Cada restaurante tiene URL y web móvil propias vinculadas a su POS/KDS. Superadmin sólo por privilegio persistido; alta pública no concede privilegios de plataforma. DiDi/Rappi quedan configurables pendientes de contrato, Uber conserva su adaptador real. Recetas/costeo por gramos no son requisito de primera venta; los históricos permanecen protegidos. Elegir plan no confirma pago. Los tiempos/metas anteriores son objetivos por verificar, no garantías de disponibilidad.
