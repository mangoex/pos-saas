# TDD-TS-291 Personalización y reemplazo seguro de líneas móviles

Estado: cobertura implementada con ejecución focal local. Cubre BDD-SC-930..939; evidencia y límites en `reports/mobile-cart-personalization-2026-09-23.md`.

| Caso | Tipo y prueba prevista | Resultado exigido |
| --- | --- | --- |
| 930/931 | Helper + componente: catálogo vacío, comentarios, extra gratis, obligatorio | Señal y + coherentes; no agregados por propagación |
| 932/935 | Función pura de importes y presentación; base 5500, extra 2500/0, cantidad 1/2 | 5500/8000/11000/16000 exactos; gratis visible; reglas promo existentes preservadas |
| 933 | Reemplazo por cart_id con dos líneas del mismo producto y opciones distintas | Sólo una línea cambia, identidad/posición estables, sin mutación del array original ni duplicados |
| 933/934 | Interacción modal: precarga, alternar, guardar, cancelar/X/Escape/fondo | Guardar sustituye; cancelar conserva línea; reutilizar modal no filtra otro borrador |
| 934 | Integración App/CartDrawer: contacto/dirección/cupón/modalidad escritos antes de editar | Guardar/cancelar no pierden datos del checkout ni disparan submit |
| 936 | Integración catálogo: opción retirada, producto inactivo, recargo cambiado, error de red | Mensaje explícito, revisión y guardado bloqueado cuando corresponde; carrito intacto |
| 937 | Persistencia + carrera: recargar, cambiar sucursal, borrar línea mientras se edita | Namespace correcto, borrador invalidado, callback viejo no recrea línea |
| 938 | Contrato checkout: solicitud en curso, timeout, 409, éxito persistido | No doble intención ni nueva clave por editar; recuperación del resultado incierto verificada |
| 939 | Navegador y accesibilidad: táctil/teclado, 360/390 px y escritorio | Un modal activo, foco correcto, acciones aisladas, CTA y opciones legibles |

Fixtures: producto A sin opciones; B con extras opcionales de 2500 y 0; C con grupo obligatorio;
D con sólo comentarios; E con grupo vacío. Dos líneas B con diferentes notas/opciones; cantidad 2;
catálogo actualizado y una sucursal ajena. No usar datos reales de contacto ni servicios productivos.

Archivos implementados:
`tests/frontend/test_mobile_cart_personalization.mjs` para funciones/contratos semánticos y
`tests/browser/test_mobile_cart_personalization.mjs` para interacción real mediante Browser y `mobile-cart-fixture.mjs`, siguiendo el harness
disponible. No sustituir los casos de comportamiento por regex sobre el código fuente.
Añadir el test focal al gate frontend de CI; el archivo browser requiere un runner real configurado.

Reusar regresiones `test_mobile_web_order_flow.mjs`, `test_mobile_order_modifier_labels.mjs` y
`test_mobile_voice_order.mjs` para captura existente; verificar pruebas backend de intención pública
cuando se cruce su contrato. Ejecutar typecheck y build de @restaurantos/mobile-web y diff --check.
Obtener RED por ausencia de edición antes de implementar, GREEN focal, auditoría R3 independiente
y CI aplicable. PostgreSQL sólo si la implementación activa cambios de su autoridad/persistencia.

Criterio de terminado: cada escenario con evidencia real, previsualización y total de backend
coherentes, checkout conservado y ningún hallazgo bloqueante de auditoría. Declarar pruebas omitidas
o infraestructura faltante; no marcar esta suite Probado por haber redactado el plan.
