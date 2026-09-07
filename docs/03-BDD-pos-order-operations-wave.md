# BDD - Operación POS, ajustes y compras de sucursal

## BDD-FEAT-062 Comentarios corporativos por producto

@PRD-FR-699 @PRD-FR-701 @comments @catalog
Feature: Administrar comentarios corporativos relacionados con productos

  @BDD-SC-203
  Scenario: Alta masiva por subcategorías desplegables con preview
    Given un Administrador autenticado y productos activos organizados por estación y subcategoría
    And el catálogo de productos identifica cada subcategoría por category_id
    When abre una categoría operativa y marca una o varias subcategorías
    And pega comentarios separados por coma, salto de línea o dos o más espacios
    Then la pantalla muestra cuántas subcategorías, productos activos y comentarios serán afectados
    And el sistema recorta vacíos y muestra creados, existentes y duplicados antes de confirmar
    And al confirmar crea una sola identidad por comentario normalizado
    And agrega relaciones para todos los productos activos de las subcategorías seleccionadas sin
      retirar relaciones anteriores no incluidas
    And el contrato global rechaza `branch_id` y cualquier override de sucursal
    And cambiar el texto o los destinos después del preview exige solicitarlo de nuevo
    And un error al leer comentarios se informa por separado sin convertir categorías y productos
      cargados en un catálogo vacío

  @BDD-SC-204
  Scenario: Los comentarios no dependen de sucursal
    Given el comentario Sin sal relacionado con un producto corporativo
    When Cajeros de dos sucursales consultan ese producto
    Then ambos reciben el mismo comentario activo
    And no existe una excepción de disponibilidad por sucursal
    And un Supervisor no puede cambiar el catálogo corporativo

  @BDD-SC-205
  Scenario: POS muestra sólo comentarios relacionados con el producto
    Given Sin azúcar está relacionado con Café y Sin lechuga con Ensalada
    When el Cajero personaliza Café
    Then ve Sin azúcar y no ve Sin lechuga
    And puede seleccionar varias indicaciones táctiles
    And el carrito muestra los textos que eligió, no sólo un conteo

  @BDD-SC-206
  Scenario: Comentario se congela sin efecto monetario ni inventariable
    Given un Cajero selecciona Sin azúcar para Café
    When el backend acepta el pedido
    Then congela ID y texto como preset_instruction en la línea
    And el precio, receta, reserva, consumo y costo permanecen sin cambio
    And KDS, comanda e historial muestran el texto congelado

  @BDD-SC-207
  Scenario: Migración conserva comentarios y pedidos históricos
    Given existen presets por producto y pedidos con snapshots anteriores
    When se ejecuta la migración al catálogo corporativo
    Then deduplica definiciones y crea relaciones con productos
    And no elimina grupos, opciones, pedidos ni snapshots históricos
    And el downgrade restaura exactamente el status previo de cada adicional afectado
    And un nuevo upgrade vuelve a marcar needs_review los conflictos sin inventar datos

## BDD-FEAT-063 Ingredientes adicionales universales

@PRD-FR-700 @PRD-FR-701 @ingredient-extras @inventory
Feature: Agregar porciones de insumos a cualquier línea durante la venta

  @BDD-SC-208
  Scenario: Administrador configura un adicional desde un insumo
    Given existe el insumo Aguacate con unidad y costo por sucursal
    When el Administrador configura nombre, porción Decimal, precio de venta y estación
    Then el adicional queda corporativo y activo
    And el precio de venta no se deriva automáticamente del costo promedio
    And no puede guardar una configuración sin porción positiva, precio explícito o estación válida

  @BDD-SC-209
  Scenario: POS ofrece adicionales junto al botón Cliente
    Given el carrito contiene una línea y existen adicionales activos
    When el Cajero abre Ingredientes adicionales
    Then la única línea queda seleccionada como destino
    And puede elegir adicionales y número entero de porciones
    And el carrito permite retirar cada adicional antes de guardar

  @BDD-SC-210
  Scenario: Adicional se usa sin relación previa con el producto
    Given Aguacate adicional no tiene relación de catálogo con Ensalada
    When el Cajero lo agrega a la línea Ensalada
    Then el backend valida el adicional corporativo sin consultar asignaciones históricas
    And recalcula precio, reserva, consumo y costo con valores canónicos
    And ignora cualquier precio o costo enviado por el navegador
    And sólo acepta de una a 99 porciones enteras por adicional
    And congela la configuración aplicada en el pedido

  @BDD-SC-211
  Scenario: Adicional no puede agregarse sin línea destino
    Given el carrito está vacío
    When el Cajero intenta abrir Ingredientes adicionales
    Then el control está deshabilitado y explica que primero debe agregar un producto
    And no crea estado parcial ni comando de backend

  @BDD-SC-212
  Scenario: Configuración histórica contradictoria requiere revisión
    Given un adicional heredado tiene cantidades o precios distintos según producto
    When se migra al catálogo universal
    Then el adicional queda needs_review y no se publica al POS
    And el sistema no elige una cantidad, precio o estación arbitrarios
    And la administración canónica no ofrece relaciones legadas por producto para resolverlo
    And ningún add_option_id ni remove_option_id ligado a la relación histórica se ofrece o acepta
      en ventas nuevas
    And preview, alta, edición o archivo de una relación histórica falla con
      ingredient_variation_assignments_read_only sin mutarla
    And pedidos y asignaciones históricas permanecen consultables

## BDD-FEAT-064 Carrito y pedidos no pagados editables

@PRD-FR-703 @PRD-FR-704 @orders @pos
Feature: Retirar líneas del carrito y enmendar pedidos antes de producción

  @BDD-SC-232
  Scenario: El catálogo no repite productos arriba de la cuadrícula
    Given el Cajero selecciona una categoría con productos activos
    When consulta el catálogo POS
    Then ve cada producto en la cuadrícula con nombre, imagen o icono y precio
    And no existe una segunda banda superior con los mismos nombres de producto

  @BDD-SC-213
  Scenario: Retirar la última unidad elimina la línea del carrito
    Given el carrito contiene una línea con cantidad uno
    When el Cajero pulsa menos o el icono Eliminar producto
    Then la línea desaparece del carrito
    And el subtotal se recalcula sin dejar una cantidad cero

  @BDD-SC-214
  Scenario: Pedidos abre detalle de pedido pagado y no pagado
    Given existen pedidos de la sucursal en diferentes estados
    When el Cajero selecciona cualquier fila del historial
    Then ve líneas, comentarios, adicionales, ajustes, eventos, pago y total
    And el backend informa si es editable y el motivo cuando no lo es

  @BDD-SC-455
  Scenario: Pedidos avisa cuántas cuentas están por aceptar
    Given la sucursal activa tiene pedidos PENDING y pedidos en otros estados
    And otra sucursal también tiene pedidos PENDING
    When el Cajero consulta cualquier pantalla del POS
    Then la navegación muestra junto a Pedidos el total exacto de pedidos PENDING de la sucursal activa
    And no cuenta pedidos de otros estados ni de otra sucursal
    And el contador se oculta cuando el total llega a cero
    And se actualiza periódicamente, al recuperar foco y después de aceptar un pedido

  @BDD-SC-215
  Scenario: Enmendar un pedido aceptado sin producción iniciada
    Given un pedido ACCEPTED sin pago y con todas sus tareas PENDING
    When un actor con orders.amend guarda una imagen de líneas con la versión vigente
    Then el backend retira líneas sustituidas lógicamente y crea las nuevas
    And compensa diferencias de reserva y reemplaza tareas pendientes
    And recalcula el total y agrega ORDER_AMENDED y auditoría

  @BDD-SC-216
  Scenario: Conflicto de versión no produce cambios parciales
    Given dos sesiones abren la misma versión editable del pedido
    When la primera guarda y la segunda intenta guardar la versión anterior
    Then la segunda recibe order_version_conflict
    And no cambia líneas, reservas, tareas, total ni eventos

  @BDD-SC-217
  Scenario: Pedido pagado o con producción iniciada es sólo lectura
    Given un pedido tiene pago confirmado o alguna tarea distinta de PENDING
    When un actor intenta enmendarlo
    Then el backend rechaza la enmienda con un motivo explícito
    And el historial conserva acceso de consulta sin mostrar Editar pedido

  @BDD-SC-248
  Scenario: Revisar pedido sin abandonar la lista
    Given el Cajero consulta Pedidos en una pantalla de escritorio
    When selecciona cualquier fila
    Then la fila permanece visible y resaltada en la columna principal
    And el detalle se abre a la derecha sin popup
    And muestra cliente, tipo, estado, productos y total
    And ofrece Editar pedido o Confirmar pagado únicamente cuando corresponda

## BDD-FEAT-068 Cobro diferido para llevar y domicilio

@PRD-FR-708 @payments @orders @pos
Feature: Confirmar pago cuando el pedido se entrega

  @BDD-SC-233
  Scenario Outline: Para llevar y domicilio quedan pendientes de pago
    Given un pedido <tipo> con productos válidos y método previsto <metodo>
    When el Cajero confirma el pedido desde el POS
    Then el backend crea la orden ACCEPTED y sus tareas productivas
    And no crea todavía un pago confirmado
    And Pedidos la muestra como Pendiente de pago

    Examples:
      | tipo     | metodo        |
      | takeout  | cash          |
      | delivery | transfer      |

  @BDD-SC-234
  Scenario: Confirmar cobro desde Pedidos
    Given un pedido Pendiente de pago por el total vigente
    When un actor con payments.confirm elige el método realmente recibido y confirma
    Then se crea un único pago CONFIRMED por el total exacto
    And el pago queda asociado al turno OPEN de la caja que confirma, no al turno histórico de captura
    And se registran PAYMENT_CONFIRMED, ORDER_CLOSED y auditoría
    And el pedido deja de aparecer como Pendiente de pago

  @BDD-SC-235
  Scenario: Editar pedido pendiente antes de producción
    Given un pedido Pendiente de pago sin pago y con todas sus tareas PENDING
    When el Cajero abre Pedidos y elige Editar pedido sobre una fila seleccionada
    Then el POS abre una ruta de edición con el identificador de ese pedido
    And muestra el folio y las líneas del pedido seleccionado en lugar de una venta nueva
    And conserva las líneas desde su snapshot aunque un producto no aparezca en el catálogo visible
    When el Cajero guarda líneas diferentes
    Then se crea una enmienda versionada sin crear otra orden
    And el método previsto permanece sin convertirse en pago

## BDD-FEAT-065 Ajustes de cortesía autorizados

@PRD-FR-705 @PRD-NFR-519 @orders @security @audit
Feature: Reducir el total antes del pago con autorización de Supervisor

  @BDD-SC-218
  Scenario: Supervisor de la sucursal autoriza una cortesía
    Given un pedido no pagado y un Supervisor elegible de la misma sucursal
    When el Cajero selecciona al Supervisor y éste captura su contraseña válida
    Then el backend emite una autorización de un solo uso para ese pedido y acción
    And la contraseña no se persiste ni aparece en logs o auditoría

  @BDD-SC-219
  Scenario: Ajuste conserva subtotal y agrega un registro inmutable
    Given el subtotal de líneas es 15000 centavos y existe una autorización válida
    When el Cajero solicita nuevo total 12000 con justificación suficiente
    Then el backend conserva 15000 como subtotal calculado
    And agrega un ajuste de -3000 con solicitante y autorizador
    And el total cobrable queda en 12000 y el pago debe coincidir con ese total

  @BDD-SC-220
  Scenario: Cajero no puede autoautorizar el cambio
    Given un Cajero conoce su propia contraseña pero no tiene orders.adjust_total
    When intenta emitir autorización como Supervisor
    Then el backend rechaza sin revelar si usuario o contraseña fue incorrecto
    And registra un evento de seguridad sin credenciales

  @BDD-SC-221
  Scenario: Autorización expirada, reutilizada o de otro pedido falla
    Given una autorización expirada, consumida o emitida para otro recurso
    When se presenta para ajustar el pedido
    Then el comando falla atómicamente
    And no cambia total ni crea ajuste o evento de negocio

  @BDD-SC-222
  Scenario: Ajuste inválido o posterior al pago se rechaza
    Given un pedido pagado o una solicitud sin justificación válida
    When se intenta un total negativo, mayor al subtotal o posterior al pago
    Then el backend rechaza la operación
    And no consume una autorización válida por un error de validación de datos

## BDD-FEAT-066 Proveedores y compras de sucursal

@PRD-FR-591 @PRD-FR-608 @PRD-FR-706 @PRD-FR-707 @suppliers @purchases @cash
Feature: Supervisor registra proveedores y compras desde el POS

  @BDD-SC-223
  Scenario: Supervisor consulta catálogo central y crea proveedor
    Given un Supervisor autenticado en su sucursal canónica
    When abre Proveedores y registra código, nombre y datos opcionales válidos
    Then ve los proveedores corporativos existentes
    And crea un proveedor corporativo habilitado para su sucursal
    And la auditoría conserva actor y sucursal de procedencia

  @BDD-SC-224
  Scenario: Código o RFC duplicado no crea proveedor parcial
    Given ya existe un proveedor con el código o RFC capturado
    When el Supervisor intenta registrarlo otra vez
    Then recibe supplier_already_exists
    And no crea proveedor, contacto ni términos de sucursal parciales

  @BDD-SC-225
  Scenario: Supervisor crea presentación exacta para proveedor nuevo
    Given un proveedor sin presentaciones y un insumo con unidad base
    When captura unidad comercial, contenido aprovechable y precio
    Then el sistema crea una presentación corporativa con conversión Decimal e historial de precio
    And queda disponible para seleccionarse en una compra de la sucursal

  @BDD-SC-226
  Scenario: Compra de varias líneas pagada en efectivo afecta caja una sola vez
    Given un Supervisor con turno abierto, proveedor y presentaciones válidas
    When guarda y confirma una compra en efectivo con varias líneas e idempotency key
    Then el backend recalcula totales y cantidades base
    And crea PURCHASE_RECEIPT por línea y actualiza costo promedio
    And crea un solo retiro SUPPLY_PURCHASE por el total confirmado

  @BDD-SC-227
  Scenario: Tarjeta o transferencia no crea movimiento de caja
    Given una compra válida de sucursal
    When se confirma con tarjeta o transferencia
    Then genera recepción y costo promedio
    And no crea retiro de efectivo
    And una compra a crédito se rechaza mientras no exista sublibro de cuentas por pagar

  @BDD-SC-228
  Scenario: Cajero o sucursal ajena no pueden administrar compras
    Given un Cajero o un Supervisor de otra sucursal
    When intenta crear proveedor, presentación, compra o confirmación fuera de alcance
    Then el backend rechaza por permiso o alcance
    And no confía en branch_id enviado por el navegador

  @BDD-SC-814
  Scenario: Dos restaurantes reutilizan códigos, folios y claves sin cruzar compras
    Given dos organizaciones y sus sucursales, proveedores, insumos y presentaciones propios
    When ambas usan el mismo código de proveedor, folio e idempotency key de confirmación
    Then cada listado y detalle devuelve sólo recursos de su organización
    And una mutación o cancelación con el ID ajeno falla sin movimientos ni caja ajenos

  @BDD-SC-229
  Scenario: Cancelación confirmada usa compensaciones
    Given una compra confirmada con entradas de inventario y retiro de caja
    When un Supervisor autorizado la cancela con motivo
    Then crea PURCHASE_REVERSAL y CASH_REVERSAL referenciados cuando corresponde
    And nunca borra ni sobrescribe los movimientos originales
