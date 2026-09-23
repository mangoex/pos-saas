# MOB-UI-002 — cierre local, 2026-09-23

R2. Referencia visual aplicada al menú React existente: cabecera de marca/sucursal,
búsqueda antes del banner, CTA al catálogo, categorías circulares, tarjetas verticales,
navegación y carrito. La paleta configurada gobierna los acentos incluso cuando el valor
legacy de apariencia es dark. No cambia API, persistencia ni cálculo del pedido.

Autoridad: SDD mobile-menu-visual, BDD-SC-940..943, TDD-TS-292 y matriz PRD-FR-061.
El PRD conserva alcance. Se aplicaron restaurantos-development y ui-ux-pro-max;
el generador CLI de esta última no estaba instalado correctamente (scripts/data eran
archivos con rutas relativas a destinos inexistentes). Se utilizaron sus instrucciones
legibles de accesibilidad, tipografía, espaciado y controles táctiles.

## Evidencia local

- Paleta: RED por módulo inexistente; GREEN de test_mobile_menu_theme.mjs para las
  cuatro paletas con light/dark/null y fallback seguro.
- Regresiones: test_mobile_cart_personalization.mjs (4), test_mobile_web_order_flow.mjs
  (22), test_mobile_order_modifier_labels.mjs, test_mobile_voice_order.mjs,
  test_mobile_product_modifiers.mjs y test_category_presentation.mjs: pasan.
- pnpm --filter @restaurantos/mobile-web build: pasa, incluyendo TypeScript y PWA.
- Browser con API sintética local: recorrido completo verifyCartEditing en escritorio
  pasa (alta rápida, extras, cantidad, guardar/cancelar, selección gratuita y nombre
  conservado). La ejecución inicial detectó que la animación de entrada del carrito
  desplazaba el objetivo durante el clic; se retiró y el recorrido pasó.
- En 390px: búsqueda devuelve sólo Café sin extras; cambio de categoría y carrito
  comprobados. El driver tuvo un fallo de coordenadas al volver del campo de nombre
  al botón de personalizar; el mismo botón funcionó al reintentar. Se completó
  manualmente editar leche, guardar $80 y conservar Persona QA. No se presenta ese
  intento automatizado móvil como verde.
- QA visual en 360/390px y escritorio: fotos reales del fixture, ausencia de foto,
  banner, tarjetas, navegación, CTA al listado. Sin desbordamiento horizontal observado.
  Colores efectivos verificados en navegador: green #087949, blue #245bc5,
  tinto #9f1239; naranja observado en la revisión inicial y cubierto por la prueba de tema.
- git diff --check: pasa (Git avisa conversión LF/CRLF, sin errores de whitespace).

## Revisión focal y límites

Se conservaron callbacks de búsqueda, filtros, favoritos, dictado, carrito y checkout.
El orden DOM de búsqueda/banner coincide con el visual. La imagen fallida ahora muestra
alternativa y conserva su espacio; no se infiere una fotografía por SKU ni se agregan
valoraciones o promociones ficticias. Controles principales de 44px, foco visible y
movimiento reducido. No se añadieron dependencias.

Preguntas operativas: ¿puede una imagen ausente dejar la tarjeta sin contenido visual?
Se usa alternativa y se verificó el estado sin foto; la regresión de categorías cubre
fallback. ¿puede un cambio visual alterar importes o perder la edición del pedido?
Los comandos no cambiaron y las regresiones de flujo/carrito verifican esa frontera.

Trazabilidad global: 5 pasan, 3 fallan por deuda previa: PRD-FR-740 ausente en PRD,
BDD-SC-819..822 duplicados y TDD-TC-259..262 duplicados. No se corrigieron ni ocultaron.
Sin suite completa local, cambios de BD, pruebas productivas, CI de este incremento,
commit, push o despliegue. GPS real, dictado con micrófono y compatibilidad en dispositivos
físicos requieren comprobación en el entorno de prueba; no se certifican con el fixture.
