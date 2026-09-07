# BDD - Administracion de usuarios y roles

## BDD-FEAT-029 Usuarios y roles operativos

```gherkin
@PRD-FR-505 @PRD-FR-507 @security @admin @phase1
Feature: Gestion basica de usuarios y roles

  @BDD-SC-043
  Scenario: Crear rol operativo
    Given existe la organizacion Kiwi Restaurante
    When el administrador crea un rol con nombre y alcance
    Then el sistema conserva el rol
    And evita duplicar otro rol con el mismo nombre
    And registra auditoria del alta

  @BDD-SC-044
  Scenario: Invitar usuario operativo
    Given existe la organizacion Kiwi Restaurante
    When el administrador registra nombre y correo del usuario
    Then el sistema crea el usuario en estado invitado
    And evita duplicar el mismo correo
    And registra auditoria del alta

  @BDD-SC-045
  Scenario: Asignar rol a usuario
    Given existe un usuario invitado
    And existe un rol operativo
    When el administrador asigna el rol al usuario
    Then el sistema conserva la relacion usuario-rol
    And permite alcance corporativo o de sucursal
    And registra auditoria de la asignacion

  @BDD-SC-057
  Scenario: Bloquear accion sensible sin permiso
    Given existe un usuario con rol Cajero en Sucursal Piloto
    And el rol no tiene permiso de ajuste de inventario
    When el usuario intenta registrar un movimiento de inventario
    Then el sistema rechaza la operacion por falta de permiso
    And registra auditoria del intento denegado
    When el administrador corporativo registra el mismo movimiento
    Then el sistema permite la operacion

  @BDD-SC-059
  Scenario: Iniciar sesion como superadmin y crear administrador
    Given existe la cuenta superadmin de Humanio para Kiwi Restaurante
    When el superadmin inicia sesion con correo y contraseña
    Then el sistema devuelve una sesion firmada
    And muestra la consola Admin autenticada
    And habilita el diagnostico tecnico superior solo para superadmin
    When el superadmin crea una cuenta de administrador con contraseña temporal
    Then el nuevo usuario queda activo
    And puede iniciar sesion con su contraseña temporal
    And el alta produce auditoria

  @BDD-SC-060
  Scenario: Entrar al panel visual segun rol
    Given existe una cuenta activa con rol administrativo
    When el usuario abre Admin sin sesion local
    Then el sistema muestra una pantalla de bienvenida con login
    And no muestra el diagnostico tecnico superior
    When el usuario inicia sesion
    Then el sistema muestra un panel visual operativo con catalogos, inventario, usuarios y roles
    And muestra el rol de la cuenta en la sesion activa

  @BDD-SC-064
  Scenario: Acceder a Admin y POS por permisos
    Given existe un usuario Cajero activo con permisos POS y sin permisos administrativos
    And puede existir un rol legacy `Caja` con el mismo perfil operativo
    When el usuario inicia sesion
    Then el dialogo unico identifica la cuenta
    And el sistema permite entrar al POS
    And no permite entrar al panel Admin administrativo
    And configura la sucursal asignada y la caja predeterminada `CAJA-01`
    Given existe un administrador corporativo activo
    When el administrador inicia sesion
    Then el dialogo unico identifica la cuenta
    And el sistema permite entrar al panel Admin
    And permite entrar al POS si necesita operar caja

  @BDD-SC-065
  Scenario: Consultar dashboard por alcance
    Given existen ventas, pagos y aperturas de caja en Sucursal Piloto
    When el administrador corporativo consulta el dashboard
    Then ve el consolidado operativo autorizado
    When un usuario con alcance de sucursal consulta el dashboard
    Then ve solo la informacion de su sucursal si tiene permiso `dashboard.read`
    And el sistema rechaza usuarios sin permiso `dashboard.read`
```
