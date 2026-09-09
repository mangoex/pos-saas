# TDD: Pruebas de Pedidos en Línea y Autoservicio Web Móvil

## TDD-TS-095

### TDD-TC-164
- Archivo: `tests/frontend/test_mobile_web_order_flow.mjs::Mobile Order WhatsApp link format for takeaway`
- Propósito: Verificar la proyección WhatsApp para recolección sólo cuando recibe teléfono configurado; no calcula ni sustituye el total autoritativo de Python.

### TDD-TC-165
- Archivo: `tests/frontend/test_mobile_web_order_flow.mjs::Mobile Order WhatsApp link format for delivery with address`
- Propósito: Verificar la proyección WhatsApp configurada con desglose, dirección y notas, sin constituir fuente de persistencia ni de éxito.

### TDD-TC-167
- Archivo: `tests/frontend/test_mobile_web_order_flow.mjs::Mobile order rejects every non-persisted response without fabricating a folio`
- Propósito: Verificar que 4xx, 5xx, timeout y JSON inválido no generan folio, id, total ni enlace simulados; el carrito conserva y reutiliza la misma clave idempotente hasta recuperar una referencia persistida compatible. El cliente sólo acepta una respuesta persistida completa y un enlace WhatsApp exige configuración devuelta por el servidor.

### TDD-TC-248
- Archivo: `apps/api/tests/test_storefront_cash_shift_status.py::test_storefront_and_catalog_report_active_cash_shift_status`
- Propósito: Verificar que la resolución pública de sucursales (`resolve_storefront`) y el catálogo público (`get_public_catalog`) reportan de forma exacta `has_active_shift: true/false` basándose en el estado de los turnos de caja (`cash_shifts`), pasando dinámicamente de cerrado a abierto y viceversa.
