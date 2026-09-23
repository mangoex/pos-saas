# MOB-CART-001 — Personalización visible y edición desde Tu Pedido

Estado: implementado localmente; evidencia y límites en `reports/mobile-cart-personalization-2026-09-23.md`.
Autoridad: PRD-FR-061. La implementación es R3 por precios,
persistencia local del carrito e integración con el envío de intenciones. No implica editar una
venta, un pago, una cuenta operativa del POS ni una intención ya enviada.

## Historia y objetivo

Como comensal del menú web móvil, quiero identificar productos con opciones y personalizar una
línea ya agregada a Tu Pedido, para revisar mi compra sin borrar y volver a capturar el producto.
En esta historia, «caja» se interpreta como el carrito Tu Pedido de las capturas del usuario.

## Base observada en el repositorio

- `apps/mobile-web/src/components/ProductCard.tsx`: tarjeta abre detalle; + usa onQuickAdd y detiene
  propagación. No muestra invitación a personalizar.
- `apps/mobile-web/src/App.tsx`, handleQuickAddToCart: abre detalle cuando algún mínimo es mayor a
  cero; de lo contrario agrega una unidad sin opciones. Esta distinción se conserva.
- `components/ProductModal.tsx`: cantidad inicial 1, notas y selecciones vacías; sólo tiene acción
  Agregar. No recibe una línea inicial ni callback de actualización.
- `components/CartDrawer.tsx`: representa opciones seleccionadas, cantidad y eliminación, pero no
  ofrece edición de la línea. Mantiene datos de checkout en estado local: desmontarlo puede perderlos.
- `types.ts`: CartItem ya contiene cart_id, product, quantity, notes, modifiers y line_total_cents.
  App persiste el carrito por organización y sucursal. La igualdad actual para agregar usa producto,
  notas y JSON de opciones; no debe reutilizarse como comando de edición.
- `api.ts`: la API recibe IDs de opciones y conserva clave idempotente en reintentos inciertos.
  El backend sigue siendo la autoridad del total y de la persistencia de la intención.

## Decisiones de experiencia

| Contexto | Presentación y acción |
| --- | --- |
| Tarjeta con opciones seleccionables | Mostrar «Personaliza tu producto» con indicador discreto. Pulsar tarjeta o invitación abre el detalle. |
| + con opciones sólo opcionales | Agregar una unidad base sin selección; conservar compra rápida. |
| + con mínimo obligatorio | Abrir detalle; no agregar hasta cumplir mínimos/máximos existentes. |
| Carrito con opciones disponibles y ninguna seleccionada | Mostrar «Sin personalizar» y acción «Personaliza tu producto». No es un error ni un bloqueo si son opcionales. |
| Carrito con opciones seleccionadas | Mantener resumen legible de selecciones, incluidas gratuitas, y acción «Editar personalización». |
| Producto sin modificadores | No mostrar invitación ni estado de personalización ficticio. Nombre/imagen o «Editar producto» permiten editar cantidad y notas. |
| Modal abierto desde carrito | Título «Editar producto»; cargar cantidad, notas y selecciones de esa línea; acción «Guardar cambios». |

Contar opciones comerciales disponibles del catálogo efectivo de la sucursal, no sólo la longitud
de la lista seleccionada ni grupos vacíos. Los tipos actuales `modifier` e `ingredient_extra` cuentan;
los comentarios `order_comment` y notas libres no activan por sí solos la invitación. Un modificador
gratuito sí cuenta y debe aparecer en el resumen; no se debe etiquetar Sin personalizar sólo porque
el recargo es cero. Se conserva el selector existente de otros tipos admitidos por el contrato.

## Contrato de edición y estados

1. Abrir edición por cart_id y capturar organización/sucursal de origen. Resolver producto por ID
   contra el catálogo efectivo vigente; no confiar exclusivamente en la copia guardada en CartItem.
2. Crear borrador independiente con cantidad, notas y option_id/text existentes. El carrito original
   no se modifica al alternar opciones. No restaurar selecciones de otro producto o modal anterior.
3. Al guardar, validar disponibilidad, pertenencia al producto, cantidades y cardinalidades; calcular
   previsualización con enteros de centavos usando el mismo precio base/promoción y reglas vigentes.
4. Reemplazar exactamente una línea por cart_id, conservar identidad y posición. No invocar Agregar,
   no duplicar cantidad ni tocar otras líneas del mismo producto. No fusionar automáticamente
   una línea editada aunque su configuración termine igual a otra; conservar el comportamiento actual
   de fusiones al agregar queda fuera de este incremento.
5. Cantidad mayor que uno comparte la misma personalización para toda la línea, como hoy. No se
   implementa división automática por unidad; dos preparaciones distintas requieren líneas separadas.
6. Cancelar, cerrar, Escape o tocar fuera del modal descartan sólo el borrador y regresan a Tu Pedido.
   Guardar y cancelar conservan nombre, teléfono, dirección, modalidad, selección de pago/cupón y
   demás datos capturados del checkout; no disparan envío. Restaurar foco y posición útil del carrito.
7. Cambiar sucursal/restaurante o eliminar la línea invalida el borrador abierto. Un callback atrasado
   no puede crear de nuevo la línea ni afectar el carrito de otra sucursal. Durante envío no editar.
8. Si el catálogo no carga, conservar la línea y ofrecer reintento. Si una opción dejó de existir,
   mostrar conflicto explícito y exigir revisión; no quitarla ni cambiar su precio silenciosamente.
   Si cambió un precio, mostrar el nuevo total y requerir Guardar. Producto no disponible: bloquear
   guardado y permitir cancelar/quitar la línea mediante las acciones existentes.

Fórmula de previsualización para opciones ordinarias del caso: cantidad × (base vigente + suma de
recargos seleccionados). Preservar reglas actuales de promoción y extras; no inventar descuentos.
Ejemplo de las capturas: Capuchino 55 + Leche de aceituna 25 = 80; quitarla devuelve 55; seleccionar
Azúcar mascabado gratis mantiene 55 y sí se muestra seleccionado. Dos unidades con el extra: 160.

Persistir el reemplazo con el namespace existente; no agregar un segundo carrito ni un nuevo backend
de precios. No se prevé migración de BD ni endpoints nuevos. La compatibilidad con borradores antiguos
sin modifiers se trata como lista vacía; un catálogo ausente no equivale a no tener opciones.

Un envío con resultado incierto debe resolverse con su payload/clave originales antes de enviar una
versión editada. No generar automáticamente otra clave al abrir o guardar el editor. Tarea de análisis
obligatoria: verificar la recuperación actual de api.ts antes de implementar; si no permite resolver
el envío previo, bloquear esa edición con explicación/reintento y documentar la ampliación necesaria.
No declarar resuelto este riesgo sólo con isSubmitting ni reiniciar claves ante cualquier error.

## Accesibilidad y presentación

Texto visible además del icono/color; nombres accesibles específicos del producto. Enter/Espacio
abren el detalle desde sus controles. +, −, favoritos y papelera no deben abrir el editor por
propagación accidental. Evitar botones anidados; usar acciones semánticas independientes. Una única
capa modal interactiva, foco contenido y retorno al activador. Revisar 360/390 px, teclado visible,
nombres largos, varias opciones y escritorio; no tapar Guardar/cerrar ni controles de cantidad.

## Plan de tareas y dependencias

| Orden | Tarea | Entregable verificable |
| --- | --- | --- |
| 1 | Confirmar contratos y fixtures de carrito, catálogo, comentarios y envío incierto | Casos canónicos base/recargo/gratis/obligatorio; resolver límite de idempotencia antes de programar |
| 2 | Escribir regresiones RED focales, empezando por editar una línea y cancelar | Fallo esperado: hoy no existe reemplazo/estado inicial del editor |
| 3 | Extraer lógica compartida de personalización y reemplazo por cart_id | Funciones puras tipadas, centavos exactos, misma fuente para indicador y validación |
| 4 | Añadir modo editar a ProductModal y coordinación en App | Borrador precargado, Guardar/Cancelar, línea estable y checkout conservado |
| 5 | Añadir señales en ProductCard y CartDrawer | Textos de la tabla, propagación y accesibilidad verificadas |
| 6 | Integrar catálogo vigente, persistencia y guardas de contexto/envío | Recarga, cambio de sucursal, línea borrada y errores sin pérdida de datos |
| 7 | Ejecutar TDD-TS-291, regresiones existentes y QA visual | Evidencia local con casos/estados probados; typecheck y build mobile-web |
| 8 | Auditoría independiente Sol con contexto fresco y CI aplicable | Hallazgos resueltos; PRD/BDD/TDD/matriz reflejan evidencia real |

La implementación UI/API se delegó a Luna con integración por el agente principal y auditoría Sol
independiente con contexto fresco, conforme al marco canónico.
PostgreSQL se activa si cambia persistencia/SQL/concurrencia backend; no por un cambio de texto.
No se altera gateway offline. Un canary productivo, si se autoriza, debe ser acotado y compensable.

Preguntas operativas para la implementación: ¿se guardó exactamente la línea elegida?, ¿por qué
se bloqueó una edición?, ¿se envió el pedido con las opciones confirmadas? Responder con estado visible,
errores estables y las evidencias de pruebas/HTTP existentes. No registrar notas, teléfonos o direcciones
ni añadir telemetría sin necesidad. Despliegue y datos productivos conservan autorización separada.

## Recuperación implementada y límites

La inspección encontró que conservar sólo la clave no preservaba el payload en un reintento. Se
amplió el adaptador móvil: antes del POST guarda en localStorage un registro v1 bajo
`restaurantos_pending_mobile_order:<effectiveKey>` con clave, body serializado, líneas y datos del
cliente necesarios para representar fielmente el resultado. Reintentar reutiliza exactamente esos
datos. El botón independiente «Reintentar envío original» evita validaciones de un formulario nuevo.
Mientras existe un intento pendiente, el carrito muestra su snapshot y bloquea modificaciones.

Un rechazo explícito `public_order_schema_invalid`, `product_unavailable`, `coupon_invalid` o
`dine_in_disabled` permite corregir el borrador. Timeout, respuesta inválida, conflictos, errores
desconocidos, 422 genérico, límites de solicitudes e indisponibilidad conservan el intento. Una
respuesta persistida válida permite eliminarlo. Si falla la limpieza tras éxito, el snapshot todavía
puede reproducirse con la misma clave. Nunca se rota una clave por editar ni por recibir un 409.

Web Locks serializa envíos de la misma clave pública entre pestañas. Un timestamp sin datos personales
en `restaurantos_completed_mobile_order:<effectiveKey>` bloquea solicitudes que ya esperaban el lock
y carritos anteriores al resultado. La edad del carrito se conserva junto a su namespace existente
en `:cart_started_at`. Las otras pestañas conservan su borrador para revisión y ofrecen la acción
explícita «Vaciar carrito para iniciar otro pedido»; no se sincronizan ni descartan silenciosamente
líneas divergentes. Guardar un resultado sólo vacía un carrito idéntico al snapshot enviado.

El almacenamiento pendiente incluye contacto/dirección/notas locales hasta resolución; se elimina
tras éxito o rechazo definitivo y no se registra su contenido en logs. No se aplica caducidad que
permita olvidar un envío ambiguo. Almacenamiento inaccesible, registros antiguos sólo con clave y
navegadores sin Web Locks fallan con explicación antes de enviar; requieren resolver el estado o usar
un navegador compatible. Esta ampliación no agrega endpoints, migraciones ni cambios al gateway.
