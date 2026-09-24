# SDD — Restricción de Horarios de Recolección y Fotografías en Sugerencias del Menú Digital

## Contexto y Problema

1. **Horarios de recolección en menú digital:** La web app móvil de administración permite configurar días y ventanas de atención por sucursal (`service_schedule`: `open_time`, `close_time`). Si bien los días cerrados se deshabilitaban correctamente, el control de hora en el carrito mostraba todas las 24 horas del día (mediante un `<input type="time">` nativo que no restringe la rueda de selección del SO), permitiendo al cliente seleccionar horas fuera del horario configurado (ej. lunes de 4 a 6 PM debe permitir únicamente slots de 16:00 a 18:00).
2. **Fotografías en sugerencias complementarias (Upsell):** La sección de recomendaciones cruzadas del carrito (`cart-upsell`) renderizaba forzosamente iconos estáticos SVG correspondientes a la categoría del platillo, aún cuando el producto contara con fotografía propia configurada en el catálogo (`image_url`).

## Decisiones Técnicas y Arquitectura

1. **Generador determinista de slots de recolección (`pickupSchedule.ts`):**
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
