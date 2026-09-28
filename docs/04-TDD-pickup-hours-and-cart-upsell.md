# TDD — Casos de Prueba para Horarios de Pickup y Fotografías en Sugerencias

## TDD-TS-296
Implementación y verificación semántica de restricción de horas de recolección y fotografías en sugerencias complementarias en el menú digital móvil.

### Casos de prueba:
### TDD-TC-960
Generación determinista de slots dentro de `[open_time, close_time]` y filtrado de horarios pasados en el día de hoy.
La autoridad temporal pasa a `test_pickup_schedule.py`: reloj UTC fijo, zona de sucursal,
segundos del margen, cambio de día/semana, cierre, DST y configuración ausente/inválida.
`test_public_pickup_schedule.py` verifica HTTP y dominio: clave activa/coherente, par cerrado,
slot vencido sin inserts, persistencia de fecha/zona/UTC, replay después de vencimiento y
conflicto al cambiar horario. Debe probarse el snapshot en SQLite/PostgreSQL y su conservación
al aceptar el pedido; no basta la nota humana ni HTTP 200.
### TDD-TC-961
Verificación de selector `<select id="pickup-time-input" className="pickup-time-field">` con opciones restringidas y auto-ajuste de horario al cambiar de día (`test_pickup_hours_and_cart_upsell.mjs`).
La prueba semántica de carrito usa proyección Python simulada y comprueba refresco al
abrir/recuperar foco, respuesta fallida, cambio de tenant/sucursal durante carga y revalidación
al enviar sin POST con slot vencido. QA visual dirigida al selector y estados de error/carga.
`test_pickup_server_options.mjs` ejecuta validación del transporte, membresía y descarte de
respuestas superadas/desmontadas. `test_pickup_cart_submit.mjs` ejecuta el handler real con
reloj/proyección simulados: horario vencido, fallo de red, cambio de contexto y doble submit.
`test_mobile_web_order_flow.mjs` ejecuta el cliente compartido y conserva el par original
en recuperación después de cambiar los inputs. Los tres tests pickup forman parte de
`pnpm test:pickup-hours`, ya incluido en la cadena semántica de CI.
### TDD-TC-962
Verificación de renderizado de fotografía del producto (`cart-upsell-card-img`) en sugerencias complementarias y fallback seguro al icono de categoría ante ausencia o fallo (`test_pickup_hours_and_cart_upsell.mjs`, `test_mobile_web_order_flow.mjs`).
