import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');

test('MobileBranchSettingsTab provides dine_in_enabled toggle above delivery fees', () => {
  const source = readFileSync(join(root, 'apps/admin-web/src/features/mobile-admin/MobileBranchSettingsTab.tsx'), 'utf8');

  // Interface & State
  assert.match(source, /dine_in_enabled\?: boolean/);
  assert.match(source, /const \[dineInEnabled, setDineInEnabled\] = useState\(true\)/);
  assert.match(source, /setDineInEnabled\(currentBranch\.dine_in_enabled !== false\)/);
  assert.match(source, /dine_in_enabled: dineInEnabled/);

  // Position above delivery fees
  const dineInIdx = source.indexOf('Comer en el Establecimiento');
  const deliveryIdx = source.indexOf('Costos de Envío a Domicilio');
  assert.ok(dineInIdx !== -1, 'Comer en el Establecimiento card must exist');
  assert.ok(deliveryIdx !== -1, 'Costos de Envío card must exist');
  assert.ok(dineInIdx < deliveryIdx, 'Comer en el Establecimiento must appear ABOVE Costos de Envío a Domicilio');
});

test('BranchesList desktop provides dine_in_enabled toggle for parity', () => {
  const source = readFileSync(join(root, 'apps/admin-web/src/features/branches/BranchesList.tsx'), 'utf8');

  assert.match(source, /dine_in_enabled\?: boolean/);
  assert.match(source, /dine_in_enabled: branch\.dine_in_enabled !== false/);
  assert.match(source, /Comer en el Establecimiento/);
});

test('CartDrawer conditionally renders Comer aquí and falls back to takeaway', () => {
  const source = readFileSync(join(root, 'apps/mobile-web/src/components/CartDrawer.tsx'), 'utf8');

  // Dine-in condition
  assert.match(source, /selectedBranch\?\.dine_in_enabled !== false/);
  assert.match(source, /if \(orderType === 'dine-in' && selectedBranch\?\.dine_in_enabled === false\)/);

  // Takeaway option is always present
  assert.match(source, /setOrderType\('takeaway'\)/);
  assert.match(source, /Llevar/);
});

test('CartDrawer provides pickup scheduler with L, M, M, J, V, S, D, time picker, and order observation', () => {
  const source = readFileSync(join(root, 'apps/mobile-web/src/components/CartDrawer.tsx'), 'utf8');

  // Day letters
  assert.match(source, /\['L',\s*'M',\s*'M',\s*'J',\s*'V',\s*'S',\s*'D'\]/);
  assert.match(source, /Día y hora para recoger/);
  assert.match(source, /pickup-day-btn/);
  assert.match(source, /pickup-time-input/);
  assert.match(source, /📅 Recoger:/);

  // Notes observation formatting
  assert.match(source, /const pickupScheduleNote = `📅 Recoger: \${dayLabel} a las \${pickupTime \|\| 'lo antes posible'}`/);
});

test('MobileOrdersMonitor displays order notes and pickup schedule on order card', () => {
  const source = readFileSync(join(root, 'apps/admin-web/src/features/mobile-orders/MobileOrdersMonitor.tsx'), 'utf8');

  assert.match(source, /order\.order_notes \|\| \(order as any\)\.notes/);
});
