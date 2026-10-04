import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const pickerPath = join(root, 'apps/admin-web/src/features/mobile-admin/PantonePalettePicker.tsx');
const dataPath = join(root, 'apps/admin-web/src/features/mobile-admin/pantonePaletteData.ts');

assert.equal(existsSync(pickerPath), true, 'PantonePalettePicker.tsx must exist');
assert.equal(existsSync(dataPath), true, 'pantonePaletteData.ts must exist');

const pickerCode = readFileSync(pickerPath, 'utf8');
const dataCode = readFileSync(dataPath, 'utf8');

// 1. Check resolvePantoneSwatch is defined in pantonePaletteData.ts
assert.match(
  dataCode,
  /export\s+function\s+resolvePantoneSwatch\s*\(/,
  'pantonePaletteData.ts must export resolvePantoneSwatch'
);

// 2. Check PantonePalettePicker imports and uses resolvePantoneSwatch
assert.match(
  pickerCode,
  /resolvePantoneSwatch/,
  'PantonePalettePicker must import and use resolvePantoneSwatch'
);

// 3. Check PantonePalettePicker provides an editable input for the hex color code
assert.match(
  pickerCode,
  /aria-label=['"]Código de color hexadecimal['"]/,
  'PantonePalettePicker must include an accessible editable input for the hex color code'
);

// 4. Check native color input for visual color picking
assert.match(
  pickerCode,
  /type=['"]color['"]/,
  'PantonePalettePicker must include a color type input for visual color picking'
);

// 5. Check hex input state and handlers
assert.match(
  pickerCode,
  /const\s+\[hexInput,\s*setHexInput\]\s*=\s*useState/,
  'PantonePalettePicker must maintain hexInput state'
);
assert.match(
  pickerCode,
  /handleHexInputChange/,
  'PantonePalettePicker must have handleHexInputChange'
);
assert.match(
  pickerCode,
  /handleNativeColorChange/,
  'PantonePalettePicker must have handleNativeColorChange'
);

console.log('✓ All Mobile Palette Custom Hex tests PASSED successfully!');
