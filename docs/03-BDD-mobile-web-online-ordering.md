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
