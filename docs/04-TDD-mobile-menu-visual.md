# TDD-TS-292 Menú visual y paleta

Cubre BDD-SC-940..943. Ejecutar test_mobile_menu_theme.mjs para las cuatro paletas, fallback y
apariencia legacy; RED por falta de resolución independiente. Regresiones ejecutables de
personalización, flujo de pedidos, etiquetas y dictado preservan el comportamiento existente.
Typecheck/build mobile-web y diff --check. QA Browser con fixture sintético: búsqueda/categorías,
detalle/carrito, cuatro paletas y 360/390/escritorio. Sin pruebas de BD: no cambia su contrato.
