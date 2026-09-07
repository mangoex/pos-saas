# Portada e imágenes por restaurante

R3 por migración aditiva. Base ee2156a, rama codex/category-images-menu-cover;
carpeta original de Sol preservada. Implementar contrato API/modelo → editor Admin →
proyección móvil → pruebas focales/QA → revisión Sol → CI. Producción requiere redeploy.

Preguntas operativas: ¿quién cambió la portada/categoría? Auditoría por actor/tenant.
¿por qué no se guardó? Respuesta explícita de validación/permiso y error en editor.
¿una liga caída impide pedir? Fallback local de imagen; catálogo y pedido no dependen
de descargar fotografías en backend. No se introduce proxy ni carga de archivos.

Migración 0082 conserva todas las filas, valores iniciales Todos/sin imagen.
Rollback de código conserva esquema; downgrade físico bloquea personalizaciones.

Evidencia local: RED inicial por ausencia de image_url; 24 pruebas API verdes más
dos variantes IPv4 mixtas añadidas y verificadas (14 casos URL locales verdes).
21 pruebas de API/alcance/trazabilidad previas; prueba semántica ejecuta proyección
real, cambio de tenant, fallback y sincronización del hero. Typecheck Admin/móvil,
ambos builds, Ruff de apps/api/tests y mypy del módulo nuevo aprobados.
Migración SQLite aprobada; PostgreSQL 16 aprobado con upgrade, downgrade protegido
y dos editores simultáneos cuya auditoría conserva la cadena de valores.
El primer intento PostgreSQL falló por servicio QA detenido; se reinició y se repitió
el gate satisfactoriamente, sin conexión a producción.

QA navegador local: editar portada «La carta del Güero», guardar liga de categoría,
renderizar ambas fotografías en hero/círculos a 390×844; seleccionar Tacos muestra
3 productos y su hero, regresar a portada muestra 8. Fotografías sólo de fixture QA.

Afirmación: una actualización sólo afecta al restaurante del actor. Evidencia/intento
de refutación: API dos tenants, edición cruzada rechazada y portada ajena sin cambios.
Resultado: aprobado. Riesgo residual: despliegue productivo no ejecutado.
Afirmación: imágenes removidas conservan trazabilidad. Refutación: A→B→null y dos
editores PostgreSQL simultáneos. Resultado: before/after serializado y valor final
coherente. Afirmación: downgrade no pierde personalización. Refutación: downgrade
con nombre editado/fotografía. Resultado: bloqueado, filas y versión preservadas.

Revisión Sol independiente cerrada sin bloqueos tras corregir destinos de red local
evidentes (incluidas representaciones IPv4 mixtas) y auditoría before/after de categoría.
La clasificación URL no consulta DNS; disponibilidad y resolución futura del alojamiento
son externas. Un fallo visual usa ilustración genérica y no altera el catálogo.
CI completo se registra en el PR. El redeploy aplica 0082 automáticamente, sin variables
de entorno nuevas. Ruta de uso: Admin → Catálogo y Precios → Categorías.
