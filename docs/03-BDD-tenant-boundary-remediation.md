# BDD — Fronteras multitenant

@BDD-SC-984
Scenario: Un administrador no puede vincular una sucursal de otro restaurante
  Given dos organizaciones con sus respectivas sucursales activas
  When el administrador de A crea o actualiza un mapping hacia la sucursal de B
  Then se rechaza antes de escribir mapping, pedido o comunicación externa
  And una sucursal propia activa sí se puede vincular
  And una sucursal inexistente o inactiva se rechaza

@BDD-SC-985
Scenario: El resolver rechaza asociaciones inválidas sin confiar en datos históricos
  Given un mapping que no corresponde a la organización o cuya sucursal está inactiva
  When se intenta resolver un evento externo
  Then no se acepta como destino del evento
  And una escritura directa cruzada es rechazada por integridad de base de datos
  And la migración se detiene sin borrar filas si encuentra datos incompatibles

@BDD-SC-986
Scenario: Omitir la sucursal en CRM no amplía el permiso
  Given un usuario autorizado sólo para clientes de una sucursal
  When consulta segmentos CRM sin branch_id
  Then sólo obtiene datos de la sucursal autorizada o una denegación explícita
  And los agregados organizacionales requieren permiso organizacional
  And ninguna variante devuelve datos de otro tenant
  And los importes mantienen centavos exactos y la última compra se expresa en UTC
  And los clientes sin pedidos siguen incluidos en el contador autorizado

@BDD-SC-990
Scenario: El agotado temporal mantiene el destino necesario para sincronizar
  Given un producto mapeado a Uber y dos sucursales propias
  When se marca agotado en una sucursal
  Then se encola el cambio pendiente de confirmación para esa sucursal
  And el mapping permanece habilitado y la otra sucursal no cambia
  And restaurar disponibilidad no reactiva mappings deshabilitados por administración
