# RestaurantOS Harness

Plataforma web SaaS multitenant para restaurantes, gobernada por PRD, SDD, BDD y TDD. Conserva módulos históricos de RestaurantOS y capacidades offline cuyo alcance se acredita por pruebas.

## Objetivo

El repositorio separa producto, comportamiento, diseño y pruebas para evitar que el código se convierta en la única fuente de verdad.

La jerarquía documental es:

1. `docs/01-PRD.md`: qué debe resolver el producto y por qué.
2. `docs/02-SDD.md`: cómo debe diseñarse el sistema.
3. `docs/03-BDD.md`: cómo debe comportarse frente a usuarios y sistemas externos.
4. `docs/04-TDD.md`: cómo se verificará cada comportamiento.
5. `docs/05-matriz-trazabilidad.md`: relación entre requisito, comportamiento, diseño y prueba.
6. `docs/06-roadmap-entregas.md`: secuencia de construcción.
7. `docs/07-analisis-consistencia.md`: contradicciones, omisiones y riesgos detectados.
8. `docs/08-adrs-propuestas.md`: decisiones arquitectónicas propuestas para fase 0.
9. `docs/09-fase-0-y-vertical-slice.md`: alcance verificable de fase 0 y primer vertical slice.
10. `docs/10-operacion-easypanel.md`: pasos de operacion inicial en Easypanel.
11. `AGENTS.md`: instrucciones permanentes para Codex.
12. `codex/CODEX_IMPORT_PROMPT.md`: prompt inicial para importar este contexto a Codex.

## Regla principal

Ningún cambio funcional debe implementarse únicamente en código cuando modifica un contrato. El
marco es proporcional al riesgo: se consulta toda la cadena de autoridad relevante, pero sólo se
edita el artefacto cuyo contenido realmente cambió.

1. PRD, cuando cambie el alcance o el valor esperado.
2. SDD, cuando cambie la arquitectura, el modelo o las reglas técnicas.
3. BDD, cuando cambie un comportamiento observable.
4. TDD, cuando cambie la estrategia de verificación.
5. Matriz, cuando cambien las relaciones, la cobertura o el estado de evidencia.
6. Código y pruebas dirigidas al cambio.

No se generan diffs ceremoniales para declarar que un artefacto no cambió. `AGENTS.md` es la fuente
canónica del proceso; este README sólo resume su aplicación.

## Flujo proporcional al riesgo

- `R0`: documentación/evidencia sin cambio de runtime.
- `R1`: refactor o UI de bajo impacto sin permisos, persistencia ni estados.
- `R2`: comportamiento, API o dominio no crítico.
- `R3`: dinero, caja, inventario, producción, permisos, datos sensibles, offline, concurrencia,
  migraciones o integraciones externas.

Para todos los niveles se preserva trabajo ajeno, se ejecutan pruebas afectadas y
`git diff --check`. PostgreSQL, SQLite, E2E, QA visual, suite completa local, auditoría independiente,
backup y canary se activan sólo por el riesgo correspondiente. La suite completa aplicable debe
ejecutarse una vez en CI; CI sólo es autoritativo para los gates que realmente contiene. Una suite
completa local requiere R3 transversal, CI ausente/inconcluso o una razón diagnóstica.

Un paquete autorizado puede incluir especificación aplicable, implementación, pruebas, commit,
merge y push. Despliegue, migración, configuración y datos productivos mantienen autorización
separada. Handoff, plan y reporte se crean sólo cuando aportan información nueva y no deben duplicar
PRD/SDD/BDD/TDD.

## Alcance vigente

El alcance comercial y sus límites se definen en `docs/01-PRD.md`; los módulos ERP históricos
no son promesas comerciales implícitas. Incluye registro y onboarding por tenant, catálogo,
menú digital, POS/caja, cocina/entrega, facturación y gestión de suscripción según sus contratos.
La fecha del trial no suspende el servicio: sólo una decisión manual de superadmin lo hace.

WhatsApp queda aplazado en la remediación del 2026-09-28. El plan no habilita sus integraciones.
La cobertura offline y los proveedores externos requieren evidencia por capacidad; código o
configuración presentes no acreditan una integración productiva.

Correcciones publicables: `docs/reports/saas-completed-fixes-2026-09-28.md`.

## Arquitectura resumida

```text
Nube central
├── Web admin
├── API central
├── PostgreSQL
├── Redis
├── Workers
├── Integraciones
├── Optimización de rutas
└── Reportes y exportaciones

Sucursal
├── Gateway Windows
├── SQLite local
├── Servicio de impresión
├── POS web/PWA
├── KDS cocina
├── KDS bebidas
├── KDS empaque
└── Pantalla de entrega
```

## Convención de identificadores

- `PRD-FR-xxx`: requisito funcional.
- `PRD-NFR-xxx`: requisito no funcional.
- `SDD-ADR-xxx`: decisión arquitectónica.
- `BDD-FEAT-xxx`: feature BDD.
- `BDD-SC-xxx`: escenario.
- `TDD-TS-xxx`: suite de pruebas.
- `TDD-TC-xxx`: caso de prueba.
- `RISK-xxx`: riesgo.
- `OPEN-xxx`: decisión abierta.

## Uso inicial

1. Crear un repositorio privado en GitHub.
2. Copiar esta estructura al repositorio.
3. Ejecutar el prompt de `codex/CODEX_IMPORT_PROMPT.md`.
4. Pedir a Codex que valide la trazabilidad aplicable y clasifique el riesgo antes de escribir código.
5. Construir primero la fase 1 descrita en `docs/06-roadmap-entregas.md`.

## Bootstrap técnico

Fase 0 incluye scaffold mínimo para:

- API FastAPI con health checks en `apps/api`.
- Apps React + TypeScript + Vite para admin, POS y KDS.
- Placeholders de `worker` y `edge-gateway`.
- Contratos JSON Schema en `packages/contracts`.
- Docker Compose local en `infra/docker`.
- Plantilla Easypanel en `infra/easypanel`.
- CI en GitHub Actions.
- Pruebas de arquitectura y trazabilidad en `tests/architecture`.
- `Dockerfile` en la raíz para desplegar la API directamente desde Easypanel.

Comandos iniciales:

```bash
python -m pip install -r apps/api/requirements-dev.txt
python -m pytest
docker compose -f infra/docker/docker-compose.yml config
```

## Easypanel

La guia operativa esta en `docs/10-operacion-easypanel.md`.
