import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdtempSync, rmSync, readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
const root = resolve(import.meta.dirname, '../..');
const tmp = mkdtempSync(join(tmpdir(), 'pickup-grace-'));
try {
  execFileSync(process.execPath, [join(root, 'node_modules/typescript/bin/tsc'), '--target', 'ES2022', '--module', 'CommonJS', '--skipLibCheck', '--outDir', tmp, join(root, 'packages/ui/src/utils/pickupGrace.ts')]);
  const { parsePickupGraceMinutes, pickupGraceMessage } = createRequire(import.meta.url)(join(tmp, 'pickupGrace.js'));
  assert.equal(parsePickupGraceMinutes('  '), null);
  for (const raw of ['1', '30', '2147483647']) assert.equal(parsePickupGraceMinutes(raw), Number(raw));
  for (const raw of ['0', '-1', '1.5', '1e2', 'abc', '2147483648']) assert.throws(() => parsePickupGraceMinutes(raw));
  assert.equal(pickupGraceMessage('takeaway', 30), 'Respetaremos tu pedido durante 30 minutos después de tu hora programada para recoger.');
  assert.match(pickupGraceMessage('takeaway', 1), /1 minuto después/);
  for (const v of [undefined, null, 0, -1, 1.5, Infinity]) assert.equal(pickupGraceMessage('takeaway', v), null);
  for (const mode of ['delivery', 'dine-in']) assert.equal(pickupGraceMessage(mode, 30), null);
  const admin = readFileSync(join(root, 'apps/admin-web/src/features/mobile-admin/MobileBranchSettingsTab.tsx'), 'utf8');
  assert.ok(admin.indexOf('pickup-grace-minutes') < admin.indexOf('Comer en el Establecimiento'));
  assert.match(admin, /pickup_grace_minutes: pickupGrace/);
  const cart = readFileSync(join(root, 'apps/mobile-web/src/components/CartDrawer.tsx'), 'utf8');
  assert.match(cart, /pickupGraceMessage\(orderType, selectedBranch\?\.pickup_grace_minutes\)/);
  console.log('PASS: optional minutes, validation, conditional notice and UI integration');
} finally { rmSync(tmp, { recursive: true, force: true }); }
