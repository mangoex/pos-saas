import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const read = (path) => readFileSync(resolve(root, path), 'utf8');

test('MobileBranchPillsBar component exists and implements horizontal swipeable pills', () => {
  const componentPath = 'apps/admin-web/src/features/mobile-admin/MobileBranchPillsBar.tsx';
  assert.ok(existsSync(resolve(root, componentPath)), 'MobileBranchPillsBar.tsx must exist');

  const source = read(componentPath);
  assert.match(source, /export const MobileBranchPillsBar/, 'Must export MobileBranchPillsBar component');
  assert.match(source, /Todas las sucursales|Todas/, 'Must contain "Todas las sucursales" option');
  assert.match(source, /overflowX:\s*['"]auto['"]|overflow-x/i, 'Must support horizontal scroll/swipe');
  assert.match(source, /onSelectBranch/, 'Must handle onSelectBranch callback');
  assert.match(source, /branchShiftStatus/, 'Must support branch shift status indicator (abierta/cerrada)');
});

test('MobileAdminShell defaults to "all" branches and integrates MobileBranchPillsBar', () => {
  const shellSource = read('apps/admin-web/src/features/mobile-admin/MobileAdminShell.tsx');
  assert.match(shellSource, /MobileBranchPillsBar/, 'MobileAdminShell must import and use MobileBranchPillsBar');
  assert.match(shellSource, /selectedBranchId.*['"]all['"]|['"]all['"].*selectedBranchId/, 'Must default selectedBranchId to "all"');
  assert.match(shellSource, /branches\s*=\s*\{/, 'Must accept branches array prop');
  assert.match(shellSource, /branchShiftStatus/, 'Must track branch shift statuses');
});

test('AdminLayout passes branches and branch selection handler to MobileAdminShell', () => {
  const layoutSource = read('apps/admin-web/src/components/AdminLayout.tsx');
  assert.match(layoutSource, /<MobileAdminShell[\s\S]*branches=\{branches\}/, 'AdminLayout must pass branches array to MobileAdminShell');
  assert.match(layoutSource, /<MobileAdminShell[\s\S]*onSelectBranch=/, 'AdminLayout must pass onSelectBranch to MobileAdminShell');
});

test('MobileOrdersMonitor supports "all" branches with branch badge on order cards', () => {
  const monitorSource = read('apps/admin-web/src/features/mobile-orders/MobileOrdersMonitor.tsx');
  assert.match(monitorSource, /branchId\s*===\s*['"]all['"]|\bbranchId\s*!==\s*['"]all['"]/, 'Must check for branchId === "all"');
  assert.match(monitorSource, /order\.branch_name|branchNameMap|badge|Sucursal/i, 'Must display branch name/badge on order when in all branches view');
});

test('MobileCashShiftTab supports multi-cash overview when branchId is "all"', () => {
  const cashSource = read('apps/admin-web/src/features/mobile-admin/MobileCashShiftTab.tsx');
  assert.match(cashSource, /branchId\s*===\s*['"]all['"]/, 'Must handle branchId === "all"');
  assert.match(cashSource, /Multicaja|Estado de Cajas|Cajas por Sucursal/i, 'Must render multicash overview when branchId is "all"');
  assert.match(cashSource, /Abrir turno|Gestionar/i, 'Must provide direct action to open or manage shift for each branch');
});

test('MobileCreateBranchModal exists and submits branch creation payload to /branches', () => {
  const modalPath = 'apps/admin-web/src/features/mobile-admin/MobileCreateBranchModal.tsx';
  assert.ok(existsSync(resolve(root, modalPath)), 'MobileCreateBranchModal.tsx must exist');

  const source = read(modalPath);
  assert.match(source, /export const MobileCreateBranchModal/, 'Must export MobileCreateBranchModal');
  assert.match(source, /fetchApi(?:<[^>]+>)?\(['"]\/branches['"]/, 'Must POST to /branches endpoint');
  assert.match(source, /method:\s*['"]POST['"]/, 'Must use POST method');
  assert.match(source, /onBranchCreated/, 'Must notify caller onBranchCreated');
  assert.match(source, /name|code/i, 'Must require branch name and code');
});

test('MobileBranchSettingsTab renders "+" new branch button and branches list selector', () => {
  const settingsSource = read('apps/admin-web/src/features/mobile-admin/MobileBranchSettingsTab.tsx');
  assert.match(settingsSource, /onOpenCreateBranch|setIsCreateModalOpen|Nueva Sucursal|\+ Sucursal/i, 'Must have a button or action to add a new branch');
  assert.match(settingsSource, /Sucursales|branches/i, 'Must render branch list or selector');
});

test('MobileBranchPillsBar supports onAddBranch "+" action', () => {
  const pillsSource = read('apps/admin-web/src/features/mobile-admin/MobileBranchPillsBar.tsx');
  assert.match(pillsSource, /onAddBranch/, 'Must accept onAddBranch callback');
  assert.match(pillsSource, /\+|Nueva/i, 'Must render "+" or "Nueva" pill when onAddBranch is provided');
});
