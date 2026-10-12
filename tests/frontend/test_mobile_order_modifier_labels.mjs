import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { existsSync, mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const formatterPath = join(root, 'packages/api-client/src/orderModifierPresentation.ts');
const orderCodePath = join(root, 'packages/api-client/src/orderCodePresentation.ts');

assert.equal(existsSync(formatterPath), true, 'the shared modifier presentation formatter must exist');
assert.equal(existsSync(orderCodePath), true, 'the shared order-code presentation formatter must exist');

const temporaryDirectory = mkdtempSync(join(tmpdir(), 'restaurantos-order-modifier-presentation-'));
process.on('exit', () => rmSync(temporaryDirectory, { recursive: true, force: true }));
const { formatOrderModifier } = await (async () => {
  execFileSync(
    process.execPath,
    [
      join(root, 'node_modules/typescript/bin/tsc'),
      '--target', 'ES2022', '--module', 'NodeNext', '--moduleResolution', 'NodeNext',
      '--outDir', temporaryDirectory, formatterPath, orderCodePath,
    ],
    { cwd: root, stdio: 'pipe' },
  );
  return import(pathToFileURL(join(temporaryDirectory, 'orderModifierPresentation.js')).href);
})();
const { formatOrderCode } = await import(
  pathToFileURL(join(temporaryDirectory, 'orderCodePresentation.js')).href
);

assert.deepEqual(
  formatOrderModifier({ option_name: 'Sin azúcar', kitchen_text: 'Sin azúcar', price_delta_cents: 0 }),
  { label: 'Sin azúcar', priceDeltaCents: 0, priceLabel: null },
  'the canonical API snapshot must render its operational kitchen text without a price label',
);
assert.deepEqual(
  formatOrderModifier({ option_name: 'Salsa', kitchen_text: 'Sin picante', price_delta_cents: 125 }),
  { label: 'Sin picante', priceDeltaCents: 125, priceLabel: '+$1.25' },
  'kitchen text must take precedence when it differs from the catalog name',
);
assert.deepEqual(
  formatOrderModifier({ option_name: 'Extra queso', kitchen_text: '+ Extra queso', price_delta_cents: 100 }),
  { label: 'Extra queso', priceDeltaCents: 100, priceLabel: '+$1.00' },
  'a decorative plus in kitchen text must not be repeated by order-detail views',
);
assert.deepEqual(
  formatOrderModifier({ option_name: 'Extra queso', kitchen_text: '+', price_delta_cents: 0 }),
  { label: 'Extra queso', priceDeltaCents: 0, priceLabel: null },
  'a bare decorative plus must fall back to the catalog name',
);
assert.deepEqual(
  formatOrderModifier({ name: 'Con todo', price_cents: 0 }),
  { label: 'Con todo', priceDeltaCents: 0, priceLabel: null },
  'historical names must remain readable',
);
assert.deepEqual(
  formatOrderModifier({ text: 'Sin cebolla', price_cents: 75 }),
  { label: 'Sin cebolla', priceDeltaCents: 75, priceLabel: '+$0.75' },
  'historical text and price aliases must remain readable',
);
assert.deepEqual(
  formatOrderModifier({ kitchen_text: 'None', option_name: 'Sin ajo', price_delta_cents: 0 }),
  { label: 'Sin ajo', priceDeltaCents: 0, priceLabel: null },
  'null-like serialization artifacts must fall through to the canonical option name',
);

const incomplete = formatOrderModifier({ price_delta_cents: 0 });
assert.ok(incomplete.label.length > 0, 'incomplete snapshots must receive an explicit fallback label');
assert.notEqual(incomplete.label, '+', 'incomplete snapshots must never become a bare plus sign');

assert.equal(formatOrderCode('S1-000001'), 'S1-000001', 'already short operational folios must remain intact');
assert.equal(
  formatOrderCode('MATRIZ-000001'),
  'PED-000001',
  'long branch-prefixed operational folios must be summarized for kitchen views',
);
assert.equal(
  formatOrderCode('PI-018F6F732D0A74F08F1C000000000001'),
  'WEB-000001',
  'public intent references must be summarized consistently',
);
assert.equal(
  formatOrderCode('018f6f73-2d0a-74f0-8f1c-000000000001'),
  'PED-000001',
  'internal UUIDs must never be exposed as the visible kitchen code',
);

for (const viewPath of [
  join(root, 'apps/admin-web/src/features/mobile-orders/MobileOrderDetailModal.tsx'),
  join(root, 'apps/pos-web/src/features/history/History.tsx'),
  join(root, 'apps/kds-web/src/features/orders/KitchenBoard.tsx'),
]) {
  const view = readFileSync(viewPath, 'utf8');
  assert.match(view, /formatOrderModifier/, `${viewPath} must use the shared formatter`);
}

const adminDetail = readFileSync(join(root, 'apps/admin-web/src/features/mobile-orders/MobileOrderDetailModal.tsx'), 'utf8');
const adminMonitor = readFileSync(join(root, 'apps/admin-web/src/features/mobile-orders/MobileOrdersMonitor.tsx'), 'utf8');
const posHistory = readFileSync(join(root, 'apps/pos-web/src/features/history/History.tsx'), 'utf8');
const kitchenBoard = readFileSync(join(root, 'apps/kds-web/src/features/orders/KitchenBoard.tsx'), 'utf8');
assert.match(adminDetail, /line_notes/, 'Admin mobile detail must keep line notes separate');
assert.match(
  adminMonitor,
  /const folio = formatOrderCode\(order\.folio\)\.toLowerCase\(\)/,
  'Admin search must use the same visible order code shown on each card',
);
assert.match(posHistory, /line\.line_notes/, 'POS history must keep line notes separate');
assert.match(kitchenBoard, /formatOrderCode\(task\.folio\)/, 'KDS must present a short operational order code');
assert.doesNotMatch(kitchenBoard, /JSON\.stringify\(mod\)/, 'KDS must never expose raw modifier snapshots');

console.log('✓ Mobile-order modifier label contract passed.');
