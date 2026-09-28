# Correcciones SaaS completadas — paquete de publicación

Base: `421805f`. Rama de integración: `codex/saas-completed-fixes`.
Autorización del usuario: commit, merge y push de las correcciones completadas.
El despliegue y las migraciones productivas conservan autorización separada.

## Alcance

- Aislamiento de mappings de marketplaces por tenant/sucursal, FK compuesta en migración
  0098, preflight sin alterar historia y corrección de kill-switch por sucursal.
- Alcance de CRM por permisos y agregación SQL conservando clasificación/importes exactos.
- Consulta autorizada de caja, evidencia real para movimientos y navegación por permisos.
- Recuperación durable en el navegador del intento de pago/entrega móvil, sin generar
  otra clave tras una respuesta perdida y sin contaminar otra vista/sesión.
- Horarios de recogida calculados/validados por Python; refresco, revalidación y replay
  en carrito. Resolución de productos restringida al tenant y catálogo de sucursal.
- Locks con hashes, dependencias corregidas, tipos/lint, gates CI del SHA y trazabilidad.

Se excluyen suscripciones 2B, preparación/venta offline nueva y el refactor de
modificadores asociado. Sus implementaciones parciales permanecen en el directorio
original y no forman parte de esta rama. Se conserva el comportamiento de suscripciones
del commit base: este paquete no certifica ni habilita su integración de cobro.
WhatsApp, costeo e inventarios no se desarrollan ni se ofrecen como alcance de esta
versión SaaS. El código histórico y sus regresiones se conservan sin ampliar el producto.

## Selección y verificación

Un checkout aislado permite verificar el contenido exacto sin borrar los pendientes.
Se retiraron del delta las rutas/imports/tablas/migraciones 0099–0102, hooks de CI y
referencias documentales de los incrementos excluidos. Se mantiene la migración 0098.
No se publican logs, capturas, `.playwright-cli`, scripts temporales ni credenciales.

La evidencia por incremento previa incluyó dos tenants/sucursales, SQLite/PostgreSQL,
replay/concurrencia de pagos, migración reversible y QA de componentes. Esta evidencia
no sustituye las comprobaciones del paquete separado. Sus resultados finales se agregan
abajo. CI remoto y despliegue son estados distintos.

### Gates del checkout separado

- Backend focal: **83 passed**, sin skips, 487.30 s; mappings, migración 0098,
  CRM/consultas, recuperación de pagos, pickup, outbox y alcance de caja. PostgreSQL
  16.15 local desechable y SQLite; no se conectó a bases productivas.
- Suspensión manual, autofacturación y trazabilidad: **17 passed**, 14.11 s.
- Política de repositorio y quality-ratchet: **14 passed**, 10.34 s.
- Ruff de `apps/api tests` verde; mypy estricto del alcance CI: **7 módulos verdes**.
- `pnpm install --frozen-lockfile`, typecheck, cadena completa frontend-semantic y
  los cinco builds frontend verdes. Validación local: Windows, Python 3.12.10,
  Node 24.11.0, pnpm 10.0.0. Node 22/Linux/Docker se verifican en CI remoto.
- Locks Python coinciden con manifiestos; auditorías del lock Python y pnpm sin
  vulnerabilidades conocidas al ejecutar. La auditoría inicial del entorno editable
  no pudo evaluar el paquete local no publicado en PyPI; se auditó el lock completo
  con `--strict -r requirements/python-dev.lock`, sin ignorar paquetes externos.
- Auditoría R3 Sol independiente del delta seleccionado y de la procedencia de
  fixtures cerrada sin hallazgos pendientes; riesgo de revocación tras claim abajo.
- `git diff --check` limpio. Evidencia local en `output/release-*`, fuera del commit;
  logs y resultado de CI del SHA publicado constituyen el gate remoto posterior.

El control SEC-001 detectó 22 fixtures sintéticas con registro ausente/desactualizado.
Se revisaron individualmente y se registraron por procedencia y SHA-256 exactos:
12 hashes actualizados y 10 entradas añadidas, con tres marcadores faltantes. El scanner
no cambia ni se excluyen directorios/patrones. Incluye deuda preexistente en HEAD;
registrar el hash de una prueba histórica WhatsApp no modifica ni habilita esa integración.
Las pruebas del scanner conservan rechazo de otro contenido o procedencia incorrecta.

### Ajustes encontrados por la suite completa de CI

La primera ejecución del PR #5 (`36495250983`) terminó con 1252 pruebas aprobadas,
14 fallidas y 15 omitidas. No se integró ese SHA. Los fallos identificaron contratos
de prueba desactualizados y una divergencia del modelo respecto a la migración 0026:

- El head esperado se actualiza a 0098; los rollbacks PostgreSQL deben conservar la
  revisión previa al intento fallido, junto con sus datos históricos.
- El fixture de IA crea un producto activo del tenant. La semilla histórica usada
  antes fue archivada por 0027; se conserva archivada y no se debilita la guarda.
- La paginación de caja prepara turnos cerrados secuencialmente, respetando un único
  turno abierto por actor. Mantiene verificación de duplicados, omisiones y cursor.
- Las expresiones booleanas del metadata se alinean literalmente con la migración
  0026 ya existente. No se cambia esquema productivo ni regla de variaciones.
- CI conserva PR/manual, sin segunda suite automática post-merge. Las regresiones
  verifican el SHA base, el fallback manual y el mismo rango para whitespace/ratchet.
- La comprobación estructural del POS sigue el helper de sesión vigente y mantiene
  la validación de sucursal antes de aplicar la sesión.

No se omiten pruebas ni se relajan permisos para resolver estos fallos. Sólo se
actualizan los hashes exactos de los dos fixtures sintéticos modificados (CI/AIA).
La revisión independiente del delta confirmó paridad del DDL y conservación de las
aserciones de concurrencia, idempotencia y rollback.

Revalidación local del ajuste: **38 passed** (contratos CI/POS, cadena Alembic y
paginación), **20 passed** (variaciones existentes/trazabilidad), **15 passed** sin
skips (IA, modificadores móviles y migraciones de presentación/dominios con PostgreSQL
y SQLite). Ruff, mypy del modelo, política de repositorio y diff-check verdes.
La nueva ejecución completa de CI del PR es el gate pendiente para integrar este cierre.

La segunda ejecución (`36497323587`) aprobó 1265 pruebas y omitió las mismas 15;
falló una prueba SQLite por contaminación entre fixtures. SQLAlchemy `AddConstraint`
modifica las FK cíclicas del metadata al crear tablas PostgreSQL; reutilizar después ese
metadata para SQLite omitía la FK del intento aceptado. Se reprodujo en el mismo proceso
con el módulo PostgreSQL seguido del caso SQLite: **1 failed, 3 passed**. El fixture ahora
clona su metadata y una regresión comprueba que emitir DDL PostgreSQL conserva intacto el
DDL SQLite compartido. No cambia el runtime ni se debilita la prueba de rechazo real.
Revalidación secuencial del módulo PostgreSQL y todo `test_public_order_intents.py`:
**30 passed**, sin skips, 72.46 s. Ruff, política, diff-check y revisión independiente
del fixture verdes; la corrida completa posterior de CI debe aprobar antes del merge.

Se mantienen visibles la deprecación Starlette/httpx, advertencias de chunks grandes,
el aviso del pyproject raíz sin tabla project y el aviso Windows de ruta temporal
corta/larga del auditor. No son resultados de pruebas omitidos ni fallos silenciados.

## Riesgos y operación

- La FK 0098 rechaza datos históricos cruzados durante preflight; no corrige ni borra
  filas automáticamente. Una base inconsistente requiere remediación explícita antes
  de desplegar. Downgrade conserva registros y sólo revierte la restricción añadida.
- Recuperación móvil requiere almacenamiento persistente y Web Locks. Si no están
  disponibles, falla antes de iniciar otro cobro.
- Una revocación posterior al claim de un job externo no puede cancelar retroactivamente
  su HTTP; las guardas verifican alcance antes de encolar/reclamar.
- El refresco de horarios puede invalidar una selección o requerir reintento. Se bloquea
  el envío mientras no exista confirmación vigente del servidor.
- Las pruebas criptográficas locales no sustituyen la instalación Linux de release.
  Avisos de tamaño de bundles siguen visibles; no se introducen silenciamientos.

Preguntas operativas: ¿el actor operó sólo en su sucursal?, ¿el pago recuperó el mismo
comando?, ¿el horario seguía vigente?, ¿el gate corresponde al SHA publicado? Responden
las auditorías de autorización/comandos existentes, la clave de recuperación, los errores
de pickup y el registro de CI. No se agregan logs de payloads sensibles.
