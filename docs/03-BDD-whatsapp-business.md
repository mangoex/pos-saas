# BDD WhatsApp Business Platform & Asistente de Menú

## BDD-FEAT-110 Onboarding con Meta Embedded Signup

@PRD-FR-092 @whatsapp @onboarding
Feature: Onboarding multi-tenant de WhatsApp Business mediante Meta Embedded Signup

  @BDD-SC-901
  Scenario: Intercambio de OAuth code y vinculación de WABA por sucursal
    Given un usuario administrador autenticado en el panel de control de mimenu
    And la integración de Meta Tech Provider configurada en el sistema
    When el usuario completa el flujo de Meta Embedded Signup y el SDK retorna un authorization code
    Then el backend intercambia el código con Meta Graph API por tokens de sistema
    And asocia el WABA ID y Phone Number ID a la sucursal activa
    And el estado de la integración de WhatsApp se actualiza a CONNECTED sin afectar a otras sucursales

## BDD-FEAT-111 Handshake y Verificación Criptográfica de Webhooks de Meta

@PRD-FR-092 @whatsapp @security
Feature: Handshake y verificación segura de webhooks entrantes de WhatsApp

  @BDD-SC-902
  Scenario: Handshake GET y validación de firma HMAC-SHA256 en POST
    Given el endpoint público de webhook de WhatsApp "/integrations/whatsapp/webhook"
    When Meta envía una solicitud GET de verificación con "hub.mode=subscribe" y "hub.verify_token" correcto
    Then el sistema responde con el valor exacto de "hub.challenge" y código HTTP 200
    When un evento POST entrante llega con firma en "X-Hub-Signature-256"
    Then el sistema valida criptográficamente la firma con el App Secret de Meta
    And almacena el payload original inmutable en "integration_webhook_logs"
    And responde HTTP 200 en menos de 3 segundos

## BDD-FEAT-112 Asistente Conversacional Basado en Menú, Horarios y Promociones

@PRD-FR-092 @whatsapp @knowledge
Feature: Respuestas automáticas con base de conocimiento del restaurante en tiempo real

  @BDD-SC-903
  Scenario: Respuesta contextualizada a consultas de menú, horarios y promociones
    Given una sucursal con WhatsApp Business conectado y catálogo activo
    When un cliente envía un mensaje preguntando por platillos, horarios o promociones
    Then el asistente consulta la base de datos de la sucursal en modo solo lectura
    And responde con los platillos disponibles, horarios vigentes o promociones del día
    And excluye productos agotados o no disponibles
    And añade el enlace al menú web móvil del restaurante para ordenar en línea

## BDD-FEAT-113 Aislamiento Multi-Tenant y Fallback Seguro

@PRD-FR-092 @whatsapp @multitenant
Feature: Aislamiento multi-tenant y manejo de fallos seguro

  @BDD-SC-904
  Scenario: Rechazo seguro de números no registrados y fallback a atención humana
    Given un mensaje entrante dirigido a un "phone_number_id" no configurado en ninguna sucursal
    When el webhook procesa el evento
    Then el sistema registra el evento y finaliza de manera segura sin emitir respuestas erróneas
    When un mensaje en una sucursal activa contiene una consulta fuera de catálogo o ambigua
    Then el asistente ofrece amablemente contactar al personal del restaurante o revisar el menú web

## BDD-FEAT-114 Detección de Intención de Compra y Carrito Asistido en WhatsApp

@PRD-FR-093 @whatsapp @commerce
Feature: Interpretación conversacional de pedidos, detección de agotados y pre-llenado de carrito

  @BDD-SC-905
  Scenario: Detección de productos, cantidades, precios en centavos y generación de enlace de carrito
    Given una sucursal activa con menú y precios vigentes en centavos
    When un comensal envía un mensaje con intención de pedido especificando productos y cantidades
    Then el asistente identifica los platillos solicitados en el catálogo activo
    And calcula las cantidades y subtotales en enteros de centavos de MXN
    And devuelve el desglose de productos con el total estimado
    And adjunta un enlace directo de carrito pre-llenado hacia el storefront web

  @BDD-SC-906
  Scenario: Detección y notificación inmediata de productos agotados o 86'd
    Given un producto marcado como no disponible en la sucursal activa
    When el cliente solicita dicho producto agotado junto con otros platillos disponibles
    Then el asistente procesa los platillos disponibles normalmente
    And alerta explícitamente que el producto no está disponible por el momento
    And excluye el monto del producto agotado del total estimado

  @BDD-SC-907
  Scenario: Manejo transparente de productos no encontrados en carta
    Given un mensaje que solicita platillos ajenos a la oferta del restaurante
    When el parser evalúa el texto contra el catálogo
    Then clasifica los artículos inexistentes como no encontrados sin forzar falsas asociaciones
    And avisa amablemente al comensal qué artículos no forman parte del menú

  @BDD-SC-908
  Scenario: Preservación estricta de la autoridad de checkout y precios
    Given una propuesta de carrito asistido generada en la conversación de WhatsApp
    When el cliente abre el enlace de carrito en el navegador web
    Then el checkout digital valida los precios actuales de la base de datos y disponibilidad en tiempo real
    And el bot de WhatsApp no crea registros de orden directamente en la base de datos sin confirmación del cliente

## BDD-FEAT-115 Notificaciones Automáticas de Estado de Pedidos por WhatsApp

@PRD-FR-094 @whatsapp @notifications
Feature: Envío de alertas de estado en tiempo real (aceptado, listo, en camino, entregado y calificación)

  @BDD-SC-909
  Scenario: Notificación de aceptación y preparación en cocina
    Given una orden recién confirmada con teléfono del comensal y sucursal con WhatsApp activo
    When el estado de la orden cambia a "ACCEPTED" o "IN_PRODUCTION"
    Then el sistema envía un mensaje de WhatsApp indicando que la cocina comenzó la preparación
    And adjunta el folio del pedido y enlace de seguimiento en vivo

  @BDD-SC-910
  Scenario: Notificación de pedido listo para recoger o en camino
    Given un pedido con teléfono de cliente registrado
    When el pedido para recoger cambia a estado "READY"
    Then el comensal recibe un mensaje indicando que puede pasar a ventanilla
    When un pedido a domicilio cambia a estado "IN_DELIVERY"
    Then el comensal recibe un mensaje indicando que el repartidor va en camino a su dirección

  @BDD-SC-911
  Scenario: Notificación de entrega con invitación a Smart Rating
    Given un pedido en estado "IN_DELIVERY" o "READY"
    When la orden transiciona a "DELIVERED"
    Then el comensal recibe un mensaje de agradecimiento confirmando la entrega
    And el mensaje incluye el enlace directo para calificar su experiencia (Smart Rating)

  @BDD-SC-912
  Scenario: Silencio seguro y no intrusivo ante teléfono ausente o canal desconectado
    Given una orden sin número de teléfono de cliente o en una sucursal sin WhatsApp configurado
    When la orden transiciona entre sus diferentes estados de cumplimiento
    Then el sistema de notificaciones omite el envío de forma segura (skipped)
    And la transición operativa de la orden concluye con éxito sin demoras ni errores

  @BDD-FEAT-116
  Feature: Campañas y Mensajes de Re-engagement por WhatsApp con Políticas de Opt-Out
    Como restaurantero o administrador de mimenu
    Quiero enviar promociones personalizadas a clientes segmentados (riesgo de pérdida, VIPs y nuevos)
    Para incentivar la recompra y fidelidad cumpliendo estrictamente las políticas de consentimiento y desuscripción de Meta

  @BDD-SC-913
  Scenario: Envío de campaña de recuperación a clientes en riesgo de abandono (churn risk)
    Given una sucursal con WhatsApp Business conectado y clientes inactivos por más de 30 días
    When el administrador dispara una campaña de re-engagement para el segmento "churn_risk" con el cupón "VUELVE10"
    Then cada cliente del segmento recibe un mensaje personalizado recordando su platillo preferido
    And el mensaje contiene el código de descuento del 10% y el enlace al menú digital
    And el mensaje incluye la cláusula de desuscripción ("Para no recibir más promociones, responde STOP o BAJA")

  @BDD-SC-914
  Scenario: Envío de campaña de lealtad a clientes VIP con productos frecuentes
    Given clientes frecuentes catalogados como segmento "vip" por volumen o recurrencia de compras
    When se ejecuta una campaña de marketing dirigida al segmento VIP
    Then los clientes reciben una propuesta de lealtad exclusiva con su producto favorito y enlace directo a la tienda

  @BDD-SC-915
  Scenario: Procesamiento automático de Opt-Out cuando el comensal responde STOP o BAJA
    Given un comensal que ha recibido un mensaje promocional por WhatsApp
    When el comensal responde con la palabra clave "BAJA", "STOP" o "CANCELAR"
    Then el webhook registra inmediatamente el número en la lista de opt-out comercial
    And el bot responde confirmando la desuscripción de comunicaciones publicitarias
    And se informa al comensal que continuará recibiendo el seguimiento de sus pedidos en curso

  @BDD-SC-916
  Scenario: Exclusión estricta de números dados de baja en futuros despachos de campañas
    Given un comensal cuyo número de teléfono tiene opt-out registrado
    When se lanza una nueva campaña promocional que incluye su segmento
    Then el servicio de campañas omite el envío a dicho número de forma segura
    And el reporte de ejecución registra al destinatario como omitido por desuscripción previa


