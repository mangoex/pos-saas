# BDD - Administración operativa por sucursal

## BDD-FEAT-050 Centro administrativo operativo de sucursal

```gherkin
@PRD-FR-505 @PRD-FR-508 @PRD-FR-509 @PRD-FR-517 @PRD-FR-518 @PRD-FR-519 @PRD-ROLE-002 @admin @branch
Feature: Un Supervisor de sucursal administra su sucursal sin ser administrador corporativo

  @BDD-SC-118
  Scenario: Supervisor autenticado obtiene sesión y contexto de su sucursal
    Given un Supervisor de sucursal autenticado con token válido
    When solicita GET /api/v1/auth/session
    Then recibe su perfil, roles, permisos y alcance de sucursal
    And active_branch contiene su sucursal, unidad de negocio, razón social y almacén
    And no recibe credenciales ni información sensible

  @BDD-SC-119
  Scenario: Cajero no obtiene capacidad de administración de sucursal
    Given un Cajero autenticado
    When solicita GET /api/v1/branch-administration/context
    Then recibe 403 permission_denied
    And no obtiene branch.admin.access ni catalog.branch.manage

  @BDD-SC-120
  Scenario: Supervisor que envía branch_id de otra sucursal recibe rechazo
    Given un Supervisor de sucursal asignado a la sucursal A
    When envía branch_id de la sucursal B a un endpoint de branch-administration
    Then recibe 403 permission_denied
    And no se filtra información de la sucursal B

  @BDD-SC-121
  Scenario: Administrador corporativo conserva selección de una sucursal activa autorizada
    Given un Administrador corporativo autenticado
    When solicita GET /api/v1/auth/session con branch_id de una sucursal activa
    Then scope.level es organization
    And allowed_branch_ids contiene las sucursales activas autorizadas
    And active_branch resuelve la sucursal solicitada

  @BDD-SC-122
  Scenario: Supervisor consulta catálogos centrales pero sólo modifica excepciones de su sucursal
    Given un Supervisor de sucursal autenticado
    When solicita GET /api/v1/branch-administration/catalog/products
    Then recibe productos centrales con precio vigente y disponibilidad efectiva
    And un producto sin precio aparece como no vendible
    And la ausencia de excepción indica herencia central
    When modifica la disponibilidad de un producto de su sucursal
    Then se actualiza únicamente branch_product_availability de su sucursal
    And se registra auditoría con valor anterior y nuevo
    And no se modifican products, categories ni price_versions

  @BDD-SC-123
  Scenario: Supervisor consulta únicamente el personal asignado a su sucursal
    Given un Supervisor de sucursal autenticado
    When solicita GET /api/v1/branch-administration/staff
    Then recibe sólo los usuarios con user_roles.branch_id igual a su sucursal
    And no recibe credenciales
    And no puede modificar usuarios, roles ni permisos

  @BDD-SC-124
  Scenario: La jerarquía distingue restaurante, panadería, producción y otros sin duplicar catálogos
    Given la jerarquía organization → legal_entity → business_unit → branch → warehouse
    When se crea una unidad de negocio con unit_type bakery o production
    Then se acepta el tipo y se conserva la jerarquía
    And los catálogos centrales no se duplican por sucursal
    And cada sucursal conserva una unidad de negocio, una razón social y un almacén

  @BDD-SC-385
  Scenario: Administrador configura domicilio, entre calles y coordenadas GPS de sucursal
    Given un Administrador corporativo autenticado
    When actualiza una sucursal con calle, número, colonia, CP, ciudad, entre calles y coordenadas GPS
    Then la sucursal persiste los datos de domicilio y geolocalización
    And la auditoría registra la actualización de la sucursal

  @BDD-SC-381
  Scenario: Consulta pública de sucursales con cálculo de cercanía por coordenadas
    Given sucursales activas registradas con coordenadas de latitud y longitud
    When un cliente o app móvil consulta las sucursales enviando latitud y longitud
    Then el backend devuelve las sucursales con la distancia calculada ordenada de la más cercana a la más lejana
```
