# PICKUP-001 — Configuración y aviso de tolerancia

R3 por persistencia/migración. PRD-FR-022, SDD pickup-grace, BDD-SC-944..947,
TDD-TS-293. Se agrega un entero opcional por sucursal y un aviso en checkout para
recoger. No cambia la hora programada, precios, pagos, estados ni pedidos históricos.

## Evidencia local

- RED: 10 fallos backend porque el valor era ignorado/no validado; frontend TS6053
  por helper inexistente. GREEN: test_pickup_grace.py + test_pickup_grace_migration.py,
  **14 pasan** con PostgreSQL local en puerto 55439, incluyendo API real con TestClient,
  permisos, alcance, auditoría, null/omisión, inválidos y migración SQLite/PostgreSQL.
- Regresión test_dine_in_configuration.py: **4 pasan**. Backend usa permiso y auditoría
  existentes sin bypass. El fixture del contrato público se corrigió con slug y clave
  activa; su fallo inicial storefront_setup_required quedó resuelto.
- Arquitectura Alembic: **12 pasan**, cadena completa SQLite hasta 0097, incluyendo
  protección de migraciones históricas forward-only. Se actualizó HEAD esperado que
  aún apuntaba a 0086. La prueba nueva de 0097 verifica filas previas, NULL, CHECK y
  downgrade en ambos motores en entornos desechables.
- test_pickup_grace.mjs pasa: parser, límites, vacío, aviso, singular, modalidades e
  integración. Regresiones carrito **4 pasan** y flujo del pedido **22 pasan**.
- Typecheck y build admin-web/mobile-web pasan. Build admin conserva advertencia de
  tamaño de bundle >500kB, sin nueva dependencia productiva.
- Browser a 390px con componentes reales y API sintética compartida: Recoger aparece
  encima de Comer en el Establecimiento; guardar 30 y recargar conserva valor; checkout
  muestra aviso de 30; Comer aquí lo oculta; -2 produce error de validación; borrar con
  teclado, guardar y recargar elimina el aviso. El comando del navegador fill('') no
  vació el control; se verificó correctamente con selección y Backspace.
- Ruff pasa para operaciones, proyecciones públicas, plataforma, pruebas y migración.
  models.py conserva dos E501 anteriores; comparación contra git show HEAD confirma
  ambos. No se introdujeron silenciamientos.
- Mypy del intérprete global terminó con error interno. Con .venv y --no-incremental
  reportó 72 errores; comparación contra los mismos archivos de HEAD mediante
  --shadow-file produjo exactamente los mismos 72 diagnósticos, descontando líneas.
  No se presenta el gate global como aprobado.
- Trazabilidad: 5 pasan, 3 fallan por deuda previa (PRD-FR-740 y duplicados
  BDD-SC-819..822/TDD-TC-259..262). Nuevos IDs sin duplicados. diff --check pasa.

## Afirmaciones R3 y límites

Auditoría independiente Sol, contexto fresco: sin hallazgos bloqueantes. Repitió los
14 tests de API/migración con PostgreSQL (ninguno omitido) y confirmó corrección del
fixture y diff limpio. Su observación de configuración en pestañas abiertas quedó
precisada en SDD: se obtiene al cargar/recargar el menú.

1. Escritura aislada/autorizada. Evidencia: filtros de organización y admin.manage.
   Refutación: sucursal ajena y actor sin rol; ambos rechazados. Riesgo residual:
   semántica de último guardado de Config se mantiene, no se agrega control de versión.
2. Valor inválido no produce escritura parcial. Evidencia: validación previa a UPDATE.
   Refutación: nombre nuevo junto a valores inválidos; nombre y auditoría sin cambios.
   Repetir un valor no altera pedidos; puede registrar otra auditoría administrativa.
3. Esquema reversible sin tocar pedidos. Evidencia: pruebas round-trip en ambos motores
   y cadena SQLite. Refutación: CHECK con cero/negativo rechaza y preserva valor previo;
   downgrade conserva fila original. Riesgo: downgrade elimina la nueva configuración,
   por lo que se recomienda rollback de app manteniendo columna o respaldo previo.
4. Aviso sólo en recoger. Evidencia: pruebas de función y UI con cambio de modalidad,
   borrado y recarga. Riesgo: pestañas ya abiertas usan la configuración cargada hasta
   recargar; no hay push de cambios ni promesa histórica guardada por pedido.

Sin CI ejecutado para este incremento ni canary productivo. La verificación fue focal,
con datos sintéticos y bases locales; no se cambió producción. Antes de desplegar,
aplicar migración 0097 de forma autorizada y comprobar guardar/borrar en una sucursal
de prueba. NULL permite desactivar el aviso sin revertir esquema. Pendiente commit/push.
