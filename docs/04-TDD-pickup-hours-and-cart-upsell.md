# TDD — Casos de Prueba para Horarios de Pickup y Fotografías en Sugerencias

## Suite: TDD-TS-296
Implementación y verificación semántica de restricción de horas de recolección y fotografías en sugerencias complementarias en el menú digital móvil.

### Casos de prueba:
- **TDD-TC-960**: Generación determinista de slots dentro de `[open_time, close_time]` y filtrado de horarios pasados en el día de hoy (`test_pickup_hours_and_cart_upsell.mjs`).
- **TDD-TC-961**: Verificación de selector `<select id="pickup-time-input" className="pickup-time-field">` con opciones restringidas y auto-ajuste de horario al cambiar de día (`test_pickup_hours_and_cart_upsell.mjs`).
- **TDD-TC-962**: Verificación de renderizado de fotografía del producto (`cart-upsell-card-img`) en sugerencias complementarias y fallback seguro al icono de categoría ante ausencia o fallo (`test_pickup_hours_and_cart_upsell.mjs`, `test_mobile_web_order_flow.mjs`).
