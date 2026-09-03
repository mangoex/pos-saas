import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');

// 1. CatalogHub verification
const catalogHub = readFileSync(join(root, 'apps/admin-web/src/features/hubs/CatalogHub.tsx'), 'utf8');
assert.equal(
  catalogHub.includes("path: '/recipes'"),
  false,
  'CatalogHub in Lite version must NOT include recipes card (costeo gramo por gramo desactivado)'
);
assert.equal(catalogHub.includes("title: 'Productos'"), true, 'CatalogHub must include Productos');
assert.equal(catalogHub.includes("title: 'Categorías'"), true, 'CatalogHub must include Categorías');

// 2. AdminAccessHub verification
const adminAccessHub = readFileSync(join(root, 'apps/admin-web/src/features/hubs/AdminAccessHub.tsx'), 'utf8');
assert.equal(
  adminAccessHub.includes("path: '/imports'"),
  false,
  'AdminAccessHub in Lite version must NOT include legacy mass imports card'
);
assert.equal(adminAccessHub.includes("title: 'Usuarios y Cuentas'"), true, 'AdminAccessHub must include Usuarios');
assert.equal(adminAccessHub.includes("title: 'Directorio de Clientes'"), true, 'AdminAccessHub must include Clientes');

// 3. BranchesHub verification
const branchesHub = readFileSync(join(root, 'apps/admin-web/src/features/hubs/BranchesHub.tsx'), 'utf8');
assert.equal(
  branchesHub.includes("path: '/cash-concepts'"),
  false,
  'BranchesHub must NOT include cash-concepts card; it belongs to ReportsHub'
);
assert.match(
  branchesHub,
  /Canales de Delivery/i,
  'BranchesHub must feature dedicated Delivery Channels card'
);
assert.match(
  branchesHub,
  /Facturación/i,
  'BranchesHub must feature dedicated Invoicing/SAT card separated from delivery channels'
);

// 4. ReportsHub verification
const reportsHub = readFileSync(join(root, 'apps/admin-web/src/features/hubs/ReportsHub.tsx'), 'utf8');
assert.equal(
  reportsHub.includes("path: '/cash-concepts'"),
  true,
  'ReportsHub must include cash-concepts card'
);

// 5. CategorySubNav verification
const subnav = readFileSync(join(root, 'apps/admin-web/src/components/CategorySubNav.tsx'), 'utf8');
const reportsHubBlock = subnav.slice(subnav.indexOf("hubPath: '/reports-hub'"));
const branchesHubBlock = subnav.slice(subnav.indexOf("hubPath: '/branches-hub'"), subnav.indexOf("hubPath: '/reports-hub'"));

assert.equal(
  branchesHubBlock.includes("path: '/cash-concepts'"),
  false,
  'CategorySubNav must NOT place cash-concepts inside branches-hub'
);
assert.equal(
  reportsHubBlock.includes("path: '/cash-concepts'"),
  true,
  'CategorySubNav MUST place cash-concepts inside reports-hub'
);

// 6. AdminLayout matching prefixes
const layout = readFileSync(join(root, 'apps/admin-web/src/components/AdminLayout.tsx'), 'utf8');
const branchesCategoryConfig = layout.slice(layout.indexOf("path: '/branches-hub'"), layout.indexOf("path: '/reports-hub'"));
const reportsCategoryConfig = layout.slice(layout.indexOf("path: '/reports-hub'"), layout.indexOf("path: '/admin-access-hub'"));

assert.equal(
  branchesCategoryConfig.includes("'/cash-concepts'"),
  false,
  'AdminLayout must not associate /cash-concepts to branches-hub'
);
assert.equal(
  reportsCategoryConfig.includes("'/cash-concepts'"),
  true,
  'AdminLayout must associate /cash-concepts to reports-hub'
);

console.log('✓ All Lite Admin consolidation semantic tests PASSED!');
