import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const tabPath = join(root, 'apps/admin-web/src/features/mobile-admin/MobileMenuManagerTab.tsx');

assert.equal(existsSync(tabPath), true, 'MobileMenuManagerTab.tsx must exist');

const code = readFileSync(tabPath, 'utf8');

// 1. Label verification
const uploadLabels = code.match(/Tomar foto\/Cargar/g);
assert.ok(
  uploadLabels && uploadLabels.length >= 2,
  'MobileMenuManagerTab must feature "Tomar foto/Cargar" for both products and categories'
);

// 2. Freedom to choose Gallery (no restrictive capture="environment")
assert.doesNotMatch(
  code,
  /capture="environment"/,
  'MobileMenuManagerTab must not use capture="environment", allowing users to pick from Gallery as well as Camera'
);

// 3. File upload handler support for both targets
assert.match(
  code,
  /handlePhotoUpload\s*=\s*\([^)]*target:\s*'product'\s*\|\s*'category'/,
  'handlePhotoUpload must support both product and category photo processing'
);

// 4. Category modal must have photo preview and removal
assert.match(
  code,
  /setCategoryForm\(\(prev\)\s*=>\s*\(\{\s*\.\.\.prev,\s*image_url:\s*compressed\s*\}\)\)/,
  'Category modal must handle compressed image URL assignment'
);

assert.match(
  code,
  /alt="Vista previa categoría"/,
  'Category modal must render preview when photo is loaded'
);

// 5. Presets available for quick covers
assert.match(
  code,
  /Portadas apetitosas sugeridas:/,
  'Category modal must offer quick preset cover suggestions'
);

console.log('\u2713 All Mobile Admin Photo & Gallery semantic tests PASSED!');
