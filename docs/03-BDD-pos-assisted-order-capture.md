# BDD - Captura asistida de pedidos en POS

## BDD-FEAT-093 Convertir lenguaje natural en un borrador revisable

```gherkin
@PRD-FR-728 @PRD-NFR-529 @pos @orders @privacy
Feature: El cajero prepara un pedido mediante texto o dictado sin delegar la confirmación

  @BDD-SC-406
  Scenario: Una solicitud inequívoca llena el carrito como borrador
    Given un Cajero con orders.create y la sucursal canónica activa
    And Baguette BBQ está disponible con el comentario Sin cebolla configurado
    When interpreta "Pedido para Miguel Ángel González con teléfono 6672013019, un baguette de BBQ sin cebolla para recoger"
    Then propone Miguel Ángel González, el teléfono normalizado y tipo takeout
    And muestra una línea de Baguette BBQ con Sin cebolla antes de aplicarla
    And aplicar llena el carrito sin crear, cobrar, aceptar ni reservar el pedido

  @BDD-SC-407
  Scenario: Un teléfono con coincidencia única selecciona al cliente
    Given el borrador contiene un teléfono mexicano válido
    When la búsqueda exacta de la sucursal devuelve un solo cliente
    Then el POS lo selecciona y conserva nombre, carrito y tipo de servicio editables

  @BDD-SC-408
  Scenario: Cero o múltiples clientes requieren decisión humana
    Given el borrador contiene un teléfono mexicano válido
    When la búsqueda devuelve cero o más de una coincidencia
    Then el POS no elige una identidad arbitraria
    And permite registrar o seleccionar al cliente mediante el flujo vigente

  @BDD-SC-409
  Scenario: Productos e instrucciones ambiguos fallan cerrados
    Given la frase nombra un producto ambiguo, no disponible o una instrucción no configurada
    When el intérprete resuelve el borrador contra el catálogo efectivo
    Then marca cada elemento no resuelto con explicación en español
    And no inventa product_id, option_id, precio ni sustitución
    And no permite aplicar una línea incompleta silenciosamente

  @BDD-SC-410
  Scenario: Descartar no modifica la venta
    Given un carrito, cliente y tipo de servicio existentes
    When el Cajero abre Captura asistida, escribe una frase y cancela
    Then conserva exactamente el carrito, cliente, modalidad y checkout anteriores

  @BDD-SC-411
  Scenario: El dictado es una mejora progresiva
    Given el navegador ofrece reconocimiento de voz
    When el Cajero pulsa Dictar, concede permiso de micrófono y hay hasta 3000 ms de silencio
    Then la transcripción queda visible y editable antes de interpretar
    And al pulsar Dictar nuevamente tras el cierre automático la nueva frase se agrega al texto existente
    But sin capacidad o con permiso denegado el POS ofrece captura escrita sin bloquear la venta
    And Detener, cerrar o un fallo permanente no reinician el reconocimiento

  @BDD-SC-412
  Scenario: La integración externa recibe texto redactado
    Given una frase con nombre y teléfono
    When el POS interpreta y aplica el borrador
    Then nombre y teléfono se extraen antes de llamar al proveedor
    And OpenRouter recibe marcadores redactados en lugar de esos valores
    And el audio del dictado no se envía a OpenRouter desde RestaurantOS
    And la frase y el teléfono no se escriben en logs, métricas ni almacenamiento persistente
    And el pedido final sólo se crea por el checkout canónico autorizado e idempotente

  @BDD-SC-413
  Scenario: El asistente pregunta cada selección obligatoria faltante
    Given un producto resuelto con grupos obligatorios de tamaño, pan y aderezo
    And la frase no define esas selecciones
    When el backend valida el borrador contra los modificadores efectivos
    Then devuelve una pregunta por cada grupo incompleto con sólo sus opciones disponibles
    And Agregar al pedido permanece deshabilitado hasta satisfacer los mínimos

  @BDD-SC-414
  Scenario: Una opción expresada en la frase se conserva sin volver a preguntarla
    Given Baguette BBQ tiene la opción efectiva Sin cebolla
    When la frase contiene "baguette BBQ sin cebolla"
    Then el borrador selecciona el option_id canónico de Sin cebolla
    And no convierte texto libre en una instrucción de cocina

  @BDD-SC-415
  Scenario: Una respuesta del modelo nunca crea autoridad de catálogo
    Given OpenRouter devuelve un product_id desconocido, JSON inválido o una cantidad fuera de rango
    When el backend reconcilia la respuesta
    Then falla cerrado sin línea aplicable
    And no inventa precio, opción, disponibilidad ni identidad de cliente

  @BDD-SC-416
  Scenario: Proveedor no configurado o indisponible conserva la venta
    Given falta la clave, ocurre timeout o OpenRouter responde con error
    When el Cajero solicita interpretar
    Then el POS explica que el asistente no está disponible
    And conserva carrito, cliente y modalidad
    And la captura manual normal continúa disponible

  @BDD-SC-417
  Scenario: El acceso del encabezado es compacto y accesible
    Given el Cajero está en Punto de Venta
    Then junto a la sucursal ve sólo el icono de persona para Pedido asistido
    And el control conserva aria-label, title, foco visible y área táctil mínima de 44 píxeles

  @BDD-SC-418
  Scenario: El diálogo guía la revisión antes de aplicar
    Given el Cajero abre Pedido asistido
    When escribe o dicta una solicitud
    Then ve una conversación legible con solicitud, interpretación y preguntas pendientes
    And puede cancelar sin cambios o agregar únicamente un borrador completo
```
