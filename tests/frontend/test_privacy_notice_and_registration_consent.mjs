import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { resolve } from 'node:path';

const projectRoot = resolve(process.cwd());

// 1. Verify Register.tsx has privacy checkbox & modal integration
const registerPath = resolve(projectRoot, 'apps/admin-web/src/features/auth/Register.tsx');
assert.ok(existsSync(registerPath), 'Register.tsx must exist');
const registerCode = readFileSync(registerPath, 'utf8');

assert.match(registerCode, /acceptedTerms|acceptedPrivacy/i, 'Register.tsx must manage accepted terms/privacy state');
assert.match(registerCode, /type=["']checkbox["']/i, 'Register.tsx must render a consent checkbox');
assert.match(registerCode, /Aviso de Privacidad/i, 'Register.tsx must explicitly mention Aviso de Privacidad');
assert.match(registerCode, /Términos|Condiciones/i, 'Register.tsx must mention Términos y Condiciones');
assert.match(registerCode, /PrivacyPolicyModal|LegalModal/i, 'Register.tsx must incorporate a PrivacyPolicyModal or LegalModal');

// 2. Verify PrivacyPolicyModal & Page exist and contain crucial legal clauses
const modalPath = resolve(projectRoot, 'apps/admin-web/src/features/legal/PrivacyPolicyModal.tsx');
assert.ok(existsSync(modalPath), 'PrivacyPolicyModal.tsx must exist in legal feature');
const modalCode = readFileSync(modalPath, 'utf8');

assert.match(modalCode, /Aviso de Privacidad/i, 'Modal must contain Aviso de Privacidad header');
assert.match(modalCode, /ARCO/i, 'Modal must detail ARCO rights');
assert.match(modalCode, /alérgenos|alergias|salud/i, 'Modal must address allergens or health notes as sensitive data');
assert.match(modalCode, /LFPDPPP/i, 'Modal must reference applicable data protection regulations');

const pagePath = resolve(projectRoot, 'apps/admin-web/src/features/legal/PrivacyPolicyPage.tsx');
assert.ok(existsSync(pagePath), 'PrivacyPolicyPage.tsx must exist for standalone /public access');

// 3. Verify App.tsx has public legal routes
const appPath = resolve(projectRoot, 'apps/admin-web/src/App.tsx');
const appCode = readFileSync(appPath, 'utf8');
assert.match(appCode, /path=["']\/privac/i, 'App.tsx must register public privacy route (/privacy or /privacidad)');

// 4. Verify CartDrawer.tsx has allergen warning and legal disclaimer
const cartPath = resolve(projectRoot, 'apps/mobile-web/src/components/CartDrawer.tsx');
const cartCode = readFileSync(cartPath, 'utf8');
assert.match(cartCode, /alerg|celiaqu|restricci/i, 'CartDrawer.tsx must advise about severe allergies / restaurant responsibility');
assert.match(cartCode, /responsabilidad.*restaurante|calidad.*restaurante/i, 'CartDrawer.tsx must state restaurant responsibility for food and pricing');

// 5. Verify documentation file with full legal text exists
const docPath = resolve(projectRoot, 'docs/legal/AVISO_DE_PRIVACIDAD.md');
assert.ok(existsSync(docPath), 'docs/legal/AVISO_DE_PRIVACIDAD.md must exist for publishing');

console.log('✅ All privacy notice, registration consent and legal disclaimers tests passed successfully.');
