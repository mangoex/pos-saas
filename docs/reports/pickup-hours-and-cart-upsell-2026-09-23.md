# Reporte de Implementación — Restricción de Horarios de Recolección y Fotos en Upsell (2026-09-23)

Clasificación de riesgo: **R2** (UI + lógica de validación de frontend en `apps/mobile-web`).
Gobierno: PRD-FR-022, PRD-FR-061, `02-SDD-pickup-hours-and-cart-upsell.md`, `03-BDD-pickup-hours-and-cart-upsell.md` (`BDD-SC-960..964`), `04-TDD-pickup-hours-and-cart-upsell.md` (`TDD-TS-296`, `TDD-TC-960..962`).

## Resumen del Cambio

1. **Horarios de recolección en menú digital:**
   - Se implementó la utilidad [`apps/mobile-web/src/utils/pickupSchedule.ts`](file:///Users/renatavictoriagonzalez/Documents/miguelgespino/pos-saas/apps/mobile-web/src/utils/pickupSchedule.ts) para generar slots acotados estrictamente entre `open_time` y `close_time` de la sucursal.
   - En [`CartDrawer.tsx`](file:///Users/renatavictoriagonzalez/Documents/miguelgespino/pos-saas/apps/mobile-web/src/components/CartDrawer.tsx), se reemplazó el control nativo `<input type="time">` (que desplegaba las 24 horas del día en dispositivos móviles) por un `<select id="pickup-time-input" className="pickup-time-field">` poblado exclusivamente con las horas operativas del día seleccionado.
   - Si el día es hoy, filtra horas pasadas (+ tiempo mínimo de preparación) y si la sucursal aún no abre, arranca desde la hora de apertura.
   - Al cambiar de día, el selector auto-ajusta la hora seleccionada al primer intervalo permitido del nuevo día si la hora previa queda fuera de rango.

2. **Fotografías en sugerencias complementarias (Upsell):**
   - En la sección `cart-upsell` de [`CartDrawer.tsx`](file:///Users/renatavictoriagonzalez/Documents/miguelgespino/pos-saas/apps/mobile-web/src/components/CartDrawer.tsx), se resuelve la imagen del producto vía `prod.image_url || getProductImage(prod)`.
   - Si cuenta con foto configurada, se renderiza la imagen `cart-upsell-card-img` con `object-fit: cover`.
   - Si no cuenta con fotografía o falla la carga en el cliente, conmuta de forma segura al fallback con el icono temático de categoría y su gradiente.

## Evidencia Local y Calidad Monotónica

- **Fase Roja (TDD):** Se verificó la falla inicial de `tests/frontend/test_pickup_hours_and_cart_upsell.mjs` antes de la implementación de la utilidad y los componentes.
- **Fase Verde (TDD):**
  - `node --test tests/frontend/test_pickup_hours_and_cart_upsell.mjs`: **3/3 pasan**.
  - `node --test tests/frontend/test_service_schedule_and_pickup_restrictions.mjs`: **3/3 pasan**.
  - `node --test tests/frontend/test_pickup_grace.mjs`: **pasa**.
  - `node --test tests/frontend/test_mobile_cart_personalization.mjs`: **4/4 pasan**.
  - `node --test tests/frontend/test_mobile_menu_theme.mjs`: **pasa**.
  - `node --test tests/frontend/test_mobile_product_modifiers.mjs`: **pasa**.
  - `node --test tests/frontend/test_mobile_web_order_flow.mjs`: **22/22 pasan**.
  - `node --test tests/frontend/test_dine_in_and_pickup_scheduling.mjs`: **7/7 pasan**.
  - Total suite frontend afectada: **42/42 pasan (100%)**.
- **Typecheck y Compilación:**
  - `pnpm --filter mobile-web build`: `tsc --noEmit && vite build` terminó exitosamente con código 0 y 0 errores de tipado.
- **Calidad de código y formato:**
  - `git diff --check`: 0 errores de espacio en blanco.
