# TDD WhatsApp Business Platform & Asistente de Menú

## TDD-TS-320 Suite de Onboarding y Configuración de WhatsApp

### TDD-TC-320 Intercambio de tokens de Embedded Signup y guardado multi-tenant
- Archivo: `tests/integration/test_whatsapp_business_integration.py::test_whatsapp_embedded_signup_exchange`
- Propósito: Verificar que el código de autorización retornado por el SDK de Facebook sea intercambiado por tokens de sistema con Meta Graph API y persista el WABA ID y Phone Number ID asociados a la sucursal activa.

## TDD-TS-321 Suite de Webhooks y Seguridad de WhatsApp

### TDD-TC-321 Handshake GET de verificación de Webhook
- Archivo: `tests/integration/test_whatsapp_business_integration.py::test_whatsapp_webhook_verification_handshake`
- Propósito: Comprobar que peticiones GET de Meta con `hub.mode=subscribe` y el `hub.verify_token` configurado retornen el `hub.challenge` con HTTP 200, y rechacen tokens inválidos con 403 Forbidden.

### TDD-TC-322 Verificación criptográfica HMAC-SHA256 e inmutabilidad de logs
- Archivo: `tests/integration/test_whatsapp_business_integration.py::test_whatsapp_webhook_signature_and_raw_log`
- Propósito: Validar que peticiones POST entrantes con firma `X-Hub-Signature-256` válida sean aceptadas, persistan el payload original en `integration_webhook_logs` y firmas manipuladas sean rechazadas con 401 Unauthorized.

## TDD-TS-322 Suite de Base de Conocimiento y Asistente Conversacional

### TDD-TC-323 Respuestas de menú y horarios con exclusión de agotados
- Archivo: `tests/integration/test_whatsapp_business_integration.py::test_whatsapp_bot_menu_and_hours_context`
- Propósito: Verificar que el asistente responda preguntas de menú con productos disponibles, respete productos marcados como agotados, informe el estado de horarios y adjunte el enlace al menú web móvil del restaurante.

## TDD-TS-323 Suite de Aislamiento Multi-Tenant y Fallback

### TDD-TC-324 Aislamiento multi-tenant y rechazo seguro de números desconocidos
- Archivo: `tests/integration/test_whatsapp_business_integration.py::test_whatsapp_multitenant_isolation_and_unmapped_number`
- Propósito: Verificar que mensajes a números no registrados finalicen de forma segura (fail-closed) sin fuga de información entre restaurantes ni llamadas espurias a Meta.

## TDD-TS-324 Suite de Pedidos Asistidos por WhatsApp (Conversational Commerce)

### TDD-TC-325 Interpretación de líneas, cantidades y cálculo monetario exacto en centavos
- Archivo: `tests/integration/test_whatsapp_business_integration.py::test_whatsapp_order_parser_intent_and_cart_link`
- Propósito: Comprobar que el parser identifique la intención de compra, reconozca cantidades en números o palabras ("2", "dos"), extraiga los productos solicitados y compute el subtotal y total estrictamente en enteros de centavos de MXN.

### TDD-TC-326 Detección y exclusión transparente de productos 86'd con aviso al cliente
- Archivo: `tests/integration/test_whatsapp_business_integration.py::test_whatsapp_order_parser_handles_86d_unavailable_items`
- Propósito: Validar que si el comensal solicita un producto marcado como no disponible (`is_available = False`), el sistema lo identifique como agotado, lo segregue en `unavailable_items`, lo excluya del total y genere una advertencia cortés.

### TDD-TC-327 Artículos no encontrados en carta tratados como unmatched_items
- Archivo: `tests/integration/test_whatsapp_business_integration.py::test_whatsapp_order_parser_handles_unmatched_items`
- Propósito: Verificar que platillos o productos que no existen en el catálogo activo se clasifiquen como `unmatched_items` sin asociaciones erróneas ni alucinaciones.

### TDD-TC-328 Generación de enlace seguro a storefront con items codificados y respuesta conversacional formateada
- Archivo: `tests/integration/test_whatsapp_business_integration.py::test_whatsapp_bot_conversational_order_proposal`
- Propósito: Verificar que el bot formule un mensaje contextualizado con emojis, desglose detallado con precios unitarios y subtotales en MXN, advertencias de agotados y un enlace `https://mimenu.com/<slug>/cart?items=...` para finalizar el checkout en la web.

## TDD-TS-325 Suite de Notificaciones de Estado de Pedido por WhatsApp

### TDD-TC-329 Envío de mensaje en transición a ACCEPTED o IN_PRODUCTION
- Archivo: `tests/integration/test_whatsapp_business_integration.py::test_whatsapp_notification_order_accepted`
- Propósito: Comprobar que al cambiar una orden a estado `ACCEPTED` o `IN_PRODUCTION`, el servicio despache un mensaje de WhatsApp notificando que la cocina comenzó a preparar el pedido, con el folio y URL de seguimiento en vivo.

### TDD-TC-330 Notificación READY o IN_DELIVERY según tipo de pedido
- Archivo: `tests/integration/test_whatsapp_business_integration.py::test_whatsapp_notification_ready_and_in_delivery`
- Propósito: Validar que para órdenes `takeout` en estado `READY` se invite a recoger en mostrador, y para órdenes `delivery` en estado `IN_DELIVERY` se notifique que el repartidor va en camino con el link de entrega.

### TDD-TC-331 Notificación de entrega DELIVERED con invitación de satisfacción Smart Rating
- Archivo: `tests/integration/test_whatsapp_business_integration.py::test_whatsapp_notification_delivered_smart_rating`
- Propósito: Verificar que al marcar la orden como `DELIVERED`, el comensal reciba una felicitación y agradecimiento junto con el enlace directo al calificador de satisfacción Smart Rating.

### TDD-TC-332 Manejo no bloqueante y omisión segura ante teléfono ausente o canal desconectado
- Archivo: `tests/integration/test_whatsapp_business_integration.py::test_whatsapp_notification_skipped_safely`
- Propósito: Comprobar que si el comensal no tiene teléfono o la sucursal no tiene WhatsApp Business habilitado, el despachador retorne `status="skipped"` limpiamente sin lanzar excepciones ni detener transiciones operativas.

## TDD-TS-326 Suite de Campañas de Marketing y Opt-Out por WhatsApp

### TDD-TC-333 Segmentación de destinatarios y previsualización de campaña
- Archivo: `tests/integration/test_whatsapp_business_integration.py::test_whatsapp_campaign_segmentation_and_preview`
- Propósito: Validar que el servicio de campañas identifique correctamente clientes elegibles en los segmentos `churn_risk`, `vip` y `new_customers`, y previsualice el mensaje con el cupón asignado, enlace de compra y cláusula de opt-out.

### TDD-TC-334 Despacho de campaña a lote segmentado con métricas de entrega
- Archivo: `tests/integration/test_whatsapp_business_integration.py::test_whatsapp_campaign_dispatch_to_segment`
- Propósito: Comprobar el envío por lote a clientes del segmento seleccionado, registrando estadísticas de ejecución (`total_targets`, `sent_count`, `skipped_count`, `failed_count`).

### TDD-TC-335 Registro y confirmación automática de Opt-Out ante mensaje STOP o BAJA
- Archivo: `tests/integration/test_whatsapp_business_integration.py::test_whatsapp_opt_out_registration_on_stop`
- Propósito: Verificar que si un comensal envía palabras clave de baja ("STOP", "BAJA", "CANCELAR"), el bot confirme la desuscripción y el sistema registre el teléfono en la lista de exclusión de marketing.

### TDD-TC-336 Exclusión estricta de números dados de baja en futuros envíos de marketing
- Archivo: `tests/integration/test_whatsapp_business_integration.py::test_whatsapp_opted_out_numbers_excluded_from_campaign`
- Propósito: Validar que un cliente con opt-out activo sea omitido de manera segura (`status="skipped"`, `reason="opted_out"`) en cualquier campaña publicitaria posterior, sin bloquear las notificaciones de pedidos activos.


