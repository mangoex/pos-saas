# TDD: Portada pública por dispositivo

## Verificación vigente de la portada SaaS móvil

- `tests/frontend/test_landing_mobile.mjs`: no inicializar el motor en móvil; inicialización
  única al pasar a escritorio; destinos del registro de prueba y login preservados.
- Ejecutar `pnpm --filter @restaurantos/landing-web test` y `typecheck`.
- QA en navegador: 320×568, 390×844 y escritorio 1440×900; acciones visibles, sin
  desbordamiento, enlaces correctos, móvil sin video, cambio de breakpoint y móvil sin JS.
- Mantener los tests API de `test_root_landing.py` para raíz sin redirección y rutas
  operativas separadas. El caso histórico TDD-TC-218 de abajo fue sustituido por
  `test_root_serves_the_acquisition_landing_for_every_device`.

## TDD-TS-101 Selección y empaquetado aislados de la portada

### TDD-TC-217 Escritorio y recursos contenidos

- Archivo: `apps/api/tests/test_root_landing.py::test_desktop_root_serves_landing_and_exact_assets`
- Propósito: demostrar que `/` entrega la portada a escritorio, que sus recursos salen sólo de
  `landing-web` y que un recurso ausente o un intento de escape devuelve `404`.

### TDD-TC-218 Teléfono redirigido sin ambigüedad de caché

- Archivo: `apps/api/tests/test_root_landing.py::test_mobile_root_redirects_to_menu_with_variant_headers`
- Propósito: cubrir `Sec-CH-UA-Mobile` y agentes de teléfono, exigir `307 /menu/`, `no-store`,
  `Vary` y `Accept-CH`, y confirmar que una señal explícita de escritorio no redirige.

### TDD-TC-219 Rutas operativas preservadas

- Archivo: `apps/api/tests/test_root_landing.py::test_root_selection_does_not_change_operational_routes`
- Propósito: comprobar que `/menu/`, `/admin/`, `/pos/`, `/kds/` y health continúan en sus
  manejadores separados después de integrar la portada.
