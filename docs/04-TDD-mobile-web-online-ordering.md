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

## TDD-TS-310 Pedido asistido público estricto

### TDD-TC-259 Dictado progresivo y callbacks vigentes
- Archivo: `tests/frontend/test_mobile_voice_order.mjs`
- Propósito: validar concatenación entre sesiones, deduplicación, doble inicio, cierre, errores y descarte de callbacks obsoletos.

### TDD-TC-260 Fallback escrito
- Archivo: `tests/frontend/test_mobile_voice_order.mjs`
- Propósito: comprobar que navegador incompatible o permiso denegado conservan textarea y envío manual.

### TDD-TC-261 Contrato tipado de carrito exacto
- Archivo: `tests/frontend/test_mobile_voice_order.mjs`
- Propósito: convertir líneas validadas en CartItem con modifiers y line_total_cents, rechazando productos u opciones no canónicas.

### TDD-TC-262 Redacción antes del proveedor
- Archivos: `apps/api/tests/test_assisted_order.py`, `apps/api/tests/test_storefront_voice_order.py`
- Propósito: demostrar que nombre/teléfono se extraen antes de OpenRouter y no aparecen en payload externo ni logs.

### TDD-TC-263 Feature flag, esquema y rate limit públicos
- Archivo: `apps/api/tests/test_storefront_voice_order.py`
- Propósito: verificar default-off, public_key activa, texto 3..1000, campos extra prohibidos, límite permitido/rechazado e indisponibilidad fail-closed del limitador.

### TDD-TC-264 Reconciliación canónica de salida
- Archivos: `apps/api/tests/test_assisted_order.py`, `apps/api/tests/test_storefront_voice_order.py`
- Propósito: rechazar JSON, IDs y cantidades inválidas; acotar el reconocimiento de opciones al segmento de cada producto, respetar negaciones y devolver todos los grupos canónicos por línea para revisión humana.

### TDD-TC-265 Ausencia de efectos de dominio
- Archivo: `apps/api/tests/test_storefront_voice_order.py`
- Propósito: comprobar que interpretar no crea intención, pedido, pago, reserva, producción ni movimiento de inventario.

### TDD-TC-266 Flujo móvil de extremo a extremo
- Archivo: `tests/e2e/mobile_voice_order.mjs`
- Propósito: verificar dictado simulado o texto, revisión, opciones, carrito exacto y continuidad hacia el checkout canónico sin persistencia anticipada.
- Estado: pendiente hasta contar con un tenant sintético, API local y navegador con simulación de
  `SpeechRecognition`; no se considera evidencia verde del incremento actual.
