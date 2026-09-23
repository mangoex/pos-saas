# TDD-TS-292 Menú visual y paleta

Cubre BDD-SC-940..943. Ejecutar test_mobile_menu_theme.mjs para las cuatro paletas, fallback y
apariencia legacy; RED por falta de resolución independiente. Regresiones ejecutables de
personalización, flujo de pedidos, etiquetas y dictado preservan el comportamiento existente.
Typecheck/build mobile-web y diff --check. QA Browser con fixture sintético: búsqueda/categorías,
detalle/carrito, cuatro paletas y 360/390/escritorio. Sin pruebas de BD: no cambia su contrato.

Regresión de septiembre: test_mobile_menu_theme.mjs prueba uploads raster base64, enlaces
HTTP y rechazo de SVG/HTML, esquemas ajenos y base64 inválido. RED observado: el JPEG
aceptado por el admin retornaba cadena vacía. QA con QA_UPLOADED_COVERS=1 y
tests/browser/pickup-grace-fixture.mjs: fotos del banner/círculos, contraste del admin
heredando texto blanco, límites del campo horario y separación del resumen a 320/390px.
