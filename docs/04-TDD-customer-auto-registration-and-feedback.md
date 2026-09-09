# TDD - Auto-Registro de Clientes en Pedidos y Trazabilidad de Satisfacción

## TDD-TS-108 Auto-Registro de Clientes y Feedback Integral

### TDD-TC-242 Auto-registro de cliente al aceptar pedido móvil público
- Archivo: `apps/api/tests/test_customer_order_auto_registration.py::test_mobile_public_order_intent_auto_registers_customer`
- Propósito: Verificar que al aceptar un pedido público con teléfono y nombre, se crea automáticamente el cliente y se vincula el `order.customer_id`.

### TDD-TC-243 Auto-registro o vinculación de cliente en venta POS
- Archivo: `apps/api/tests/test_customer_order_auto_registration.py::test_pos_local_order_auto_registers_or_links_customer`
- Propósito: Validar que `create_local_order` con teléfono y nombre registra o asocia al cliente sin duplicar registros.

### TDD-TC-244 Captura incondicional de calificación y feedback privado
- Archivo: `apps/api/tests/test_customer_order_auto_registration.py::test_customer_feedback_persistence_and_average_rating`
- Propósito: Validar que toda calificación de 1 a 5 estrellas se almacena en `customer_feedbacks` vinculada a `customer_id` y `customer_phone`.

### TDD-TC-245 Directorio administrativo con rating_summary y feedbacks
- Archivo: `apps/api/tests/test_customer_order_auto_registration.py::test_list_customers_includes_rating_summary_and_feedbacks`
- Propósito: Comprobar que `GET /customers` incluye `average_rating`, `rating_count`, y comentarios recientes para cada cliente.

### TDD-TC-246 Vinculación de feedback emitido antes de la aceptación de pedido móvil
- Archivo: `apps/api/tests/test_customer_order_auto_registration.py::test_mobile_public_order_feedback_linked_before_and_after_acceptance`
- Propósito: Asegurar que una calificación emitida inmediatamente tras enviar el pedido en la web móvil (previo a la aceptación operativa) quede vinculada al cliente y se refleje en su promedio de satisfacción.

### TDD-TC-247 Actualización idempotente de feedback y auto-sanación de calificaciones huérfanas
- Archivo: `apps/api/tests/test_customer_order_auto_registration.py::test_feedback_upsert_and_retroactive_healing`
- Propósito: Validar que el envío posterior de comentario privado actualiza el feedback sin duplicarlo, y que calificaciones históricas con `customer_id` nulo se auto-sanan por número de teléfono.
