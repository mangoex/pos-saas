# SDD: cierre SaaS A01–A12

Diseño R3 completo. Este documento precisa el SDD principal; implementación, pruebas y
producción deben acreditarse por separado. No declara que ya exista middleware automático.

## Identidad pública y PWA (A01/A10)

`GET /api/v1/public/storefronts/{identifier}` devuelve
`organization{id,name,public_slug,mobile_theme}`, `branches:[BranchInfo public_key]`
y `selected_branch_id:null|id`. El slug canónico de organización es único y normalizado.
Compatibilidad por código/UUID de sucursal sólo con coincidencia exacta e inequívoca:
desconocido 404, ambiguo 409; nunca fallback a primera sucursal ni substring.
Las rutas legacy `/public/catalog` y `/public/branches` exigen respectivamente `public_key`
e `identifier`; sin contexto explícito devuelven 422. `/public/mobile-theme` exige identifier,
mientras `/catalog/mobile-theme` lee/escribe sólo la organización del administrador autenticado.
La migración 0069 incorpora slug y aprovisiona claves opacas; GET no crea claves ni filas.
Colisiones requieren resolución explícita antes de abrir tráfico. Catálogo y captura usan
la clave de sucursal obtenida dentro del restaurante resuelto, sin aceptar mezcla de contexto.
GPS sólo ordena sucursales de esa organización. Un error de API muestra estado de error,
nunca productos genéricos. Carrito, favoritos, sucursal y caché incluyen organización en su
clave; datos legacy sin procedencia no se importan. Manifest usa identidad, iconos, start_url
`/menu/{slug}/` y scope del negocio. El service worker no comparte respuestas entre tenants.
Las fotografías de producto proceden exclusivamente de `image_url` del catálogo resuelto;
sin fotografía se muestra un icono, nunca una coincidencia de SKU/nombre con imágenes Kiwi.
Portadas sin imagen propia usan ilustración neutra de categoría. El frontend no inventa
calorías, tiempos de preparación, etiquetas nutricionales ni valoraciones por nombre/SKU.
Las recomendaciones del carrito usan iconos de categoría. Los slugs, claves y progreso
incorporados por 0069/0070 se conservan al revertir versión: el rollback es aditivo para
permitir regresar la imagen sin destruir URLs emitidas ni datos del onboarding.

## Autorización, estado y auditoría (A02/A03/A06/A12)

Cada frontera resuelve actor persistido, organización efectiva, permiso y sucursal antes de
leer o mutar el destino. El servicio vuelve a verificar pertenencia; IDs del cliente nunca
son autoridad. Incluye usuarios, roles, importación/plantillas, productos, caja, pedidos, KDS,
reportes, impresión y facturación. Superadmin sólo por autoridad persistida; bootstrap CLI
explícito fuera del login, credencial única sin secreto fijo. Impersonación registra actor
real, actor efectivo, organización destino, operación, recurso y correlación; no usa defaults
de organización/sucursal ni expone credenciales. Revocación/suspensión se comprueba en cada
operación protegida incluso con JWT vigente, también en workers y replay sensible.

El contexto de soporte se liga a la sesión SQL de la petición mediante una dependencia
compartida de las rutas API. Comprueba en cada petición al superadministrador emisor, al
usuario efectivo activo y al tenant firmado; registra un intento autorizado con correlación
sin URL query, payload ni credenciales. Los eventos de dominio conservan esa correlación y
ambos actores. El contexto no es global ni se comparte entre peticiones. Una revocación del
emisor invalida el uso posterior del token de soporte aunque todavía no haya expirado.

Los comandos fiscales de emision, cancelacion y recibo registran en `audit_events` solo
organizacion, sucursal, actor real/efectivo, correlacion y el resultado `confirmed`,
`simulated` o `failed`; nunca credenciales, RFC, razon social, correo, UUID/timbre ni
payload/respuesta del PAC. `confirmed` se persiste con el efecto local solo despues de la
confirmacion del proveedor. Una excepcion o timeout revierte el efecto local pendiente y
se audita aparte con confirmacion del proveedor `unknown`, sin afirmar estado fiscal final.

Emision directa y autofacturacion crean primero un comando durable `pending`, lo reclaman por CAS como `inflight` y solo entonces llaman al PAC. La identidad usa los pedidos ordenados; el hash del receptor detecta conflicto pero no permite eludir un pedido `inflight` o `unknown` cambiando RFC o agrupacion. Tras respuesta, factura, auditoria y comando `confirmed` se confirman juntos. Si ese commit falla, el comando queda `unknown` con el recurso del proveedor cuando se conoce; reintentar queda bloqueado hasta reconciliacion explicita. La reconciliacion consulta el recurso conocido antes de registrar un resultado; sin recurso permanece pendiente y nunca reemite. Claims unicos por pedido hacen atomica esa barrera incluso para agrupaciones concurrentes solapadas; el replay exacto devuelve la factura ya registrada. Recibo y cancelacion conservan este limite para la siguiente fase.



Caja y pedido POS resuelven una sola sucursal efectiva; su organización es la única que se
persiste en turno, comando y pedido. Replays se restringen a esa organización/sucursal;
actor de otro tenant se rechaza antes de generar efectos operativos.

Conceptos, movimientos y compensaciones de caja derivan `organization_id` del actor activo y
de la sucursal autorizada. Código de concepto e idempotency key sólo son únicos dentro del
tenant; el concepto, turno, comando, lock, ledger y compensación deben compartir esa misma
organización. Un concepto de otro tenant se rechaza antes de crear movimiento o comando.
Los cortes de usuario y sus reaperturas usan la organización del actor y del turno validado;
detalle, conteo, finalización, comandos, operaciones y compensaciones no resuelven el tenant
piloto ni aceptan un `cash_cut_id` o solicitud de otro tenant. Las proyecciones de reportes fijan
la organización del actor tras autorizar la sucursal; cada consulta de ventas, correcciones,
insumos, compras y movimientos de caja usa ese alcance, sin organización piloto.

Merma real restringe idempotencia de movimiento, confirmación y reversión por `organization_id`.
La confirmación y reversión adquieren lock por tenant/key, bloquean el registro y reclaman la
transición con CAS antes de crear movimientos o actualizar costo; un replay sólo resuelve dentro
del tenant.

## Registro, planes y operación ligera (A04/A05/A11)

La portada sirve adquisición en móvil y escritorio; no redirige dispositivos al menú de
otro negocio. Signup valida plan permitido y confirma atómicamente organización, sucursal,
almacén, roles/permisos sin duplicados, owner y sesión. Unicidad de permisos se conserva;
conflicto concurrente produce error controlado, no tenant parcial. Onboarding persiste avance
y permite reanudar datos de negocio, catálogo y caja/impresión sin recrear entidades.
Trial: inicio UTC al alta confirmada, fin inicio + 14 días, válido sólo mientras now < fin.
El servidor aplica expiración en cada operación; cliente sólo presenta el estado. Activación
exige evidencia de pago verificable o concesión administrativa auditada. La selección Básico/
Pro no finge cobro ni habilita un proveedor inexistente; reglas comerciales no definidas de
cuotas/límites deben explicitarse antes de cobrarlas. Estado vencido/suspendido impide nueva
operación comercial y checkout; consulta de estado y renovación autorizada siguen disponibles.
El flujo habilita primer ticket sin receta, costo de insumos ni configuración ERP; rutas de
módulos excluidos dejan de ser entrada comercial, sin borrar históricos ni movimientos.

## Integraciones y pedidos (A07/A08/A09)

Resolver identidad de integración/tienda externa inequívoca a organización y sucursal antes
de elegir secreto. Ausencia de configuración, secreto o firma válida rechaza sin procesar.
Validación criptográfica corresponde al contrato oficial de cada adaptador, nunca a un
identificador externo autodeclarado. Conservar payload original con acceso restringido,
inbox y clave única (integración, evento); reintentos no duplican intención/orden.
Kill-switch separa disponibilidad local de envío remoto: pendiente, confirmado o error;
confirmado exige respuesta aceptada del proveedor. Timeout permanece incierto/pendiente,
reintento idempotente y reconciliación recuperan estado sin afirmar éxito por configuración.
Adaptadores no habilitados no se anuncian como sincronizados. Certificar cada proveedor
con credenciales/entorno autorizado; pruebas simuladas no prueban funcionamiento real.

### A07 — configuración diferida de DiDi Food y Rappi

DiDi Food y Rappi conservan configuración por organización: identificador de cliente, secreto,
secreto de webhook, ambiente y mapeos de sucursal. Los secretos sólo se aceptan al guardar y no
se devuelven al navegador. Guardar la configuración los deja deshabilitados y en estado
`PENDING_VALIDATION`; no demuestra conectividad, no habilita una recepción real ni transmite
disponibilidad. La activación requiere contrato de partner, prueba sandbox y verificación
autorizada posterior.
Captura pública y WhatsApp delegan al mismo servicio persistente y limitado por tráfico:
cabecera, líneas, modificadores y snapshots atómicos con idempotency key obligatoria.
Reintento idéntico devuelve la intención original; misma clave con contenido distinto falla.
La intención PENDING_REVIEW sólo se vuelve pedido operativo tras aceptación autorizada del
POS, conservando organización/sucursal hasta KDS. WhatsApp abre borrador, no confirma entrega
ni pago. No hay checkout alternativo con garantías menores.
`POST /public/whatsapp-orders` es una adaptación de compatibilidad: requiere `public_key`
e `Idempotency-Key`; valida cualquier branch_id contra la clave, convierte items a líneas
canónicas y aplica los mismos límites de tráfico. Usa 201 al crear, 200 al repetir y errores
canónicos (422 esquema, 409 conflicto/no disponible, 404 contexto contradictorio).
Devuelve `public_reference` y estado pendiente, no folio operativo. El borrador WhatsApp se
construye con snapshots ya persistidos; sin teléfono configurado no inventa destinatario.

## Producción y reversibilidad

### Copiloto ejecutivo

El copiloto consulta únicamente `sales_operation_snapshots` y sus líneas confirmadas, la misma
autoridad del dashboard. Requiere organización y sucursal autorizadas antes de construir cualquier
contexto para un proveedor; sin costos trazables responde `NOT_AVAILABLE` y nunca inventa margen.

### A08 — confirmación Uber Eats de disponibilidad

Para Uber Eats, una mutación de disponibilidad crea o sustituye de forma idempotente un comando
durable por tienda e ítem. El worker obtiene un token `client_credentials` con alcance
`eats.store` y ejecuta `POST /v2/eats/stores/{store_id}/menus/items/{item_id}`. Sólo `204 No
Content` marca el comando `CONFIRMED`; timeout o 5xx queda `RETRY`, y credenciales/configuración
inválidas queda `FAILED`. La reactivación envía `suspension_info.suspension: null`; no se inventa
una duración de suspensión. El proveedor debe haber aprobado/whitelisteado la app, el menú original
debe haberse subido por API y se requiere una tienda sandbox autorizada antes de habilitar tráfico.
El comando guarda una versión deseada y un lease. El worker reclama y confirma en transacciones
cortas separadas por la llamada HTTP; sólo el mismo token y versión puede confirmar, por lo que una
respuesta vieja no puede sobrescribir un cambio más reciente. Si una respuesta vieja llega después
de una confirmación nueva, vuelve a encolar el último deseo para reconciliar el proveedor. El lease
vencido permite recuperación tras reinicio. Configuración deshabilitada, tenant inactivo o trial
vencido no producen tráfico saliente. Los
errores transitorios usan backoff acotado; no se reintentan credenciales o respuestas 4xx finales.
El proceso se provisiona separadamente, no desde el contenedor API: desde `apps/api`, `python -m
restaurant_os.uber_availability_worker --once` sirve para una ejecución acotada y `python -m
restaurant_os.uber_availability_worker` para el worker persistente una vez autorizado el despliegue.
La decisión técnica A08 conserva `httpx` como dependencia de runtime, en vez de usar la biblioteca
estándar: el adaptador necesita timeouts y un transporte simulado determinista para verificar el
contrato OAuth/HTTP sin red; no añade una dependencia crítica nueva porque ya era parte del conjunto
de desarrollo del API y ahora respalda una frontera de producción explícita.
Fuentes primarias: https://developer.uber.com/docs/eats/references/api/v2/post-eats-stores-storeid-menus-items-itemid
y https://developer.uber.com/docs/eats/guides/authentication .

Mismo VPS es posible; separar proyectos Kiwi/SaaS con app, PostgreSQL, Redis, secretos,
volúmenes y backups propios. Verificar host/base efectivos, SHA de imagen y dominio, no sólo
nombres de servicios. Backup restaurado, capacidad medida y rollback de imagen compatible
preceden migración. Reversión no elimina pedidos ni pagos; conservar nuevos identificadores
si un downgrade destructivo los perdería. Canary acotado con tenant sintético autorizado,
observación y compensación, nunca modificación directa de historia. Despliegue, migración,
configuración y datos reales requieren autorización productiva separada.

Señales operativas: correlación y tenant resuelto (¿quién atendió?), fase/error de onboarding
(¿dónde falló?), estado de inbox/envío y reintento (¿qué ocurrió?), SHA y destino DB/Redis
redactados (¿qué servicio atendió?). No incluir tokens, contraseñas ni PII completa en logs.


El importador de documento requiere proveedor configurado y respuesta válida. La falta de
clave de IA nunca devuelve catálogo fijo por nombre o tamaño de archivo; se expone error
para que el administrador configure el proveedor o capture manualmente. No se reescriben
catálogos existentes sin una corrección de datos autorizada y con respaldo.


## Coexistencia EasyPanel y evidencia de infraestructura

Compartir VPS o proyecto EasyPanel no selecciona por sí mismo el restaurante del menú.
Las rutas y consultas deben resolver el tenant de forma inequívoca. Para Kiwi y SaaS se
recomiendan proyectos separados con sus servicios, credenciales, volúmenes y respaldos;
pueden coexistir en una VPS con capacidad suficiente. Es una separación por producto,
no un despliegue por restaurante. EasyPanel documenta redes de proyecto y conexión interna
entre servicios; la captura general no acredita host efectivo, variables ni montaje real.
Verificar origen Git/rama/imagen, dominio→puerto, DB/Redis, volúmenes y restauración antes de
mover servicios o autorizar release. Ningún cambio de configuración productiva se deduce de
haber observado los nombres en una captura.

Fuentes oficiales: https://easypanel.io/docs/services/postgres,
https://easypanel.io/docs/api-reference/endpoints y
https://easypanel.io/docs/services/app (consulta 2026-09-04).

Los enlaces entre Admin y POS conservan el origen del despliegue compilado, incluso con puerto personalizado o hostname local. Sólo un bundle de desarrollo usa los puertos de Vite separados; el hostname no determina el entorno.

El registro guiado usa `defer_catalog_setup=true`: crea la identidad y sucursal sin sembrar productos; la elección explícita de plantilla se hace en onboarding. Menú vacío no elimina datos existentes. El endpoint conserva compatibilidad de siembra explícita para clientes previos que no usan registro guiado.


### Suscripción administrada y continuidad de soporte

La activación se ejecuta mediante comando superadmin explícito. Sin verificador de pago integrado, el camino disponible es una concesión administrativa con razón obligatoria; registra actor real, tenant, estado y plan anterior/nuevo, razón y correlación. Editar plan conserva una preferencia comercial; las rutas genéricas no activan suscripciones. El estado sólo puede suspenderse con razón. GET /subscription/status autentica al titular aun vencido sin conceder permisos operativos.

El traspaso a POS conserva organización efectiva, emisor de soporte y correlación en pos_session_handoffs mediante la migración aditiva 0072. Antes de consumir se valida de nuevo usuario, organización y autoridad vigente del emisor. El token resultante conserva las claims de soporte para que solicitudes posteriores sigan validando revocación y atribuyendo al actor real.

Paridad fiscal receipt/cancel: cada recurso mantiene un comando durable y claim exclusivo antes del PAC; `unknown` bloquea reemision y exige reconciliacion explicita. Cancel conserva hash de motivo/sustitucion para detectar conflicto; ninguna respuesta timeout declara estado fiscal final.

La simulación de DiDi/Rappi consulta primero la configuración de la organización del actor.
Un borrador deshabilitado devuelve HTTP 409 `integration_pending_validation` antes de crear
mapeos, pedidos o bitácoras. Una edición con secretos vacíos conserva los secretos existentes.

Los simuladores históricos de Uber/DiDi/Rappi usan la organización del actor y autorizan
la sucursal solicitada. La simulación requiere un mapeo activo configurado previamente;
si no existe devuelve 409 sin crear mapeos. Antes de crear el pedido resuelven la tienda
externa, exigen organización propia y correspondencia con branch_id si se proporciona, y
autorizan la sucursal resuelta. Una tienda ajena produce 403 sin pedido ni bitácora de webhook.
Ausencia de credenciales se persiste como NULL; nunca como la cadena None.

El catálogo de motivos de merma deriva organización del actor autorizado para crear o editar.
Las lecturas revalidan inventory.read y sucursal cuando se indica; todas las consultas y
actualizaciones restringen organización. No existe fallback al catálogo piloto.

El flujo de merma real conserva organización desde el actor: alta valida sucursal, insumo y
motivo propios; confirmar/revertir buscan la merma dentro de esa organización antes de autorizar
la sucursal y los movimientos heredan esa misma organización. Detalle y listado requieren
organización explícita además de branch.

Las compras sugeridas no generan cantidad, costo ni proveedor mientras POS-SaaS carezca de
una fuente trazable que relacione ventas con consumo de inventario. El endpoint devuelve cero
propuestas; conservar su forma no autoriza reintroducir una demanda fija ni costeo por receta.


La reconciliación de receipt/cancel consulta el recurso ya conocido (`GET /receipts/{id}` o `GET /invoices/{id}`) antes de confirmar el comando local. Receipt exige estado `open`; cancel exige `cancelled`/`canceled` o aceptación de cancelación. Un timeout, identificador ausente o estado distinto conserva `unknown`, sin reenvío automático. La actualización local, el comando y la auditoría confirmada comparten una transacción; si ésta falla después de la respuesta, el comando vuelve a `unknown` con el identificador del proveedor.

El rollback de tablas preserva los comandos y claims para recuperación, pero una imagen de aplicación anterior a estos guards no los interpreta: revertir binario no autoriza reintentos fiscales.

Los comentarios públicos persisten la organización de la sucursal resuelta. El listado admin
deriva organización del actor, autoriza branch cuando se solicita y filtra ambos ámbitos.
Los grants offline reciben organización desde el actor autenticado y el dominio confirma que
coincide con su organización persistida antes de autorizar sucursal/dispositivo.
La ruta histórica `/recipes/ai-parse` conserva respuesta 409 `feature_out_of_saas_scope` después
de autenticar y autorizar catálogo; no consulta insumos, productos ni costos en POS-SaaS.
# Aislamiento de Customer AI

Las recomendaciones administrativas y la segmentación CRM reciben la organización del actor ya
autenticado. Si la solicitud incluye sucursal, se autoriza en esa misma organización antes de leer
clientes, productos o pedidos. La ruta pública conserva el contrato de `branch_id`: deriva su
organización sólo de una sucursal activa existente y devuelve una lista vacía cuando no puede
resolverla. Los recomendadores no rellenan precios ni puntuaciones de confianza cuando carecen de
una fuente trazable.

Las lecturas administrativas de almacenes, unidades, insumos, existencias y kardex reciben la
organización autenticada además de la sucursal autorizada. El alta de unidad/insumo persiste
la organización del actor; código y SKU sólo son únicos dentro del tenant. Actualizar exige que
el destino y cualquier unidad referenciada pertenezcan al mismo tenant.

Las mutaciones de roles resuelven primero la organización persistida del actor y sólo aceptan un
`role_id` de esa organización. Actualizar permisos valida el rol propio antes de sustituir sus
relaciones; eliminar filtra la fila final por organización. La autoridad owner se reconoce por su
grant persistido dentro del mismo tenant: puede renombrar la etiqueta, pero no cambiar el alcance,
vaciar permisos ni eliminar el rol de autoridad. Los almacenes creados o actualizados derivan la
organización del actor y validan sucursal y destino en ella. La unicidad de un almacén por sucursal
se conserva; una sucursal activa no puede quedar sin almacén activo.

Las proyecciones de `platform_data` no usan una organización piloto: requieren `organization_id`
o derivan el ámbito únicamente de una sucursal activa explícita, verificando coincidencia si ambos
se reciben. Catálogo, categorías, existencias, kardex, almacenes, unidades, insumos, identidad y
recetas fallan cerrados sin ese ámbito. `bootstrap-status` es una vista del tenant autenticado,
no un conteo global de la plataforma.


El portal público de autofactura exige una `public_key` activa. Antes de consultar el folio o la factura existente, resuelve la clave opaca contra organización y sucursal activas; cada lookup y emisión filtra `organization_id`, `branch_id` y `folio`. Una clave inválida responde como ticket público no encontrado sin proyectar importes, RFC ni estado de otro restaurante.

Un receipt sólo confirma creación si FacturAPI devuelve identificador y estado `open`; un identificador con estado distinto queda `unknown` para reconciliación por consulta. Un replay de emisión directa/autofactura requiere además el mismo hash de receptor: el mismo pedido con RFC o payload fiscal distinto se rechaza sin segunda llamada al PAC.


La importación histórica resuelve organización desde el actor autorizado y exige que la sucursal autorizada pertenezca a esa organización. Batches, idempotencia de manifiesto, unidades, insumos, categorías, productos, versiones de precio y auditorías usan esa organización; un batch ajeno no es consultable, ingestable ni completables.

### Alcance de categorías y modificadores

Las categorías, sus selectores obligatorios, opciones y asociaciones producto-opción
resuelven la organización exclusivamente del actor con `catalog.manage`. Cada lectura y mutación
filtra la categoría o grupo por esa organización; un ID de otro tenant no revela cobertura, valores
o asociaciones ni permite modificarlos. Las notas de variación predefinidas crean y sincronizan su
grupo dentro de la misma organización del producto. Las proyecciones de modificadores fallan
cerradas cuando no reciben una organización o sucursal activa resuelta.

### Alcance de Admin AI por organización

Admin AI obtiene la organización exclusivamente del usuario persistido y autoriza la sucursal antes
de construir contexto, iniciar o continuar conversaciones, persistir propuestas o aplicar revisiones.
El contexto, diagnósticos y referencias de productos, insumos, unidades, modificadores y recetas se
filtran por ese ámbito. Los IDs de conversación o propuesta de otra organización responden como no
encontrados y no se reenvían al proveedor. Las recetas y costeo por gramos continúan fuera del alcance
público SaaS; esta corrección no habilita esos flujos.

### Pedidos delivery, repartidores y asistencia por tenant

Una actualización de estado de Uber Eats, DiDi Food o Rappi resuelve primero la organización del
actor y exige que el pedido pertenezca a esa organización, a una sucursal autorizada y al proveedor
de la ruta. El servicio repite esos predicados en los `UPDATE` de pedido y metadatos de canal.

Repartidores, códigos de empleado y registros de asistencia se crean, consultan y modifican dentro
de la organización persistida del actor. Los códigos pueden repetirse entre tenants; la resolución
de asistencia nunca busca un código global y los reportes filtran organización además de sucursal.

### OCR de factura sin datos inventados

El parser de factura devuelve sólo proveedor, folio, cantidad y precio presentes y parseables en
el texto recibido. Campos ausentes permanecen `null` y líneas incompletas se omiten; no se generan
cantidades, costos ni nombres predeterminados. La ruta exige `inventory.read` y su salida continúa
siendo un borrador sujeto a revisión, sin autoridad para crear una compra.


### Proveedores y compras directas por tenant

El actor autenticado resuelve la organización antes de crear, editar, listar o desactivar proveedores, contactos, términos, presentaciones y documentos de compra. La creación o edición de proveedor puede indicar una `branch_id` propia: entonces `catalog.manage` se autoriza en esa sucursal; sin sucursal requiere alcance organizacional. Términos y compras autorizan la sucursal explícita y validan proveedor, insumo, presentación y unidades de la misma organización. Detalle y listado de compras vuelven a filtrar organización y sucursal. Folio e idempotency key pueden coincidir en organizaciones distintas; la confirmación es única por `(organization_id, confirmation_idempotency_key)` y sus movimientos de inventario/caja conservan el tenant. No se habilita costeo por receta ni cuentas por pagar.

## Adaptación a GitHub publicada

El esquema canónico usa organizations.slug desde 0069 publicada; public_slug es sólo alias de respuesta. La nueva cadena inicia en 0070_storefront_identity y termina en 0080_delivery_inbox_idempotency. El rollback compatible mínimo es 0069; no revertir esa migración publicada, que eliminaría slug. La normalización de prueba legacy y los identificadores se conservan en rollback aditivo.
