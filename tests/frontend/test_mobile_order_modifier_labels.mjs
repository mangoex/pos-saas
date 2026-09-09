import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { existsSync, mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const formatterPath = join(root, 'packages/api-client/src/orderModifierPresentation.ts');

assert.equal(existsSync(formatterPath), true, 'the shared modifier presentation formatter must exist');

const temporaryDirectory = mkdtempSync(join(tmpdir(), 'restaurantos-order-modifier-presentation-'));
process.on('exit', () => rmSync(temporaryDirectory, { recursive: true, force: true }));
const { formatOrderModifier } = await (async () => {
  execFileSync(
    process.execPath,
    [
      join(root, 'node_modules/typescript/bin/tsc'),
      '--target', 'ES2022', '--module', 'NodeNext', '--moduleResolution', 'NodeNext',
      '--outDir', temporaryDirectory, formatterPath,
    ],
    { cwd: root, stdio: 'pipe' },
  );
  return import(pathToFileURL(join(temporaryDirectory, 'orderModifierPresentation.js')).href);
})();

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

const incomplete = formatOrderModifier({ price_delta_cents: 0 });
assert.ok(incomplete.label.length > 0, 'incomplete snapshots must receive an explicit fallback label');
assert.notEqual(incomplete.label, '+', 'incomplete snapshots must never become a bare plus sign');

for (const viewPath of [
  join(root, 'apps/admin-web/src/features/mobile-orders/MobileOrderDetailModal.tsx'),
  join(root, 'apps/pos-web/src/features/history/History.tsx'),
]) {
  const view = readFileSync(viewPath, 'utf8');
  assert.match(view, /formatOrderModifier/, `${viewPath} must use the shared formatter`);
}

const adminDetail = readFileSync(join(root, 'apps/admin-web/src/features/mobile-orders/MobileOrderDetailModal.tsx'), 'utf8');
const posHistory = readFileSync(join(root, 'apps/pos-web/src/features/history/History.tsx'), 'utf8');
assert.match(adminDetail, /line_notes/, 'Admin mobile detail must keep line notes separate');
assert.match(posHistory, /line\.line_notes/, 'POS history must keep line notes separate');

console.log('✓ Mobile-order modifier label contract passed.');
