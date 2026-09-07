# BDD SaaS vigente — cierre A01–A12

Estos escenarios son aceptación pendiente de evidencia; los BDD históricos +500 no sustituyen estos contratos.

## BDD-FEAT-700 Sign Up Público Autoservicio

```gherkin
@PRD-FR-001
Feature: Sign Up Público Autoservicio

  @BDD-SC-700
  Scenario: Cumplir el contrato de PRD-FR-001 con alcance propio
    Given un visitante sin cuenta y un negocio B independiente existente
    And los datos de entrada y permisos del requisito PRD-FR-001 satisfechos
    When el actor autorizado ejecuta el recorrido definido en PRD-FR-001
    Then Sign Up Público Autoservicio: Cualquier usuario debe poder registrarse en la plataforma mediante formulario público (nombre del negocio, correo, contraseña y teléfono), sin requerir intervención manual ni agentes de ventas.
    And no se consultan ni modifican datos de B
```

@BDD-SC-813
Scenario: Copiloto ejecutivo aislado por sucursal
  Given un actor autorizado para una sucursal de su organización
  When solicita un análisis ejecutivo
  Then el proveedor recibe sólo snapshots confirmados de esa sucursal
  And los costos no disponibles no se presentan como márgenes

## BDD-FEAT-701 Aprovisionamiento Atómico de Tenant

```gherkin
@PRD-FR-002
Feature: Aprovisionamiento Atómico de Tenant

  @BDD-SC-701
  Scenario: Cumplir el contrato de PRD-FR-002 con alcance propio
    Given un visitante sin cuenta y un negocio B independiente existente
    And los datos de entrada y permisos del requisito PRD-FR-002 satisfechos
    When el actor autorizado ejecuta el recorrido definido en PRD-FR-002
    Then existen organización, sucursal principal, almacén, roles/permisos y owner con sesión en una sola transacción
    And no se consultan ni modifican datos de B
```

## BDD-FEAT-702 Aislamiento Multi-Tenant Estricto

```gherkin
@PRD-FR-003
Feature: Aislamiento Multi-Tenant Estricto

  @BDD-SC-702
  Scenario: Cumplir el contrato de PRD-FR-003 con alcance propio
    Given una organización A habilitada y una organización B independiente
    And los datos de entrada y permisos del requisito PRD-FR-003 satisfechos
    When el actor autorizado ejecuta el recorrido definido en PRD-FR-003
    Then Aislamiento Multi-Tenant Estricto: Todo dato, catálogo, usuario, pedido, turno y factura debe pertenecer estrictamente a su `organization_id`. Todas las consultas y mutaciones de la API deben forzar el filtro por organización. Queda estrictamente prohibida cualquier fuga de información entre tenants.
    And no se consultan ni modifican datos de B
    And conceptos homónimos e Idempotency-Key iguales de caja se procesan de forma independiente por tenant
    And un movimiento de A que referencia un concepto de B se rechaza antes de crear movimiento o comando
    And el ledger de A no expone movimientos ni compensaciones de B
    And un corte o solicitud de reapertura de A no puede leerse, decidirse ni compensarse desde B y no deja comandos de B
    And los reportes de gastos, ventas e insumos de A sólo agregan datos de A después de autorizar su sucursal
    And A y B pueden confirmar o revertir merma con la misma Idempotency-Key sin compartir replay ni movimiento
```

## BDD-FEAT-703 Wizard de Onboarding en 3 Pasos (5 Minutos)

```gherkin
@PRD-FR-004
Feature: Wizard de Onboarding en 3 Pasos (5 Minutos)

  @BDD-SC-703
  Scenario: Cumplir el contrato de PRD-FR-004 con alcance propio
    Given una organización A habilitada y una organización B independiente
    And los datos de entrada y permisos del requisito PRD-FR-004 satisfechos
    When el actor autorizado ejecuta el recorrido definido en PRD-FR-004
    Then el usuario completa datos del negocio, catálogo express y caja/impresión, pudiendo reanudar cada paso sin duplicar entidades
    And no se consultan ni modifican datos de B
```

## BDD-FEAT-704 Gestión de Planes y Suscripción

```gherkin
@PRD-FR-005
Feature: Gestión de Planes y Suscripción

  @BDD-SC-704
  Scenario: Cumplir el contrato de PRD-FR-005 con alcance propio
    Given una organización A habilitada y una organización B independiente
    And los datos de entrada y permisos del requisito PRD-FR-005 satisfechos
    When el actor autorizado ejecuta el recorrido definido en PRD-FR-005
    Then Gestión de Planes y Suscripción: Manejo de suscripción autoservicio ($349 MXN Básico / $599 MXN Pro) con soporte para período de prueba (Trial 14 días), estado activo, aviso de pago vencido y suspensión automática.
    And no se consultan ni modifican datos de B
```

## BDD-FEAT-705 Catálogo Simplificado de Productos

```gherkin
@PRD-FR-010
Feature: Catálogo Simplificado de Productos

  @BDD-SC-705
  Scenario: Cumplir el contrato de PRD-FR-010 con alcance propio
    Given una organización A habilitada y una organización B independiente
    And los datos de entrada y permisos del requisito PRD-FR-010 satisfechos
    When el actor autorizado ejecuta el recorrido definido en PRD-FR-010
    Then Catálogo Simplificado de Productos: Administración de categorías, productos, descripción corta, fotos optimizadas, código rápido y visibilidad en menú digital.
    And no se consultan ni modifican datos de B
```

## BDD-FEAT-706 Precios Diferenciados por Canal (Salón vs Delivery)

```gherkin
@PRD-FR-011
Feature: Precios Diferenciados por Canal (Salón vs Delivery)

  @BDD-SC-706
  Scenario: Cumplir el contrato de PRD-FR-011 con alcance propio
    Given una organización A habilitada y una organización B independiente
    And los datos de entrada y permisos del requisito PRD-FR-011 satisfechos
    When el actor autorizado ejecuta el recorrido definido en PRD-FR-011
    Then el mismo producto conserva precio de salón y precio delivery exactos, y cada canal muestra y cobra el correspondiente
    And no se consultan ni modifican datos de B
```

## BDD-FEAT-707 Variantes y Modificadores

```gherkin
@PRD-FR-012
Feature: Variantes y Modificadores

  @BDD-SC-707
  Scenario: Cumplir el contrato de PRD-FR-012 con alcance propio
    Given una organización A habilitada y una organización B independiente
    And los datos de entrada y permisos del requisito PRD-FR-012 satisfechos
    When el actor autorizado ejecuta el recorrido definido en PRD-FR-012
    Then las variantes y grupos obligatorios/opcionales se validan, y los extras actualizan el total exacto sin omitir requisitos
    And no se consultan ni modifican datos de B
```

## BDD-FEAT-708 Kill-Switch y Agotados por Canal

```gherkin
@PRD-FR-013
Feature: Kill-Switch y Agotados por Canal

  @BDD-SC-708
  Scenario: Cumplir el contrato de PRD-FR-013 con alcance propio
    Given una organización A habilitada y una organización B independiente
    And los datos de entrada y permisos del requisito PRD-FR-013 satisfechos
    When el actor autorizado ejecuta el recorrido definido en PRD-FR-013
    Then Kill-Switch y Agotados por Canal: El operador puede marcar un producto como agotado temporalmente en una sucursal, desactivándolo de inmediato en el POS, Menú Web y plataformas de delivery.
    And no se consultan ni modifican datos de B
```

## BDD-FEAT-709 Interfaz Táctil Optimizada

```gherkin
@PRD-FR-020
Feature: Interfaz Táctil Optimizada

  @BDD-SC-709
  Scenario: Cumplir el contrato de PRD-FR-020 con alcance propio
    Given una organización A habilitada y una organización B independiente
    And los datos de entrada y permisos del requisito PRD-FR-020 satisfechos
    When el actor autorizado ejecuta el recorrido definido en PRD-FR-020
    Then Interfaz Táctil Optimizada: Diseñada con tokens CSS nativos de alto contraste para tablets económicas (Android/iPad) y monitores touch. Navegación por pestañas de categoría, barra de búsqueda en tiempo real y selector de cantidades rápido.
    And no se consultan ni modifican datos de B
```

## BDD-FEAT-710 Captura Dinámica de Comandas

```gherkin
@PRD-FR-021
Feature: Captura Dinámica de Comandas

  @BDD-SC-710
  Scenario: Cumplir el contrato de PRD-FR-021 con alcance propio
    Given una organización A habilitada y una organización B independiente
    And los datos de entrada y permisos del requisito PRD-FR-021 satisfechos
    When el actor autorizado ejecuta el recorrido definido en PRD-FR-021
    Then Captura Dinámica de Comandas:
    And no se consultan ni modifican datos de B
```

## BDD-FEAT-711 Modalidades de Venta

```gherkin
@PRD-FR-022
Feature: Modalidades de Venta

  @BDD-SC-711
  Scenario: Cumplir el contrato de PRD-FR-022 con alcance propio
    Given una organización A habilitada y una organización B independiente
    And los datos de entrada y permisos del requisito PRD-FR-022 satisfechos
    When el actor autorizado ejecuta el recorrido definido en PRD-FR-022
    Then Modalidades de Venta: Soporte para Venta en Mostrador (Rápida / Para Llevar), Mesas / Comedor (con nombre de mesa o identificador) y Pedido para Recoger.
    And no se consultan ni modifican datos de B
```

## BDD-FEAT-712 División de Cuentas (Split Bill)

```gherkin
@PRD-FR-023
Feature: División de Cuentas (Split Bill)

  @BDD-SC-712
  Scenario: Cumplir el contrato de PRD-FR-023 con alcance propio
    Given una organización A habilitada y una organización B independiente
    And los datos de entrada y permisos del requisito PRD-FR-023 satisfechos
    When el actor autorizado ejecuta el recorrido definido en PRD-FR-023
    Then División de Cuentas (Split Bill):
    And no se consultan ni modifican datos de B
```

## BDD-FEAT-713 Propinas Integradas

```gherkin
@PRD-FR-024
Feature: Propinas Integradas

  @BDD-SC-713
  Scenario: Cumplir el contrato de PRD-FR-024 con alcance propio
    Given una organización A habilitada y una organización B independiente
    And los datos de entrada y permisos del requisito PRD-FR-024 satisfechos
    When el actor autorizado ejecuta el recorrido definido en PRD-FR-024
    Then Propinas Integradas: Captura ágil de propinas con botones rápidos de porcentaje sugerido (10%, 15%, 20%) o monto libre, registradas por separado para cuadre contable.
    And no se consultan ni modifican datos de B
```

## BDD-FEAT-714 Cobro Multiforma de Pago

```gherkin
@PRD-FR-025
Feature: Cobro Multiforma de Pago

  @BDD-SC-714
  Scenario: Cumplir el contrato de PRD-FR-025 con alcance propio
    Given una organización A habilitada y una organización B independiente
    And los datos de entrada y permisos del requisito PRD-FR-025 satisfechos
    When el actor autorizado ejecuta el recorrido definido en PRD-FR-025
    Then Cobro Multiforma de Pago: Registro de Efectivo (con calculadora de cambio automática), Tarjeta de Débito/Crédito (referencia bancaria opcional), Transferencia SPEI y pagos mixtos (ej. mitad efectivo, mitad tarjeta).
    And no se consultan ni modifican datos de B
```

## BDD-FEAT-715 Inmutabilidad y Auditoría de Pagos

```gherkin
@PRD-FR-026
Feature: Inmutabilidad y Auditoría de Pagos

  @BDD-SC-715
  Scenario: Cumplir el contrato de PRD-FR-026 con alcance propio
    Given una organización A habilitada y una organización B independiente
    And los datos de entrada y permisos del requisito PRD-FR-026 satisfechos
    When el actor autorizado ejecuta el recorrido definido en PRD-FR-026
    Then Inmutabilidad y Auditoría de Pagos: Todo pago confirmado es inmutable en base de datos. Anulaciones o cancelaciones de tickets cobran con registro de motivo y requieren PIN de autorización de supervisor.
    And no se consultan ni modifican datos de B
```

## BDD-FEAT-716 Impresión Térmica Desatendida

```gherkin
@PRD-FR-027
Feature: Impresión Térmica Desatendida

  @BDD-SC-716
  Scenario: Cumplir el contrato de PRD-FR-027 con alcance propio
    Given una organización A habilitada y una organización B independiente
    And los datos de entrada y permisos del requisito PRD-FR-027 satisfechos
    When el actor autorizado ejecuta el recorrido definido en PRD-FR-027
    Then Impresión Térmica Desatendida: Emisión automática de comanda a cocina y ticket para el cliente en impresoras térmicas de 58mm y 80mm vía ESC/POS o diálogo de impresión ligero, conteniendo código QR de autofacturación.
    And no se consultan ni modifican datos de B
```

## BDD-FEAT-717 Resiliencia y Modo Offline

```gherkin
@PRD-FR-028
Feature: Resiliencia y Modo Offline

  @BDD-SC-717
  Scenario: Cumplir el contrato de PRD-FR-028 con alcance propio
    Given una organización A habilitada y una organización B independiente
    And los datos de entrada y permisos del requisito PRD-FR-028 satisfechos
    When el actor autorizado ejecuta el recorrido definido en PRD-FR-028
    Then Resiliencia y Modo Offline: Soporte de cobro local continuo hasta por 2 horas en caso de caída de internet, almacenando tickets y pagos en SQLite local y sincronizando en segundo plano al reconectar.
    And no se consultan ni modifican datos de B
```

## BDD-FEAT-718 Apertura de Turno con Fondo Inicial

```gherkin
@PRD-FR-030
Feature: Apertura de Turno con Fondo Inicial

  @BDD-SC-718
  Scenario: Cumplir el contrato de PRD-FR-030 con alcance propio
    Given una organización A habilitada y una organización B independiente
    And los datos de entrada y permisos del requisito PRD-FR-030 satisfechos
    When el actor autorizado ejecuta el recorrido definido en PRD-FR-030
    Then Apertura de Turno con Fondo Inicial: Apertura obligatoria de turno ingresando el monto del fondo fijo en caja antes de registrar la primera venta.
    And no se consultan ni modifican datos de B
```

## BDD-FEAT-719 Movimientos de Turno (Entradas y Retiros)

```gherkin
@PRD-FR-031
Feature: Movimientos de Turno (Entradas y Retiros)

  @BDD-SC-719
  Scenario: Cumplir el contrato de PRD-FR-031 con alcance propio
    Given una organización A habilitada y una organización B independiente
    And los datos de entrada y permisos del requisito PRD-FR-031 satisfechos
    When el actor autorizado ejecuta el recorrido definido en PRD-FR-031
    Then Movimientos de Turno (Entradas y Retiros): Registro de gastos menores (ej. compra de hielo urgente) y retiros parciales de efectivo con motivo auditable y firma de recepción.
    And no se consultan ni modifican datos de B
```

## BDD-FEAT-720 Corte X (Corte Parcial Informativo)

```gherkin
@PRD-FR-032
Feature: Corte X (Corte Parcial Informativo)

  @BDD-SC-720
  Scenario: Cumplir el contrato de PRD-FR-032 con alcance propio
    Given una organización A habilitada y una organización B independiente
    And los datos de entrada y permisos del requisito PRD-FR-032 satisfechos
    When el actor autorizado ejecuta el recorrido definido en PRD-FR-032
    Then Corte X (Corte Parcial Informativo): Consulta en cualquier momento del turno de las ventas acumuladas por forma de pago sin cerrar el turno.
    And no se consultan ni modifican datos de B
```

## BDD-FEAT-721 Corte Z (Cierre Ciego y Cuadre de Turno)

```gherkin
@PRD-FR-033
Feature: Corte Z (Cierre Ciego y Cuadre de Turno)

  @BDD-SC-721
  Scenario: Cumplir el contrato de PRD-FR-033 con alcance propio
    Given una organización A habilitada y una organización B independiente
    And los datos de entrada y permisos del requisito PRD-FR-033 satisfechos
    When el actor autorizado ejecuta el recorrido definido en PRD-FR-033
    Then el cajero cuenta sin ver el esperado; se calcula diferencia y se congela el turno con corte inmutable, bloqueando nuevos cobros en él
    And no se consultan ni modifican datos de B
```

## BDD-FEAT-722 Notificación Inmediata al Propietario

```gherkin
@PRD-FR-034
Feature: Notificación Inmediata al Propietario

  @BDD-SC-722
  Scenario: Cumplir el contrato de PRD-FR-034 con alcance propio
    Given una organización A habilitada y una organización B independiente
    And los datos de entrada y permisos del requisito PRD-FR-034 satisfechos
    When el actor autorizado ejecuta el recorrido definido en PRD-FR-034
    Then Notificación Inmediata al Propietario: Al emitirse el Corte Z, el sistema genera automáticamente un extracto y lo envía por WhatsApp o email al dueño con el total vendido, método de pago y diferencia de caja.
    And no se consultan ni modifican datos de B
```

## BDD-FEAT-723 Bandeja Centralizada de Delivery

```gherkin
@PRD-FR-040
Feature: Bandeja Centralizada de Delivery

  @BDD-SC-723
  Scenario: Cumplir el contrato de PRD-FR-040 con alcance propio
    Given una organización A habilitada y una organización B independiente
    And los datos de entrada y permisos del requisito PRD-FR-040 satisfechos
    When el actor autorizado ejecuta el recorrido definido en PRD-FR-040
    Then Bandeja Centralizada de Delivery: Recepción directa de pedidos provenientes de Uber Eats, DiDi Food y Rappi en una sola pantalla unificada de comandas en el POS.
    And no se consultan ni modifican datos de B
```

## BDD-FEAT-724 Inyección Automática a Cocina

```gherkin
@PRD-FR-041
Feature: Inyección Automática a Cocina

  @BDD-SC-724
  Scenario: Cumplir el contrato de PRD-FR-041 con alcance propio
    Given una organización A habilitada y una organización B independiente
    And los datos de entrada y permisos del requisito PRD-FR-041 satisfechos
    When el actor autorizado ejecuta el recorrido definido en PRD-FR-041
    Then Inyección Automática a Cocina: Los pedidos aceptados de las apps se imprimen o proyectan en KDS con el mismo formato que los pedidos locales, indicando nombre de la app, número de orden y repartidor.
    And no se consultan ni modifican datos de B
```

## BDD-FEAT-725 Idempotencia de Webhooks de Plataformas

```gherkin
@PRD-FR-042
Feature: Idempotencia de Webhooks de Plataformas

  @BDD-SC-725
  Scenario: Cumplir el contrato de PRD-FR-042 con alcance propio
    Given una organización A habilitada y una organización B independiente
    And los datos de entrada y permisos del requisito PRD-FR-042 satisfechos
    When el actor autorizado ejecuta el recorrido definido en PRD-FR-042
    Then Idempotencia de Webhooks de Plataformas: Recepción robusta de eventos de pedidos de delivery con `idempotency_key`, preservando el payload original de la plataforma y garantizando cero duplicados.
    And no se consultan ni modifican datos de B
```

## BDD-FEAT-726 Kill-Switch Global de Platillos (1 Clic)

```gherkin
@PRD-FR-043
Feature: Kill-Switch Global de Platillos (1 Clic)

  @BDD-SC-726
  Scenario: Cumplir el contrato de PRD-FR-043 con alcance propio
    Given una organización A habilitada y una organización B independiente
    And los datos de entrada y permisos del requisito PRD-FR-043 satisfechos
    When el actor autorizado ejecuta el recorrido definido en PRD-FR-043
    Then Kill-Switch Global de Platillos (1 Clic): Botón maestro en POS/Backoffice que permite marcar un platillo como agotado y transmite la actualización en batch a las APIs de Uber Eats, DiDi Food y Rappi en simultáneo.
    And no se consultan ni modifican datos de B
```

## BDD-FEAT-727 Token Único y Código QR en Ticket

```gherkin
@PRD-FR-050
Feature: Token Único y Código QR en Ticket

  @BDD-SC-727
  Scenario: Cumplir el contrato de PRD-FR-050 con alcance propio
    Given una organización A habilitada y una organización B independiente
    And los datos de entrada y permisos del requisito PRD-FR-050 satisfechos
    When el actor autorizado ejecuta el recorrido definido en PRD-FR-050
    Then Token Único y Código QR en Ticket: Cada ticket emitido en POS genera un `invoice_token` criptográfico seguro impreso en el ticket junto con un código QR y URL corta (`https://pos.midominio.com/f/{token}`).
    And no se consultan ni modifican datos de B
```

## BDD-FEAT-728 Portal Comensal Móvil de Autofacturación

```gherkin
@PRD-FR-051
Feature: Portal Comensal Móvil de Autofacturación

  @BDD-SC-728
  Scenario: Cumplir el contrato de PRD-FR-051 con alcance propio
    Given una organización A habilitada y una organización B independiente
    And los datos de entrada y permisos del requisito PRD-FR-051 satisfechos
    When el actor autorizado ejecuta el recorrido definido en PRD-FR-051
    Then el portal móvil muestra el consumo del token y captura RFC, razón social, código postal, régimen, uso CFDI y correo con validación
    And no se consultan ni modifican datos de B
```

## BDD-FEAT-729 Timbrado CFDI 4.0 Automatizado (FacturAPI / PAC)

```gherkin
@PRD-FR-052
Feature: Timbrado CFDI 4.0 Automatizado (FacturAPI / PAC)

  @BDD-SC-729
  Scenario: Cumplir el contrato de PRD-FR-052 con alcance propio
    Given una organización A habilitada y una organización B independiente
    And los datos de entrada y permisos del requisito PRD-FR-052 satisfechos
    When el actor autorizado ejecuta el recorrido definido en PRD-FR-052
    Then Timbrado CFDI 4.0 Automatizado (FacturAPI / PAC): Validación con el catálogo SAT y timbrado oficial inmediato mediante integración con FacturAPI / PAC autorizado.
    And no se consultan ni modifican datos de B
```

## BDD-FEAT-730 Descarga y Envío Automático

```gherkin
@PRD-FR-053
Feature: Descarga y Envío Automático

  @BDD-SC-730
  Scenario: Cumplir el contrato de PRD-FR-053 con alcance propio
    Given una organización A habilitada y una organización B independiente
    And los datos de entrada y permisos del requisito PRD-FR-053 satisfechos
    When el actor autorizado ejecuta el recorrido definido en PRD-FR-053
    Then Descarga y Envío Automático: En menos de 5 segundos tras pulsar "Facturar", la pantalla ofrece los botones de descarga de PDF y XML, enviando copias al correo del cliente.
    And no se consultan ni modifican datos de B
```

## BDD-FEAT-731 Factura Global Automatizada

```gherkin
@PRD-FR-054
Feature: Factura Global Automatizada

  @BDD-SC-731
  Scenario: Cumplir el contrato de PRD-FR-054 con alcance propio
    Given una organización A habilitada y una organización B independiente
    And los datos de entrada y permisos del requisito PRD-FR-054 satisfechos
    When el actor autorizado ejecuta el recorrido definido en PRD-FR-054
    Then Factura Global Automatizada: Consolidación automática de los tickets no autofacturados del período para generar el CFDI 4.0 global al público en general.
    And no se consultan ni modifican datos de B
```

## BDD-FEAT-732 Menú Digital Responsivo (PWA)

```gherkin
@PRD-FR-060
Feature: Menú Digital Responsivo (PWA)

  @BDD-SC-732
  Scenario: Cumplir el contrato de PRD-FR-060 con alcance propio
    Given una organización A habilitada y una organización B independiente
    And los datos de entrada y permisos del requisito PRD-FR-060 satisfechos
    When el actor autorizado ejecuta el recorrido definido en PRD-FR-060
    Then Menú Digital Responsivo (PWA): Catálogo digital público y atractivo disponible en URL única por restaurante (`https://menu.pos-saas.com/{slug}`), compatible con smartphones y códigos QR en mesas.
    And no se consultan ni modifican datos de B
```

## BDD-FEAT-733 Personalización de Platillos en Menú Web

```gherkin
@PRD-FR-061
Feature: Personalización de Platillos en Menú Web

  @BDD-SC-733
  Scenario: Cumplir el contrato de PRD-FR-061 con alcance propio
    Given una organización A habilitada y una organización B independiente
    And los datos de entrada y permisos del requisito PRD-FR-061 satisfechos
    When el actor autorizado ejecuta el recorrido definido en PRD-FR-061
    Then Personalización de Platillos en Menú Web: El comensal puede elegir opciones, modificadores y extras con recálculo dinámico de precio.
    And no se consultan ni modifican datos de B
```

## BDD-FEAT-734 Carrito y Checkout para WhatsApp

```gherkin
@PRD-FR-062
Feature: Carrito y Checkout para WhatsApp

  @BDD-SC-734
  Scenario: Cumplir el contrato de PRD-FR-062 con alcance propio
    Given una organización A habilitada y una organización B independiente
    And los datos de entrada y permisos del requisito PRD-FR-062 satisfechos
    When el actor autorizado ejecuta el recorrido definido en PRD-FR-062
    Then Carrito y Checkout para WhatsApp: Carrito interactivo con selección de tipo de entrega (Para recoger en sucursal o A domicilio con dirección) y notas especiales.
    And no se consultan ni modifican datos de B
```

## BDD-FEAT-735 Generación de Pedido Formateado a WhatsApp

```gherkin
@PRD-FR-063
Feature: Generación de Pedido Formateado a WhatsApp

  @BDD-SC-735
  Scenario: Cumplir el contrato de PRD-FR-063 con alcance propio
    Given una organización A habilitada y una organización B independiente
    And los datos de entrada y permisos del requisito PRD-FR-063 satisfechos
    When el actor autorizado ejecuta el recorrido definido en PRD-FR-063
    Then se persiste una intención pendiente con sus líneas y se abre el borrador WhatsApp del restaurante; sólo aceptación POS crea pedido operativo
    And no se consultan ni modifican datos de B
```

## BDD-FEAT-736 Dashboard Ejecutivo Resumido

```gherkin
@PRD-FR-070
Feature: Dashboard Ejecutivo Resumido

  @BDD-SC-736
  Scenario: Cumplir el contrato de PRD-FR-070 con alcance propio
    Given una organización A habilitada y una organización B independiente
    And los datos de entrada y permisos del requisito PRD-FR-070 satisfechos
    When el actor autorizado ejecuta el recorrido definido en PRD-FR-070
    Then Dashboard Ejecutivo Resumido: Métricas claras sin saturación: Ventas brutas hoy, Ticket promedio, Comparativa vs semana anterior, Top 5 platillos más vendidos y Distribución de pagos.
    And no se consultan ni modifican datos de B
```

## BDD-FEAT-737 Gestión de Personal con PIN de 4 Dígitos

```gherkin
@PRD-FR-071
Feature: Gestión de Personal con PIN de 4 Dígitos

  @BDD-SC-737
  Scenario: Cumplir el contrato de PRD-FR-071 con alcance propio
    Given una organización A habilitada y una organización B independiente
    And los datos de entrada y permisos del requisito PRD-FR-071 satisfechos
    When el actor autorizado ejecuta el recorrido definido en PRD-FR-071
    Then Gestión de Personal con PIN de 4 Dígitos: Alta ágil de cajeros y supervisores con asignación de PIN de 4 dígitos para cambio rápido de usuario en el POS físico.
    And no se consultan ni modifican datos de B
```

## BDD-FEAT-738 Reporte Automatizado al Dueño

```gherkin
@PRD-FR-072
Feature: Reporte Automatizado al Dueño

  @BDD-SC-738
  Scenario: Cumplir el contrato de PRD-FR-072 con alcance propio
    Given una organización A habilitada y una organización B independiente
    And los datos de entrada y permisos del requisito PRD-FR-072 satisfechos
    When el actor autorizado ejecuta el recorrido definido en PRD-FR-072
    Then Reporte Automatizado al Dueño: Configuración de envío nocturno del resumen de caja y ventas por WhatsApp o correo electrónico.
    And no se consultan ni modifican datos de B
```

## BDD-FEAT-739 El POS debe responder a interacciones táctiles en < 100 ms.

```gherkin
@PRD-NFR-001
Feature: El POS debe responder a interacciones táctiles en < 100 ms.

  @BDD-SC-739
  Scenario: Cumplir el contrato de PRD-NFR-001 con alcance propio
    Given una organización A habilitada y una organización B independiente
    And los datos de entrada y permisos del requisito PRD-NFR-001 satisfechos
    When el actor autorizado ejecuta el recorrido definido en PRD-NFR-001
    Then El POS debe responder a interacciones táctiles en < 100 ms.
    And no se consultan ni modifican datos de B
```

## BDD-FEAT-740 Garantía absoluta de aislamiento de datos a nivel de base de datos (`organization_id` en todas las capas).

```gherkin
@PRD-NFR-002
Feature: Garantía absoluta de aislamiento de datos a nivel de base de datos (`organization_id` en todas las capas).

  @BDD-SC-740
  Scenario: Cumplir el contrato de PRD-NFR-002 con alcance propio
    Given una organización A habilitada y una organización B independiente
    And los datos de entrada y permisos del requisito PRD-NFR-002 satisfechos
    When el actor autorizado ejecuta el recorrido definido en PRD-NFR-002
    Then Garantía absoluta de aislamiento de datos a nivel de base de datos (`organization_id` en todas las capas).
    And no se consultan ni modifican datos de B
```

## BDD-FEAT-741 Uptime del 99.9% para la API central y el portal de autofacturación.

```gherkin
@PRD-NFR-003
Feature: Uptime del 99.9% para la API central y el portal de autofacturación.

  @BDD-SC-741
  Scenario: Cumplir el contrato de PRD-NFR-003 con alcance propio
    Given una organización A habilitada y una organización B independiente
    And los datos de entrada y permisos del requisito PRD-NFR-003 satisfechos
    When el actor autorizado ejecuta el recorrido definido en PRD-NFR-003
    Then Uptime del 99.9% para la API central y el portal de autofacturación.
    And no se consultan ni modifican datos de B
```

## BDD-FEAT-742 El POS debe tolerar hasta 2 horas de trabajo sin internet localmente.

```gherkin
@PRD-NFR-004
Feature: El POS debe tolerar hasta 2 horas de trabajo sin internet localmente.

  @BDD-SC-742
  Scenario: Cumplir el contrato de PRD-NFR-004 con alcance propio
    Given una organización A habilitada y una organización B independiente
    And los datos de entrada y permisos del requisito PRD-NFR-004 satisfechos
    When el actor autorizado ejecuta el recorrido definido en PRD-NFR-004
    Then El POS debe tolerar hasta 2 horas de trabajo sin internet localmente.
    And no se consultan ni modifican datos de B
```

## BDD-FEAT-743 Generación y respuesta de timbrado CFDI 4.0 en < 5 segundos.

```gherkin
@PRD-NFR-005
Feature: Generación y respuesta de timbrado CFDI 4.0 en < 5 segundos.

  @BDD-SC-743
  Scenario: Cumplir el contrato de PRD-NFR-005 con alcance propio
    Given una organización A habilitada y una organización B independiente
    And los datos de entrada y permisos del requisito PRD-NFR-005 satisfechos
    When el actor autorizado ejecuta el recorrido definido en PRD-NFR-005
    Then Generación y respuesta de timbrado CFDI 4.0 en < 5 segundos.
    And no se consultan ni modifican datos de B
```

## BDD-FEAT-744 Interfaces diseñadas para tablets de bajo costo y celulares bajo estándar WCAG 2.1 AA.

```gherkin
@PRD-NFR-006
Feature: Interfaces diseñadas para tablets de bajo costo y celulares bajo estándar WCAG 2.1 AA.

  @BDD-SC-744
  Scenario: Cumplir el contrato de PRD-NFR-006 con alcance propio
    Given una organización A habilitada y una organización B independiente
    And los datos de entrada y permisos del requisito PRD-NFR-006 satisfechos
    When el actor autorizado ejecuta el recorrido definido en PRD-NFR-006
    Then Interfaces diseñadas para tablets de bajo costo y celulares bajo estándar WCAG 2.1 AA.
    And no se consultan ni modifican datos de B
```

## BDD-FEAT-745 Autoridad superadmin persistida, aprovisionamiento administrativo auditable y soporte con actor real, actor efectivo y tenant destino; jamás autoridad por correo ni bootstrap desde login público.

```gherkin
@PRD-FR-080
Feature: Autoridad superadmin persistida, aprovisionamiento administrativo auditable y soporte con actor real, actor efectivo y tenant destino; jamás autoridad por correo ni bootstrap desde login público.

  @BDD-SC-745
  Scenario: Cumplir el contrato de PRD-FR-080 con alcance propio
    Given una organización A habilitada y una organización B independiente
    And los datos de entrada y permisos del requisito PRD-FR-080 satisfechos
    When el actor autorizado ejecuta el recorrido definido en PRD-FR-080
    Then Autoridad superadmin persistida, aprovisionamiento administrativo auditable y soporte con actor real, actor efectivo y tenant destino; jamás autoridad por correo ni bootstrap desde login público.
    And no se consultan ni modifican datos de B
```

## BDD-FEAT-746 Identidad pública exacta del restaurante, estado local y PWA aislados; slug inválido o ambiguo falla explícitamente sin catálogo sustituto.

```gherkin
@PRD-FR-081
Feature: Identidad pública exacta del restaurante, estado local y PWA aislados; slug inválido o ambiguo falla explícitamente sin catálogo sustituto.

  @BDD-SC-746
  Scenario: Cumplir el contrato de PRD-FR-081 con alcance propio
    Given una organización A habilitada y una organización B independiente
    And los datos de entrada y permisos del requisito PRD-FR-081 satisfechos
    When el actor autorizado ejecuta el recorrido definido en PRD-FR-081
    Then Identidad pública exacta del restaurante, estado local y PWA aislados; slug inválido o ambiguo falla explícitamente sin catálogo sustituto.
    And no se consultan ni modifican datos de B

  @BDD-SC-812
  Scenario: Alta administrativa y setup conservan la identidad pública del restaurante
    Given un superadmin crea dos restaurantes, incluido un administrador pendiente de setup
    When cada administrador completa o repite el setup de su propio restaurante
    Then cada tenant tiene un public_slug y una única clave pública activa de su propia sucursal
    And menu_url, listado y detalle refieren el mismo slug sin regenerarlo durante el replay
    And el trial permanece vigente por catorce días y el setup termina en complete
```

## BDD-FEAT-747 Importaciones y toda administración validan actor, organización y sucursal de destino antes de efectos.

```gherkin
@PRD-FR-082
Feature: Importaciones y toda administración validan actor, organización y sucursal de destino antes de efectos.

  @BDD-SC-747
  Scenario: Cumplir el contrato de PRD-FR-082 con alcance propio
    Given una organización A habilitada y una organización B independiente
    And los datos de entrada y permisos del requisito PRD-FR-082 satisfechos
    When el actor autorizado ejecuta el recorrido definido en PRD-FR-082
    Then Importaciones y toda administración validan actor, organización y sucursal de destino antes de efectos.
    And no se consultan ni modifican datos de B
```

## BDD-FEAT-748 Primera venta ligera sin recetas, compras ni costeo de insumos; módulos ERP excluidos del producto, preservando historia y compensaciones.

```gherkin
@PRD-FR-083
Feature: Primera venta ligera sin recetas, compras ni costeo de insumos; módulos ERP excluidos del producto, preservando historia y compensaciones.

  @BDD-SC-748
  Scenario: Cumplir el contrato de PRD-FR-083 con alcance propio
    Given una organización A habilitada y una organización B independiente
    And los datos de entrada y permisos del requisito PRD-FR-083 satisfechos
    When el actor autorizado ejecuta el recorrido definido en PRD-FR-083
    Then Primera venta ligera sin recetas, compras ni costeo de insumos; módulos ERP excluidos del producto, preservando historia y compensaciones.
    And no se consultan ni modifican datos de B
```

## BDD-FEAT-749 Release exige evidencia diferenciada local/PostgreSQL/CI/Git/despliegue/canary; verificar aislamiento de infraestructura Kiwi y SaaS, backups restaurables y reversión antes de habilitación comercial.

```gherkin
@PRD-NFR-007
Feature: Release exige evidencia diferenciada local/PostgreSQL/CI/Git/despliegue/canary; verificar aislamiento de infraestructura Kiwi y SaaS, backups restaurables y reversión antes de habilitación comercial.

  @BDD-SC-749
  Scenario: Cumplir el contrato de PRD-NFR-007 con alcance propio
    Given una organización A habilitada y una organización B independiente
    And los datos de entrada y permisos del requisito PRD-NFR-007 satisfechos
    When el actor autorizado ejecuta el recorrido definido en PRD-NFR-007
    Then Release exige evidencia diferenciada local/PostgreSQL/CI/Git/despliegue/canary; verificar aislamiento de infraestructura Kiwi y SaaS, backups restaurables y reversión antes de habilitación comercial.
    And no se consultan ni modifican datos de B
```

## BDD-FEAT-800 Restaurante desconocido y cambio de negocio

```gherkin
@PRD-FR-081
Feature: Restaurante desconocido y cambio de negocio

  @BDD-SC-800
  Scenario: Restaurante desconocido y cambio de negocio
    Given un visitante conserva carrito de tacos y solicita sushi o un slug desconocido
    When resuelve el restaurante y carga catálogo
    Then sushi sólo muestra datos de sushi; el slug desconocido devuelve 404 sin catálogo sustituto
```

## BDD-FEAT-801 Mutaciones cruzadas rechazadas

```gherkin
@PRD-FR-003
Feature: Mutaciones cruzadas rechazadas

  @BDD-SC-801
  Scenario: Mutaciones cruzadas rechazadas
    Given administradores A y B con sesiones vigentes
    When A intenta consultar o modificar un recurso de B por ID
    Then se rechaza sin revelar datos ni modificar B
    And A no puede cambiar por ID el estado delivery ni el repartidor de B
    And asistencia resuelve códigos de empleado dentro del tenant del actor
```

## BDD-FEAT-802 Correo no concede autoridad

```gherkin
@PRD-FR-080
Feature: Correo no concede autoridad

  @BDD-SC-802
  Scenario: Correo no concede autoridad
    Given una cuenta ordinaria usa un correo antes privilegiado
    When inicia sesión e intenta operar como superadmin
    Then se rechaza el privilegio; login no aprovisiona superadmin
    And Cada petición de soporte revalida al emisor y registra actor real, efectivo, tenant y correlación
    And Revocar la autoridad del emisor impide reutilizar el token de soporte vigente

  @BDD-SC-810
  Scenario: La autoridad persistida no permite recuperación por un tenant suspendido
    Given un superadmin persistido cuya organización de plataforma está suspendida
    When intenta consultar métricas o actualizar su propia contraseña
    Then ambas operaciones se rechazan y la cuenta no cambia de estado

  @BDD-SC-811
  Scenario: Aprovisionamiento no promueve usuarios de tenant existentes
    Given una cuenta existente pertenece a un tenant
    When el provisionador local recibe su correo
    Then rechaza la promoción sin alterar su flag ni sus credenciales
```

## BDD-FEAT-803 Signup atómico con permisos sembrados

```gherkin
@PRD-FR-002
Feature: Signup atómico con permisos sembrados

  @BDD-SC-803
  Scenario: Signup atómico con permisos sembrados
    Given permisos predeterminados ya existen y dos solicitudes compiten
    When se registra un negocio o se inyecta un fallo durante aprovisionamiento
    Then el alta válida obtiene un único tenant completo y todo fallo revierte sus entidades
```

## BDD-FEAT-804 Límite exacto de prueba y suspensión

```gherkin
@PRD-FR-005
Feature: Límite exacto de prueba y suspensión

  @BDD-SC-804
  Scenario: Límite exacto de prueba y suspensión
    Given trial iniciado en t0 y token emitido antes del vencimiento
    When se opera en t0+14 días o después de suspensión
    Then la operación comercial se rechaza aunque el token no haya expirado
```

## BDD-FEAT-805 Webhook sin autenticidad no produce pedidos

```gherkin
@PRD-FR-042
Feature: Webhook sin autenticidad no produce pedidos

  @BDD-SC-805
  Scenario: Webhook sin autenticidad no produce pedidos
    Given integración ausente o firma ausente o incorrecta
    When se recibe un evento externo
    Then se rechaza sin crear pedidos; un evento firmado válido repetido sólo se procesa una vez
```

## BDD-FEAT-806 Estado remoto exige confirmación

```gherkin
@PRD-FR-043
Feature: Estado remoto exige confirmación

  @BDD-SC-806
  Scenario: Estado remoto exige confirmación
    Given producto agotado localmente y proveedor con timeout
    When se solicita sincronizar disponibilidad
    Then se informa pendiente o error y nunca confirmado sin respuesta del proveedor
```

## BDD-FEAT-807 Captura canónica hasta cocina

```gherkin
@PRD-FR-063
Feature: Captura canónica hasta cocina

  @BDD-SC-807
  Scenario: Captura canónica hasta cocina
    Given menú A con productos y modificadores válidos
    When checkout se repite y POS A acepta la intención
    Then existe una intención con líneas y un pedido en KDS A; POS B no puede aceptarla
    And WhatsApp conserva referencia pública al reintentar y no crea folio operativo antes de aceptación
    And sin clave pública o Idempotency-Key rechaza sin crear intención, pago ni pedido
```

## BDD-FEAT-808 Primera venta sin ERP

```gherkin
@PRD-FR-083
Feature: Primera venta sin ERP

  @BDD-SC-808
  Scenario: Primera venta sin ERP
    Given negocio nuevo sin recetas ni costos de insumos
    When termina onboarding, abre caja y vende un producto
    Then emite primer ticket sin configuración de recetas o compras
    And la navegación no ofrece recetas multinivel, producción por lotes, almacenes múltiples ni traspasos
    And una URL histórica de esos módulos muestra que está fuera de alcance sin montar el ERP
    And mermas, caja, compensaciones y extras simples permanecen disponibles
    And elegir menú vacío en registro guiado no agrega productos de otra plantilla
    And un OCR ilegible devuelve campos vacíos y nunca inventa proveedor, folio, cantidad o costo
```

## BDD-FEAT-809 Liberación con evidencia verificable

```gherkin
@PRD-NFR-007
Feature: Liberación con evidencia verificable

  @BDD-SC-809
  Scenario: Liberación con evidencia verificable
    Given candidato de release e infraestructura separados de Kiwi
    When se verifica imagen, migración, backup restaurado y canary autorizado
    Then el cierre identifica cada gate por entorno y mantiene abierto todo gate sin evidencia
```

Paridad fiscal receipt/cancel: cada recurso mantiene un comando durable y claim exclusivo antes del PAC; `unknown` bloquea reemision y exige reconciliacion explicita. Cancel conserva hash de motivo/sustitucion para detectar conflicto; ninguna respuesta timeout declara estado fiscal final.

### A07 — borrador de partner sin efectos operativos

Dada una configuración guardada de DiDi o Rappi pendiente de validación, al editar campos
con secretos vacíos se conservan las claves y nunca se devuelven al navegador. Al intentar
simular un pedido mediante API, se obtiene 409 `integration_pending_validation` y no se crea
ningún pedido. Guardar o simular no activa la integración.

### A07 — simuladores históricos con aislamiento

Con dos organizaciones configuradas para un proveedor, el administrador A puede generar
un pedido de prueba sólo en su tienda autorizada. Indicar una tienda de B o una sucursal de B
produce 403 y conserva pedidos y bitácoras. Un borrador sin claves indica que no hay secretos
guardados. Esto no certifica el contrato externo de DiDi/Rappi.

Una simulación DiDi/Rappi sin mapeo previo devuelve 409 y conserva cero mapeos, incluso
si los artículos recibidos son inválidos. La vinculación se configura en su formulario.

### Catálogo de motivos de merma por organización

A y B pueden crear el mismo código con nombres propios. Cada listado devuelve únicamente
los motivos propios. B no puede editar ni inactivar un motivo de A; el rechazo conserva
todos sus campos. A mantiene la capacidad de editar su motivo.

Una merma de B no puede confirmarse ni revertirse con un actor de A aunque éste conozca su ID.
El listado sin sucursal tampoco amplía el conjunto fuera de la organización autorizada. Los
movimientos creados por confirmación o reversión conservan la organización de la merma.

Al solicitar compras sugeridas sin una base trazable de consumo, el sistema devuelve una lista
vacía y no inventa proveedor, costo o cantidad. Un historial de compra sólo prueba costo previo,
no demanda futura.

Las lecturas administrativas de A y B para catálogo, categorías, existencias, kardex, almacenes,
unidades, insumos, usuarios, roles y sucursales sólo devuelven el tenant del actor. Una proyección
interna sin organización ni sucursal activa explícita falla cerrada; indicar una sucursal de B desde
A se rechaza antes de ejecutar la consulta. El estado de bootstrap de A no contiene conteos ni la
sucursal principal de B.


### Reconciliación fiscal de receipt y cancel

Dado un receipt o una cancelación cuyo proveedor respondió pero falló el commit local, cuando el operador repite el comando, el sistema rechaza el nuevo envío y conserva `unknown`. Cuando ejecuta la reconciliación y el recurso conocido confirma el estado esperado, el sistema registra el efecto local una vez y el siguiente intento devuelve el resultado confirmado sin llamar al proveedor. Si la consulta expira, no hay confirmación local ni reenvío.

### Comentarios, offline y recetas fuera de alcance

Los comentarios creados en sucursales A y B sólo aparecen a sus respectivos administradores;
solicitar branch ajena devuelve 403. Un grant offline no acepta una organización distinta a la
organización persistida del actor. Solicitar costeo AI de receta devuelve 409 explícito y no
procesa inventario, porque recetas por gramos están fuera del producto SaaS.

### Inventario administrativo por tenant

A y B pueden crear el mismo código de unidad y SKU. Sus listados de unidades, insumos, stock y
almacenes sólo muestran recursos propios; consultar el kardex con item ajeno devuelve vacío. A no
puede editar unidad/insumo de B ni crear un insumo que referencie unidad de B.

### Roles, permisos y almacenes por tenant

A no puede renombrar, eliminar ni sustituir permisos de un rol de B aunque conozca su ID; el rol y
sus permisos quedan intactos. B conserva las guardas persistidas de su rol owner para alcance,
permisos y eliminación. A puede administrar su propio almacén, pero no actualizar el de B ni crear
uno para una sucursal de B. Crear un segundo almacén en la misma sucursal se rechaza y una sucursal
activa conserva su almacén activo.


### Aislamiento de autofactura por clave pública

Dado que A y B tienen el mismo folio, cuando el comensal usa la clave pública activa de A, el portal sólo muestra y emite el pedido de A. Una clave inválida devuelve ticket no encontrado y no expone datos fiscales o importes. Si cambia el RFC de un pedido ya facturado, el portal rechaza el conflicto sin un segundo timbrado.


### Aislamiento de importación histórica

Dadas organizaciones A y B con códigos de catálogo iguales, cuando cada administrador importa su manifiesto en su sucursal, ambos batches y recursos quedan en su propia organización. B no puede listar, leer registros, completar ni agregar filas al batch de A; el rechazo conserva los registros y catálogos de ambos.

### Selectores de categoría aislados

Dadas organizaciones A y B con categorías, productos y selectores de igual nombre, cuando B usa
el ID de categoría, grupo, opción o asociación de A, la API responde 403 o 404 y conserva la
configuración de A. A puede consultar su cobertura, crear una opción y asociar su producto propio.

### Admin AI aislado por tenant

Dadas organizaciones A y B con catálogos distintos, cuando cada administrador solicita una propuesta,
el contexto enviado al proveedor contiene sólo los recursos de su organización. B no puede leer,
revisar ni continuar una conversación o propuesta de A; el rechazo no cambia la propuesta de A.
