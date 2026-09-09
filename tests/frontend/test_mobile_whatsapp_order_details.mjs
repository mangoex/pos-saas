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

// 4. Verify that BranchesList.tsx defaults whatsapp_ordering_enabled to false (opt-in)
assert.match(
  branchesList,
  /whatsapp_ordering_enabled:\s*false/,
  'BranchesList.tsx must default whatsapp_ordering_enabled to false'
);

// 5. Verify that App.tsx strictly checks whatsapp_ordering_enabled === true
const appTsx = readFileSync(join(root, 'apps/mobile-web/src/App.tsx'), 'utf8');
assert.match(
  appTsx,
  /Boolean\(selectedBranch\?\.whatsapp_ordering_enabled\)\s*===\s*true/,
  'App.tsx must pass Boolean(selectedBranch?.whatsapp_ordering_enabled) === true'
);

// 6. Verify that api.ts strictly checks whatsappOrderingEnabled === true
assert.match(
  mobileApi,
  /whatsappOrderingEnabled\s*===\s*true/,
  'api.ts must only create whatsappUrl if whatsappOrderingEnabled === true'
);

// 7. Verify that OrderSuccessModal.tsx guards both redirect and button with isWhatsAppEnabled
const orderSuccessModal = readFileSync(join(root, 'apps/mobile-web/src/components/OrderSuccessModal.tsx'), 'utf8');
assert.match(
  orderSuccessModal,
  /const isWhatsAppEnabled = Boolean\(branch\?\.whatsapp_ordering_enabled\) && Boolean\(orderResult\.whatsapp_url\);/,
  'OrderSuccessModal must compute isWhatsAppEnabled based on branch.whatsapp_ordering_enabled'
);
assert.match(
  orderSuccessModal,
  /if\s*\(isWhatsAppEnabled && orderResult\.whatsapp_url/,
  'OrderSuccessModal must guard useEffect redirect with isWhatsAppEnabled'
);
assert.match(
  orderSuccessModal,
  /\{isWhatsAppEnabled && orderResult\.whatsapp_url &&/,
  'OrderSuccessModal must guard WhatsApp button with isWhatsAppEnabled'
);

console.log('✓ All Mobile WhatsApp order details tests PASSED!');
