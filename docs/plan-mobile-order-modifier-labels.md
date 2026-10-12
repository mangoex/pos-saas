# Etiquetas de comentarios y modificadores en pedidos móviles

Corrección R3 acotada a la presentación de instrucciones operativas. El pedido móvil ya conserva
las selecciones en `selected_modifiers`; la API usa el snapshot canónico `option_name`,
`kitchen_text` y `price_delta_cents`, mientras Admin móvil, el historial POS y KDS consumen alias
distintos y pueden renderizar sólo `+`, `None` o el snapshot interno. No cambia alcance comercial,
persistencia, estados,
permisos ni esquema; PRD y SDD permanecen vigentes. Se aclaran BDD-SC-733,
BDD-SC-LITE-014 y TDD-TS-233.

## Criterios de aceptación

1. `Sin azúcar`, `Con todo`, `Sin picante` y cualquier otra selección válida muestran una etiqueta
   en Admin móvil y POS antes de aceptar, y permanecen legibles en esas vistas y KDS después de
   aceptar el pedido.
2. La presentación prioriza la instrucción operativa `kitchen_text`, continúa con
   `option_name` y conserva compatibilidad con `name` y `text` de snapshots históricos.
3. El importe usa `price_delta_cents` y acepta `price_cents` para historia previa; cero no agrega
   un cargo visual.
4. Un snapshot incompleto muestra una etiqueta de contingencia y nunca un signo `+` aislado.
5. `line_notes` sigue siendo una nota del producto separada y no se confunde con modificadores.
6. La solución no reescribe pedidos históricos ni altera la transición pendiente → aceptado.
7. KDS muestra el folio operativo cuando es legible y resume referencias internas UUID/PI sin
   cambiar el identificador enviado a la API.

## Plan y tareas

1. Añadir una prueba RED ejecutable con snapshots canónicos, históricos, texto libre, precio cero
   y forma incompleta.
2. Crear un formateador compartido y tipado en `packages/api-client` para etiqueta y precio.
3. Adoptar el formateador en `MobileOrderDetailModal`, historial POS y KDS, y agregar un formateador
   presentacional para el código breve del pedido.
4. Fortalecer la prueba semántica para demostrar que las tres vistas usan el contrato compartido.
5. Ejecutar la prueba focal, typecheck de Admin/POS/KDS y los builds activados,
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
- prueba semántica de consumo en Admin móvil, POS y KDS, incluido el código breve del pedido;
- prueba API focal del snapshot pendiente y aceptado;
- typecheck de KDS y los gates ya activados para Admin/POS;
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

## Ampliación KDS 2026-10-11

- RED: la regresión focal falló porque aún no existía el formateador compartido de código breve.
- GREEN: pasaron la regresión de etiquetas/códigos, las pruebas semánticas de KDS, monitor Admin y
  Admin Lite, los typechecks de Admin/POS/KDS, el caso API pendiente → aceptado, el build de KDS y
  `git diff --check`.
- QA visual local con datos simulados: KDS mostró `Sin cebolla`, `Sin ajo`, `Sin sal`, la nota de
  línea separada y `PED-000001` en lugar del UUID; no se usaron datos ni servicios productivos.
- La reauditoría Sol final no encontró hallazgos P1/P2. Conserva como riesgo residual la posible
  colisión presentacional del sufijo breve; las transiciones siguen usando el ID interno completo.
- El gate global de trazabilidad quedó en 4 fallos y 4 pases por inconsistencias previas fuera de
  este diff. El entorno usó Node 20.20.2 pese al requisito Node >=22. CI completo, canary y
  verificación productiva no se ejecutaron.
