# Correcciones visuales del menú y Recoger

R2, base 255a536. Regresión de MOB-UI-002: el filtro de imágenes aceptaba sólo HTTP(S)
y descartaba los uploads raster base64 válidos del admin. Se conserva la validación
restrictiva por formato/tamaño. No cambian contratos API, persistencia, precios ni calendario.
PRD existente conservado; criterios BDD-SC-941/943/944 y cobertura TDD-TS-292 ampliados.

Contraste: label #334155 e input #0f172a sobre blanco, independientes del texto heredado.
Checkout: ancho nativo de hora acotado, encabezado flexible, mayor separación de aviso
y resumen; siete días en dos filas a <=380px. Paleta de sucursal preservada.

Evidencia local:
- RED: test_mobile_menu_theme rechazó JPEG base64 del admin; GREEN tras corrección.
- Semánticas de tema/fotos y pickup-grace aprobadas; carrito 4/4 y pedidos 22/22.
- Typecheck admin y typecheck/build mobile aprobados; diff --check limpio.
- Browser con componentes reales y API sintética: 4 imágenes portada/categoría (hero
  y círculos) cargadas con naturalWidth >0; contraste admin probado heredando blanco.
- Paleta tinto, 390px: campo horario de 290px dentro de tarjeta 320px. A 320px:
  campo 220px dentro de tarjeta 250px y días scrollWidth=clientWidth=220, sin fuga.
- Revisión focal de origen de imagen -> img.src: sólo raster base64 acotado o HTTP(S)
  sin credenciales; SVG/HTML y esquemas ejecutables permanecen rechazados.

Reproducir QA: QA_UPLOADED_COVERS=1 node tests/browser/pickup-grace-fixture.mjs;
abrir menú /menu/?restaurant=tinto en 4174 y /qa-pickup en 4175. Fixtures sin producción.
No se verificó Safari en iPhone físico: confirmar el control nativo tras redeploy.
Evidencia registrada antes de publicación. El usuario autorizó commit y push después
del cierre local; despliegue y verificación productiva quedan pendientes.
