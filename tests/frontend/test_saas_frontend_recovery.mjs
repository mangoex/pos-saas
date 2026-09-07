import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const mobileApi = readFileSync(join(root, 'apps/mobile-web/src/api.ts'), 'utf8');
const mobileApp = readFileSync(join(root, 'apps/mobile-web/src/App.tsx'), 'utf8');
const register = readFileSync(join(root, 'apps/admin-web/src/features/auth/Register.tsx'), 'utf8');
const wizard = readFileSync(join(root, 'apps/admin-web/src/features/onboarding/OnboardingWizardModal.tsx'), 'utf8');
const subscription = readFileSync(join(root, 'apps/admin-web/src/features/auth/SubscriptionStatus.tsx'), 'utf8');
const overview = readFileSync(join(root, 'apps/admin-web/src/features/dashboard/Overview.tsx'), 'utf8');
const integrations = readFileSync(join(root, 'apps/admin-web/src/features/integrations/IntegrationsHub.tsx'), 'utf8');
const landing = readFileSync(join(root, 'apps/landing-web/src/index.html'), 'utf8');
const inventoryHub = readFileSync(join(root, 'apps/admin-web/src/features/hubs/InventoryHub.tsx'), 'utf8');
const categorySubNav = readFileSync(join(root, 'apps/admin-web/src/components/CategorySubNav.tsx'), 'utf8');
const posAdminHub = readFileSync(join(root, 'apps/pos-web/src/features/admin/AdminHub.tsx'), 'utf8');

assert.match(mobileApi, /fetchStorefront/, 'the mobile client must resolve an exact storefront before loading a catalog');
assert.doesNotMatch(mobileApi, /BACKUP_CATALOG|Loading fallback catalog/, 'a failed or empty catalog must not show products from another restaurant');
assert.match(mobileApp, /restaurantos_storefront:\$\{organization\.id\}:\$\{selectedBranch\.id\}/, 'cart and favorites must be scoped to the resolved organization and branch');
assert.match(mobileApp, /manifest\.webmanifest/, 'the installed app manifest must follow the resolved storefront');
assert.match(register, /password\.length < 8/, 'signup must apply the API minimum password length');
assert.match(register, /plan:/, 'the selected plan must be submitted with signup');
assert.match(wizard, /['\"]\/saas\/onboarding['\"]/, 'the remote wizard must persist progress through tenant-owned onboarding');
assert.doesNotMatch(wizard, /seed-starter-template/, 'the SaaS wizard must not seed global fallback products');
assert.match(subscription, /\/subscription\/status/, 'subscription state must remain server-authoritative after public registration');
assert.match(wizard, /register_name/, 'the wizard must let the administrator choose the first register identifier');
assert.match(overview, /\/saas\/onboarding/, 'dashboard onboarding must resume from tenant-owned server state');
assert.doesNotMatch(overview, /restaurantos_onboarding_(completed|dismissed)/, 'dashboard onboarding may not use browser-global completion or dismissal state');
assert.match(integrations, /isDeferredProvider/, 'DiDi and Rappi must remain pending until provider validation');
assert.match(integrations, /has_client_secret[\s\S]*has_webhook_secret/, 'deferred integrations must receive only masked-secret presence flags');
assert.match(landing, /\/admin\/register\?plan=trial/, 'trial CTA must select the trial plan at registration');
assert.match(landing, /\/admin\/register\?plan=starter/, 'starter CTA must select the starter plan at registration');
assert.doesNotMatch(inventoryHub, /path: '\/(warehouses|production|inventory\/transfers)'/, 'lite inventory hub must not link to ERP-only modules');
assert.doesNotMatch(categorySubNav, /path: '\/(warehouses|production|inventory\/transfers)'/, 'lite inventory subnavigation must not link to blocked ERP modules');
assert.doesNotMatch(posAdminHub, /to: '\/administration\/(production|transfers|counts|inventory)'/, 'POS administration must not link to advanced inventory modules');

console.log('✓ SaaS frontend recovery semantic tests passed');

assert.match(mobileApp, /'menu', 'order', 'mobile'/, 'published menu paths must resolve the storefront');
assert.doesNotMatch(mobileApp, /restaurantos_selected_branch_id|kiwi_selected_branch_id/, 'branch preferences must not be browser-global');
assert.match(mobileApp, /catalogError/, 'catalog failures must show a recoverable state');

assert.match(readFileSync(join(root, 'apps/mobile-web/vite.config.ts'), 'utf8'), /base: '\/menu\/'/, 'nested and trailing-slash menu URLs must share the absolute asset root');
