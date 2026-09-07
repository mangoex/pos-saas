# BDD - Importación de catálogos heredados por sucursal

## BDD-FEAT-053 Migración trazable de Constitución

```gherkin
@PRD-FR-690 @PRD-FR-691 @PRD-FR-692 @PRD-FR-696 @PRD-FR-697 @PRD-FR-702 @import @branch
Feature: Importar datos heredados sin mezclar sucursales ni duplicar reintentos

  @BDD-SC-144
  Scenario: Un lote identifica sucursal y fuentes
    Given un administrador corporativo y la sucursal Constitución
    When inicia un lote con manifiesto y checksum por archivo
    Then el lote conserva origen, sucursal, actor y conteos
    And repetir el mismo manifiesto no crea otro lote ni otro destino

  @BDD-SC-145
  Scenario: Un producto válido recibe estación determinista y alcance corporativo
    Given una fila de PRODUCTOS con SKU numérico entre comillas, nombre y categoría en mayúsculas
    When se importa la fila sin estación de producción
    Then se quita la comilla inicial y se asigna la estación definida por DATA-003
    And el producto queda activo en el catálogo corporativo sin inventar precio ni receta

  @BDD-SC-146
  Scenario: Insumos corporativos no alteran existencias ni costo promedio
    Given una fila de INSUMOS con unidad y costos heredados
    When se materializa el insumo para Constitución
    Then se crea o vincula el catálogo corporativo del insumo y se conserva el costo como referencia del lote
    And no se crea movimiento, saldo inicial, recepción ni costo promedio contable

  @BDD-SC-147
  Scenario: Presentación incompleta permanece pendiente
    Given una fila de PRESENTACIONES sin proveedor
    When se importa la fila
    Then queda needs_review vinculada al insumo cuando sea posible
    And no se crea purchase_presentation con un proveedor ficticio

  @BDD-SC-148
  Scenario: Archivo de recetas sin componentes se rechaza con evidencia
    Given un archivo RECETAS cuyas columnas y filas son las de PRODUCTOS
    When se valida la fuente
    Then sus filas quedan needs_review con razón missing_recipe_components
    And no se crea una receta vacía

  @BDD-SC-149
  Scenario: Clientes se aíslan y consultan por página
    Given clientes heredados de Constitución
    When un actor autorizado consulta el directorio con búsqueda, limit y offset
    Then sólo recibe clientes centrales o de su sucursal autorizada
    And la respuesta contiene total, limit, offset e items sin consultas por cliente

  @BDD-SC-150
  Scenario: Otra sucursal comparte catálogo pero no clientes locales
    Given un producto, insumo y cliente importados desde Constitución
    When un Supervisor de otra sucursal consulta catálogo y directorio
    Then recibe el mismo producto e insumo corporativos
    But no recibe el cliente cuyo origen es Constitución

  @BDD-SC-151
  Scenario: Ajustes respetan autoridad y disponibilidad local
    Given un producto importado que forma parte del catálogo corporativo
    When el administrador completa su configuración o el Supervisor cambia disponibilidad local
    Then el backend vuelve a validar permiso y sucursal
    And el Supervisor no modifica identidad, categoría, precio, estación ni alcance corporativo
    And el sistema registra auditoría con valores anteriores y nuevos
```
