# SDD — Restricción de Horarios de Recolección y Fotografías en Sugerencias del Menú Digital

## Contexto y Problema

1. **Horarios de recolección en menú digital:** La web app móvil de administración permite configurar días y ventanas de atención por sucursal (`service_schedule`: `open_time`, `close_time`). Si bien los días cerrados se deshabilitaban correctamente, el control de hora en el carrito mostraba todas las 24 horas del día (mediante un `<input type="time">` nativo que no restringe la rueda de selección del SO), permitiendo al cliente seleccionar horas fuera del horario configurado (ej. lunes de 4 a 6 PM debe permitir únicamente slots de 16:00 a 18:00).
2. **Fotografías en sugerencias complementarias (Upsell):** La sección de recomendaciones cruzadas del carrito (`cart-upsell`) renderizaba forzosamente iconos estáticos SVG correspondientes a la categoría del platillo, aún cuando el producto contara con fotografía propia configurada en el catálogo (`image_url`).

## Decisiones Técnicas y Arquitectura

1. **Generador inicial de slots de recolección (`pickupSchedule.ts`), sustituido por la autoridad Python descrita abajo:**
   - Se crea el módulo puro [`apps/mobile-web/src/utils/pickupSchedule.ts`](file:///Users/renatavictoriagonzalez/Documents/miguelgespino/pos-saas/apps/mobile-web/src/utils/pickupSchedule.ts) con las funciones:
     - `generatePickupTimeSlots(schedule, options)`: genera intervalos de 15 minutos acotados estrictamente entre `schedule.open_time` y `schedule.close_time`. Si el día es hoy (`isToday: true`), adelanta el inicio a `Math.max(openMinutes, now + 15min)`. Si la ventana ya concluyó para hoy, retorna un arreglo vacío.
     - `getInitialPickupTime(currentTime, availableSlots)`: asegura que el horario seleccionado pertenezca al conjunto permitido. Si el día cambia o la hora previa queda fuera de rango, cae al primer slot válido.
   - En [`CartDrawer.tsx`](file:///Users/renatavictoriagonzalez/Documents/miguelgespino/pos-saas/apps/mobile-web/src/components/CartDrawer.tsx), el selector se implementa como un `<select id="pickup-time-input" className="pickup-time-field">` cuyas opciones son exactamente los slots generados. Esto garantiza que tanto en iOS Safari como en Chrome Android el desplegable contenga únicamente las horas operativas configuradas.

2. **Resolución visual en sugerencias complementarias:**
   - Para cada producto sugerido, se obtiene su URL de imagen mediante `prod.image_url || getProductImage(prod)`.
   - Si existe una imagen válida y no ha fallado en cliente, se renderiza `<img className="cart-upsell-card-img" src={prodImg} alt={prod.name} loading="lazy" />` con ajuste `object-fit: cover`.
   - Si no cuenta con imagen o la imagen produce error (`onError`), se conmuta dinámicamente al estado de fallback que renderiza el icono temático correspondiente (`getRecommendationIcon(prod)`) con su gradiente y borde de categoría.

## Invariantes Preservadas

- Invariante de validación en frontera: la comprobación de límites de horario al momento del checkout se mantiene intacta como salvaguarda.
- Monocromía y paleta dinámica: los selectores y tarjetas se adhieren a las variables CSS del tema del restaurante.
- Cero llamadas a APIs externas no autorizadas y compatibilidad estricta con TypeScript.

## Remediación temporal SaaS del 2026-09-28

`pickup_schedule.py` calcula opciones con `datetime` aware, `ZoneInfo` y un reloj recibido
como parámetro. `GET /api/v1/public/branches/{public_key}/pickup-options` resuelve la clave
activa y su par organización/sucursal activa; no acepta IDs de tenant del cliente. Retorna
`generated_at`, `timezone`, `configured` y los siete días de la semana local actual, cada
uno con fecha ISO, índice lunes=0 y slots `{value: HH:mm, scheduled_at: UTC ISO}`.
Respuesta `Cache-Control: no-store`; no realiza reconciliación de caja ni otra escritura.

Se preservan los intervalos de 15 minutos, el margen mínimo de 15 minutos para hoy y la
ventana inclusiva de apertura/cierre del contrato existente. El margen incluye segundos:
16:00:01 no permite recoger 16:15:00. Días pasados/cerrados, ventanas inválidas o nocturnas
no generan slots. Horas locales inexistentes o ambiguas por cambio de offset se excluyen;
una zona inválida devuelve indisponibilidad explícita, sin usar la zona del navegador.
La semana sigue siendo lunes a domingo; no se añade otro horizonte de programación.

El carrito consume estas opciones, muestra fechas en la zona de la sucursal y refresca al
montarse, cada minuto y al recuperar visibilidad/foco. Antes de enviar consulta de nuevo y
exige que la fecha/hora seleccionada siga disponible. Un fallo de carga impide presentar
una programación como confirmable; el usuario puede reintentar. Sin horario configurado se
conserva la modalidad existente sin programación (lo antes posible), sin inventar una ventana.

`usePickupOptions` descarta respuestas superadas incluso si el transporte ignora AbortSignal;
al desmontar o cambiar sucursal cancela el lector anterior. La UI compara también el contexto
de sucursal, modalidad, cierre y bloqueo antes de entregar el formulario después de un await.
El formulario queda deshabilitado durante esa validación y un ref impide el doble submit.
El montaje y un cambio explícito de día pueden seleccionar el primer slot devuelto por Python.
Un refresco que invalida una hora ya elegida la deja vacía: no sustituye silenciosamente la
programación al enviar. Los atajos muestran horas devueltas por el servidor, sin calcular
minutos relativos con el reloj del dispositivo. La fecha ISO completa evita reutilizar el
índice de un lunes anterior como si fuera el de la nueva semana.

La captura pública acepta el par opcional `pickup_date` (YYYY-MM-DD) y `pickup_time` (HH:mm)
sólo para `takeout`. Ambos o ninguno; pertenecen a la huella idempotente. Python revalida
una creación nueva antes de precios, inserts o efectos. Al reintentar un comando persistido
devuelve su resultado previo antes de validar el reloj actual, incluso si la hora ya pasó;
cambiar fecha/hora bajo la misma key produce conflicto. La programación validada se guarda
en `customer_snapshot.pickup` con fecha, hora, zona e instante UTC y se conserva al aceptar
la intención. JSON existente evita una migración innecesaria; no se reescribe historia ni
se modifica dinero, tolerancia de recogida o estados de producción. Clientes anteriores sin
par mantienen captura sin programación; una nota de texto no constituye horario validado.

Preguntas operativas: ¿se rechazó una selección vencida antes de persistir?, ¿se recuperó
un comando previo aunque su horario ya pasó? Pruebas y códigos acotados `pickup_slot_unavailable`
y `pickup_schedule_invalid` diferencian estos casos sin registrar teléfono ni notas del cliente.
