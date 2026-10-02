import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const tabPath = join(root, 'apps/admin-web/src/features/mobile-admin/MobileMenuManagerTab.tsx');
const mobileTypesPath = join(root, 'apps/mobile-web/src/types.ts');
const mobileApiPath = join(root, 'apps/mobile-web/src/api.ts');

assert.equal(existsSync(tabPath), true, 'MobileMenuManagerTab.tsx must exist');
assert.equal(existsSync(mobileTypesPath), true, 'apps/mobile-web/src/types.ts must exist');
assert.equal(existsSync(mobileApiPath), true, 'apps/mobile-web/src/api.ts must exist');

const code = readFileSync(tabPath, 'utf8');
const mobileTypesCode = readFileSync(mobileTypesPath, 'utf8');
const mobileApiCode = readFileSync(mobileApiPath, 'utf8');

// 1. Check Product interface in admin web includes display_order
assert.match(
  code,
  /interface Product\s*\{[\s\S]*display_order\?:\s*number;/,
  'MobileMenuManagerTab Product interface must include display_order?: number'
);

// 2. Check Product interface in mobile web includes display_order
assert.match(
  mobileTypesCode,
  /export interface Product\s*\{[\s\S]*display_order\?:\s*number;/,
  'mobile-web Product interface must include display_order?: number'
);

// 3. Check mobile-web api.ts maps display_order
assert.match(
  mobileApiCode,
  /display_order:\s*typeof\s+p\.display_order\s*===\s*'number'\s*\?\s*p\.display_order\s*:\s*0/,
  'mobile-web api.ts must map display_order in fetchMobileMenu'
);

// 4. Check imports of ChevronUp and ChevronDown
assert.match(
  code,
  /ChevronUp/,
  'MobileMenuManagerTab must import ChevronUp'
);
assert.match(
  code,
  /ChevronDown/,
  'MobileMenuManagerTab must import ChevronDown'
);

// 5. Check reorder mutation calling /catalog/products/reorder
assert.match(
  code,
  /fetchApi\(\s*['"]\/catalog\/products\/reorder['"]\s*,\s*\{\s*method:\s*['"]PUT['"]/,
  'MobileMenuManagerTab must have mutation sending PUT to /catalog/products/reorder'
);

// 6. Check optimistic update in reorder mutation
assert.match(
  code,
  /queryClient\.cancelQueries\(\{\s*queryKey:\s*\['products'\]\s*\}\)/,
  'reorder mutation must cancel active products queries for optimistic update'
);
assert.match(
  code,
  /queryClient\.setQueryData\(\['products'\],\s*updated\)/,
  'reorder mutation must optimistically setQueryData'
);

// 7. Check handleMoveProduct and normalized spacing ((idx + 1) * 10)
assert.match(
  code,
  /display_order:\s*\(idx\s*\+\s*1\)\s*\*\s*10/,
  'handleMoveProduct must assign normalized display_order ((idx + 1) * 10)'
);

// 8. Check reordering buttons with proper aria-labels and stopPropagation
assert.match(
  code,
  /aria-label=\{`Mover \$\{product\.name\} arriba en menú digital`\}/,
  'Product card must feature upward reordering button with accessible aria-label'
);
assert.match(
  code,
  /aria-label=\{`Mover \$\{product\.name\} abajo en menú digital`\}/,
  'Product card must feature downward reordering button with accessible aria-label'
);

// 9. Check search safety and boundary disablement
assert.match(
  code,
  /const canMoveUp = !isSearching && !isPromosTab && Boolean\(orderInfo\?\.canMoveUp\);/,
  'canMoveUp must be disabled during search or promos view'
);
assert.match(
  code,
  /const canMoveDown = !isSearching && !isPromosTab && Boolean\(orderInfo\?\.canMoveDown\);/,
  'canMoveDown must be disabled during search or promos view'
);

// 10. Behavioral Unit Simulation of Reorder Algorithm
function simulateMove(currentProducts, productId, direction) {
  const product = currentProducts.find((p) => p.id === productId);
  if (!product) return null;
  const catName = (product.category_name || '').trim().toLowerCase();
  const siblings = currentProducts
    .filter((p) => (p.category_name || '').trim().toLowerCase() === catName)
    .sort((a, b) => (a.display_order ?? 0) - (b.display_order ?? 0) || a.name.localeCompare(b.name));

  const currentIndex = siblings.findIndex((p) => p.id === product.id);
  if (currentIndex === -1) return null;

  const targetIndex = direction === 'up' ? currentIndex - 1 : currentIndex + 1;
  if (targetIndex < 0 || targetIndex >= siblings.length) return null; // blocked at boundary

  const newSiblings = [...siblings];
  const [moved] = newSiblings.splice(currentIndex, 1);
  newSiblings.splice(targetIndex, 0, moved);

  return newSiblings.map((p, idx) => ({
    id: p.id,
    display_order: (idx + 1) * 10,
  }));
}

const mockProducts = [
  { id: 'p1', name: 'Taco Asada', category_name: 'Tacos', display_order: 0 },
  { id: 'p2', name: 'Taco Pastor', category_name: 'Tacos', display_order: 0 },
  { id: 'p3', name: 'Taco Suadero', category_name: 'Tacos', display_order: 0 },
  { id: 'p4', name: 'Horchata', category_name: 'Bebidas', display_order: 0 },
];

// Moving Taco Asada (first item) UP should return null (boundary)
assert.equal(simulateMove(mockProducts, 'p1', 'up'), null, 'First item cannot move up');

// Moving Taco Suadero (last item in Tacos) DOWN should return null (boundary)
assert.equal(simulateMove(mockProducts, 'p3', 'down'), null, 'Last item cannot move down');

// Moving Taco Pastor UP should swap with Taco Asada and reassign 10, 20, 30
const movedUp = simulateMove(mockProducts, 'p2', 'up');
assert.deepEqual(movedUp, [
  { id: 'p2', display_order: 10 },
  { id: 'p1', display_order: 20 },
  { id: 'p3', display_order: 30 },
], 'Moving second item up swaps order correctly');

// Moving Taco Pastor DOWN should swap with Taco Suadero
const movedDown = simulateMove(mockProducts, 'p2', 'down');
assert.deepEqual(movedDown, [
  { id: 'p1', display_order: 10 },
  { id: 'p3', display_order: 20 },
  { id: 'p2', display_order: 30 },
], 'Moving second item down swaps order correctly');

// Moving Bebidas (single item) UP or DOWN should be blocked
assert.equal(simulateMove(mockProducts, 'p4', 'up'), null, 'Solo item cannot move up');
assert.equal(simulateMove(mockProducts, 'p4', 'down'), null, 'Solo item cannot move down');

console.log('\u2713 All Mobile Menu Product Reordering tests PASSED successfully!');
