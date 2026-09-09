# TDD — Test-Driven Development Strategy

> Registro histórico RestaurantOS: referencias PRD renumeradas +500 para evitar colisiones
> semánticas con SaaS. Los suplementos anteriores al paquete SaaS conservan evidencia del
> producto previo; no certifican comportamiento SaaS vigente. El contrato nuevo está en
> `03-BDD-saas-remediation.md` y `04-TDD-saas-remediation.md`.


## 1. Objetivo

Definir cómo se construirá cada comportamiento mediante pruebas primero, con cobertura de dominio, infraestructura, sincronización e interfaces.

## 2. Ciclo obligatorio

1. Elegir requisito y escenario BDD.
2. Escribir prueba fallida.
3. Implementar la mínima solución.
4. Refactorizar.
5. Ejecutar regresión.
6. Actualizar trazabilidad.
7. Confirmar observabilidad y manejo de error.

## 3. Pirámide de pruebas

### 3.1 Unitarias
Para reglas puras:

- costeo,
- conversiones,
- máquinas de estado,
- permisos,
- cálculo de caja,
- selección de lotes,
- validación de recetas,
- normalización de pedidos,
- exportación canónica.

### 3.2 Integración
Para:

- PostgreSQL,
- SQLite,
- Redis,
- migraciones,
- repositorios,
- outbox/inbox,
- jobs,
- XML,
- archivos,
- impresión simulada.

### 3.3 Contrato
Para:

- API central,
- gateway,
- frontends,
- marketplaces,
- WhatsApp,
- rutas,
- CONTPAQi adapters.

### 3.4 End-to-end
Para flujos críticos:

- venta completa,
- offline y reconexión,
- cocina,
- caja,
- compra,
- lote,
- reparto,
- exportación.

### 3.5 Caos y resiliencia
Para:

- pérdida de internet,
- duplicación de mensajes,
- reinicio de gateway,
- caída de Redis,
- impresora no disponible,
- proveedor externo lento,
- reintentos,
- restauración de backup.

## 4. Suites

### TDD-TS-001 Costing
Casos:

- costo de receta simple,
- costo multinivel,
- costo con merma,
- costo por lote,
- costo estándar versionado,
- promedio ponderado,
- redondeos,
- inventario negativo,
- devolución,
- transferencia,
- ciclo rechazado.

### TDD-TS-002 Inventory Ledger
Casos:

- entrada,
- reserva,
- consumo,
- liberación,
- merma,
- reversión,
- conteo,
- traspaso,
- concurrencia,
- idempotencia.

### TDD-TS-003 Order State Machine
Casos:

- flujo ideal a domicilio (DRAFT a CLOSED),
- flujo ideal para recoger (READY a DELIVERED),
- cancelación desde estados previos a entrega,
- transiciones inválidas,
- estados alternos terminales (REJECTED, FAILED, RETURNED),
- cierre,
- reapertura,
- permisos,
- eventos generados.

### TDD-TS-004 Sync Engine
Casos:

- operación offline,
- reintento,
- duplicado,
- orden de eventos,
- checkpoint,
- reinicio,
- conflicto,
- dos cajas,
- lag,
- pérdida parcial de respuesta.

### TDD-TS-005 Cash
Casos:

- apertura,
- movimiento,
- corte parcial,
- arqueo,
- diferencia,
- cierre,
- reapertura,
- compensación de pago.

### TDD-TS-006 Production
Casos:

- tareas por estación,
- finalización conjunta,
- reapertura,
- incidencia,
- consumo,
- impresión.

### TDD-TS-007 Purchasing
Casos:

- XML válido,
- XML duplicado,
- receptor incorrecto,
- concepto no mapeado,
- recepción,
- cuenta por pagar,
- pago parcial,
- devolución.

### TDD-TS-008 Delivery
Casos:

- zona válida,
- zona inválida,
- geocodificación,
- agrupación,
- capacidad,
- ventanas,
- proveedor caído,
- despacho manual,
- liquidación.

### TDD-TS-009 Integrations
Casos:

- webhook válido,
- firma inválida,
- duplicado,
- producto no mapeado,
- confirmación,
- cancelación,
- rate limit,
- DLQ.

### TDD-TS-010 Exports
Casos:

- factura individual,
- global,
- separación por razón social,
- doble exportación,
- reexportación,
- redondeos,
- layout configurable,
- conciliación.

### TDD-TS-011 Printing
Casos:

- trabajo exitoso,
- impresora desconectada,
- reintento,
- duplicado,
- reimpresión autorizada,
- cambio de impresora,
- spooler reiniciado.

### TDD-TS-012 Security
Casos:

- RBAC,
- scope por sucursal,
- escalación,
- sesión expirada,
- rate limit,
- auditoría,
- secreto ausente.

## 5. Casos críticos detallados

### TDD-TC-001 Idempotencia de pedido externo

Given una clave idempotente ya procesada  
When se recibe el mismo comando  
Then se retorna el resultado original  
And no se insertan nuevas líneas, pagos ni eventos.

### TDD-TC-002 Reconexión después de confirmación perdida

Given la nube procesó el comando  
And el gateway no recibió respuesta  
When el gateway reintenta  
Then la nube reconoce la clave  
And retorna la confirmación existente  
And no duplica el pedido.

### TDD-TC-003 Dos cajas offline

Given dos cajas crean pedidos durante desconexión  
When ambas sincronizan  
Then sus UUID son distintos  
And sus folios locales no colisionan  
And ambos pedidos se conservan.

### TDD-TC-004 Consumo por receta versionada

Given un pedido usa receta versión 3  
And la receta vigente cambia a versión 4  
When se confirma producción del pedido original  
Then el consumo usa versión 3.

### TDD-TC-005 Cancelación posterior

Given existe consumo confirmado  
When se cancela  
Then no se borra el consumo  
And se genera merma o recuperación compensatoria.

### TDD-TC-006 Cierre de caja inmutable

Given un turno cerrado  
When un usuario intenta editar un movimiento previo  
Then la operación falla  
And se requiere reapertura o compensación auditada.

### TDD-TC-007 Exportación duplicada

Given un ticket pertenece a un lote confirmado  
When se intenta agregarlo a otro lote  
Then el sistema rechaza la operación.

## 6. Property-based testing

Aplicar a:

- conversiones de unidad,
- grafos de recetas,
- costo promedio,
- reservas y consumos,
- suma de pagos,
- redondeos,
- secuencias de sincronización,
- invariantes de caja.

Invariantes:

- ningún movimiento desaparece,
- existencia final = suma de movimientos,
- total de pagos = total cobrado,
- una receta válida no contiene ciclos,
- reintentar comando idempotente no cambia el estado,
- un ticket confirmado pertenece como máximo a un lote activo.

## 7. Mutation testing

Aplicar inicialmente a:

- costeo,
- inventario,
- caja,
- sincronización,
- exportaciones.

Meta inicial: mutation score mayor a 70% en módulos críticos.

## 8. Cobertura

No usar cobertura como única métrica.

Mínimos:

- dominio crítico: 90% branches,
- adaptadores: 80%,
- frontend operativo: 80% en lógica y componentes críticos,
- escenarios BDD críticos: 100% automatizados.

## 9. Datos de prueba

- Factories deterministas.
- Reloj inyectable.
- UUID predecible en tests.
- Zonas horarias explícitas.
- Fixtures por sucursal.
- Catálogos versionados.
- XML sintéticos sin datos reales.
- Direcciones de prueba.
- Impresoras simuladas.

## 10. Entornos

- Local.
- CI.
- Staging.
- Piloto.
- Producción.

Cada entorno debe tener configuración propia y secretos separados.

## 11. CI gates

Un pull request no puede integrarse si falla:

- lint,
- type check,
- unit tests,
- integration tests afectadas,
- contract tests,
- migraciones,
- seguridad de dependencias,
- trazabilidad documental,
- cobertura mínima.

La suite autoritativa completa se ejecuta una sola vez en `pull_request`. El workflow verifica además
el whitespace del diff real contra `origin/${{ github.base_ref }}`; no sustituye esa comprobación por
un árbol de trabajo limpio. `main` permanece protegido por checks requeridos y no ejecuta un segundo
ciclo completo post-merge. Despliegue y verificación productiva son gates separados.

La seguridad de dependencias usa un único `dependency-review` sobre el delta del pull request y
rechaza vulnerabilidades nuevas de severidad alta o crítica. La acción se fija a un SHA revisado para
no ejecutar código remoto mutable por etiqueta. Este gate requiere que GitHub Dependency Review esté
disponible para el repositorio; un check ausente, omitido o no habilitado no cuenta como aprobación y
no se sustituye agregando scanners redundantes al checkout local.

## 12. Pruebas de desempeño

Escenarios:

- 500 pedidos por hora por sucursal.
- 15 cajas activas.
- ráfaga de webhooks duplicados.
- 2 horas offline.
- 10,000 comandos pendientes.
- 500 trabajos de impresión.
- 1,000 SKUs.
- recetas de 10 niveles.
- optimización de 100 pedidos y 30 repartidores.
- exportación de 50,000 líneas.

## 13. Pruebas de recuperación

- restaurar PostgreSQL,
- restaurar gateway,
- reconstruir proyecciones,
- reproducir outbox,
- recuperar archivos,
- rotar secretos,
- desplegar rollback.

## 14. Definition of Done técnica

- prueba escrita antes del cambio,
- escenario BDD satisfecho,
- migración probada,
- observabilidad,
- auditoría,
- error manejado,
- rollback,
- documentación,
- trazabilidad.

## 15. Integridad del harness

### TDD-TS-061 Identificadores y matriz de trazabilidad

Casos:

- extraer definiciones formales sin confundir menciones históricas;
- rechazar requisitos, features, escenarios, suites y casos definidos más de una vez;
- rechazar escenarios sin una etiqueta `BDD-SC-xxx` propia;
- exigir exactamente una fila de matriz por requisito PRD;
- rechazar referencias TDD en la columna BDD y referencias BDD en la columna TDD;
- rechazar referencias de matriz sin definición;
- rechazar escenarios BDD y suites TDD formales que no estén relacionados en la matriz;
- aceptar únicamente los estados declarados por la matriz.

### TDD-TC-056 El gate falla ante una colisión documental

Given un conjunto sintético de documentos con un escenario duplicado, otro sin identificador o una
referencia TDD dentro de la columna BDD
When el validador de trazabilidad analiza sus definiciones y filas
Then informa la ambigüedad concreta y el gate falla antes de integrar el cambio.

### TDD-TS-102 Quality ratchet del pull request

Casos:

- analizar sólo adiciones de archivos Python, TypeScript y JavaScript en el diff `base...head`;
- rechazar `type: ignore`, `noqa`, `pragma: no cover`, `@ts-ignore`, `@ts-nocheck`,
  `eslint-disable` y pruebas marcadas como omitidas o esperadamente fallidas;
- ignorar deuda histórica que no aparece como línea añadida;
- aceptar únicamente una excepción local con `quality-ratchet: allow -- <razón>` no vacía;
- producir hallazgos deterministas con ruta, línea y categoría sin repetir el código fuente;
- fallar cerrado si Git no puede resolver o comparar la base.

### TDD-TC-220 El ratchet distingue una adición degradante de deuda histórica

Given diffs sintéticos con silenciamientos nuevos, excepciones justificadas, deuda no añadida y una
base Git inválida
When el quality ratchet analiza las adiciones o intenta obtener el diff
Then bloquea sólo la degradación nueva no justificada, redacta su salida y falla cerrado cuando no
puede demostrar qué cambió.

## Personalización visual

BDD-MEDIA-001/002: `test_category_presentation.py` verifica API, persistencia, aislamiento,
permisos, validación y auditoría; `test_category_presentation_migration.py` verifica 0082
en SQLite y PostgreSQL. `tests/frontend/test_category_presentation.mjs` ejecuta la
proyección móvil y fallbacks, además del contrato de edición. Typecheck Admin/móvil,
build y QA visual de diálogo, portada y círculos en escritorio/móvil. R3 por migración:
revisión Sol independiente. Evidencia y límites en `docs/plan-category-presentation.md`.

## Enlaces personalizados: verificación

BDD-DOM-001/002/003: `apps/api/tests/test_restaurant_domains.py` (API/aislamiento/DNS),
`apps/api/tests/test_restaurant_domains_postgres.py` (persistencia, concurrencia y migración),
`tests/frontend/test_restaurant_links.mjs` (enlaces/QR/estados). Build Admin y QA visual.
Revisión R3 Sol independiente y CI completo; TXT/TLS de un cliente real sólo se certifica
durante activación supervisada con autorización productiva.

BDD-DOM-004/005: ampliar `test_restaurant_domains.py` con configuración vacía/inválida,
resolución de slug y alias, hijo anidado/reservado/desconocido, organización suspendida, raíz,
Admin/POS/KDS, manifiesto raíz y matriz host tacos contra token/login/slug/branch key/cuerpo sushi.
Probar que dominio propio activo conserva precedencia y que los hosts centrales exactos no se
convierten en tenants. Añadir una prueba semántica móvil para la resolución por contexto de host,
enlaces/QR wildcard y compatibilidad `/menu/{slug}/`. Gates: pytest focal de dominios/storefront,
Ruff y mypy focales, pruebas frontend afectadas, typecheck/build Admin y móvil, trazabilidad y
`git diff --check`. No se activa PostgreSQL al no cambiar persistencia/SQL/concurrencia; CI completo
sigue siendo el gate de suite antes de release. DNS/TLS/EasyPanel y canary real quedan fuera de la
evidencia local y requieren autorización productiva separada.

## Recuperación SaaS

BDD-REC-001: test_saas_storefront.py y pruebas semánticas móvil, E2E dos tenants. BDD-REC-002: test_saas_onboarding.py, test_saas_onboarding_wizard.py y prueba de migración desde 0069 con trial legacy. BDD-REC-003: test_saas_sensitive_authorization.py, test_saas_superadmin.py, pruebas de alcance y webhooks. Ejecutar focales por paquete y gates completos una vez antes de release. PostgreSQL para migración/concurrencia; revisión R3 independiente.
