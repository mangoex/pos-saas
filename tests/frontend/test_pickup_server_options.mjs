import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import test from 'node:test';

const root = resolve(import.meta.dirname, '../..');
const tmp = mkdtempSync(join(tmpdir(), 'pickup-server-'));
execFileSync(process.execPath, [join(root, 'node_modules/typescript/bin/tsc'),
  '--target', 'ES2022', '--module', 'CommonJS', '--skipLibCheck', '--outDir', tmp,
  join(root, 'apps/mobile-web/src/utils/pickupSchedule.ts')]);
const { parsePickupOptions, validatePickupSelection, createPickupOptionsLoader } =
  createRequire(import.meta.url)(join(tmp, 'utils/pickupSchedule.js'));
process.on('exit', () => rmSync(tmp, { recursive: true, force: true }));

const projection = (time = '16:15') => ({
  generated_at: '2026-09-28T22:00:00+00:00', timezone: 'America/Chihuahua', configured: true,
  days: Array.from({ length: 7 }, (_, day_index) => ({
    date: `2026-${day_index < 3 ? '09' : '10'}-${String(day_index < 3 ? 28 + day_index : day_index - 2).padStart(2, '0')}`,
    day_index, is_today: day_index === 0, is_past: false, is_closed: day_index !== 0,
    slots: day_index === 0 ? [{ value: time, scheduled_at: '2026-09-28T22:15:00+00:00' }] : [],
  })),
});

test('server projection preserves exact slots; invalid or missing data fails closed', () => {
  const data = projection();
  assert.deepEqual(parsePickupOptions(data), data);
  for (const bad of [null, {}, { ...data, configured: 'false' },
    { ...data, days: [] }, { ...data, days: [{ ...data.days[0], slots: [{}] }, ...data.days.slice(1)] }]) {
    assert.throws(() => parsePickupOptions(bad), /pickup_options_invalid/);
  }
});

test('revalidation rejects expired dates/times instead of substituting a new slot', () => {
  assert.doesNotThrow(() => validatePickupSelection(projection(), '2026-09-28', '16:15'));
  assert.throws(() => validatePickupSelection(projection('16:30'), '2026-09-28', '16:15'), /pickup_slot_unavailable/);
  assert.throws(() => validatePickupSelection(projection(), '2026-10-05', '16:15'), /pickup_slot_unavailable/);
  assert.throws(() => validatePickupSelection(projection(), '', ''), /pickup_slot_unavailable/);
  const unconfigured = { ...projection(), configured: false, days: projection().days.map(day => ({ ...day, slots: [], is_closed: true })) };
  assert.doesNotThrow(() => validatePickupSelection(unconfigured, '', ''));
  assert.throws(() => validatePickupSelection(unconfigured, '2026-09-28', '16:15'), /pickup_slot_unavailable/);
});

test('late branch A response cannot replace branch B, even if transport ignores abort', async () => {
  const requests = [];
  const published = [];
  const loader = createPickupOptionsLoader((key, signal) => new Promise(resolveFetch => requests.push({ key, signal, resolveFetch })),
    (key, data) => published.push({ key, data }));
  const a = loader.load('branch-a');
  const b = loader.load('branch-b');
  requests[1].resolveFetch(projection('17:00'));
  await b;
  requests[0].resolveFetch(projection());
  await assert.rejects(a, /pickup_request_superseded/);
  assert.equal(requests[0].signal.aborted, true);
  assert.deepEqual(published.map(x => x.key), ['branch-b']);
  assert.equal(published[0].data.days[0].slots[0].value, '17:00');
});

test('dispose prevents pending responses from reaching an unmounted cart', async () => {
  let finish;
  let published = false;
  const loader = createPickupOptionsLoader(() => new Promise(resolveFetch => { finish = resolveFetch; }), () => { published = true; });
  const pending = loader.load('branch-a');
  loader.dispose();
  finish(projection());
  await assert.rejects(pending, /pickup_request_superseded/);
  assert.equal(published, false);
});
