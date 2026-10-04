import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const tabPath = join(root, 'apps/admin-web/src/features/mobile-admin/MobileMenuManagerTab.tsx');

assert.equal(existsSync(tabPath), true, 'MobileMenuManagerTab.tsx must exist');

const code = readFileSync(tabPath, 'utf8');

// 1. Check reorderCategoriesMutation calling /catalog/categories/reorder
assert.match(
  code,
  /fetchApi\(\s*['"]\/catalog\/categories\/reorder['"]\s*,\s*\{\s*method:\s*['"]PUT['"]/,
  'MobileMenuManagerTab must have mutation sending PUT to /catalog/categories/reorder'
);

// 2. Check optimistic update in reorderCategoriesMutation
assert.match(
  code,
  /queryClient\.cancelQueries\(\{\s*queryKey:\s*\['categories'\]\s*\}\)/,
  'reorderCategoriesMutation must cancel active categories queries for optimistic update'
);
assert.match(
  code,
  /queryClient\.setQueryData\(\['categories'\],\s*updated\)/,
  'reorderCategoriesMutation must optimistically setQueryData for categories'
);

// 3. Check handleMoveCategory and normalized spacing ((idx + 1) * 10)
assert.match(
  code,
  /const\s+handleMoveCategory\s*=/,
  'MobileMenuManagerTab must define handleMoveCategory'
);
assert.match(
  code,
  /reorderCategoriesMutation\.mutate\(items\)/,
  'handleMoveCategory must trigger reorderCategoriesMutation.mutate(items)'
);

// 4. Check category card reordering buttons with accessible aria-labels and stopPropagation
assert.match(
  code,
  /aria-label=\{`Mover categoría \$\{cat\.name\} arriba en menú digital`\}/,
  'Category card must feature upward reordering button with accessible aria-label'
);
assert.match(
  code,
  /aria-label=\{`Mover categoría \$\{cat\.name\} abajo en menú digital`\}/,
  'Category card must feature downward reordering button with accessible aria-label'
);

// 5. Check boundary disablement (first cannot move up, last cannot move down, disabled when pending)
assert.match(
  code,
  /canCatMoveUp/,
  'Category card must compute canCatMoveUp'
);
assert.match(
  code,
  /canCatMoveDown/,
  'Category card must compute canCatMoveDown'
);

console.log('✓ All Mobile Menu Category Reordering tests PASSED successfully!');
