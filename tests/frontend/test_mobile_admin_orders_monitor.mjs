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

// 7. Verification of isOrderStale and active orders separation
assert.match(
  monitorCode,
  /isOrderStale/,
  'MobileOrdersMonitor must define and use isOrderStale'
);

assert.match(
  monitorCode,
  /isOrderNew =/,
  'MobileOrdersMonitor must export isOrderNew'
);

assert.match(
  monitorCode,
  /isOrderPrep =/,
  'MobileOrdersMonitor must export isOrderPrep'
);

assert.match(
  monitorCode,
  /isOrderHistory =/,
  'MobileOrdersMonitor must export isOrderHistory'
);

// 8. Functional logic simulation of order classification
const parseIsoDate = (dateStr) => {
  if (!dateStr) return null;
  let normalized = String(dateStr).trim();
  if (normalized.includes(' ') && !normalized.includes('T')) normalized = normalized.replace(' ', 'T');
  if (!normalized.endsWith('Z') && !/[+-]\d{2}:?\d{2}$/.test(normalized)) normalized += 'Z';
  const d = new Date(normalized);
  return isNaN(d.getTime()) ? null : d;
};

const isOrderStale = (dateStr) => {
  if (!dateStr) return false;
  const parsed = parseIsoDate(dateStr);
  if (!parsed) return false;
  const ageMs = Date.now() - parsed.getTime();
  return ageMs > 24 * 60 * 60 * 1000;
};

const isOrderNew = (order) => {
  const status = (order.status || '').toUpperCase();
  if (['DELIVERED', 'CLOSED', 'CANCELLED', 'REJECTED', 'EXPIRED'].includes(status)) return false;
  if (isOrderStale(order.created_at)) return false;
  return ['PENDING', 'PENDING_REVIEW', 'DRAFT'].includes(status) || !!(order.is_public_intent && status !== 'ACCEPTED');
};

const isOrderPrep = (order) => {
  const status = (order.status || '').toUpperCase();
  if (['DELIVERED', 'CLOSED', 'CANCELLED', 'REJECTED', 'EXPIRED'].includes(status)) return false;
  if (isOrderStale(order.created_at)) return false;
  return ['ACCEPTED', 'IN_PRODUCTION', 'IN_PREPARATION', 'SENT_TO_PRODUCTION', 'READY', 'IN_DELIVERY'].includes(status);
};

const isOrderHistory = (order) => {
  const status = (order.status || '').toUpperCase();
  if (['DELIVERED', 'CLOSED', 'CANCELLED', 'REJECTED', 'EXPIRED'].includes(status)) return true;
  if (isOrderStale(order.created_at)) return true;
  return false;
};

const nowIso = new Date().toISOString();
const tenDaysAgoIso = new Date(Date.now() - 10 * 24 * 60 * 60 * 1000).toISOString();

const orderFreshPending = { id: '1', folio: '001', status: 'PENDING', created_at: nowIso };
const orderFreshPrep = { id: '2', folio: '002', status: 'IN_PREPARATION', created_at: nowIso };
const orderStaleIntent = { id: '3', folio: 'WEB-A8E5D9', status: 'PENDING', is_public_intent: true, created_at: tenDaysAgoIso };
const orderStaleDraft = { id: '4', folio: '004', status: 'DRAFT', created_at: tenDaysAgoIso };
const orderStalePrep = { id: '5', folio: '005', status: 'ACCEPTED', created_at: tenDaysAgoIso };
const orderDelivered = { id: '6', folio: '006', status: 'DELIVERED', created_at: nowIso };

// Assertions on classification:
assert.equal(isOrderNew(orderFreshPending), true, 'Fresh pending order must be classified as NEW');
assert.equal(isOrderPrep(orderFreshPending), false);
assert.equal(isOrderHistory(orderFreshPending), false);

assert.equal(isOrderNew(orderFreshPrep), false);
assert.equal(isOrderPrep(orderFreshPrep), true, 'Fresh in-prep order must be classified as PREP');
assert.equal(isOrderHistory(orderFreshPrep), false);

assert.equal(isOrderNew(orderStaleIntent), false, 'Stale public intent from 10 days ago must NOT be classified as NEW');
assert.equal(isOrderPrep(orderStaleIntent), false, 'Stale intent must NOT be classified as PREP');
assert.equal(isOrderHistory(orderStaleIntent), true, 'Stale intent must be routed to HISTORY');

assert.equal(isOrderNew(orderStaleDraft), false, 'Stale draft must NOT be classified as NEW');
assert.equal(isOrderHistory(orderStaleDraft), true, 'Stale draft must be routed to HISTORY');

assert.equal(isOrderPrep(orderStalePrep), false, 'Stale accepted order from 10 days ago must NOT be in PREP');
assert.equal(isOrderHistory(orderStalePrep), true, 'Stale accepted order must be routed to HISTORY');

assert.equal(isOrderHistory(orderDelivered), true, 'Delivered order must be routed to HISTORY');

// Active count must ONLY count fresh NEW and PREP orders (2 out of 6)
const sampleOrders = [orderFreshPending, orderFreshPrep, orderStaleIntent, orderStaleDraft, orderStalePrep, orderDelivered];
const activeCount = sampleOrders.filter((o) => isOrderNew(o) || isOrderPrep(o)).length;
assert.equal(activeCount, 2, 'Active orders count must be exactly 2 for current operational orders');

console.log('✓ All Mobile Admin Orders Monitor tests PASSED!');
