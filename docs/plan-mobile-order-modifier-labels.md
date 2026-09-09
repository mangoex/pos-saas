# Etiquetas de comentarios y modificadores en pedidos móviles

Corrección R3 acotada a la presentación de instrucciones operativas. El pedido móvil ya conserva
las selecciones en `selected_modifiers`; la API usa el snapshot canónico `option_name`,
`kitchen_text` y `price_delta_cents`, mientras Admin móvil y el historial POS consumen alias
distintos y pueden renderizar sólo `+`. No cambia alcance comercial, persistencia, estados,
permisos ni esquema; PRD y SDD permanecen vigentes. Se aclaran BDD-SC-733,
BDD-SC-LITE-014 y TDD-TS-233.

## Criterios de aceptación

1. `Sin azúcar`, `Con todo`, `Sin picante` y cualquier otra selección válida muestran una etiqueta
   en Admin móvil y en el detalle POS antes y después de aceptar el pedido.
2. La presentación prioriza la instrucción operativa `kitchen_text`, continúa con
   `option_name` y conserva compatibilidad con `name` y `text` de snapshots históricos.
3. El importe usa `price_delta_cents` y acepta `price_cents` para historia previa; cero no agrega
   un cargo visual.
4. Un snapshot incompleto muestra una etiqueta de contingencia y nunca un signo `+` aislado.
5. `line_notes` sigue siendo una nota del producto separada y no se confunde con modificadores.
6. La solución no reescribe pedidos históricos ni altera la transición pendiente → aceptado.

## Plan y tareas

1. Añadir una prueba RED ejecutable con snapshots canónicos, históricos, texto libre, precio cero
   y forma incompleta.
2. Crear un formateador compartido y tipado en `packages/api-client` para etiqueta y precio.
3. Adoptar el formateador en `MobileOrderDetailModal` y en el detalle de historial POS.
4. Fortalecer la prueba semántica para demostrar que ambas vistas usan el contrato compartido.
5. Ejecutar la prueba focal, typecheck de Admin/POS, builds de ambas aplicaciones,
   `git diff --check` y trazabilidad; CI completo queda como gate de integración.
6. Solicitar auditoría Sol independiente sobre corrección, compatibilidad histórica, ausencia de
   mutación de snapshots y suficiencia de las pruebas.

## Reversibilidad y operación

La reversión es sólo de código frontend y no requiere migración. Los snapshots existentes conservan
su forma original. Durante un canary autorizado, el operador debe poder responder: ¿qué texto
recibieron Admin, POS y KDS para la misma selección?, ¿la instrucción permanece después de aceptar
el pedido?, ¿alguna selección produjo una etiqueta vacía? La comprobación productiva y el redeploy
requieren autorización separada.

## Evidencia esperada

- prueba unitaria del formateador con el payload real de la API;
- prueba semántica de consumo en Admin móvil y POS;
- prueba API focal del snapshot pendiente y aceptado;
- typecheck y build de las dos aplicaciones afectadas;
- revisión Sol sin hallazgos bloqueantes o correcciones incorporadas y verificadas.

## Cierre local

- RED: la regresión falló con `the shared modifier presentation formatter must exist` antes de
  incorporar el formateador.
- GREEN: pasó la regresión de etiquetas, el test existente del monitor móvil, el caso API
  pendiente → aceptado, Ruff focal, typecheck y build de Admin/POS, trazabilidad y
  `git diff --check`.
- La prueba nueva forma parte de `test:frontend-semantic`, que es el gate frontend configurado en CI.
- Sol reauditoró el diff después de corregir la cobertura API, el cableado de CI y los prefijos `+`
  decorativos; no quedaron hallazgos bloqueantes ni P1/P2.
- CI completo, QA visual y canary productivo no se ejecutaron y permanecen como evidencia de
  integración/release, no como evidencia local aprobada.
