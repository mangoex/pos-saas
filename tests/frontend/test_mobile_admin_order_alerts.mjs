import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const output = mkdtempSync(join(tmpdir(), 'restaurantos-mobile-alerts-'));

try {
  const source = join(root, 'apps/admin-web/src/features/mobile-orders/mobileOrderAlerts.ts');
  execFileSync(process.execPath, [
    join(root, 'node_modules/typescript/bin/tsc'),
    '--target', 'ES2022',
    '--module', 'NodeNext',
    '--moduleResolution', 'NodeNext',
    '--outDir', output,
    source,
  ]);
  const alerts = await import(pathToFileURL(join(output, 'mobileOrderAlerts.js')).href);
  const at = '2026-09-13T05:00:00.000Z';
  const first = alerts.reconcileMobileOrderAlerts(null, 'branch-a', [
    { id: 'intent-a', created_at: at, status: 'PENDING', is_public_intent: true },
  ]);
  assert.deepEqual(first.newOrderIds, [], 'first load must establish a silent baseline');

  const second = alerts.reconcileMobileOrderAlerts(first.state, 'branch-a', [
    { id: 'intent-a', created_at: at, status: 'PENDING', is_public_intent: true },
    { id: 'intent-b', created_at: at, status: 'PENDING', is_public_intent: true },
  ]);
  assert.deepEqual(second.newOrderIds, ['intent-b'], 'same timestamp must not hide a new id');

  const lowerIdAtSameTime = alerts.reconcileMobileOrderAlerts(second.state, 'branch-a', [
    { id: 'intent-0', created_at: at, status: 'PENDING', is_public_intent: true },
  ]);
  assert.deepEqual(
    lowerIdAtSameTime.newOrderIds,
    ['intent-0'],
    'same-timestamp detection must not depend on random id ordering',
  );

  const replay = alerts.reconcileMobileOrderAlerts(lowerIdAtSameTime.state, 'branch-a', [
    { id: 'intent-b', created_at: at, status: 'PENDING', is_public_intent: true },
  ]);
  assert.deepEqual(replay.newOrderIds, [], 'an observed intent must not alert twice');

  const branchChange = alerts.reconcileMobileOrderAlerts(replay.state, 'branch-b', [
    { id: 'intent-c', created_at: '2026-09-13T05:01:00.000Z', status: 'PENDING', is_public_intent: true },
  ]);
  assert.deepEqual(branchChange.newOrderIds, [], 'branch changes must create a silent baseline');

  const ignored = alerts.reconcileMobileOrderAlerts(branchChange.state, 'branch-b', [
    { id: 'order-pos', created_at: '2026-09-13T05:02:00.000Z', status: 'PENDING' },
    { id: 'intent-done', created_at: '2026-09-13T05:03:00.000Z', status: 'ACCEPTED', is_public_intent: true },
  ]);
  assert.deepEqual(ignored.newOrderIds, [], 'only pending public intents may alert');

  const largeBaseline = alerts.reconcileMobileOrderAlerts(null, 'branch-large',
    Array.from({ length: 1001 }, (_, index) => ({
      id: `intent-${index}`,
      created_at: `2026-09-13T05:${String(Math.floor(index / 60)).padStart(2, '0')}:${String(index % 60).padStart(2, '0')}.000Z`,
      status: 'PENDING',
      is_public_intent: true,
    })),
  );
  const largeReplay = alerts.reconcileMobileOrderAlerts(largeBaseline.state, 'branch-large', [{
    id: 'intent-0',
    created_at: '2026-09-13T05:00:00.000Z',
    status: 'PENDING',
    is_public_intent: true,
  }]);
  assert.deepEqual(largeReplay.newOrderIds, [], 'cursor must not forget older ids after 1000 orders');

  const shell = readFileSync(join(root, 'apps/admin-web/src/features/mobile-admin/MobileAdminShell.tsx'), 'utf8');
  assert.match(shell, /MobileOrderAlertsCoordinator/, 'mobile shell must mount a persistent alert coordinator');
  assert.doesNotMatch(
    shell,
    /currentTab === ['"]orders['"][\s\S]{0,180}MobileOrderAlertsCoordinator/,
    'coordinator must not live inside the conditional orders tab',
  );

  const coordinator = readFileSync(
    join(root, 'apps/admin-web/src/features/mobile-orders/MobileOrderAlertsCoordinator.tsx'),
    'utf8',
  );
  assert.match(coordinator, /await ctx\.resume\(\)/, 'audio resume must be awaited');
  assert.match(coordinator, /ctx\.state === ['"]running['"]/, 'ready state must reflect a running context');
  assert.match(coordinator, /ctx\.onstatechange/, 'audio suspension must update the visible state');
  assert.match(coordinator, /new AbortController\(\)/, 'a stalled alert request must be aborted');
  assert.match(coordinator, /6_500/, 'poll timeout must finish before the next interval');
  assert.match(coordinator, /cache: ['"]no-store['"]/, 'alert polling must bypass browser caches');
  assert.match(
    coordinator,
    /restaurantos:mobile-order-alert/,
    'bounded operational signals must expose reconciliation and audio failures',
  );
  assert.match(
    coordinator,
    /setPendingVisualAlertIds\(\(current\) =>/,
    'visible acknowledgements must retain exact order identities',
  );
  assert.doesNotMatch(
    coordinator,
    /await playNewOrderSound\(\);\s*setPendingVisualAlertIds\(\[\]\)/,
    'automatic sound must not erase the visible new-order acknowledgement',
  );
  assert.match(
    coordinator,
    /void playNewOrderSound\(\)/,
    'audio activation must not hold the polling lock',
  );
  assert.match(coordinator, /requestSequenceRef/, 'stale polling responses must be ignored');
  assert.match(
    coordinator,
    /\/orders\/public-intent-alerts/,
    'coordinator must use the minimal public-intent alert feed',
  );
} finally {
  rmSync(output, { recursive: true, force: true });
}

console.log('Mobile admin order alert contract passed');
