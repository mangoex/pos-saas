import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const read = path => readFileSync(new URL('../../' + path, import.meta.url), 'utf8');
const view = read('apps/admin-web/src/features/domains/RestaurantLinks.tsx');
const qr = read('apps/admin-web/src/features/onboarding/QRCodeCard.tsx');
const app = read('apps/admin-web/src/App.tsx');
assert.match(view, /navigator\.clipboard\.writeText/);
assert.match(view, /canonical_menu_url/);
assert.match(view, /fullUrl=\{data.links.menu\}/, 'QR must use the exact preferred menu URL');
assert.match(view, /pending_dns:[\s\S]*pending_tls:[\s\S]*active:[\s\S]*disabled:/);
assert.match(view, /disabled=\{busy \|\| !confirmed\[domain.id\]/, 'TLS acknowledgement gates activation');
assert.match(app, /SuperadminRoute><RestaurantLinks supervision/);
assert.doesNotMatch(qr, /`\/r\//, 'Printed QR must use the supported menu route');
assert.match(qr, /window.open\(resolvedUrl/, 'Preview and QR must open the same URL');
console.log('Restaurant links / supervised domains UI contract passed');
