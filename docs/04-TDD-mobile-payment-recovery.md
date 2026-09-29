# TDD — Recuperación móvil

## TDD-TS-399 Recuperación de comandos móviles

- `tests/frontend/test_mobile_order_recovery.mjs`: ejecutar módulo TypeScript con transporte,
  almacenamiento y locks deterministas; simular respuesta perdida antes/después del commit,
  recarga, pago seguido de fallo de entrega, dos pestañas, cambio de sesión, payload modificado,
  almacenamiento denegado/corrupto y estado canónico confirmado antes de intentar otro pago.
- Backend: regresiones de `pay_order` y `fulfill_order`, identidad de respuesta histórica,
  idempotencia y autorización con PostgreSQL/SQLite; ningún nuevo cálculo financiero en JS.
- Conectar pantalla móvil real al módulo; typecheck, prueba semántica de integración y QA visual
  de estado incierto/recuperación. Auditoría Sol independiente del paquete R3.

Afirmación: recuperación no duplica efectos y conserva el comando. Refutación: pérdida de cada
respuesta, recarga, concurrencia y fallos de persistencia; resultados y límites en reporte de ejecución.

- Regresión de auditoría: cambio A → B con pago de A en vuelo y retorno A → B → A;
  controles de B disponibles y respuesta tardía no altera una vista nueva. Comprobación de
  navegador con transporte sintético en `output/playwright/setup-mobile-qa.js`, evidencia en reporte.
