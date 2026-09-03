# SDD — Software Design Document: POS-SaaS
## Arquitectura Multi-Tenant para Micro-POS Gastronómico en la Nube

---

## 1. Objetivo y Alcance Técnico

Definir la arquitectura de software, modelo de aislamiento multi-tenant, contratos de API, estrategia de persistencia y flujo de datos para **POS-SaaS**, una solución cloud ligera, resiliente y autoservicio orientada a micro y pequeños restaurantes en México y Latinoamérica.

El diseño prioriza:
- **Onboarding autoservicio en < 5 minutos** (sin intervención humana ni infraestructura local compleja).
- **Aislamiento multi-tenant estricto** en PostgreSQL compartido.
- **Resiliencia operativa** (cobro continuo en POS con sincronización local).
- **Inmutabilidad financiera** en pagos, turnos y cortes de caja.
- **Desacople radical de la complejidad de ERPs tradicionales** (recetas complejas, costeo gramo a gramo, traspasos inter-almacén quedan hibernados).

---

## 2. Principios de Arquitectura

1. **Aislamiento Multi-Tenant por Columna con Row-Level Enforcement:** Toda entidad del dominio cuenta con `organization_id`. Cada consulta y mutación en la API resuelve y filtra forzosamente por la organización autenticada.
2. **Monolito Modular Cloud-First:** Un único backend en FastAPI (`apps/api`) altamente cohesivo y modularizado por bounded contexts (Auth, Tenant, Catalog, Orders, Cash, Delivery, Invoicing).
3. **Frontend Especializado en Monorepo:** Aplicaciones independientes en React 19 + TypeScript + Vite:
   - `pos-web`: Terminal táctil ultrarrápida para mostrador y mesas.
   - `admin-web`: Backoffice ejecutivo para configuración y métricas.
   - `mobile-web`: Menú web público y generador de pedidos a WhatsApp.
   - `kds-web`: Pantalla de comandas en cocina.
4. **Idempotencia y Eventos Inmutables:** Comandos de pago, aperturas, cierres de caja y webhooks externos emplean `idempotency_key` y registros append-only.
5. **Precisión Numérica Absoluta:** Todos los montos monetarios se representan en `Decimal` o enteros en centavos (unidad mínima monetaria MXN). Queda prohibido el uso de punto flotante binario (`float`).
6. **Fechas en UTC con Presentación Local:** Almacenamiento en UTC (`DateTime(timezone=True)`) y renderizado según el timezone configurado en la sucursal (ej. `America/Mexico_City`, `America/Chihuahua`).

---

## 3. Topología del Sistema y Componentes

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                            CLIENTES FRONTEND                                │
│                                                                             │
│   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌────────────┐   │
│   │   pos-web    │   │  admin-web   │   │  mobile-web  │   │  kds-web   │   │
│   │ (POS Táctil) │   │ (Backoffice) │   │ (Menú & WA)  │   │  (Cocina)  │   │
│   └──────┬───────┘   └──────┬───────┘   └──────┬───────┘   └─────┬──────┘   │
└──────────┼──────────────────┼──────────────────┼─────────────────┼──────────┘
           │                  │                  │                 │
           ▼                  ▼                  ▼                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         API GATEWAY & BACKEND (FastAPI)                     │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Tenant Resolution & Auth Middleware (JWT / Session / Public Slug)   │   │
│   └──────────────────────────────────┬──────────────────────────────────┘   │
│                                      │                                      │
│   ┌──────────────────────────────────┴──────────────────────────────────┐   │
│   │                      MÓDULOS DE DOMINIO POS-SAAS                    │   │
│   │                                                                     │   │
│   │  [Tenant / Onboarding]   [Catálogo & Precios]   [Caja, Turnos & X/Z]│   │
│   │  [Órdenes & Comandas]    [Delivery Hub Unif.]   [Autofacturación]   │   │
│   └──────────────────────────────────┬──────────────────────────────────┘   │
└──────────────────────────────────────┼──────────────────────────────────────┘
                                       │
           ┌───────────────────────────┼───────────────────────────┐
           ▼                           ▼                           ▼
┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│    PostgreSQL       │     │     FacturAPI       │     │  Delivery Hub Apps  │
│  (Base Multi-tenant │     │    (CFDI 4.0 SAT    │     │ (Uber Eats, DiDi,   │
│   con org_id keys)  │     │   PAC Autorizado)   │     │  Rappi Webhooks/API)│
└─────────────────────┘     └─────────────────────┘     └─────────────────────┘
```

---

## 4. Estrategia Multi-Tenancy y Aprovisionamiento Autoservicio

### 4.1 Modelo de Datos Multi-Tenant

Se implementa el patrón **Shared Database, Shared Schema with Tenant Column Isolation**.
- La clave de partición lógica es `organization_id` (UUIDv4).
- Todas las tablas de datos de negocio (`branches`, `products`, `orders`, `cash_shifts`, `payments`, `users`, `roles`) contienen `organization_id` indexado.
- La restricción de unicidad en identificadores de negocio (códigos de producto, folios de tickets, emails de sucursales) se modela de forma compuesta:
  ```sql
  UNIQUE(organization_id, code)
  UNIQUE(organization_id, folio)
  ```

### 4.2 Resolución de Tenant en Peticiones (Tenant Context)

Existen tres mecanismos deterministas de resolución de tenant en la API:

1. **Sesión Autenticada (Admin, POS, KDS):**
   - El token Bearer JWT contiene `sub` (user_id), `email` y `org_id`.
   - La dependencia FastAPI `get_current_tenant_context(session, token)` valida la vigencia del token y extrae el `organization_id`.
   - Todas las consultas de repositorio inyectan automáticamente el predicado:
     `where(table.c.organization_id == tenant_context.organization_id)`.

2. **Acceso Público a Menú Web (`mobile-web`):**
   - Ruta pública: `GET /api/v1/public/catalog/{tenant_slug}`.
   - El resolver busca en `organizations` por `slug` y obtiene el `organization_id` correspondiente sin requerir autenticación previa.

3. **Acceso a Autofacturación Comensal:**
   - Ruta pública: `GET /api/v1/public/invoicing/ticket/{invoice_token}`.
   - El resolver busca el ticket por su token criptográfico único y resuelve el tenant y orden de forma segura.

### 4.3 Flujo Atómico de Sign Up y Aprovisionamiento (Onboarding en 5 Minutos)

Para habilitar el autoservicio sin barreras técnicas, se implementa el endpoint público:
`POST /api/v1/auth/signup`

**Payload:**
```json
{
  "business_name": "Taquería Los Compadres",
  "owner_name": "Carlos Rodríguez",
  "email": "carlos@tacoscompadres.com",
  "password": "PasswordSegura123!",
  "phone": "+525512345678",
  "business_type": "taqueria"
}
```

**Transacción Atómica en Base de Datos:**
1. Crea registro en `organizations` (`name`, `slug`, `status='active'`).
2. Crea registro en `legal_entities` con razón social inicial genérica editable posteriormente.
3. Crea registro en `business_units` y `branches` ("Sucursal Matriz", timezone local).
4. Crea registro en `warehouses` ("Almacén Mostrador") vinculado a la sucursal.
5. Siembra roles predeterminados para el tenant:
   - `Owner`: Permisos completos de gestión, catálogo, caja, facturación y reportes.
   - `Supervisor`: Supervisión de sucursal, cortes Z y kill-switch.
   - `Cajero`: Apertura/cierre de turnos, captura y cobro en POS.
6. Crea usuario en `users` con rol `Owner`, contraseña hasheada con sal usando PBKDF2/SHA256 y estado `active`.
7. Siembra catálogo inicial sugerido según `business_type` (ej. si es "taqueria", genera categorías "Tacos", "Gringas", "Bebidas" con platillos modelo y modificadores básicos para que el usuario empiece de inmediato).
8. Genera token de sesión JWT y retorna perfil listo para entrar al Backoffice o POS.

---

## 5. Arquitectura de los 5 Pilares Críticos

### 5.1 Pilar 1: POS Táctil Ultrarrápido & Turnos de Caja (Cortes X y Z)

#### Máquina de Estados de Turno de Caja (`cash_shifts`):
- `OPEN`: Turno abierto con fondo inicial obligatorio (`opening_amount`).
- `CLOSED`: Turno cerrado tras arqueo de efectivo y generación de Corte Z.

#### Flujo de Arqueo a Ciegas (Prevención de Fugas de Efectivo):
1. Al pulsar "Cerrar Turno", el cajero ve únicamente la pantalla de captura de denominaciones (billetes de $500, $200, $100, etc. y monedas).
2. El sistema **no muestra** el total esperado en efectivo para evitar que el cajero ajuste los billetes contados al sistema.
3. El cajero confirma su conteo físico (`declared_cash`).
4. El backend calcula la diferencia:
   $$\text{diferencia} = \text{declared\_cash} - (\text{opening\_amount} + \text{cash\_sales} + \text{cash\_in} - \text{cash\_out})$$
5. Se almacena el registro inmutable de `cash_shift_cut` con desglose exacto:
   - Total Ventas Efectivo
   - Total Ventas Tarjeta
   - Total Ventas Transferencia
   - Total Propinas
   - Total Movimientos de Entrada/Salida
   - Sobrante o Faltante
6. Se envía automáticamente el corte a la impresora térmica y se dispara la notificación al dueño.

#### División de Cuentas (Split Bill):
- **Partes iguales:** Divide el gran total entre $N$ comensales. El redondeo de centavos sobrantes se asigna al primer ticket para garantizar suma exacta:
  $$\sum_{i=1}^{N} \text{subticket}_i = \text{total\_orden}$$
- **Por ítems:** Se seleccionan líneas del pedido actual y se transfieren a subcuentas independientes para cobro individual en diferentes métodos de pago.

### 5.2 Pilar 2: Delivery Hub Unificado & Kill-Switch Global

#### Adaptadores e Inyección Centralizada:
- Módulo `apps/api/restaurant_os/integrations/`:
  - `uber_eats.py`: Webhooks de creación, cancelación y estatus de Uber Eats.
  - `didi_food.py`: Webhooks de ordenes de DiDi Food.
  - `rappi.py`: Webhooks de pedidos de Rappi.
- Cada webhook recibido:
  1. Valida firma HMAC o token de autenticación del proveedor.
  2. Verifica `idempotency_key` en `integration_events`.
  3. Mapea el payload externo al contrato canónico `OrderCreate` interno.
  4. Inyecta la orden en `orders` con canal (`uber_eats`, `didi`, `rappi`) y emite evento WebSocket a `pos-web` y `kds-web`.

#### Kill-Switch Global (Botón Maestro de Agotados):
- Endpoint: `POST /api/v1/catalog/products/{id}/kill-switch`
- Parámetros: `branch_id`, `is_available: bool`, `sync_delivery: bool`.
- Ejecución:
  1. Actualiza `branch_product_availability` en la base de datos local.
  2. Si `sync_delivery = True`, lanza tareas asíncronas vía `DeliveryHubService` hacia las APIs de Uber Eats, DiDi y Rappi para marcar el `external_item_id` como agotado/pausado de inmediato.

### 5.3 Pilar 3: Autofacturación 1-Click (CFDI 4.0 SAT)

#### Arquitectura de Emisión Fiscal con FacturAPI:
- Al momento de cobro y cierre de un ticket en POS:
  1. Se genera un `invoice_token` criptográfico aleatorio no predecible (16 bytes base64url).
  2. Se asocia a la orden con fecha límite de facturación (ej. último día del mes en curso).
  3. Se imprime en el ticket:
     - URL corta: `https://factura.pos-saas.com/f/{invoice_token}`
     - Código QR con la URL codificada.

#### Portal Móvil de Comensal (`/f/{token}`):
- Front estático ultraligero cargado en el navegador móvil del comensal.
- Valida token contra `GET /api/v1/public/invoicing/ticket/{token}`.
- Muestra monto del ticket, fecha y sucursal.
- Formulario con autocompletado y validación de RFC mexicano (formato regex oficial SAT).
- Al pulsar "Emitir Factura":
  1. Invoca `POST /api/v1/public/invoicing/issue-cfdi`.
  2. Backend llama a `FacturAPIClient` con CSD del tenant.
  3. FacturAPI timbra ante el SAT en < 3 segundos.
  4. Retorna URLs firmadas de descarga de XML y PDF.
  5. Envía automáticamente correo con los comprobantes fiscales al comensal.
  6. Marca la orden como `invoiced = true` para evitar doble facturación.

### 5.4 Pilar 4: Menú Web & Pedidos Directos por WhatsApp

#### Topología de Menú Web (`apps/mobile-web`):
- PWA responsiva montada en subdominio o ruta: `/menu/{tenant_slug}`.
- Carga de catálogo optimizada mediante caché HTTP y CDN para apertura instantánea en redes 4G móviles.
- Selector interactivo de opciones y modificadores obligatorios/opcionales.

#### Generación y Formateo a WhatsApp:
- Al pulsar "Enviar Pedido por WhatsApp":
  1. Genera orden preliminar en `orders` con estado `pending_confirmation` y canal `whatsapp_web`.
  2. Construye el mensaje estructurado con emojis y formato Markdown de WhatsApp:
     - Encabezado con número de orden y nombre del cliente.
     - Detalle de productos y modificadores.
     - Total calculado con método de pago elegido.
     - Enlace de confirmación.
  3. Dispara deep-link `whatsapp://send?phone={branch_whatsapp}&text={encoded_message}` abriendo la app de WhatsApp del comensal lista para dar "Enviar".

### 5.5 Pilar 5: Backoffice Ultraligero & Precios por Canal

#### Catálogo Simplificado:
- Tabla `products` adaptada con dos columnas de precios directos:
  - `price_dine_in`: Precio estándar para comedor y mostrador.
  - `price_delivery`: Precio sugerido para apps externas con recargo de plataforma (configurable globalmente, ej. +25%).
- Edición ágil en `admin-web` con tabla editable y alternancia rápida de disponibilidad.

#### Control de Personal con PIN Rápido:
- Cada empleado cuenta con un PIN de 4 dígitos en `users.pin_hash`.
- En el POS físico, al cambiar de mesero o cajero, se despliega un teclado numérico táctil para autenticación en 1 segundo sin requerir teclear contraseñas alfanuméricas complejas.

#### Reportes Ejecutivos Diarios:
- Job programado al final del día o disparado tras el último corte Z.
- Genera payload consolidado y lo despacha vía webhook/WhatsApp API al teléfono del dueño:
  - Ventas totales del día vs día anterior.
  - Total en efectivo, tarjetas y apps de delivery.
  - Faltantes o sobrantes de caja reportados.
  - Top 3 platillos más vendidos.

---

## 6. Plan de Podado y Desacople de Módulos ERP Tradicional

Para mantener la base de código limpia, mantenible y enfocada en el éxito del SaaS, los siguientes módulos heredados entran en modo **Hibernado / Desacoplado**:

| Módulo Heredado | Estado en POS-SaaS | Acción en Arquitectura |
|---|---|---|
| **Recetas y Subrecetas Multinivel** | Hibernado | Deshabilitar rutas en `admin-web`. Mantener tablas en BD sin forzar dependencias en la creación de platillos. |
| **Costeo Gramo a Gramo / Rendimientos** | Hibernado | Desacoplado del flujo de venta. Los platillos no requieren costeo teórico para venderse. |
| **Producción por Lotes de Elaborados** | Hibernado | Ocultar del menú de navegación. |
| **Traspasos Multi-Almacén** | Hibernado | Cada sucursal opera con un único almacén principal asociado por defecto. |
| **Cuentas por Pagar & XML Proveedores** | Hibernado | Deshabilitar pantallas y controladores de recepción de compras con XML. |
| **Rutas & Despacho de Repartidores Propios**| Hibernado | Los pedidos a domicilio se asignan de forma directa simple sin cálculo geográfico de rutas. |

---

## 7. Plan de Seguridad y Cumplimiento

1. **Protección de Datos Multi-Tenant:** Ninguna consulta SQL o llamada a ORM puede omitir el filtro de `organization_id`. Se auditará mediante pruebas de penetración automatizadas que intenten consultar recursos de la Organización A con credenciales de la Organización B.
2. **Cifrado de Credenciales y PINs:**
   - Contraseñas con PBKDF2-SHA256 (260,000 iteraciones).
   - PINs de cajero hasheados antes de almacenamiento.
   - Tokens de sesión JWT firmados con HMAC-SHA256 y expiración determinista.
3. **Resguardo de Certificados SAT (CSD):**
   - Las llaves privadas (`.key`) y certificados (`.cer`) de los clientes para facturación se delegan de forma segura en la bóveda de FacturAPI o se almacenan cifrados con AES-256 en el backend.
