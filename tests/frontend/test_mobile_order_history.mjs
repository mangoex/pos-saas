import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import vm from 'node:vm';
import test from 'node:test';

const ts = createRequire(import.meta.url)('typescript');
const source = readFileSync('apps/admin-web/src/features/mobile-orders/MobileOrdersMonitor.tsx', 'utf8');
const ast = ts.createSourceFile('monitor.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
let handler;
function find(node) {
  if (ts.isVariableDeclaration(node) && node.name.getText(ast) === 'loadOrders') {
    handler = node.initializer.arguments[0].getText(ast);
  }
  ts.forEachChild(node, find);
}
find(ast);
assert.ok(handler, 'test must execute the actual component handler');
const now = Date.parse('2026-09-30T18:00:00Z');
class FixedDate extends Date {
  constructor(value) { super(value === undefined ? now : value); }
  static now() { return now; }
}
const compile = code => ts.transpileModule(code, { compilerOptions: {
  module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.React,
} }).outputText;

function harness(fetchApi) {
  const state = {}, exports = {};
  const scopeRef = { current: { branchId: 'a', pages: 1, busy: false } };
  const context = vm.createContext({ exports, Date: FixedDate, scopeRef, branchId: 'a', fetchApi,
    require: () => ({}), ApiError: class ApiError extends Error {},
    window: { dispatchEvent: () => {} }, CustomEvent: class {},
    onActiveOrdersCountChange: count => { state.count = count; },
    ...Object.fromEntries(['Orders', 'NextCursor', 'Refreshing', 'Error', 'Loading', 'LastUpdated']
      .map(name => [`set${name}`, value => { state[name] = value; }])),
  });
  vm.runInContext(compile(source), context);
  context.isOrderNew = exports.isOrderNew;
  context.isOrderPrep = exports.isOrderPrep;
  vm.runInContext(compile(`globalThis.load = ${handler};`), context);
  return { state, scopeRef, load: context.load, classify: exports };
}
const row = (id, hours = 0, status = 'PENDING') => ({ id, status,
  created_at: new Date(now - hours * 3600000).toISOString(), is_public_intent: true });

test('old pending intents are history without changing the persisted status', () => {
  const h = harness(async () => ({}));
  const old = row('old', 25);
  assert.equal(h.classify.isOrderHistory(old), true);
  assert.equal(h.classify.isOrderNew(old), false);
  assert.equal(old.status, 'PENDING');
  assert.equal(h.classify.isOrderNew(row('fresh')), true);
});

test('load more and silent refresh keep requested depth and exclude old intents from active count', async () => {
  const calls = [];
  const h = harness(async path => {
    calls.push(path);
    return path.includes('&cursor=') ? { items: [row('old', 25)], next_cursor: null }
      : { items: [row('fresh')], next_cursor: 'older+page' };
  });
  await h.load();
  assert.equal(h.state.NextCursor, 'older+page');
  await h.load(false, true);
  assert.deepEqual(Array.from(h.state.Orders, item => item.id), ['fresh', 'old']);
  assert.equal(h.state.count, 1);
  assert.equal(h.state.NextCursor, null);
  await h.load(true);
  assert.equal(h.state.Orders.length, 2);
  assert.equal(calls.filter(path => path.includes('cursor=older%2Bpage')).length, 2);
});

test('a late branch response cannot publish orders and concurrent refreshes cannot overlap', async () => {
  let resolveRequest, calls = 0;
  const h = harness(() => { calls++; return new Promise(resolve => { resolveRequest = resolve; }); });
  const loading = h.load();
  await h.load(true);
  assert.equal(calls, 1);
  h.scopeRef.current = { branchId: 'b', pages: 1, busy: false };
  resolveRequest({ items: [row('foreign')], next_cursor: null });
  await loading;
  assert.equal(h.state.Orders, undefined);
});

test('failed additional page preserves existing rows and shows an error', async () => {
  let failed = false;
  const h = harness(async () => {
    if (failed) throw new Error('offline');
    return { items: [row('fresh')], next_cursor: 'next' };
  });
  await h.load(); failed = true;
  await h.load(false, true);
  assert.equal(h.state.Orders.length, 1);
  assert.equal(h.state.NextCursor, 'next');
  assert.ok(h.state.Error);
});

test('expired detail renders a terminal label without accept, reject or payment controls', () => {
  const modalSource = readFileSync(
    'apps/admin-web/src/features/mobile-orders/MobileOrderDetailModal.tsx', 'utf8');
  let stateIndex = 0;
  const detail = { id: 'expired', folio: 'WEB-EXPIRED', status: 'EXPIRED', is_public_intent: true,
    branch_id: 'a', organization_id: 'org-a', total_cents: 10000, lines: [], payments: [],
    production_tasks: [], service_type: 'takeout', created_at: '2026-09-29T17:00:00Z' };
  const react = { createElement: (type, props, ...children) => ({ type, props, children }),
    useState: value => [stateIndex++ === 0 ? detail : value, () => {}],
    useRef: value => ({ current: value }), useEffect: () => {},
  };
  const exports = {};
  vm.runInNewContext(compile(modalSource), { exports, require: name =>
    name === 'react' ? { __esModule: true, default: react, ...react } : {},
  });
  const tree = exports.MobileOrderDetailModal({ orderId: detail.id, isOpen: true, onClose: () => {} });
  const text = JSON.stringify(tree);
  assert.match(text, /Expirado/);
  assert.doesNotMatch(text, /Aceptar Pedido|Rechazar Pedido|Entregar \/ Cobrar|Entregado \(Por Cobrar\)|Método de Cobro al Entregar/);
});
