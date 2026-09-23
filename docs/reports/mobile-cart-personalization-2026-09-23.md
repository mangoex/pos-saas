# MOB-CART-001 — Evidencia local, 23 de septiembre de 2026

Alcance R3: menú móvil y Tu Pedido, edición de borradores y recuperación del envío. No se cambia
una cuenta POS, pago, venta histórica, esquema, endpoint ni gateway. Base Git: `1ba2e95`.
PRD-FR-061; SDD mobile-cart-personalization; BDD-SC-930..939; TDD-TS-291.

## Resultado

Las tarjetas indican personalización disponible; el carrito distingue Sin personalizar de opciones
elegidas, incluidas gratuitas. Imagen, nombre y acción explícita abren un borrador precargado.
Guardar reemplaza la línea sin fusionar; cerrar/cancelar no altera el pedido ni desmonta checkout.
Catálogo vigente valida precio, cantidad 1..99, opciones y cardinalidades. Una opción retirada exige
quitarla explícitamente; productos retirados no se guardan. El reintento incierto conserva body,
clave y recibo; Web Locks y marca de finalización evitan recrear un pedido desde pestañas antiguas.

## Pruebas y refutación R3

| Afirmación | Evidencia / intento de refutación | Resultado y límite |
| --- | --- | --- |
| Sólo cambia la línea elegida | `test_mobile_cart_personalization.mjs`: dos líneas del mismo producto, original inmutable, ID eliminado, precios falsificados, opción retirada, límites y cantidad 100 | 4 casos agrupados pasan; funciones ejecutadas, no sólo regex |
| El total es exacto y gratuito cuenta como personalización | Base 5500, recargo 2500, gratis 0, cantidades 1/2, promoción4500; navegador 16000→11000 | Pasa localmente; backend conserva autoridad final |
| Editar/cancelar conserva checkout | Driver Browser `tests/browser/test_mobile_cart_personalization.mjs` sobre API sintética: nombre capturado, notas, cantidad, guardar, Escape, opción gratuita | PASS en navegador real; no se envió a producción |
| El modal respeta teclado y tamaño | QA manual 360/390 px y recorrido automatizado escritorio1280: CTA visible, nombre legible, Cancelar, foco vuelve a activador; + obligatorio abre modal con Agregar bloqueado | Pasa en navegador de escritorio redimensionado; teclado virtual de dispositivo físico no certificado |
| Recarga conserva línea editada | Recarga misma sucursal: cantidad2, notas Tibio QA, Azúcar mascabado, total11000 | Pasa en navegador |
| Un envío incierto no cambia body ni clave | `test_mobile_web_order_flow.mjs`: timeout+inputs distintos, legacy sin body, 409/429/503/422 desconocido, almacenamiento inaccesible, lock ausente, tres envíos en cola, epoch antiguo y fallo de limpieza tras éxito | 22 casos pasan; backend y navegador sin Web Locks no se simulan como éxito |
| Reintento no elimina trabajo local divergente | Revisión de `setCart`: sólo vacía si coincide con `result.items`; pestaña antigua bloqueada con vaciado explícito | Inspección Sol y pruebas de fence API; no prueba multi-pestaña con infraestructura productiva |

RED observado: helper inexistente antes de implementación; la nueva prueba de limpieza falló al
bloquear replay por completion; la prueba 422 sin código falló al borrar pending. Todos esos casos
quedaron GREEN tras sus correcciones. La antigua comprobación textual de mínimos en ProductModal
se movió al enlace con `validateCartDraft`; la regla se ejecuta con pruebas semánticas del helper.

Otros gates locales: typecheck y build/PWA mobile-web pasan; regresiones de etiquetas de
modificadores y dictado pasan; `git diff --check` pasa. El test focal nuevo quedó incluido en
`test:frontend-semantic`, que usa el gate existente de CI.

Auditoría Sol independiente con contexto fresco: concluida sin bloqueantes. Se resolvieron en este
mismo ciclo los hallazgos sobre nombre/imagen editables, recuperación independiente del formulario,
modales simultáneos por enlace directo, exclusión entre pestañas, conservación de carritos divergentes,
limpieza fallida y HTTP 422 ambiguo. El build final y QA390 concluyeron después de la revisión y pasan.

Backend de intención pública: 24 pasan y 2 fallan (`test_public_intent_is_exactly_once_and_total_is_derived_in_python`
y `test_public_reference_read_is_redacted`) por comparaciones exactas del JSON que recibe campos
adicionales. No hay diff en backend ni en sus pruebas frente a HEAD; no se presenta esa suite como
verde. La trazabilidad global conserva los tres problemas previamente identificados: PRD-FR-740
ausente y duplicados BDD-SC-819..822/TDD-TC-259..262. No se silenció ninguno.

## Límites y operación

No se ejecutó PostgreSQL: este diff no cambia persistencia backend, SQL o migraciones. No se ejecutó
suite global local ni CI remoto para este incremento. El driver de navegador requiere la conexión
Browser y el servidor sintético `node tests/browser/mobile-cart-fixture.mjs`; no se configura como
un job remoto autónomo. El caso combinado de teléfono/dirección/cupón y teclado virtual queda para
canary: el navegador de pruebas no mantuvo la entrada del campo tel incluso antes de editar; nombre
y notas sí se verificaron. No se atribuye esa observación a pérdida de estado del editor.

Persisten datos de contacto/dirección/notas del intento original localmente hasta resolución. Se
limpian tras éxito o rechazo definitivo; logs sólo contienen estado/código. Claves antiguas sin
payload, almacenamiento inaccesible y falta de Web Locks bloquean envío con explicación. Para una
intención antigua ambigua se requiere confirmar con sucursal; no se ofrece borrar la clave y reenviar.

Canary pendiente, separado del código: producto de prueba con extra de pago y gratuito; verificar
base→personalizado→sin extra, cantidad2 y recepción del total backend. Si se acepta una intención
de prueba, cancelarla por el flujo autorizado; no editar datos históricos. Este trabajo no realiza
despliegue, migración ni cambios de datos productivos.
