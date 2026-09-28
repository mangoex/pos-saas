// SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-mobile-order-recovery-tests-v1
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import vm from 'node:vm';
import test from 'node:test';

const require = createRequire(import.meta.url);
const ts = require('typescript');
const sourcePath = 'apps/admin-web/src/features/mobile-orders/mobileOrderRecovery.ts';
const scope = { organizationId: 'org-a', branchId: 'branch-a', actorId: 'actor-a', orderId: 'order-a' };

function harness() {
  const source = readFileSync(sourcePath, 'utf8');
  const exports = {};
  vm.runInNewContext(ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText, { exports });
  const data = new Map();
  const calls = [];
  let token = 'session-a';
  let serial = 0;
  let paid = false;
  let delivered = false;
  let losePayment = false;
  let loseDelivery = false;
  const receipts = new Map();
  let queue = Promise.resolve();
  const canonical = () => ({ id: scope.orderId, organization_id: scope.organizationId,
    branch_id: scope.branchId, total_cents: 34900, status: delivered ? 'DELIVERED' : 'READY',
    payment_status: paid ? 'CONFIRMED' : 'PENDING' });
  const dependencies = {
    storage: { getItem: (k) => data.get(k) ?? null, setItem: (k, v) => data.set(k, v),
      removeItem: (k) => data.delete(k) },
    currentSession: () => token,
    newKey: () => `00000000-0000-4000-8000-${String(++serial).padStart(12, '0')}`,
    lock: (_name, fn) => {
      const result = queue.then(fn);
      queue = result.catch(() => {});
      return result;
    },
    api: async (path, options) => {
      if (!options?.method) return canonical();
      calls.push({ path, ...options });
      const key = options.headers['Idempotency-Key'];
      if (path.endsWith('/payments')) {
        if (!receipts.has(key)) {
          assert.equal(paid, false, 'must not create a second payment');
          paid = true;
          receipts.set(key, { id: 'receipt-original', status: 'CONFIRMED',
            method: 'cash', amount_cents: 34900 });
        }
        if (losePayment) { losePayment = false; throw new Error('response lost'); }
        return receipts.get(key);
      }
      delivered = true;
      if (loseDelivery) { loseDelivery = false; throw new Error('delivery response lost'); }
      return { id: scope.orderId, status: 'DELIVERED' };
    },
  };
  const run = (action = 'pay', overrides = {}) => exports.runMobileOrderCommand({
    scope, action, method: 'cash', registerId: 'CAJA-01', session: 'session-a', ...overrides,
  }, dependencies);
  return { run, data, calls, dependencies, receipts,
    losePayment: () => { losePayment = true; }, loseDelivery: () => { loseDelivery = true; },
    switchSession: () => { token = 'session-b'; } };
}

test('mobile handlers do not create a different financial identity on every retry', () => {
  const modal = readFileSync('apps/admin-web/src/features/mobile-orders/MobileOrderDetailModal.tsx', 'utf8');
  assert.doesNotMatch(modal, /(?:pay-mobile|mobile-fulfill).*Date\.now\(\)/);
  assert.match(modal, /runMobileOrderCommand/);
});

test('lost payment response replays the original body and returns the original receipt after reload', async () => {
  const h = harness();
  h.losePayment();
  await assert.rejects(h.run(), /response lost/);
  assert.equal(h.data.size, 1);
  const recovered = await h.run();
  assert.equal(recovered.payment.id, 'receipt-original');
  assert.equal(h.calls[0].body, h.calls[1].body);
  assert.equal(h.calls[0].headers['Idempotency-Key'], h.calls[1].headers['Idempotency-Key']);
  assert.equal(h.receipts.size, 1);
  assert.equal(h.data.size, 0);
});

test('delivery retry keeps its identity and does not pay again', async () => {
  const h = harness();
  h.loseDelivery();
  await assert.rejects(h.run('pay_and_deliver'), /delivery response lost/);
  await h.run('pay_and_deliver');
  const payments = h.calls.filter((c) => c.path.endsWith('/payments'));
  const deliveries = h.calls.filter((c) => c.path.endsWith('/deliver'));
  assert.equal(payments.length, 1);
  assert.equal(deliveries.length, 2);
  assert.equal(deliveries[0].headers['Idempotency-Key'], deliveries[1].headers['Idempotency-Key']);
});

test('two tabs serialize before rereading canonical state', async () => {
  const h = harness();
  await Promise.all([h.run(), h.run()]);
  assert.equal(h.calls.filter((c) => c.path.endsWith('/payments')).length, 1);
});

test('changed payload and session cannot consume the unresolved payment', async () => {
  const h = harness();
  h.losePayment();
  await assert.rejects(h.run(), /response lost/);
  await assert.rejects(h.run('pay', { method: 'card' }), /pendiente/i);
  assert.equal(h.calls.length, 1);
  h.switchSession();
  await assert.rejects(h.run(), /sesión/i);
  assert.equal(h.calls.length, 1);
  assert.equal(h.data.size, 1);
});

test('storage denied or corrupt and missing cross-tab locking fail before payment', async () => {
  const denied = harness();
  denied.dependencies.storage.setItem = () => { throw new Error('storage denied'); };
  await assert.rejects(denied.run(), /storage denied/);
  assert.equal(denied.calls.length, 0);
  const corrupt = harness();
  corrupt.dependencies.storage.getItem = () => 'broken JSON';
  await assert.rejects(corrupt.run(), /recuperación/i);
  assert.equal(corrupt.calls.length, 0);
  const noLock = harness();
  noLock.dependencies.lock = undefined;
  await assert.rejects(noLock.run(), /pestañas/i);
  assert.equal(noLock.calls.length, 0);
});

test('session change after payment cannot continue delivery in the new session', async () => {
  const h = harness();
  const api = h.dependencies.api;
  h.dependencies.api = async (path, options) => {
    const response = await api(path, options);
    if (path.endsWith('/payments')) h.switchSession();
    return response;
  };
  await assert.rejects(h.run('pay_and_deliver'), /sesión/i);
  assert.equal(h.calls.length, 1);
  assert.equal(h.data.size, 1);
});

test('failed persistence after payment confirmation leaves the original command recoverable', async () => {
  const h = harness();
  const write = h.dependencies.storage.setItem;
  let writes = 0;
  h.dependencies.storage.setItem = (k, v) => {
    if (++writes === 2) throw new Error('storage denied after commit');
    write(k, v);
  };
  await assert.rejects(h.run(), /storage denied after commit/);
  assert.equal(h.receipts.size, 1);
  const result = await h.run();
  assert.equal(result.payment.id, 'receipt-original');
  assert.equal(h.calls[0].headers['Idempotency-Key'], h.calls[1].headers['Idempotency-Key']);
  assert.equal(h.receipts.size, 1);
});

test('a foreign tenant cannot reuse the original namespace or canonical order', async () => {
  const h = harness();
  h.losePayment();
  await assert.rejects(h.run(), /response lost/);
  const original = [...h.data.entries()];
  await assert.rejects(h.run('pay', { scope: { ...scope, organizationId: 'org-b', actorId: 'actor-b' } }), /contexto/i);
  assert.deepEqual([...h.data.entries()], original);
  assert.equal(h.calls.length, 1);
  assert.doesNotMatch(original[0][1], /session-a|customer|email|phone|address|card_token/);
});

test('uncertain delivery blocks switching workflow and retains its original key', async () => {
  const h = harness();
  h.loseDelivery();
  await assert.rejects(h.run('pay_and_deliver'), /delivery response lost/);
  await assert.rejects(h.run('pay'), /pendiente/i);
  assert.equal(h.calls.length, 2);
  await h.run('pay_and_deliver');
  assert.equal(h.calls.length, 3);
});
