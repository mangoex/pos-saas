# MOB-UI-002 — Menú cálido con paleta configurable

PRD-FR-061. Riesgo R2: presentación y resolución de tema. La referencia visual del usuario guía
el fondo cálido, banner fotográfico, círculos y tarjetas verticales; los contenidos son del catálogo.
No se incorporan valoraciones, notificaciones o descuentos ficticios.

Se conserva React, la tipografía instalada y todos los callbacks de catálogo, favoritos, dictado,
carrito y checkout. El banner separa sucursal/búsqueda de fotografía y permite ir al menú.
Dos columnas en teléfono; una en anchos muy pequeños; navegación con cuatro acciones existentes.
Imágenes mantienen espacio reservado y alternativa cuando no hay fotografía. Controles de 44px,
foco visible, contraste y movimiento reducido. No hay cambio de backend, API o persistencia.

La resolución de fotografías admite también uploads raster data:image base64 (jpeg/jpg/png/webp/gif,
máximo 2 MiB de URL), conforme al validador del catálogo. SVG/HTML incrustados se rechazan.
El horario nativo usa min-width:0, max-width:100% y apariencia normalizada para evitar el ancho
intrínseco de Safari; encabezado flexible, resumen espaciado y días en dos filas hasta 380px.

La paleta de sucursal (orange/green/blue/tinto) gobierna acentos, botones y superficies suaves.
El valor legacy mobile_theme=dark no reemplaza esa paleta: actualmente no tiene superficies oscuras
independientes y no se introduce un nuevo modo oscuro en este incremento. Se conserva como atributo
separado de apariencia. Paleta inválida vuelve a orange.

Secuencia: criterios y prueba de paleta RED; resolución y presentación; regresiones funcionales,
build y QA visual de paletas/ancho reducido. PRD mantiene su alcance; se activan SDD, BDD, TDD y matriz.
