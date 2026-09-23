# BDD-FEAT-191 Personalización visible y edición del carrito móvil

Estado: criterios aprobados MOB-CART-001, implementados localmente. Evidencia y límites por caso en el reporte del incremento; sin certificación productiva.

```gherkin
@PRD-FR-061 @mobile-web @cart
Feature: Reconocer y editar la personalización antes de enviar el pedido
  @BDD-SC-930
  Scenario: El menú distingue productos personalizables
    Given un producto con opciones comerciales seleccionables y otro sin ellas
    When se muestra el menú
    Then sólo el primero invita Personaliza tu producto
    And grupos vacíos o únicamente comentarios no generan una invitación falsa
    And tocar la invitación abre su detalle sin agregar una unidad

  @BDD-SC-931
  Scenario: Agregado rápido respeta opciones opcionales y obligatorias
    Given un producto con extras opcionales y otro con mínimo de selección obligatorio
    When el comensal usa el signo más
    Then el primero se agrega sin selección con estado Sin personalizar
    And el segundo abre el detalle sin agregarse hasta completar sus requisitos

  @BDD-SC-932
  Scenario: Opciones gratuitas también son personalización
    Given Capuchino de 55 pesos con azúcar mascabado sin cargo
    When se selecciona sólo azúcar mascabado
    Then Tu Pedido muestra la selección y Editar personalización
    And el total es 55 pesos y no muestra Sin personalizar

  @BDD-SC-933
  Scenario: Editar sustituye sólo la línea elegida
    Given dos líneas del mismo producto con preparaciones diferentes
    When se abre una línea desde su nombre, imagen o acción de edición
    Then aparecen su cantidad, notas y opciones actuales
    When se guarda una selección distinta
    Then se reemplaza sólo esa línea con el mismo cart_id y posición
    And no se agrega otra unidad ni se fusionan líneas por efecto de editar

  @BDD-SC-934
  Scenario: Cancelar conserva carrito y captura del checkout
    Given un carrito con datos de contacto, modalidad y dirección capturados
    When el comensal cambia cantidad, notas y opciones en el editor y cancela
    Then la línea y sus importes originales permanecen intactos
    And al regresar a Tu Pedido conserva datos, foco y posición útil

  @BDD-SC-935
  Scenario: Guardar recalcula recargos y cantidad exactamente
    Given Capuchino de 55 pesos y leche de aceituna de 25 pesos
    When se guarda una unidad con ese extra
    Then la línea vale 80 pesos
    When se guardan dos unidades con ese extra
    Then la línea vale 160 pesos
    When se retira el extra de ambas
    Then la línea vale 110 pesos y vuelve a Sin personalizar
    And subtotal y total siguen las reglas existentes y Python valida el envío

  @BDD-SC-936
  Scenario: Catálogo modificado requiere revisión explícita
    Given una opción guardada desapareció o cambió de precio
    When se abre la edición con el catálogo efectivo actual
    Then se informa el cambio y no se transforma silenciosamente el carrito
    And una opción inválida o un mínimo pendiente bloquea Guardar
    And un fallo de carga permite reintentar sin borrar la línea

  @BDD-SC-937
  Scenario: Persistencia y contexto impiden aplicar un borrador a otra sucursal
    Given un borrador abierto para una línea de una sucursal
    When cambia la sucursal o desaparece la línea antes de Guardar
    Then el borrador no modifica ni recrea líneas en el contexto nuevo
    And un guardado válido se recupera al recargar sólo dentro de su organización y sucursal

  @BDD-SC-938
  Scenario: Editar no duplica un envío incierto
    Given un envío está en curso o su resultado sigue siendo incierto
    When el comensal intenta editar y reenviar el carrito
    Then se resuelve primero el envío anterior con su payload y clave originales
    And abrir o guardar un editor no genera una nueva intención ni cambia esa clave
    And un pedido ya confirmado no se modifica desde este editor

  @BDD-SC-939
  Scenario: Controles independientes y acceso por teclado
    Given el menú y Tu Pedido a 360 o 390 píxeles de ancho
    When se usa teclado para abrir, guardar o cancelar una edición
    Then el foco permite completar la tarea y regresa al activador
    And los botones de cantidad, favoritos y papelera no abren el editor
    And un producto sin modificadores permite editar cantidad y notas sin invitación falsa
```
