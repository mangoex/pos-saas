# BDD — Recuperación móvil

@BDD-SC-991
Scenario: Recuperar pago confirmado cuya respuesta se perdió
  Given un intento persistido antes del cobro
  When el servidor confirma y se pierde la respuesta y la pantalla recarga
  Then repite clave y cuerpo originales y recibe el mismo recibo
  And sólo existe un pago, movimiento e historial financiero

@BDD-SC-992
Scenario: Reanudar entrega después de confirmar cobro
  Given el pago confirmado y la entrega pendiente o con respuesta perdida
  When el operador reintenta
  Then reanuda entrega con su clave original sin crear otro pago

@BDD-SC-993
Scenario: No mezclar intenciones entre pestañas y sesiones
  Given dos pestañas del mismo pedido o un cambio de actor y tenant
  When intentan cobrar concurrentemente o reanudar el intento ajeno
  Then serializan el intento propio y no usan claves ni cuerpos del otro contexto
  And cambiar método o caja durante resultado incierto exige resolver el intento original

@BDD-SC-994
Scenario: Persistencia y coordinación son requisito previo al cobro
  Given almacenamiento no disponible o corrupto o Web Locks no disponible
  When el operador intenta cobrar
  Then recibe un error explícito antes de cualquier POST financiero
  And los datos del intento pendiente no se eliminan silenciosamente
