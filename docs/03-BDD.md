# BDD — Behavior-Driven Development

> Registro histórico RestaurantOS: referencias PRD renumeradas +500 para evitar colisiones
> semánticas con SaaS. Los suplementos anteriores al paquete SaaS conservan evidencia del
> producto previo; no certifican comportamiento SaaS vigente. El contrato nuevo está en
> `03-BDD-saas-remediation.md` y `04-TDD-saas-remediation.md`.


## Convenciones

- Lenguaje Gherkin.
- Cada escenario debe incluir identificador.
- Etiquetas obligatorias: requisito, módulo, prioridad y tipo.
- Los escenarios críticos deben automatizarse.
- No describir implementación interna en BDD.

## BDD-FEAT-001 Operación offline de pedidos

```gherkin
@PRD-FR-680 @PRD-FR-682 @critical @offline
Feature: Operación de pedidos sin internet

  Background:
    Given la sucursal tiene un gateway local activo
    And el catálogo vigente está sincronizado
    And la caja tiene un turno abierto

  @BDD-SC-001
  Scenario: Crear un pedido mientras la sucursal no tiene internet
    Given la conexión con la nube está interrumpida
    When el cajero crea y acepta un pedido para recoger
    Then el gateway asigna un identificador único
    And el pedido aparece en el KDS local
    And el comando queda pendiente de sincronización
    And el usuario ve que el pedido está operando en modo offline

  @BDD-SC-002
  Scenario: Sincronizar un pedido creado offline
    Given existe un pedido local pendiente de sincronización
    When la conexión con la nube se recupera
    Then el gateway envía el comando una sola vez de forma efectiva
    And la nube registra el pedido
    And el gateway recibe confirmación
    And el pedido conserva su identidad y folio
```

## BDD-FEAT-002 Idempotencia

```gherkin
@PRD-FR-522 @PRD-FR-687 @critical
Feature: Evitar pedidos duplicados

  @BDD-SC-003
  Scenario: Reintento del mismo webhook externo
    Given la plataforma externa envió un pedido con identificador externo X
    And el pedido X ya fue aceptado
    When el mismo webhook se recibe nuevamente
    Then el sistema responde de forma idempotente
    And no crea un segundo pedido
    And registra el reintento
```

## BDD-FEAT-003 Producción por estaciones

```gherkin
@PRD-FR-511 @PRD-FR-540 @PRD-FR-543 @production
Feature: Separación de componentes por estación

  @BDD-SC-004
  Scenario: Un combo genera tareas en cocina y bebidas
    Given un combo contiene una hamburguesa asignada a cocina
    And contiene una bebida asignada a bebidas
    When el pedido se envía a producción
    Then cocina recibe la tarea de hamburguesa
    And bebidas recibe la tarea de bebida
    And empaque no puede liberar el pedido hasta que ambas tareas terminen
```

## BDD-FEAT-004 Inventario reservado y consumido

```gherkin
@PRD-FR-563 @PRD-FR-564 @inventory @critical
Feature: Reserva y consumo de inventario

  @BDD-SC-005
  Scenario: Reservar al aceptar y consumir al producir
    Given existe inventario disponible para una receta
    When el pedido es aceptado
    Then el sistema crea reservas por los componentes requeridos
    And la existencia física no disminuye todavía
    When la producción es confirmada
    Then las reservas se convierten en movimientos de consumo
    And la existencia disminuye
```

## BDD-FEAT-005 Cancelación

```gherkin
@PRD-FR-528 @PRD-FR-565 @PRD-FR-566 @critical
Feature: Cancelación de pedido

  @BDD-SC-006
  Scenario: Cancelar antes de producir
    Given un pedido aceptado tiene inventario reservado
    And ningún componente ha sido producido
    When un usuario autorizado cancela el pedido
    Then las reservas se liberan
    And no se genera merma

  @BDD-SC-007
  Scenario: Cancelar después de producir
    Given un pedido tiene componentes confirmados como producidos
    When un usuario autorizado cancela el pedido
    Then el sistema solicita clasificar recuperación o merma
    And genera movimientos compensatorios
    And conserva auditoría
```

## BDD-FEAT-006 Recetas multinivel

```gherkin
@PRD-FR-580 @PRD-FR-581 @costing
Feature: Recetas y subrecetas

  @BDD-SC-008
  Scenario: Calcular costo de producto con aderezo por lote
    Given una ensalada utiliza una porción de aderezo
    And el aderezo tiene una receta vigente
    When se calcula el costo estándar de la ensalada
    Then el costo del aderezo se obtiene recursivamente
    And se suma al resto de componentes

  @BDD-SC-009
  Scenario: Rechazar ciclo de recetas
    Given la receta A contiene la receta B
    When se intenta agregar A como componente de B
    Then el sistema rechaza el cambio
    And explica que se generaría un ciclo
```

## BDD-FEAT-007 Producción por lote

```gherkin
@PRD-FR-583 @PRD-FR-585 @PRD-FR-587
Feature: Producción de aderezos por lote

  @BDD-SC-010
  Scenario: Registrar rendimiento real menor al esperado
    Given una orden planea producir 10 litros de aderezo
    When el operador registra 9.4 litros reales
    Then el sistema calcula la diferencia de rendimiento
    And registra la merma real
    And calcula el costo real por litro
    And crea un lote con caducidad
```

## BDD-FEAT-008 Caja

```gherkin
@PRD-FR-550 @PRD-FR-556 @PRD-FR-557 @cash @critical
Feature: Turno y corte de caja

  @BDD-SC-011
  Scenario: Cerrar turno con diferencia
    Given una caja tiene ventas y movimientos registrados
    When el cajero captura el efectivo contado
    Then el sistema calcula el efectivo esperado
    And muestra la diferencia
    And requiere autorización si supera el límite
    And al cerrar genera un corte inmutable
```

## BDD-FEAT-009 Pagos inmutables

```gherkin
@PRD-FR-554 @cash
Feature: Corrección de pagos

  @BDD-SC-012
  Scenario: Corregir una forma de pago confirmada
    Given un pago fue confirmado como tarjeta
    When un usuario autorizado detecta que debía ser efectivo
    Then el sistema no edita el pago original
    And crea movimientos compensatorios
    And registra motivo y autorización
```

## BDD-FEAT-010 Compras XML

```gherkin
@PRD-FR-602 @PRD-FR-603 @purchasing
Feature: Importación de XML de proveedor

  @BDD-SC-013
  Scenario: Importar CFDI nuevo
    Given un XML válido corresponde a la razón social de la sucursal
    When el usuario lo importa
    Then el sistema extrae proveedor, conceptos e impuestos
    And propone equivalencias
    And permite crear recepción y cuenta por pagar

  @BDD-SC-014
  Scenario: Rechazar XML duplicado
    Given el UUID fiscal ya fue importado
    When el usuario intenta importar el mismo XML
    Then el sistema lo rechaza
    And muestra la importación original
```

## BDD-FEAT-011 Traspasos

```gherkin
@PRD-FR-569 @inventory
Feature: Traspaso entre sucursales

  @BDD-SC-015
  Scenario: Confirmar recepción parcial
    Given una sucursal origen envió 20 unidades
    When la sucursal destino recibe 19
    Then el sistema registra salida de 20 en origen
    And entrada de 19 en destino
    And mantiene una diferencia pendiente de conciliación
```

## BDD-FEAT-012 Optimización de reparto

```gherkin
@PRD-FR-623 @PRD-FR-624 @delivery
Feature: Optimización simultánea

  @BDD-SC-016
  Scenario: Agrupar pedidos compatibles
    Given existen tres pedidos próximos en ubicación
    And dos estarán listos dentro de la misma ventana
    And hay un repartidor con capacidad suficiente
    When el despachador solicita optimización
    Then el sistema propone una ruta con los pedidos compatibles
    And muestra secuencia y ETA
    And deja visible cualquier pedido no asignado

  @BDD-SC-017
  Scenario: Operar manualmente sin proveedor de rutas
    Given el proveedor de optimización no responde
    When el despachador abre el tablero
    Then puede asignar pedidos manualmente
    And el sistema registra que la asignación fue manual
```

## BDD-FEAT-013 Impresión

```gherkin
@PRD-FR-546 @PRD-FR-548 @printing
Feature: Impresión automática

  @BDD-SC-018
  Scenario: Reintentar una impresión fallida
    Given una comanda fue enviada a una impresora sin papel
    When el agente detecta el error
    Then el trabajo queda en estado fallido o reintentable
    And no se duplica silenciosamente
    When la impresora vuelve a estar disponible
    Then un usuario puede reintentar
    And el sistema conserva el historial
```

## BDD-FEAT-014 Facturación y exportación

```gherkin
@PRD-FR-660 @PRD-FR-664 @exports
Feature: Exportación de tickets

  @BDD-SC-019
  Scenario: Crear lote de exportación individual
    Given existen tickets elegibles de una razón social
    When el usuario crea un lote
    Then el sistema genera documentos, conceptos, clientes y pagos
    And marca los tickets como incluidos
    And evita incluirlos en otro lote activo

  @BDD-SC-020
  Scenario: Reexportar con autorización
    Given un lote fue rechazado por el sistema contable
    When un usuario autorizado corrige el layout
    Then el sistema crea una nueva versión de exportación
    And conserva el archivo anterior
    And registra motivo y usuario
```

## BDD-FEAT-015 Permisos

```gherkin
@PRD-FR-505 @security
Feature: Permisos por sucursal

  @BDD-SC-021
  Scenario: Impedir ajuste de inventario a cajero
    Given un usuario tiene rol de cajero
    When intenta crear un ajuste de inventario
    Then el sistema rechaza la operación
    And registra el intento
```

## BDD-FEAT-016 Conectividad externa

```gherkin
@PRD-FR-689 @offline
Feature: Continuidad de canales externos

  @BDD-SC-022
  Scenario: Continuar con enlace de respaldo
    Given la conexión principal falla
    And el enlace 4G está disponible
    When llega un pedido externo
    Then el pedido se entrega a la sucursal
    And el sistema informa que opera con respaldo

  @BDD-SC-023
  Scenario: Pérdida total de conectividad
    Given fallan la conexión principal y el respaldo
    When la nube detecta que la sucursal no confirma recepción
    Then intenta pausar la sucursal en canales compatibles
    And alerta a operación corporativa
    And la sucursal continúa con pedidos locales
```

## BDD-FEAT-060 Integridad de especificaciones y trazabilidad

```gherkin
@PRD-NFR-510 @architecture @documentation
Feature: Rechazar ambigüedades estructurales del harness

  @BDD-SC-195
  Scenario: El gate detecta definiciones duplicadas y referencias mal ubicadas
    Given los documentos PRD, BDD, TDD y la matriz de trazabilidad
    When el gate de arquitectura analiza sus definiciones formales
    Then cada identificador tiene una sola definición
    And cada escenario BDD tiene un identificador propio
    And cada requisito tiene una sola fila en la matriz
    And las columnas BDD y TDD contienen referencias de su tipo correcto
    And toda referencia de la matriz apunta a una definición existente
    And cada escenario BDD y suite TDD definidos aparece en la matriz

  @BDD-SC-420
  Scenario: El quality ratchet rechaza degradación nueva sin heredar deuda histórica
    Given un pull request con su base Git disponible y deuda histórica fuera del diff
    When el gate analiza las líneas añadidas en fuentes Python, TypeScript y JavaScript
    Then rechaza silenciamientos de tipos, lint o cobertura y pruebas desactivadas sin justificación
    And acepta una excepción local con una razón visible para revisión
    And no falla por líneas históricas no modificadas
    And informa sólo ruta, línea y categoría sin reproducir el contenido
    And falla cerrado cuando no puede resolver la base del pull request
```

## Regla de expansión

Cada historia nueva deberá incluir:

- escenario feliz,
- validaciones,
- permisos,
- fallo de proveedor,
- reintento,
- offline cuando aplique,
- auditoría,
- reversión o compensación,
- concurrencia cuando aplique.

## Enlaces personalizados

- BDD-DOM-001: Dos administradores consultan sólo sus enlaces; un alias nuevo conserva
  el canónico y alias anteriores; un nombre ocupado no se asigna al otro restaurante.
- BDD-DOM-002: Solicitar dominio produce instrucciones DNS. TXT incorrecto no activa;
  TXT correcto espera HTTPS. Administrador común no activa; superadmin confirma ruta/TLS
  y revalida TXT. Baja conserva historial y bloquea tráfico.
- BDD-DOM-003: Dominio de tacos con sesión/slug/clave de sushi rechaza acceso; host
  desconocido no sirve el SaaS. X-Forwarded-Host no altera resolución. Raíz de tacos
  abre menú propio y manifiesto conserva origen/scope. Plataforma compartida sigue operando.

## Recuperación SaaS

- BDD-REC-001: Dado dos restaurantes, al navegar entre URLs y reintentar un pedido, catálogo/carrito/POS/KDS permanecen en su organización; slug inexistente falla sin productos ficticios.
- BDD-REC-002: Dado un alta por plan o prueba, al terminar/reanudar onboarding desde otro navegador se conserva el avance; al vencer 14 días el servidor rechaza nueva operación incluso con sesión vigente.
- BDD-REC-003: Dado un actor normal, revocado o de otro tenant, no obtiene privilegios por correo ni modifica recursos ajenos; eventos externos necesitan autenticidad y destino inequívoco.
