# Editor móvil de modificadores comerciales

Riesgo R3: precios, persistencia y aislamiento de catálogo. Autoridad: PRD-FR-010 y PRD-FR-061.

`GET /api/v1/products/{id}/simple-modifiers` requiere `catalog.manage` y organización del actor.
Devuelve `product` (snapshot vigente con precio y categoría), `options`, `revision` opaca y `editable`. POST/PUT de catálogo aceptan opcionalmente
`simple_modifiers: {options: [{name, price_delta_cents}], expected_revision}`. Omitir el campo
conserva el catálogo. Creación requiere revisión null; actualización requiere la revisión leída.

La transacción de producto incluye opciones y auditoría, con un único commit. La actualización
bloquea producto, grupo y opciones; una revisión obsoleta falla cerrada. El hash incluye precio
vigente y producto; el formulario se hidrata desde ese mismo snapshot y sólo envía campos editados.
Cambios de precio y overrides de sucursal invalidan la revisión del producto. Un compare-and-swap
de updated_at protege SQLite, donde FOR UPDATE no bloquea. Cada guardado aceptado registra auditoría,
incluso si las opciones no cambiaron. Se conserva el grupo
`Extras`, incluso archivado o vacío tras el fallo de c231982; opciones se actualizan/reactivan por
nombre y las retiradas se archivan. Nunca se borran snapshots ni grupos ajenos. Si Extras contiene
reglas obligatorias, opciones de inventario, overrides de sucursal, nombres no representables por la gramática, vínculos canónicos o semántica avanzada, el editor
simplificado no lo modifica. Los catálogos avanzados siguen bajo su propia autoridad.

Se reutiliza el tipo interno existente `instruction` con `inventory_effect=false` y cargo exacto;
la proyección pública y el snapshot lo identifican como `modifier`, no `order_comment` ni
`preset_instruction`. No se agrega un tipo `surcharge` ni una migración. El precio del servidor
es autoritativo; un extra de 1000 centavos sobre base de 4500 produce 5500 por unidad.

Validación: nombres únicos sin distinguir mayúsculas, no vacíos, máximo 120 caracteres; importes
enteros entre 0 y 2147483647 centavos; máximo 100 opciones por solicitud. El editor convierte
decimales MXN exactamente y rechaza basura, negativos y fracciones de centavo. No convierte un
precio inválido en cero. Una carga fallida bloquea guardado; respuestas atrasadas no cambian otro
borrador. Archivar el producto conserva el contrato DELETE existente y la historia.

Preguntas operativas: ¿se guardó el conjunto completo? Auditoría `product.simple_modifiers_saved`
en la misma transacción. ¿por qué se rechazó? Códigos estables `invalid_simple_modifiers`,
`simple_modifiers_conflict`, `simple_modifiers_managed_elsewhere`. ¿se duplicó en un reintento?
IDs estables y restricción SKU/grupo/nombre, revisión y pruebas de repetición; una respuesta perdida
requiere recargar antes de editar nuevamente. Sin logs nuevos de nombres o payloads sensibles.

Reversión: omitir el campo conserva compatibilidad de clientes anteriores; opciones retiradas se
pueden reactivar sin tocar ventas previas. Despliegue y canary requieren autorización separada.
