import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdtempSync, rmSync } from 'node:fs';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import test from 'node:test';

const root = resolve(import.meta.dirname, '../..');
const temporary = mkdtempSync(join(tmpdir(), 'mobile-cart-'));
let helpers;
try {
  execFileSync(process.execPath, [join(root, 'node_modules/typescript/bin/tsc'), '--target', 'ES2022', '--module', 'CommonJS', '--strict', '--skipLibCheck', '--outDir', temporary, join(root, 'apps/mobile-web/src/utils/cartPersonalization.ts')]);
  helpers = createRequire(import.meta.url)(join(temporary, 'utils/cartPersonalization.js'));
} finally { rmSync(temporary, { recursive: true, force: true }); }
const option = { id: 'milk', name: 'Leche', price_delta_cents: 2500, selection_kind: 'modifier' };
const free = { id: 'sugar', name: 'Azúcar', price_delta_cents: 0, selection_kind: 'ingredient_extra' };
const product = { id: 'coffee', sku: 'coffee', name: 'Café', price_cents: 5500, modifier_groups: [{ id: 'extras', name: 'Extras', minimum_selections: 0, maximum_selections: 2, is_required: false, options: [option, free] }] };
const selected = (o) => ({ option_id: o.id, name: o.name, price_delta_cents: o.price_delta_cents, selection_kind: o.selection_kind });
const original = { cart_id: 'first', product, quantity: 1, notes: 'Caliente', modifiers: [selected(option)], line_total_cents: 8000 };

test('commercial availability differs from comments and zero surcharge', () => {
  assert.equal(helpers.hasCustomizationOptions(product), true);
  assert.equal(helpers.hasCustomizationOptions({ ...product, modifier_groups: [] }), false);
  assert.equal(helpers.hasCustomizationOptions({ ...product, modifier_groups: [{ ...product.modifier_groups[0], options: [{ ...free, selection_kind: 'order_comment' }] }] }), false);
  assert.equal(helpers.hasSelectedCustomization([selected(free)]), true);
  assert.equal(helpers.hasSelectedCustomization(undefined), false);
});
test('exact cents and existing promotion policy', () => {
  assert.equal(helpers.calculateLineTotal(product, 1, []), 5500);
  assert.equal(helpers.calculateLineTotal(product, 2, [selected(option)]), 16000);
  assert.equal(helpers.calculateLineTotal(product, 2, [selected(free)]), 11000);
  assert.equal(helpers.calculateLineTotal({ ...product, is_promo: true, promo_price_cents: 4500 }, 2, [selected(option)]), 14000);
});
test('editing replaces one identity and position without mutating or merging', () => {
  const second = { ...original, cart_id: 'second', notes: '' };
  const cart = [original, second];
  const next = helpers.replaceCartLine(cart, 'first', product, 2, '', [selected(free)]);
  assert.equal(next.length, 2);
  assert.equal(next[0].cart_id, 'first');
  assert.equal(next[0].line_total_cents, 11000);
  assert.equal(next[1], second);
  assert.equal(original.quantity, 1);
  assert.equal(original.notes, 'Caliente');
  assert.equal(helpers.replaceCartLine(cart, 'deleted', product, 2, '', []), cart);
});
test('current catalog owns prices and selection membership', () => {
  const next = helpers.replaceCartLine([original], 'first', product, 1, '', [{ ...selected(option), price_delta_cents: 1 }]);
  assert.equal(next[0].line_total_cents, 8000);
  assert.equal(next[0].modifiers[0].price_delta_cents, 2500);
  assert.match(helpers.validateCartDraft(product, 1, [{ ...selected(option), option_id: 'removed' }]), /disponible/);
  assert.match(helpers.validateCartDraft({ ...product, is_available: false }, 1, []), /disponible/);
  assert.ok(helpers.validateCartDraft(product, 0, []));
  assert.ok(helpers.validateCartDraft(product, 1.5, []));
  assert.ok(helpers.validateCartDraft(product, 100, []));
  assert.ok(helpers.validateCartDraft(product, 1, [selected(option), selected(option)]));
  assert.ok(helpers.validateCartDraft({ ...product, modifier_groups: [{ ...product.modifier_groups[0], minimum_selections: 1 }] }, 1, []));
  assert.ok(helpers.validateCartDraft({ ...product, modifier_groups: [{ ...product.modifier_groups[0], maximum_selections: 1 }] }, 1, [selected(option), selected(free)]));
  assert.equal(helpers.validateCartDraft(product, 1, [selected(free)]), null);
});
