# BDD: Pedidos en Línea y Autoservicio Web Móvil

## BDD-FEAT-092: Captura de Pedidos Públicos en Línea

@BDD-SC-377
Scenario: Captura de pedido público con precios autorizados de catálogo
  Given un cliente accede a la web de autoservicio para una sucursal activa
  When selecciona productos del catálogo y envía la orden con datos de entrega
  Then se persiste una intención PENDING_REVIEW con referencia pública y total calculado por Python
  And no se crea un pedido operativo, turno, pago, reserva ni tarea durante la captura
  And los precios vigentes de catálogo no usan fallbacks artificiales

@BDD-SC-378
Scenario: Rechazo de producto sin precio activo configurado
  Given un producto del catálogo que carece de precio activo en la sucursal
  When se intenta persistir una intención pública que lo incluye
  Then el backend rechaza la intención con error explícito de precio faltante
  And no persiste una intención, pedido, turno, pago, reserva ni tarea parcial

@BDD-SC-379
Scenario: Captura pública no crea ni asocia turno de caja
  Given una sucursal activa con o sin turno físico presencial
  When se persiste una intención pública válida
  Then se persiste una intención PENDING_REVIEW sin turno, pago, reserva ni tarea
  And la aceptación autenticada posterior resuelve el pedido operativo conforme al dominio canónico

@BDD-SC-382
Scenario: Resolución GPS queda fuera del incremento MOB-ORD-001
  Given múltiples sucursales con coordenadas registradas
  When un cliente móvil autoriza ubicación GPS
  Then MOB-ORD-001 no define ni implementa resolución o asignación automática por GPS
  And la captura pública sigue resolviendo la sucursal exclusivamente mediante public_key

@BDD-SC-383
Scenario: Captura de pedidos fuera de horario con caja cerrada
  Given una sucursal seleccionada que no tiene turno de caja abierto en ese momento
  When un cliente confirma un pedido desde la app móvil
  Then la intención queda pendiente de revisión sin crear turno virtual ni reutilizar un turno histórico
  And la app conserva el carrito si no recibe una referencia persistida válida

@BDD-SC-384
Scenario: Modalidades públicas en barra, para llevar y envío
  Given un cliente armando su carrito de compra en la app web móvil
  When selecciona comer en local (en barra), para llevar o a domicilio y envía una intención válida
  Then la intención conserva el tipo de servicio validado por Python
  And la captura no crea pedido operativo, asignación de mesa ni turno de caja

@BDD-SC-501
Scenario: Modo catálogo y bloqueo de pedidos cuando la caja está cerrada
  Given una sucursal activa sin turnos de caja en estado OPEN o CLOSING
  When un comensal abre la aplicación web móvil del menú
  Then la API pública de storefront y catálogo reporta "has_active_shift: false"
  And la web móvil muestra los productos y categorías con navegación normal
  And la categoría inicial se presenta como "Cerrado por el momento" en vez de "Todos"
  And el botón de envío de pedido se encuentra deshabilitado mostrando "Abriremos pronto"

## BDD-FEAT-810 Pedido asistido público como borrador del carrito

@PRD-FR-739 @PRD-NFR-531 @mobile-web @voice @privacy
Feature: Dictar o escribir una solicitud sin delegar autoridad al proveedor de IA

@BDD-SC-819
Scenario: Dictado soportado conserva una transcripción visible y editable
  Given el navegador ofrece SpeechRecognition y el comensal autoriza el micrófono
  When dicta una frase, el navegador cierra la sesión y vuelve a dictar
  Then la nueva frase se agrega sin duplicados al texto existente
  And cerrar, detener o un callback obsoleto no altera una sesión posterior

@BDD-SC-820
Scenario: Captura escrita permanece disponible sin micrófono
  Given el navegador no ofrece SpeechRecognition o el permiso se deniega
  When el comensal abre Pedido por voz
  Then puede escribir, editar y enviar la solicitud sin bloquear el menú ni el carrito

@BDD-SC-821
Scenario: La integración externa recibe texto redactado y acotado
  Given una solicitud contiene nombre y teléfono sintéticos
  When el backend solicita un borrador al adaptador OpenRouter
  Then el proveedor recibe marcadores redactados en lugar de esos valores
  And logs y métricas no contienen transcript, PII, catálogo completo ni respuesta cruda

@BDD-SC-822
Scenario: Python rechaza autoridad inventada por el modelo
  Given el proveedor devuelve un producto desconocido o una cantidad inválida
  When Python reconcilia la propuesta contra la sucursal pública
  Then falla cerrado con código estable y no devuelve una línea aplicable

  Given el texto menciona una opción ajena o no puede segmentarse sin ambigüedad
  When Python reconcilia las coincidencias locales contra el catálogo del producto
  Then no selecciona esa opción automáticamente
  And devuelve únicamente grupos canónicos para decisión humana

@BDD-SC-823
Scenario: Modificadores obligatorios requieren decisión humana
  Given un producto válido tiene grupos obligatorios incompletos
  When el borrador se muestra al comensal
  Then presenta sólo las opciones canónicas disponibles
  And no permite agregar el artículo hasta cumplir cada mínimo y máximo

@BDD-SC-824
Scenario: Borrador válido entra al carrito con total exacto
  Given Python devuelve productos, cantidades y opciones canónicas completas
  When el comensal confirma el borrador
  Then mobile-web crea CartItem tipados con modifiers y line_total_cents exacto
  And el checkout normal permanece editable y es la única frontera que persiste la intención

@BDD-SC-825
Scenario: Configuración, límite o proveedor indisponible preservan el estado
  Given la función está apagada, el cliente excede el límite o OpenRouter falla
  When el comensal solicita interpretar
  Then recibe un error estable sin éxito falso
  And conserva transcripción, carrito y captura escrita
