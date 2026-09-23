# PICKUP-001 — Tolerancia informativa para recoger

PRD-FR-022. R3 por persistencia y migración. Secuencia: contrato y RED, migración/API,
admin/checkout, pruebas dirigidas y QA, auditoría independiente con contexto fresco.

`branches.pickup_grace_minutes`: INTEGER nullable, sin default. NULL significa sin aviso;
enteros 1..2147483647 (límite técnico PostgreSQL), sin límite comercial nuevo. Rechazar
booleanos, cadenas, fracciones, cero y negativos en dominio antes de cualquier escritura.
PUT /branches/{id} conserva valor si se omite; null lo limpia; entero lo reemplaza.
Mantiene admin.manage, alcance de organización y auditoría branch.updated transaccional.
GET administrativo, listado público y storefront exponen sólo el mismo campo adicional.

Admin móvil: tarjeta Recoger inmediatamente antes de Comer en el Establecimiento;
campo etiquetado, opcional y guardado con Config. Checkout: aviso junto a la hora
de recoger únicamente en takeaway y con valor positivo configurado de la sucursal actual:
«Respetaremos tu pedido durante N minutos después de tu hora programada para recoger».
Singular para 1. No calcula nueva hora, no altera calendario ni envía notificaciones externas.
Se consulta la configuración al cargar el menú; una pestaña abierta requiere recarga para
ver cambios posteriores del admin. No agrega snapshots, vencimientos ni estados a pedidos.

Migración aditiva 0097, constraint CHECK, compatible PostgreSQL/SQLite. Desplegar esquema
antes del código; default NULL conserva comportamiento previo. Para rollback preferir
revertir aplicación conservando columna; downgrade elimina sólo esta configuración, por lo
que se debe respaldar si se desea recuperarla. No ejecutar migraciones productivas sin autorización.

Operación: ¿se guardó o borró el valor y quién lo cambió? audit branch.updated incluye
valor/null, actor y sucursal. ¿falló validación o alcance? errores de negocio estables
pickup_grace_minutes_invalid / branch_not_found y autorización existente. No logs nuevos
con datos de clientes. Actualizaciones usan la semántica de último guardado existente;
repetir el mismo valor conserva resultado y no genera efectos sobre pedidos históricos.
