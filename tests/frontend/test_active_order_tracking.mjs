import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import vm from 'node:vm';
import test from 'node:test';

const ts = createRequire(import.meta.url)('typescript');
const source = readFileSync('apps/mobile-web/src/components/ActiveOrderTracker.tsx', 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: {
  module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.React,
  esModuleInterop: true,
} }).outputText;
const tracked = (reference, status = 'ACCEPTED') => ({ public_reference: reference,
  status, total_cents: 10000, created_at: '2026-09-30T18:00:00Z' });

function harness(initialOrders, fetchTracking, initialProps = {}) {
  const slots = [], effects = [], intervals = new Map(), saved = [], calls = [];
  let cursor = 0, dirty = false, nextId = 0, tree;
  const props = { initialOrder: initialOrders[0], initialOrders, ...initialProps };
  const react = {
    createElement: (type, props, ...children) => ({ type, props, children }),
    useState: (initial) => {
      const index = cursor++;
      if (!(index in slots)) slots[index] = typeof initial === 'function' ? initial() : initial;
      return [slots[index], (value) => {
        const next = typeof value === 'function' ? value(slots[index]) : value;
        if (!Object.is(next, slots[index])) { slots[index] = next; dirty = true; }
      }];
    },
    useRef: (value) => {
      const index = cursor++;
      return slots[index] ??= { current: value };
    },
    useEffect: (run, deps) => {
      const index = cursor++;
      const prior = slots[index];
      if (!prior || deps.some((dep, i) => !Object.is(dep, prior.deps[i]))) {
        slots[index] = { deps, cleanup: prior?.cleanup };
        effects.push(() => {
          slots[index].cleanup?.();
          slots[index].cleanup = run();
        });
      }
    },
  };
  const exports = {};
  vm.runInNewContext(compiled, { exports,
    require: (name) => {
      if (name === 'react') return { __esModule: true, default: react, ...react };
      if (name === 'lucide-react') return {};
      if (name === '../api') return {
        fetchPublicOrderTracking: async (reference) => {
          calls.push(reference); return fetchTracking(reference);
        },
        getTrackedOrders: () => initialOrders,
        saveTrackedOrder: (order) => saved.push(order), clearTrackedOrder: () => {},
        formatMoney: (cents) => String(cents),
      };
      throw new Error(`Unexpected import ${name}`);
    },
    navigator: {}, window: {
      setInterval: (fn) => { intervals.set(++nextId, fn); return nextId; },
      clearInterval: (id) => intervals.delete(id),
    },
  });
  const render = () => {
    cursor = 0; dirty = false;
    tree = exports.ActiveOrderTracker(props);
    while (effects.length) effects.shift()();
  };
  const flush = async () => {
    for (let i = 0; i < 10; i++) {
      await new Promise(resolve => setImmediate(resolve));
      if (dirty) render();
    }
  };
  render();
  return { calls, saved, flush,
    tick: async () => { for (const fn of [...intervals.values()]) fn(); await flush(); },
    unmount: () => { for (const slot of slots) slot?.cleanup?.(); },
    updateProps: next => { Object.assign(props, next); render(); },
    tree: () => tree,
  };
}

test('delivered order stops polling while another active order keeps refreshing', async () => {
  const h = harness([tracked('a'), tracked('b')], async reference =>
    tracked(reference, reference === 'a' ? 'DELIVERED' : 'IN_PRODUCTION'));
  await h.flush();
  assert.equal(h.calls.filter(ref => ref === 'a').length, 1);
  await h.tick();
  assert.equal(h.calls.filter(ref => ref === 'a').length, 1);
  assert.equal(h.calls.filter(ref => ref === 'b').length, 2);
  h.unmount();
});

test('expired orders are terminal and displayed with their real status', async () => {
  const h = harness([tracked('expired', 'EXPIRED')], async () => null);
  await h.flush(); await h.tick();
  assert.equal(h.calls.length, 0);
  assert.match(JSON.stringify(h.tree()), /Expirado/i);
  h.unmount();
});

test('slow request cannot overlap and a response after unmount is discarded', async () => {
  let resolveRequest;
  const h = harness([tracked('slow')], () => new Promise(resolve => { resolveRequest = resolve; }));
  await h.flush(); await h.tick();
  assert.equal(h.calls.length, 1);
  h.unmount();
  resolveRequest(tracked('slow', 'READY'));
  await h.flush();
  assert.equal(h.saved.length, 0);
});

test('switching branches resets scoped orders and discards the old response', async () => {
  let resolveOld;
  const a = { ...tracked('a'), branch_id: 'branch-a' };
  const b = { ...tracked('b'), branch_id: 'branch-b' };
  const h = harness([a], reference => reference === 'a'
    ? new Promise(resolve => { resolveOld = resolve; })
    : Promise.resolve({ ...b, status: 'READY' }),
  { branchId: 'branch-a', initialOrders: undefined });
  await h.flush();
  h.updateProps({ branchId: 'branch-b', initialOrder: b });
  await h.flush();
  resolveOld({ ...a, status: 'READY' });
  await h.flush(); await h.tick();
  assert.equal(h.calls.filter(ref => ref === 'a').length, 1);
  assert.ok(h.saved.length);
  assert.ok(h.saved.every(order => order.branch_id === 'branch-b'));
  h.unmount();
});
