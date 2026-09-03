# Contexto del producto: POS-SaaS

## 1. Visión y Propósito

**POS-SaaS** es una plataforma en la nube (SaaS Multi-tenant) diseñada específicamente para micro y pequeños negocios gastronómicos en México y Latinoamérica:
- Taquerías
- Cafeterías
- Dark kitchens
- Fondas
- Pizzerías
- Food trucks y carritos

El objetivo central es erradicar la burocracia, costos exorbitantes y fricción técnica de los ERPs tradicionales, ofreciendo una solución que se configura en **5 minutos**, con planes accesibles entre **$349 y $599 MXN / mes**.

---

## 2. Los 5 Dolores Críticos que Resuelve

1. **POS Táctil Ultrarrápido:**
   - Toma de comandas y cobro en mostrador o mesas en segundos desde tablets económicas, iPads o computadoras.
   - División de cuentas, propinas sugeridas, control estricto de turnos y cortes de caja (Corte X y Corte Z) para eliminar fugas de efectivo.

2. **Delivery Hub Unificado:**
   - Recepción centralizada de pedidos de Uber Eats, DiDi Food y Rappi en una única pantalla y comanda de cocina.
   - **Kill-Switch Global:** Un solo botón maestro para pausar o apagar platillos agotados en simultáneo en todas las apps de delivery.

3. **Autofacturación 1-Click (CFDI 4.0 SAT):**
   - Ticket con código QR dinámico y URL corta única.
   - El comensal escanea el QR desde su celular, captura su RFC y datos fiscales en menos de 1 minuto y recibe su factura CFDI 4.0 al instante sin saturar al cajero.

4. **Menú Web con Pedidos por WhatsApp:**
   - Menú digital responsivo propio (sin la comisión del 30% de las plataformas).
   - Carrito de compras con selección de variantes/modificadores y checkout con mensaje estructurado directo al WhatsApp del restaurante.

5. **Backoffice Ultraligero y Multi-tenant:**
   - Registro autoservicio (Sign up en 5 minutos) con aprovisionamiento inmediato.
   - Catálogo ágil con precios diferenciados por canal (Salón vs Delivery Apps para absorber comisiones).
   - Reportes ejecutivos automatizados enviados diariamente al WhatsApp o correo del dueño.

---

## 3. Estrategia Técnica y Podado de Complejidad

El proyecto se apoya en un código base gastronómico probado, aplicando una estricta estrategia de simplificación:
- **REUTILIZAR:**
  - Backend modular en FastAPI (Python tipado) con SQLAlchemy y PostgreSQL.
  - Frontend moderno en React 19 + TypeScript estricto con Vite.
  - Sincronización y resiliencia offline local (SQLite en gateway para operaciones sin internet).
  - Adaptadores existentes de FacturAPI (CFDI 4.0) y agregadores de delivery (Uber Eats, DiDi Food, Rappi).
- **PODAR PARA MVP (Fuera de alcance inicial):**
  - Costeo teórico gramo a gramo y recetas/subrecetas multinivel.
  - Lotes de producción interna de elaborados (panadería, salsas por lote).
  - Múltiples almacenes por sucursal y traspasos inter-almacén.
  - Cuentas por pagar, recepción de compras con XML de proveedores a crédito.
  - Despacho y optimización de rutas avanzadas para flotas de repartidores propios.

---

## 4. Modelo de Negocio e Infraestructura

- **Modelo:** Suscripción mensual / anual autoservicio (Tier Básico $349 MXN, Tier Pro $599 MXN).
- **Multi-tenancy:** Base de datos relacional compartida con aislamiento estricto por `organization_id` en todas las consultas y mutaciones.
- **Despliegue:** API y servicios centrales en contenedores Docker gestionados vía Easypanel / Cloud VPS, con bases de datos PostgreSQL y Redis.
