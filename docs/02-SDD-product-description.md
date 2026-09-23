# CAT-DESC-001 — Descripción editable en admin móvil

R2, PRD-FR-010. Se reutiliza products.description nullable String(360); sin migración.
El editor carga la descripción existente desde el snapshot del producto y permite
editarla como texto plano de hasta 360 caracteres. Vacío elimina el texto; omitir
description conserva el existente. Productos nuevos mantienen el texto por defecto
si clientes antiguos omiten el campo. POST/PUT validan tipo y longitud en dominio.
La revisión optimista existente incluye la descripción; sólo se envían campos cambiados.
Tarjeta y detalle del menú usan el mismo valor del catálogo público; no cambia dinero.

Secuencia: contrato/RED HTTP y formulario, implementación, regresiones y QA móvil.
Operación: ¿se guardó la descripción? product.updated registra el campo; ¿se intentó
cambiar un producto ajeno? alcance organizacional y catalog.manage siguen gobernando.
