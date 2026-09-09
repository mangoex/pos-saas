# TDD - Suite Móvil de Administración y Puesta en Marcha Rápida

## TDD-TS-109 Suite Móvil de Administración y Puesta en Marcha Rápida

### TDD-TC-246 Navegación y montaje reactivo de pestañas operativas en MobileAdminShell
- Archivo: `apps/api/tests/test_mobile_admin_suite.py::test_mobile_admin_tabs_and_contracts`
- Propósito: Verificar la disponibilidad y respuesta de los contratos de backend que nutren las pestañas móviles de Pedidos, Caja, Menú y Sucursal.

### TDD-TC-247 Apertura y cierre operativo de turno de caja con validación de fondo de caja y registro de movimientos
- Archivo: `apps/api/tests/test_mobile_admin_suite.py::test_mobile_cash_shift_open_close_and_movements`
- Propósito: Validar que el flujo móvil de apertura con fondo inicial en centavos, consulta de turno actual, registro de movimiento y cierre operativo responde conforme a las invariantes de caja.

### TDD-TC-248 Actualización ágil de disponibilidad y persistencia de producto con imagen en catálogo móvil
- Archivo: `apps/api/tests/test_mobile_admin_suite.py::test_mobile_catalog_toggle_availability_and_product_image`
- Propósito: Validar que la alternancia de disponibilidad de producto (`active` vs `inactive`) y la persistencia de productos con `image_url` operan correctamente en el catálogo.

### TDD-TC-249 Exposición de enlaces digitales de sucursal y alternancia reversible a vista de escritorio
- Archivo: `apps/api/tests/test_mobile_admin_suite.py::test_mobile_branch_settings_and_links`
- Propósito: Comprobar la consulta de enlaces digitales públicos (`/saas/links`) y actualización de configuración de sucursal (`whatsapp_ordering_enabled`, `google_review_url`).
