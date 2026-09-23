# CAT-DESC-001 — Cierre local

R2, base 41a6aaa. Campo Descripción del producto debajo del nombre en Editar Platillo,
precargado desde el snapshot vigente, contador y límite de 360, texto vacío permitido.
POST/PUT conservan description si se omite; validan tipo/longitud en dominio. El menú
consume el valor existente del catálogo público, sin cambio de precios ni opciones.
Sin migración: columna nullable String(360) existente. PRD-FR-010 ya cubre descripción
corta; SDD/BDD/TDD/matriz activados para contrato de edición y cobertura.

Evidencia:
- RED HTTP: faltaba description en snapshot; segundo RED: campo ignorado al guardar.
- `test_product_description.py`: 7 passed (edición/vacío/omisión/límite/tipos,
  creación, API pública y restaurante ajeno); regresión inicial conjunta con
  `test_mobile_product_modifiers.py`: 33 passed.
- `test_product_description_postgres.py`: 1 passed en PostgreSQL local con schema
  desechable y migraciones reales: 360 caracteres Unicode, rechazo de 361 y vacío.
- Semántica `test:mobile-product-modifiers` aprobada: precarga, cambio aislado,
  vaciar y payload sin precio cuando sólo cambia descripción.
- Browser con componente real y API sintética: precarga, editar, guardar/reabrir,
  texto personalizado conservado; QA móvil a 390px. No se escribe producción.
- Typecheck/build admin aprobados; advertencia previa de bundle mayor de 500 kB.
- Ruff focal y diff --check aprobados. Mypy focal: 37 diagnósticos existentes tanto
  en HEAD como en cambios (shadow files), ninguno nuevo. Gate absoluto no verde.
- Trazabilidad: 3 failed/5 passed por problemas previos PRD-FR-740 sin definición y
  duplicados BDD-SC-819..822/TDD-TC-259..262; no se silencian ni excluyen.

Revisión focal: campo se valida antes de persistir, permisos/organización y bloqueo
existentes se conservan; texto renderizado por React sin HTML, revisión optimista ya
incluye descripción. Auditoría product.updated incluye el campo modificado.
No se requiere auditoría independiente R3: cambio acotado de texto descriptivo.
Evidencia registrada antes de publicación; el usuario autorizó commit, integración
en main y push tras el cierre local. CI y despliegue no certificados aquí. Tras desplegar API/admin,
confirmar descripción real en tarjeta y detalle del menú (recargar si estaba abierto).
