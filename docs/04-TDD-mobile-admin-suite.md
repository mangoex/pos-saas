# TDD - Suite Móvil de Administración y Puesta en Marcha Rápida

## TDD-TS-109 Suite Móvil de Administración y Puesta en Marcha Rápida

### TDD-TC-250 Navegación y montaje reactivo de pestañas operativas en MobileAdminShell
- Archivo: `apps/api/tests/test_mobile_admin_suite.py::test_mobile_admin_tabs_and_contracts`
- Propósito: Verificar la disponibilidad y respuesta de los contratos de backend que nutren las pestañas móviles de Pedidos, Caja, Menú y Sucursal.

### TDD-TC-251 Apertura y cierre operativo de turno de caja con reintento estable y evidencia real
- Archivo: `apps/api/tests/test_mobile_admin_suite.py::test_mobile_cash_shift_open_close_and_movements`
- Propósito: Validar que el flujo móvil de apertura con fondo inicial en centavos, consulta de turno actual, registro de movimiento con evidencia capturada y cierre operativo responde conforme a las invariantes de caja; la misma intención conserva su clave ante error incierto y rota al cambiar payload o confirmar éxito.

### TDD-TC-252 Actualización ágil de disponibilidad y persistencia de producto con imagen en catálogo móvil
- Archivo: `apps/api/tests/test_mobile_admin_suite.py::test_mobile_catalog_toggle_availability_and_product_image`
- Propósito: Validar que la alternancia de disponibilidad de producto (`active` vs `inactive`) y la persistencia de productos con `image_url` operan correctamente en el catálogo.

### TDD-TC-253 Exposición de enlaces digitales de sucursal y alternancia reversible a vista de escritorio
- Archivo: `apps/api/tests/test_mobile_admin_suite.py::test_mobile_branch_settings_and_links`
- Propósito: Comprobar la consulta de enlaces digitales públicos (`/saas/links`) y actualización de configuración de sucursal (`whatsapp_ordering_enabled`, `google_review_url`).

### TDD-TC-254 Cobro y entrega integrada de comanda con snapshot de venta y liquidación de pedidos entregados
- Archivo: `apps/api/tests/test_mobile_admin_suite.py::test_mobile_order_payment_and_fulfillment`
- Propósito: Validar que un pedido en estado listo o entregado puede recibir cobro vía `POST /orders/{id}/payments`, registrando el pago con el método seleccionado contra el turno de caja abierto, creando snapshot histórico de venta, emitiendo evento `PAYMENT_CONFIRMED` y actualizando la proyección de `payment_status` a `CONFIRMED`.

### TDD-TC-255 Coordinador persistente en el shell móvil
- Archivos: `tests/frontend/test_mobile_admin_order_alerts.mjs`,
  `apps/api/tests/test_mobile_admin_suite.py::test_mobile_public_intent_alert_feed_is_minimal_scoped_and_cursor_aware`
- Propósito: comprobar que el coordinador se monta fuera de la vista condicional de Pedidos y permanece activo al navegar por cualquier pestaña.

### TDD-TC-256 Cursor determinista y deduplicación
- Archivos: `tests/frontend/test_mobile_admin_order_alerts.mjs`,
  `apps/api/tests/test_mobile_admin_suite.py::test_mobile_public_intent_alert_feed_is_minimal_scoped_and_cursor_aware`
- Propósito: verificar línea base silenciosa, claves `(created_at, id)`, timestamps iguales, respuestas obsoletas, cambio de sucursal y ausencia de duplicados.

### TDD-TC-257 Estado real de AudioContext
- Archivo: `tests/frontend/test_mobile_admin_order_alerts.mjs`
- Propósito: verificar que `resume()` se espera, que sólo `running` activa la alarma y que suspensión/rechazo conserva el fallback visual.

### TDD-TC-258 Regresión del monitor de pedidos
- Archivo: `tests/frontend/test_mobile_admin_orders_monitor.mjs`
- Propósito: confirmar que listado, filtros, aceptación, cobro y entrega permanecen independientes del coordinador global de alertas.

### TDD-TC-259 Horarios de servicio de sucursal y reconciliación de caja automática
- Archivo: `apps/api/tests/test_branch_service_schedule_and_auto_cash.py`
- Propósito: Validar que `service_schedule`, `auto_cash_shift_enabled` y `auto_cash_opening_cents` se persisten en la sucursal, y que `reconcile_branch_auto_cash_shift` abre automáticamente el turno de caja con fondo predeterminado ($500.00 MXN) dentro de horario y cierra operativamente fuera de horario o en día de descanso, respetando cierres manuales previos del día y turnos manuales en horas extra.

### TDD-TC-260 Restricción de días y horas de servicio en selector para recoger del menú digital
- Archivo: `tests/frontend/test_service_schedule_and_pickup_restrictions.mjs`
- Propósito: Comprobar que en el checkout del menú digital (`CartDrawer`), los días marcados como cerrado (`is_open: false`) quedan deshabilitados en el selector de días (L, M, M, J, V, S, D), el selector de hora queda restringido al rango `[open_time, close_time]` del día elegido, los chips rápidos se filtran para no rebasar el horario, y la validación de envío rechaza pedidos fuera de servicio.

### TDD-TC-261 Persistencia y exposición de métodos de cobro y datos bancarios de sucursal
- Archivo: `apps/api/tests/test_branch_payment_methods_and_storefront.py`
- Propósito: Comprobar que `accepts_cash_payments`, `accepts_card_payments` y `bank_transfer_info` se persisten mediante `update_branch`, se devuelven en `list_branches` y se exponen en `resolve_storefront` para consumo público.

### TDD-TC-262 Presentación condicional de métodos de pago, cupones y datos de transferencia en carrito digital
- Archivo: `tests/frontend/test_cart_payment_methods_and_coupons.mjs`
- Propósito: Verificar que el carrito oculta el formulario de cupón cuando no hay promociones activas, restringe los métodos de pago (Efectivo, Tarjeta, Transferencia) según la configuración de la sucursal, muestra los datos bancarios al elegir transferencia y aplica estilo amplio a las tarjetas de productos.
