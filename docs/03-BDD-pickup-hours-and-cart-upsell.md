# BDD — Restricción de Horarios de Recolección y Fotos en Upsell del Menú Digital

## Feature: Restricción de Horarios de Recolección en Menú Digital
Como comensal que realiza un pedido para recoger
Quiero que el selector de horario solo me muestre las horas disponibles dentro del horario de atención del restaurante
Para no seleccionar un horario en que la sucursal se encuentre cerrada

### Escenario: BDD-SC-960 Selección de horarios para día futuro con horario acotado
- **Dado** que la sucursal tiene configurado el día Lunes con apertura a las 16:00 y cierre a las 18:00
- **Cuando** el comensal selecciona el día Lunes en el selector de recolección del carrito
- **Entonces** las únicas opciones disponibles en el selector de hora corresponden al intervalo entre 16:00 y 18:00
- **Y** no se muestra ninguna hora fuera de dicha ventana operativa.

### Escenario: BDD-SC-961 Selección de horarios para el día de hoy
- **Dado** que la sucursal tiene configurado el día de hoy con apertura a las 16:00 y cierre a las 22:00
- **Cuando** la hora actual es antes de la apertura (ej. 10:00)
- **Entonces** el primer slot seleccionable es la hora de apertura (16:00)
- **Y** cuando la hora actual es durante el horario de servicio (ej. 16:20)
- **Entonces** los slots anteriores a la hora actual más el margen de preparación quedan excluidos.

### Escenario: BDD-SC-962 Ajuste automático al cambiar de día
- **Dado** que el comensal tiene seleccionada una hora que no existe en el horario del nuevo día elegido
- **Cuando** el comensal hace clic en otro día con horario distinto
- **Entonces** la hora seleccionada se actualiza automáticamente al primer slot permitido de ese día.

---

## Feature: Fotografías en Sugerencias Complementarias del Carrito
Como comensal en la pantalla de pago del carrito
Quiero ver la foto real del producto en las sugerencias complementarias
Para tener mayor certeza visual y apetito sobre lo que agrego a mi orden

### Escenario: BDD-SC-963 Producto sugerido con fotografía configurada
- **Dado** que un producto sugerido cuenta con `image_url` en el catálogo del restaurante
- **Cuando** se despliega la sección de "Sugerencias para tu orden"
- **Entonces** la tarjeta muestra la imagen real del platillo (`cart-upsell-card-img`)
- **Y** no muestra el icono temático por defecto.

### Escenario: BDD-SC-964 Fallback a icono cuando el producto no tiene fotografía
- **Dado** que un producto sugerido no cuenta con fotografía o su carga falla en el cliente
- **Cuando** se renderiza la tarjeta en la sección de sugerencias
- **Entonces** se muestra el icono temático representativo de su categoría con su respectivo gradiente.
