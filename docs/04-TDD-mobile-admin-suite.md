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
