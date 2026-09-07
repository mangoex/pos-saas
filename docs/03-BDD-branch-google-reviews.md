# BDD - Configuración de Google Reviews por Sucursal y Smart Rating de Comensales

## BDD-FEAT-102 Configuración y Captura de Reseñas de Google por Sucursal

```gherkin
@PRD-FR-734 @branches @admin @google_reviews
Feature: Configuración de enlace de Google Reviews por sucursal en Backoffice

  @BDD-SC-473
  Scenario: Guardar y editar enlace de Google Reviews por sucursal
    Given un usuario administrador autenticado con permiso "admin.manage" o "catalog.manage"
    When actualiza la sucursal "Sucursal Principal" ingresando la URL de Google Reviews "https://g.page/r/AbCdEfGhIjK/review"
    Then el sistema almacena el campo "google_review_url" asociado a la sucursal
    And al consultar el listado de sucursales en el panel administrativo se retorna la URL configurada

  @BDD-SC-474
  Scenario: Retorno de google_review_url en endpoint público de sucursales
    Given una sucursal activa con "google_review_url" configurado
    When un comensal anónimo consulta el endpoint público "/api/v1/public/branches"
    Then la sucursal incluye el atributo "google_review_url" con su valor correspondiente
    And si la sucursal no tiene URL configurada, el atributo retorna null sin generar error

  @BDD-SC-475
  Scenario: Smart Rating de 1 a 5 Estrellas en Confirmación de Pedido
    Given un comensal que ha finalizado un pedido en mobile-web para una sucursal con Google Reviews
    When el comensal selecciona 5 estrellas en el modal de confirmación
    Then la interfaz muestra el botón para abrir el enlace de Google Reviews de la sucursal
    When el comensal selecciona 2 estrellas en el modal de confirmación
    Then la interfaz muestra un cuadro de comentarios interno para capturar feedback privado sin redirigir a Google
```
