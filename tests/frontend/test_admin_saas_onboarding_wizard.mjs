import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');

// 1. OnboardingWizardModal verification
const wizardModal = readFileSync(
  join(root, 'apps/admin-web/src/features/onboarding/OnboardingWizardModal.tsx'),
  'utf8'
);
assert.match(
  wizardModal,
  /fetchApi<OrganizationProfile>\('\/organization\/profile'\)/,
  'OnboardingWizardModal must query /organization/profile'
);
assert.match(
  wizardModal,
  /fetchApi<OrganizationProfile>\('\/organization\/profile',\s*\{\s*method:\s*'PATCH'/,
  'OnboardingWizardModal must support PATCH /organization/profile'
);
assert.match(
  wizardModal,
  /QRCodeCard/,
  'OnboardingWizardModal must integrate QRCodeCard for step 3'
);
assert.match(
  wizardModal,
  /redirectToPos/,
  'OnboardingWizardModal must support direct handoff to POS'
);
assert.match(
  wizardModal,
  /Cargar Menú de Muestra/i,
  'OnboardingWizardModal must include 1-click starter menu seed button'
);
assert.match(
  wizardModal,
  /const handleContinueToQr = async \(\)/,
  'OnboardingWizardModal must persist the menu step before opening QR setup'
);
assert.match(
  wizardModal,
  /step: 'menu', business_type: 'blank'/,
  'An existing menu must advance onboarding without reseeding products'
);
assert.doesNotMatch(
  wizardModal,
  /onClick=\{\(\) => setStep\(3\)\}/,
  'QR setup must not be reachable through an optimistic local-only step advance'
);
assert.match(
  wizardModal,
  /const persistRegisterStep = async \(\): Promise<boolean>/,
  'Register completion must wait for the persisted backend response'
);

// 2. QRCodeCard verification
const qrCard = readFileSync(
  join(root, 'apps/admin-web/src/features/onboarding/QRCodeCard.tsx'),
  'utf8'
);
assert.match(
  qrCard,
  /fetchApi<RestaurantLinksResponse>\('\/saas\/links'\)/,
  'QRCodeCard must obtain the canonical public URL from /saas/links'
);
assert.doesNotMatch(
  qrCard,
  /\/menu\/\$\{restaurantSlug\}\//,
  'QRCodeCard must not reconstruct a tenant URL from untrusted local state'
);
assert.match(
  qrCard,
  /navigator\.clipboard\.writeText/,
  'QRCodeCard must support copying menu link'
);
assert.match(
  qrCard,
  /api\.qrserver\.com\/v1\/create-qr-code/,
  'QRCodeCard must generate printable QR code'
);
assert.match(
  qrCard,
  /download = `menu-qr-\$\{restaurantSlug\}\.png`/,
  'QRCodeCard must provide PNG download'
);

// 3. Overview dashboard integration
const overview = readFileSync(
  join(root, 'apps/admin-web/src/features/dashboard/Overview.tsx'),
  'utf8'
);
assert.match(
  overview,
  /import \{ OnboardingWizardModal \} from '\.\.\/onboarding\/OnboardingWizardModal'/,
  'Overview must import OnboardingWizardModal'
);
assert.match(
  overview,
  /import \{ QRCodeCard \} from '\.\.\/onboarding\/QRCodeCard'/,
  'Overview must import QRCodeCard'
);
assert.match(
  overview,
  /Asistente de Configuración Inicial/i,
  'Overview must include Onboarding Quickstart Banner'
);
assert.match(
  overview,
  /<OnboardingWizardModal/,
  'Overview must render OnboardingWizardModal component'
);
assert.match(
  overview,
  /<QRCodeCard/,
  'Overview must render QRCodeCard component'
);

// 4. AdminLayout topbar integration
const adminLayout = readFileSync(
  join(root, 'apps/admin-web/src/components/AdminLayout.tsx'),
  'utf8'
);
assert.match(
  adminLayout,
  /import \{ OnboardingWizardModal \} from '\.\.\/features\/onboarding\/OnboardingWizardModal'/,
  'AdminLayout must import OnboardingWizardModal'
);
assert.match(
  adminLayout,
  /trial_days_remaining/,
  'AdminLayout must read trial_days_remaining from organization profile'
);
assert.match(
  adminLayout,
  /Asistente Inicial/,
  'AdminLayout must feature Asistente Inicial button in topbar'
);
assert.match(
  adminLayout,
  /<OnboardingWizardModal/,
  'AdminLayout must render OnboardingWizardModal component'
);

console.log('✓ All SaaS Onboarding Wizard and QR Generator semantic tests PASSED!');
