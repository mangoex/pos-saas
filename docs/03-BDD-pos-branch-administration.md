# BDD - Frontend de administración operativa por sucursal en el POS

## BDD-FEAT-051 Centro administrativo de sucursal dentro del POS

```gherkin
@PRD-FR-505 @PRD-FR-508 @PRD-FR-517 @PRD-FR-518 @PRD-FR-519 @pos @branch @frontend
Feature: El Supervisor administra su sucursal dentro del POS sin entrar al admin corporativo

  @BDD-SC-125
  Scenario: La sesión canónica reemplaza los permisos guardados localmente
    Given un Supervisor que abre el POS con un token válido
    When el frontend llama a GET /api/v1/auth/session
    Then obtiene usuario, roles, permisos, alcance y active_branch desde PostgreSQL
    And no confía en el objeto user de localStorage ni en is_superadmin
    And el active_branch.id reemplaza cualquier branch_id local para scope branch

  @BDD-SC-126
  Scenario: Supervisor ve Administración dentro del POS
    Given un Supervisor con permiso branch.admin.access
    When el POS carga la sesión canónica
    Then el menú Administración es visible
    And las tarjetas de productos, insumos, sucursal activa y personal son navegables dentro del layout POS

  @BDD-SC-127
  Scenario: Cajero no ve ni abre Administración
    Given un Cajero sin branch.admin.access
    When el POS carga la sesión canónica
    Then el menú Administración no es visible
    And si escribe /pos/administration directamente recibe acceso denegado o redirección a /pos/pos

  @BDD-SC-128
  Scenario: Ninguna tarjeta abandona el layout POS
    Given un Supervisor en el centro de administración
    When selecciona cualquier tarjeta habilitada
    Then la navegación usa Link o useNavigate dentro de PosLayout
    And no hay enlaces a /admin ni window.location hacia módulos corporativos

  @BDD-SC-129
  Scenario: La disponibilidad local hereda, cambia y vuelve a heredar
    Given un Supervisor con catalog.branch.manage en su sucursal
    When consulta los productos del catálogo
    Then ve la disponibilidad efectiva y la fuente (central o excepción local)
    When marca un producto como no disponible
    Then se actualiza sólo branch_product_availability de su sucursal
    When vuelve a heredar
    Then se elimina la excepción local y la disponibilidad vuelve al valor central

  @BDD-SC-130
  Scenario: El personal de sucursal es sólo lectura
    Given un Supervisor con branch.staff.read
    When consulta el personal de su sucursal
    Then ve nombre, correo, estado y roles informativos
    And no hay botones para crear, editar ni eliminar usuarios
    And la administración de cuentas corresponde al administrador corporativo

  @BDD-SC-131
  Scenario: La configuración usa la sucursal canónica
    Given un Supervisor con scope branch
    When abre la configuración del POS
    Then la sucursal mostrada es el active_branch de la sesión canónica
    And el control de sucursal no permite cambiar la asignación
    And el identificador de caja conserva su configuración local

  @BDD-SC-132
  Scenario: Los modificadores envían Bearer mediante fetchApi
    Given un Supervisor operando el POS
    When selecciona un producto con modificadores
    Then la petición de modificadores usa fetchApi con Authorization Bearer
    And no usa un fetch directo sin cabecera de autenticación

  @BDD-SC-133
  Scenario: Una cuenta sin permiso para operar no entra al POS
    Given una cuenta autenticada con permisos que no incluyen pos.operate
    When intenta abrir cualquier ruta del POS
    Then la aplicación muestra acceso denegado antes de renderizar PosLayout
    And no permite operar caja ni abrir la administración de sucursal

  @BDD-SC-134
  Scenario: Una sucursal local obsoleta no gobierna la operación
    Given una sesión branch cuyo localStorage contiene otra sucursal
    When GET /api/v1/auth/session devuelve el active_branch autorizado
    Then el frontend reemplaza la sucursal local con active_branch.id
    And las operaciones posteriores usan únicamente la sucursal canónica

  @BDD-SC-135
  Scenario: Una selección corporativa se valida antes de aplicarse
    Given una sesión organization con varias allowed_branch_ids
    When el usuario selecciona otra sucursal en Configuración
    Then el frontend solicita GET /api/v1/auth/session con esa branch_id
    And sólo aplica la selección si la respuesta confirma el mismo active_branch.id
    And si la validación falla conserva la sesión canónica anterior
```
