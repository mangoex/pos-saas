# BDD - Checador de personal

## BDD-FEAT-073 Entradas y salidas por código

```gherkin
@PRD-FR-712 @attendance @pos @staff
Feature: Personal registra entrada y salida desde el POS

  @BDD-SC-249
  Scenario: Primera checada válida queda pendiente en azul
    Given un POS autenticado con sucursal activa y un Usuario activo con clave "A7K204"
    When el empleado captura su clave en Checador
    Then el backend registra la hora UTC y el día local de la sucursal
    And el reporte muestra una sola checada azul
    And la auditoría no copia código ni nombre del empleado

  @BDD-SC-250
  Scenario: Segunda checada completa entrada y salida
    Given una persona con una checada en el día local de la sucursal
    When captura la misma clave por segunda vez
    Then el reporte muestra la primera checada verde como Entrada
    And muestra la segunda roja como Salida
    And una tercera checada del mismo día se rechaza sin insertar

  @BDD-SC-251
  Scenario: Código inválido, inexistente o inactivo falla cerrado
    Given una clave que no tiene seis caracteres alfanuméricos o no identifica a una persona activa
    When se intenta registrar una checada
    Then el POS muestra un error de código no válido
    And no se crea checada ni confirmación visible

  @BDD-SC-252
  Scenario: Administrador asigna identificadores laborales únicos entre catálogos
    Given los catálogos corporativos de Usuarios y Repartidores
    When un Administrador crea o edita un código
    Then el código se normaliza a seis caracteres alfanuméricos en mayúsculas
    And queda reservado para una sola persona sin sustituir su UUID técnico
    And un código ya usado en cualquiera de los dos catálogos se rechaza atómicamente
    And todo Usuario o Repartidor nuevo requiere su código
    And los registros heredados sin código se conservan sin inventar valores
    And una edición rechazada conserva íntegros el rol y los demás datos del Usuario
    And una migración correctiva restaura el rol de la cuenta superadministradora canónica si una
    versión anterior lo eliminó

  @BDD-SC-253
  Scenario: Reporte filtra por código, periodo y sucursal autorizada
    Given un Supervisor con branch.staff.read y un Administrador corporativo
    When consultan por código, día o mes y sucursal
    Then el Supervisor sólo recibe checadas de su sucursal
    And el Administrador puede consultar todas o una sucursal activa
    And día y mes simultáneos se rechazan como filtro ambiguo

  @BDD-SC-254
  Scenario: Menú y diálogo conservan la operación POS
    Given una sesión con pos.operate
    When observa el menú lateral
    Then Checador aparece entre Pedidos y Administración
    And al abrirlo ve la hora actual y un único campo para la clave
    And cerrar o registrar no navega fuera de la venta actual
```
