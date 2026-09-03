import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');

// 1. AdminHub.tsx verification
const adminHubContent = readFileSync(
  join(root, 'apps/pos-web/src/features/admin/AdminHub.tsx'),
  'utf8'
);

assert.equal(
  adminHubContent.includes("to: '/administration/production'"),
  false,
  'AdminHub in POS Lite must NOT include /administration/production card'
);
assert.equal(
  adminHubContent.includes("to: '/administration/transfers'"),
  false,
  'AdminHub in POS Lite must NOT include /administration/transfers card'
);
assert.equal(
  adminHubContent.includes("to: '/administration/counts'"),
  false,
  'AdminHub in POS Lite must NOT include /administration/counts card'
);
assert.equal(
  adminHubContent.includes("to: '/historical-reports'"),
  false,
  'AdminHub in POS Lite must NOT include /historical-reports card'
);

// Verify core operational cards remain
assert.equal(
  adminHubContent.includes("to: '/sales-monitor'"),
  true,
  'AdminHub must retain /sales-monitor'
);
assert.equal(
  adminHubContent.includes("to: '/administration/products'"),
  true,
  'AdminHub must retain /administration/products'
);
assert.equal(
  adminHubContent.includes("to: '/administration/waste'"),
  true,
  'AdminHub must retain /administration/waste'
);
assert.equal(
  adminHubContent.includes("to: '/administration/purchases'"),
  true,
  'AdminHub must retain /administration/purchases'
);

// 2. PosLayout.tsx verification
const posLayoutContent = readFileSync(
  join(root, 'apps/pos-web/src/components/PosLayout.tsx'),
  'utf8'
);

assert.equal(
  posLayoutContent.includes("hasPermission('cash.user_cut.read')"),
  false,
  'PosLayout must NOT grant Administración access to pure cashiers via cash.user_cut.read'
);
assert.match(
  posLayoutContent,
  /hasPermission\('branch\.admin\.access'\)\s*\|\|\s*hasPermission\('admin\.manage'\)/,
  'PosLayout must strictly gate Administración with branch.admin.access or admin.manage'
);

console.log('✓ All POS Lite consolidation semantic tests PASSED!');
