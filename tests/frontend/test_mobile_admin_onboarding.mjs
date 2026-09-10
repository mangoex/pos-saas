import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');

// 1. MobileAdminShell integration
const shellPath = join(root, 'apps/admin-web/src/features/mobile-admin/MobileAdminShell.tsx');
assert.equal(existsSync(shellPath), true);
const shellCode = readFileSync(shellPath, 'utf8');

assert.match(shellCode, /import\s*\{\s*OnboardingWizardModal\s*\}\s*from/, 'MobileAdminShell must import OnboardingWizardModal');
assert.match(shellCode, /\/saas\/onboarding/, 'MobileAdminShell must query /saas/onboarding');
assert.match(shellCode, /Asistente de configuración inicial móvil/, 'MobileAdminShell must feature mobile onboarding banner');
assert.match(shellCode, /<OnboardingWizardModal/, 'MobileAdminShell must render OnboardingWizardModal');
assert.match(shellCode, /onOpenOnboarding=/, 'MobileAdminShell must pass onOpenOnboarding handler to settings tab');

// 2. MobileBranchSettingsTab integration
const settingsPath = join(root, 'apps/admin-web/src/features/mobile-admin/MobileBranchSettingsTab.tsx');
assert.equal(existsSync(settingsPath), true);
const settingsCode = readFileSync(settingsPath, 'utf8');
assert.match(settingsCode, /onOpenOnboarding\?:/, 'MobileBranchSettingsTab must declare onOpenOnboarding prop');
assert.match(settingsCode, /Asistente de Menú y QR/, 'MobileBranchSettingsTab must feature Asistente de Menú y QR card');

// 3. OnboardingWizardModal 3-option menu setup
const wizardPath = join(root, 'apps/admin-web/src/features/onboarding/OnboardingWizardModal.tsx');
const wizardCode = readFileSync(wizardPath, 'utf8');
assert.match(wizardCode, /Con IA por Tipo/, 'OnboardingWizardModal must offer Con IA por Tipo option');
assert.match(wizardCode, /Subir Carta/, 'OnboardingWizardModal must offer Subir Carta option');
assert.match(wizardCode, /Tomar foto\/Cargar carta/, 'OnboardingWizardModal must provide Tomar foto/Cargar carta button');
assert.doesNotMatch(wizardCode, /capture="environment"/, 'OnboardingWizardModal must not use capture="environment" to allow both camera and gallery');
assert.match(wizardCode, />\s*Manual\s*</, 'OnboardingWizardModal must offer Manual option');
assert.match(wizardCode, /Continuar con catálogo en blanco/, 'OnboardingWizardModal must provide Continuar con catálogo en blanco');

console.log('✓ All Mobile Admin Onboarding semantic tests PASSED!');
