# TDD - Venta cruzada determinista en el pedido móvil

## TDD-TS-107 Recomendaciones acotadas por catálogo efectivo

### TDD-TC-238 Clasificación, coocurrencia y disponibilidad por sucursal

- Archivo: `apps/api/tests/test_customer_ai.py::test_branch_scoped_cross_category_recommendations`
- Propósito: comprobar que un alimento cuyo nombre contiene `te` sigue siendo alimento por su
  estación canónica, que la mayor coocurrencia no prevalece sobre una indisponibilidad local y que
  el resultado conserva sólo bebidas elegibles con motivo histórico.

### TDD-TC-239 Contrato público de sucursal y fallo cerrado

- Archivo: `apps/api/tests/test_customer_ai.py::test_public_upsell_endpoint_requires_branch_context`
- Propósito: verificar que la ruta pública acepta la sucursal seleccionada y que omitirla no usa una
  sucursal implícita ni devuelve productos de otra operación.

### TDD-TC-240 Estado móvil sin fallback fabricado

- Archivo: `tests/frontend/test_mobile_web_order_flow.mjs`
- Propósito: comprobar que la petición incluye `branch_id`, que una respuesta vacía o fallida se
  conserva vacía y que `CartDrawer` limpia resultados anteriores sin reclasificar nombres ni tomar
  los primeros productos del catálogo.

### TDD-TC-241 Aislamiento de recomendaciones y CRM administrativos

- Archivo: `apps/api/tests/test_customer_ai.py::test_crm_ignores_customers_and_orders_from_another_organization`
- Archivo: `apps/api/tests/test_customer_ai.py::test_customer_recommendations_rejects_another_tenant_branch`
- Propósito: comprobar que los datos de otro tenant no entran al segmento CRM y que la autorización
  de una sucursal ajena falla antes de ejecutar el recomendador. Los precios sin versión vigente no
  se sustituyen por un valor fabricado.
