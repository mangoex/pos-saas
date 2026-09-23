# BDD-FEAT-193 — Aviso de tolerancia para recoger

```gherkin
@PRD-FR-022 @pickup
Feature: Configurar tolerancia informativa por sucursal
  @BDD-SC-944
  Scenario: Guardar y recuperar minutos
    Given un administrador autorizado en Config móvil
    When guarda 30 en Recoger encima de Comer en el Establecimiento
    Then al recargar conserva 30 y queda auditoría de sucursal
    And la etiqueta y el valor de Recoger son legibles sobre la tarjeta blanca del admin
    And el cliente que elige Recoger ve 30 minutos después de su hora programada
  @BDD-SC-945
  Scenario: Eliminar o conservar configuración opcional
    Given una sucursal configurada con 30 minutos
    When borra el campo y guarda
    Then el valor queda null y desaparece el aviso
    And omitir el campo en otra actualización conserva su valor anterior
  @BDD-SC-946
  Scenario: Validación y aislamiento
    Given solicitudes con valores inválidos o una sucursal ajena
    When intentan modificar la tolerancia
    Then se rechazan sin escritura ni auditoría de éxito
  @BDD-SC-947
  Scenario: Modalidades y sucursales
    Given una sucursal con 1 minuto y otra sin configuración
    When cambio de sucursal o modalidad
    Then el aviso refleja la sucursal y sólo aparece al Recoger
    And no cambia precio, calendario, estado ni pedidos históricos
```
