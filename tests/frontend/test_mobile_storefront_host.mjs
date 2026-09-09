import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const read = path => readFileSync(new URL('../../' + path, import.meta.url), 'utf8');
const api = read('apps/mobile-web/src/api.ts');
const app = read('apps/mobile-web/src/App.tsx');
const qr = read('apps/admin-web/src/features/onboarding/QRCodeCard.tsx');
const wizard = read('apps/admin-web/src/features/onboarding/OnboardingWizardModal.tsx');

assert.match(api, /public\/storefront-context/, 'wildcard resolution must ask the backend for host context');
assert.match(app, /fetchStorefrontContext/, 'root mobile view must resolve a backend host context');
assert.match(app, /storefront-context\/manifest\.webmanifest/, 'wildcard manifest must remain root-scoped');
assert.doesNotMatch(app, /location\.hostname/, 'browser hostname must not become tenant authority');
assert.match(app, /fetchStorefront\(storefrontIdentifier\)/, 'legacy path storefront links remain supported');
assert.match(qr, /fetchApi[\s\S]*\/saas\/links/, 'every QR fallback must obtain its authoritative menu URL');
assert.doesNotMatch(qr, /window\.location\.origin/, 'QR fallback must not infer a public tenant URL in the browser');
assert.doesNotMatch(wizard, /\/menu\/\{currentSlug\}\//, 'onboarding must not display a stale legacy-only URL');
console.log('Mobile storefront host-context contract passed');
