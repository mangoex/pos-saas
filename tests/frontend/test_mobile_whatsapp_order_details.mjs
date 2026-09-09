import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');

// 1. Verify that apps/mobile-web/src/api.ts includes modifiers and detailed order types in generateWhatsAppOrderUrl
const mobileApi = readFileSync(join(root, 'apps/mobile-web/src/api.ts'), 'utf8');

assert.match(
  mobileApi,
  /item\.modifiers/,
  'mobile-web api.ts must iterate item.modifiers in generateWhatsAppOrderUrl'
);
assert.match(
  mobileApi,
  /Adicional:/,
  'mobile-web api.ts must include Adicional: label for modifiers in WhatsApp text'
);
assert.match(
  mobileApi,
  /Para Comer Aquí/,
  'mobile-web api.ts must format dine-in label in WhatsApp text'
);
assert.match(
  mobileApi,
  /Envío a Domicilio/,
  'mobile-web api.ts must format delivery label in WhatsApp text'
);

// 2. Verify that BranchesList.tsx includes whatsapp_ordering_enabled
const branchesList = readFileSync(join(root, 'apps/admin-web/src/features/branches/BranchesList.tsx'), 'utf8');
assert.match(
  branchesList,
  /whatsapp_ordering_enabled/,
  'BranchesList.tsx must include whatsapp_ordering_enabled in state/form'
);

// 3. Verify that BranchInfo in mobile-web types.ts includes whatsapp_ordering_enabled
const mobileTypes = readFileSync(join(root, 'apps/mobile-web/src/types.ts'), 'utf8');
assert.match(
  mobileTypes,
  /whatsapp_ordering_enabled\?: boolean/,
  'mobile-web types.ts must include whatsapp_ordering_enabled in BranchInfo'
);

console.log('✓ All Mobile WhatsApp order details tests PASSED!');
