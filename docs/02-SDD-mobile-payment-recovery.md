# SDD — Recuperación de cobro y entrega móvil

Paquete 3 R3 de `plan-remediacion-saas-2026-09-28.md`; PRD-FR-025/026 y contrato
existente `payment_commands`/`order_fulfillment_commands`. No cambian fórmulas, importes ni estados.

El servidor Python conserva autoridad para total en centavos, permiso, caja y transición.
El cliente consulta estado canónico antes de crear un intento, copia el total sin recalcularlo y
persiste clave y cuerpo originales antes de POST. Una respuesta perdida conserva el registro;
el replay backend devuelve la respuesta original. Pago confirmado y entrega pendiente son etapas
distintas: reanudar entrega no crea otro pago. La pantalla refleja el estado devuelto por servidor.

Persistencia local mínima: versión, tenant/sucursal/actor/pedido, claves UUID, monto entero,
método, caja, comando de entrega y recibo técnico mínimo. Sin token, cliente, dirección ni tarjeta.
Namespace por tenant/sucursal/actor/pedido; sesión autenticada se comprueba antes/después de cada
espera. Cambio de sesión interrumpe antes del siguiente envío y no reutiliza contexto ajeno.
La identidad del actor se obtiene de `/auth/session`; tenant/sucursal del pedido autorizado.

Web Locks serializa read-modify-send-clear por namespace entre pestañas. Al liberar el lock,
la pestaña siguiente relee tanto persistencia como estado remoto. Sin bloqueo entre pestañas o
almacenamiento fiable se rechaza antes de cobrar; nunca se simula persistencia en memoria.
Datos corruptos no se descartan silenciosamente. Un método/caja diferente durante pago incierto
produce conflicto explícito conservando el intento original. No hay limpieza automática por edad.

Se persiste cada etapa antes del próximo efecto; almacenamiento fallido después de confirmación
deja la clave anterior recuperable. Resultado financiero incierto se recupera mediante la misma
clave/cuerpo. Resultado de entrega perdido se repite con su propia clave. Confirmación explícita
del backend es la única condición para retirar un intento terminado; conflictos no rotan claves.

Preguntas operativas: ¿qué pedido tiene resultado incierto?, ¿el cobro fue confirmado pero falta
entrega?, ¿se repitió la misma clave? UI con estado/error de recuperación; backend conserva auditoría
e idempotencia existentes, sin nuevos logs con datos del cliente. Los recibos de pruebas son sintéticos.

Reversibilidad: el registro lleva versión; no borrar intentos al volver a una versión anterior.
No requiere migración porque utiliza tablas/contratos durables existentes. PostgreSQL verifica
concurrencia/replay y SQLite compatibilidad; auditoría independiente R3 y QA visual focal.
