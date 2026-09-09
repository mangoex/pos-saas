import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');

// 1. MobileOrdersMonitor component verification
const monitorPath = join(root, 'apps/admin-web/src/features/mobile-orders/MobileOrdersMonitor.tsx');
assert.equal(existsSync(monitorPath), true, 'MobileOrdersMonitor.tsx must exist in features/mobile-orders');

const monitorCode = readFileSync(monitorPath, 'utf8');

assert.match(
  monitorCode,
  /\/orders\/accounts|\/orders/i,
  'MobileOrdersMonitor must query orders or accounts endpoint'
);

assert.match(
  monitorCode,
  /folio/i,
  'MobileOrdersMonitor must display order folio'
);

assert.match(
  monitorCode,
  /service_type|order_type/i,
  'MobileOrdersMonitor must handle order service type (dine-in, takeout, delivery)'
);

assert.match(
  monitorCode,
  /customer_label|customer_snapshot|owner_name/i,
  'MobileOrdersMonitor must display customer information'
);

assert.match(
  monitorCode,
  /setSelectedOrder|onSelectOrder|openDetail/i,
  'MobileOrdersMonitor must have handler to open order detail'
);

// 2. MobileOrderDetailModal component verification
const detailModalPath = join(root, 'apps/admin-web/src/features/mobile-orders/MobileOrderDetailModal.tsx');
assert.equal(existsSync(detailModalPath), true, 'MobileOrderDetailModal.tsx must exist in features/mobile-orders');

const modalCode = readFileSync(detailModalPath, 'utf8');

assert.match(
  modalCode,
  /wa\.me/i,
  'MobileOrderDetailModal must provide direct WhatsApp link for customer'
);

assert.match(
  modalCode,
  /selected_modifiers|modifiers|extras/i,
  'MobileOrderDetailModal must break down selected modifiers and extras'
);

assert.match(
  modalCode,
  /line_notes|notes/i,
  'MobileOrderDetailModal must show product notes or special requests'
);

assert.match(
  modalCode,
  /table_number|mesa|delivery_address/i,
  'MobileOrderDetailModal must display table number or delivery address'
);

assert.match(
  modalCode,
  /total_cents|total/i,
  'MobileOrderDetailModal must display order total'
);

// 3. AdminLayout integration verification
const layoutPath = join(root, 'apps/admin-web/src/components/AdminLayout.tsx');
const layoutCode = readFileSync(layoutPath, 'utf8');

assert.match(
  layoutCode,
  /MobileOrdersMonitor/i,
  'AdminLayout must import and integrate MobileOrdersMonitor'
);

assert.match(
  layoutCode,
  /isMobile|max-width:\s*768/i,
  'AdminLayout must check for mobile viewport'
);

// 5. Verification of today-only orders and no "Panel Completo"
assert.match(
  monitorCode,
  /isToday/,
  'MobileOrdersMonitor must include isToday filter for orders'
);

assert.doesNotMatch(
  monitorCode,
  /Panel Completo/,
  'MobileOrdersMonitor must NOT contain Panel Completo button'
);

assert.doesNotMatch(
  layoutCode,
  /Panel completo activo en celular/,
  'AdminLayout must NOT contain Panel completo banner on mobile'
);

// 6. Modal button verification
assert.match(
  modalCode,
  /Aceptar Pedido/,
  'MobileOrderDetailModal must have Aceptar Pedido button for incoming orders'
);

assert.match(
  modalCode,
  /Listo para Entregar/,
  'MobileOrderDetailModal must have Listo para Entregar button for ready orders'
);

assert.match(
  modalCode,
  /onOrderAccepted/,
  'MobileOrderDetailModal must accept onOrderAccepted callback'
);

assert.match(
  monitorCode,
  /onOrderAccepted/,
  'MobileOrdersMonitor must wire onOrderAccepted to switch tab to READY'
);

console.log('✓ All Mobile Admin Orders Monitor tests PASSED!');
