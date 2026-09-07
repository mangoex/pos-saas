# BDD - Módulos operativos de sucursal dentro del POS

## BDD-FEAT-052 Administración operativa completa sin acceso corporativo

```gherkin
@PRD-FR-505 @PRD-FR-518 @PRD-FR-519 @pos @branch @frontend
Feature: El Supervisor abre los módulos operativos de su sucursal dentro del POS

  @BDD-SC-136
  Scenario: Supervisor ve Administración en la navegación POS
    Given una sesión canónica con pos.operate y branch.admin.access
    When PosLayout renderiza la navegación
    Then muestra la opción Administración con el mismo estilo de las opciones del POS
    And la opción abre /pos/administration sin abandonar PosLayout

  @BDD-SC-137
  Scenario: Cajero no obtiene acceso administrativo
    Given una sesión canónica de Cajero sin branch.admin.access
    When PosLayout renderiza la navegación
    Then no muestra la opción Administración
    And las rutas /pos/administration y sus descendientes rechazan el acceso directo

  @BDD-SC-138
  Scenario: El centro contiene sólo módulos operativos permitidos
    Given un Supervisor dentro del centro de administración
    Then ve Productos y recetas, Insumos, Proveedores, Compras y Producción
    And ve Mermas, Traspasos y Conteos físicos
    And no ve Sucursales, Usuarios, Roles ni Personal de sucursal como tarjetas

  @BDD-SC-139
  Scenario: Todas las tarjetas conservan la experiencia visual del POS
    Given un Supervisor en el centro de administración
    When abre cualquiera de las ocho tarjetas
    Then la vista conserva sidebar, colores, espaciado y navegación de regreso del POS
    And no navega a /admin ni usa window.location hacia el administrador corporativo

  @BDD-SC-140
  Scenario: Cada resumen usa la sucursal canónica
    Given un Supervisor asignado a la sucursal A
    When consulta proveedores, compras, producción, mermas, traspasos o conteos
    Then cada petición dependiente de sucursal usa active_branch.id de la sesión canónica
    And no acepta una sucursal diferente desde localStorage ni desde la URL

  @BDD-SC-141
  Scenario: Los módulos conservan permisos granulares
    Given una cuenta con branch.admin.access pero sin el permiso de un módulo
    When intenta abrir directamente ese módulo
    Then PermissionRoute rechaza la ruta
    And el backend conserva su propia validación de permiso y alcance

  @BDD-SC-142
  Scenario: Proveedores es consulta y no administración central
    Given un Supervisor con purchases.read
    When abre Proveedores
    Then consulta proveedores y presentaciones autorizados para su operación
    And no puede crear ni modificar el catálogo central de proveedores

  @BDD-SC-143
  Scenario: Una base sin la migración de permisos mantiene el acceso cerrado
    Given producción permanece en 0023_physical_counts
    When una Supervisora inicia sesión
    Then la sesión no inventa branch.admin.access en el cliente
    When operación aplica alembic upgrade head hasta 0024_branch_admin_scope
    And la Supervisora inicia una sesión nueva
    Then la sesión canónica contiene branch.admin.access y el menú puede mostrarse
```
