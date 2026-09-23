# CAT-DELETE-001 — Eliminación de categoría y productos

PRD-FR-010, R3: operación masiva sobre catálogo y persistencia. Sin migración: status
archived ya está modelado y excluido por las lecturas de catálogo. No se borran filas,
pedidos, precios históricos, recetas, modificadores ni movimientos de inventario.

DELETE /api/v1/categories/{id}?delete_products=true exige actor y catalog.manage.
La categoría se busca por ID y organización del actor; flag omitido/falso rechaza.
Una transacción archiva categoría y todos los productos con su category_id Y organization_id.
Auditoría category.deleted incluye categoría, IDs y estados anteriores de productos.
Repetir el DELETE sobre categoría archivada es no-op, sin nueva auditoría ni otros efectos.
Guardar/eliminar un producto o editar la categoría desde formularios viejos no puede
reactivar filas archivadas. Nombres de categorías archivadas siguen reservados por el
índice único existente y producen error de negocio explícito, no error de base de datos.
La reserva de nombres también cubre diferencias de mayúsculas. Los importadores Excel
y legacy usan la misma exclusión y serialización: no reactivan categorías/productos
archivados ni insertan productos nuevos en categorías eliminadas.

La eliminación y altas/ediciones normales del catálogo serializan por organización
antes de bloquear filas de producto/categoría. PostgreSQL usa el bloqueo de fila de
organizations; SQLite conserva su serialización de escritores. No cambia lecturas ni
comandos de pedidos. La pertenencia al ejecutar la transacción determina el alcance.

UI: dos pasos, botón debajo de Guardar; confirmación menciona nombre de categoría,
todos sus productos y todas las sucursales del restaurante. Cancelar vuelve al editor.
Solicitud pendiente bloquea guardado, confirmación repetida y cierre; errores mantienen
editor abierto. Éxito invalida categorías/productos y vuelve al filtro Todos. La portada
maestra no ofrece eliminación. Modal desplazable en móvil para alcanzar el nuevo botón.

Secuencia: contrato/RED, backend/UI, PostgreSQL y regresiones, QA, auditoría Sol.
Operación: ¿qué se archivó y quién lo hizo? auditoría con IDs y estados previos.
¿la solicitud afectó otro restaurante? guardas de actor/organización y pruebas adversas.
Recuperación excepcional mediante comando administrativo compensatorio auditado fuera
de este alcance; conservar el evento y filas permite reconstruir estados anteriores.
Rollback de código no restaura datos; no se ejecutan eliminaciones productivas en desarrollo.
