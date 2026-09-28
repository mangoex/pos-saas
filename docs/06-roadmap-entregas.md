# Roadmap de entregas

## Remediación SaaS 2026-09-28

Alcance acotado y evidencia: `docs/reports/saas-completed-fixes-2026-09-28.md`.
WhatsApp y sus flujos Meta quedan aplazados por decisión del usuario; no forman parte del release.
El historial de fases siguientes se conserva y no acredita implementación productiva actual.

## Principio

Construir vertical slices utilizables. No desarrollar todos los módulos horizontalmente antes de probar operación real.

## Fase 0 — Harness y plataforma

Entregables:

- monorepo,
- CI/CD,
- entornos,
- autenticación,
- organización,
- sucursales,
- dispositivos,
- logging,
- auditoría,
- migraciones,
- contratos,
- feature flags.

Gate:

- despliegue en staging,
- migración reproducible,
- observabilidad,
- smoke tests.

## Fase 1 — Venta local, cocina y caja

Vertical slice:

1. abrir caja,
2. crear pedido,
3. enviar a cocina,
4. imprimir,
5. completar,
6. cobrar,
7. cerrar caja.

Incluye:

- catálogo mínimo,
- POS,
- KDS,
- estaciones,
- impresión,
- pagos,
- corte,
- gateway local,
- operación offline básica.

Gate:

- piloto en una sucursal,
- prueba de dos horas offline,
- cero pedidos perdidos,
- reimpresión auditada.

### Ola inmediata OPS-WAVE-001

Antes de declarar estable la venta local y abrir el piloto ampliado se entregan, en este orden:

1. `POS-CAT-002/003`: comentarios corporativos por producto y adicionales universales;
2. `POS-ORD-002`: retiro de carrito y enmiendas de pedidos no pagados;
3. `POS-SEC-001`: cortesías append-only con reautenticación de Supervisor;
4. `PUR-OPS-001`: alta controlada de proveedores y compras desde la sucursal.

Cada incremento se integra y despliega antes de iniciar la siguiente migración. Compras cubre en
esta ola efectivo, tarjeta y transferencia; crédito permanece en Fase 3 hasta tener cuenta por pagar.

### Bloque de remediación previa a piloto — auditoría 2026-08-19

La ola inmediata no puede declararse cerrada con la evidencia actual. Se ejecutan cuatro paquetes R3
independientes y secuenciales:

1. `SEC-001`: contención de artefactos sensibles y guards default-deny de seed/KDS/sync/print.
   `SEC-001A` cubre código/CI; `SEC-001B` cubre privacidad, rotación e historia Git y requiere
   autorización operacional separada.
2. `OPS-WAVE-001R`: sustituir cortesía y reimpresión simuladas, y reparar proveedor/compra contra
   permisos, scope, atomicidad, `Decimal` Python y compensaciones aprobadas.
3. `MOB-ORD-001`: intención pública persistida/idempotente, UI sin éxito falso y aceptación por el
   dominio canónico sin crear turnos de caja.
4. `PCO-008P`: trasplantar el paquete PCO-008/008R aprobado pero no publicado, conservar ADR-028/029,
   remapear por colisión a BDD-SC-393..403 y TDD-TC-171..181, y resolver integración sobre la head resultante.

Cada paquete completa PRD/SDD/BDD/TDD/matriz, RED, implementación mínima Terra, GREEN focal,
PostgreSQL/SQLite cuando aplique, CI, QA visual, auditoría independiente Sol y publicación autorizada
antes de iniciar el siguiente. Ninguno puede usar `DATABASE_URL`, datos productivos o evidencia de un
commit anterior como sustituto del gate actual. El piloto queda bloqueado hasta cerrar los cuatro y
resolver los pendientes mínimos de producción/readiness en una revisión final proporcional.

## Fase 2 — Inventario, recetas y producción

Incluye:

- unidades,
- conversiones,
- recetas,
- subrecetas,
- lotes,
- caducidad,
- reserva,
- consumo,
- merma,
- producción por lote,
- costo promedio,
- costo estándar,
- kardex,
- conteos,
- traspasos.

Gate:

- costeo reproducible,
- conciliación de consumo,
- trazabilidad de lote.

## Fase 3 — Compras y cuentas por pagar

Incluye:

- proveedores,
- recepciones,
- XML,
- equivalencias,
- crédito,
- vencimientos,
- pagos,
- devoluciones.

Gate:

- XML duplicado bloqueado,
- recepción genera inventario,
- crédito genera saldo.

## Fase 4 — Domicilio y rutas

Incluye:

- clientes,
- direcciones,
- zonas,
- costos,
- tiempos,
- repartidores,
- optimización,
- despacho manual,
- liquidación.

Gate:

- rutas sugeridas,
- fallback manual,
- cobros conciliados.

## Fase 5 — Canales externos

Incluye:

- WhatsApp,
- chatbot,
- marketplaces,
- mapeos,
- webhooks,
- idempotencia,
- health,
- reintentos,
- DLQ.

Gate:

- pedidos externos sin recaptura,
- duplicados bloqueados,
- incidencias visibles.

## Fase 6 — Exportación fiscal

Incluye:

- modelo canónico,
- factura individual,
- global,
- adaptador configurable,
- lotes,
- conciliación,
- reexportación.

Gate:

- importación validada en la versión real de CONTPAQi.

## Fase 7 — Despliegue a siete sucursales

Incluye:

- instalación de gateways,
- matriz de impresoras,
- capacitación,
- migración de catálogos,
- monitoreo,
- soporte,
- rollback.

## Backlog posterior

- app del repartidor,
- tracking,
- pago en línea,
- promociones avanzadas,
- fidelización,
- pronóstico,
- multiempresa autoservicio,
- CFDI directo.
