import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { cpSync, mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const require = createRequire(import.meta.url);
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const temporaryDirectory = mkdtempSync(join(tmpdir(), 'restaurantos-mobile-web-'));
const mobileOrderLocks = new Map();
const mockMobileOrderLocks = {
  request(name, callback) {
    const previous = mobileOrderLocks.get(name) ?? Promise.resolve();
    let release;
    const current = new Promise((resolveLock) => { release = resolveLock; });
    mobileOrderLocks.set(name, current);
    return previous.then(callback).finally(() => {
      release();
      if (mobileOrderLocks.get(name) === current) mobileOrderLocks.delete(name);
    });
  },
};
const testNavigator = globalThis.navigator ?? {};
Object.defineProperty(globalThis, 'navigator', { configurable: true, value: testNavigator });
Object.defineProperty(testNavigator, 'locks', { configurable: true, value: mockMobileOrderLocks });

let buildWhatsAppLink;
let fetchMobileMenu;
let fetchOrderUpsellRecommendations;
let submitMobileOrder;
let hasPendingMobileOrder;
let mobileOrderTimestamp;
let getSavedCustomerProfile;
let saveCustomerProfile;
let MIMENU_CUSTOMER_PROFILE_KEY;
let LEGACY_CUSTOMER_PROFILE_KEY;

try {
  const source = join(root, 'apps/mobile-web/src/api.ts');
  const envDts = join(root, 'apps/mobile-web/src/vite-env.d.ts');
  execFileSync(
    process.execPath,
    [
      join(root, 'node_modules/typescript/bin/tsc'),
      '--target', 'ES2022',
      '--module', 'CommonJS',
      '--skipLibCheck',
      '--outDir', temporaryDirectory,
      envDts,
      source,
    ],
    { cwd: root, stdio: 'pipe' },
  );
  cpSync(join(root, 'apps/mobile-web/src/assets'), join(temporaryDirectory, 'assets'), { recursive: true, force: true });
  require.extensions['.jpg'] = (module, filename) => { module.exports = filename; };
  require.extensions['.png'] = (module, filename) => { module.exports = filename; };
  const mobileApi = require(join(temporaryDirectory, 'api.js'));
  buildWhatsAppLink = mobileApi.buildWhatsAppLink;
  fetchMobileMenu = mobileApi.fetchMobileMenu;
  fetchOrderUpsellRecommendations = mobileApi.fetchOrderUpsellRecommendations;
  submitMobileOrder = mobileApi.submitMobileOrder;
  hasPendingMobileOrder = mobileApi.hasPendingMobileOrder;
  mobileOrderTimestamp = mobileApi.mobileOrderTimestamp;
  getSavedCustomerProfile = mobileApi.getSavedCustomerProfile;
  saveCustomerProfile = mobileApi.saveCustomerProfile;
  MIMENU_CUSTOMER_PROFILE_KEY = mobileApi.MIMENU_CUSTOMER_PROFILE_KEY;
  LEGACY_CUSTOMER_PROFILE_KEY = mobileApi.LEGACY_CUSTOMER_PROFILE_KEY;
} catch (err) {
  rmSync(temporaryDirectory, { recursive: true, force: true });
  throw err;
}

process.on('exit', () => {
  rmSync(temporaryDirectory, { recursive: true, force: true });
});

test('Mobile Order WhatsApp link format for takeaway', () => {
  const info = {
    name: 'Carlos Ruiz',
    phone: '5511223344',
    order_type: 'takeaway',
    address_street: '',
    address_number: '',
    address_neighborhood: '',
    address_notes: '',
    payment_method: 'cash',
    cash_amount: '200',
    order_notes: 'Sin cubiertos',
  };

  const items = [
    {
      cart_id: 'item-1',
      product: { id: 'prod-1', name: 'Jugo Verde', price_cents: 6500 },
      quantity: 2,
      notes: 'Sin popote',
      line_total_cents: 13000,
    },
  ];

  const total = 13000;
  const link = buildWhatsAppLink('KIWI-5001', info, items, total, '5215500000000');

  assert.ok(link.startsWith('https://wa.me/5215500000000?text='));
  const decoded = decodeURIComponent(link.replace('https://wa.me/5215500000000?text=', ''));

  assert.match(decoded, /#KIWI-5001/);
  assert.match(decoded, /Carlos Ruiz/);
  assert.match(decoded, /Para Recoger en Barra/);
  assert.match(decoded, /2x Jugo Verde/);
  assert.match(decoded, /\$130\.00 MXN/);
  assert.match(decoded, /Sin popote/);
  assert.match(decoded, /Paga con: \$200/);
});

test('Mobile Order WhatsApp link format for delivery with address', () => {
  const info = {
    name: 'Mariana Lopez',
    phone: '5599887766',
    order_type: 'delivery',
    address_street: 'Calle Roble',
    address_number: '450 Int 2',
    address_neighborhood: 'Col. Roma',
    address_notes: 'Edificio gris',
    payment_method: 'card',
    order_notes: '',
  };

  const items = [
    {
      cart_id: 'item-2',
      product: { id: 'prod-2', name: 'Sando Kyoto Pollo BBQ', price_cents: 12000 },
      quantity: 1,
      notes: '',
      line_total_cents: 12000,
    },
    {
      cart_id: 'item-3',
      product: { id: 'prod-3', name: 'Smoothie Rosa', price_cents: 9000 },
      quantity: 1,
      notes: '',
      line_total_cents: 9000,
    },
  ];

  const total = 21000;
  const link = buildWhatsAppLink('KIWI-8822', info, items, total, '5215500000000');
  const decoded = decodeURIComponent(link.replace('https://wa.me/5215500000000?text=', ''));

  assert.match(decoded, /#KIWI-8822/);
  assert.match(decoded, /Mariana Lopez/);
  assert.match(decoded, /Envío a Domicilio/);
  assert.match(decoded, /Calle Roble #450 Int 2, Col\. Roma/);
  assert.match(decoded, /Tarjeta \(Al recibir\)/);
  assert.match(decoded, /\$210\.00 MXN/);
});

test('Mobile order rejects every non-persisted response without fabricating a folio', async () => {
  const info = {
    name: 'Cliente de prueba', phone: '5511223344', order_type: 'takeaway',
    address_street: '', address_number: '', address_neighborhood: '', address_notes: '',
    payment_method: 'cash', order_notes: '',
  };
  const items = [{ cart_id: 'line-1', product: { id: 'prod-1', name: 'Jugo', price_cents: 6500 }, quantity: 1, line_total_cents: 6500 }];
  const originalFetch = global.fetch;
  for (const response of [
    { ok: false, status: 400, text: async () => 'bad request' },
    { ok: false, status: 500, text: async () => 'server error' },
    { ok: true, status: 200, json: async () => ({ folio: 'KIWI-1' }) },
  ]) {
    global.fetch = async () => response;
    await assert.rejects(() => submitMobileOrder(info, items, 'branch-1'));
  }
  global.fetch = async () => { throw new Error('timeout'); };
  await assert.rejects(() => submitMobileOrder(info, items, 'branch-1'));
  global.fetch = originalFetch;
});

test('Public intent retries retain pending state except persisted success', async () => {
  const info = {
    name: 'Cliente de prueba', phone: '5511223344', order_type: 'takeaway',
    address_street: '', address_number: '', address_neighborhood: '', address_notes: '',
    payment_method: 'cash', order_notes: '',
  };
  const items = [{ cart_id: 'line-1', product: { id: 'prod-1', name: 'Jugo', price_cents: 6500 }, quantity: 1, line_total_cents: 6500 }];
  const originalFetch = global.fetch;
  const originalStorage = global.localStorage;
  const storage = new Map();
  global.localStorage = {
    getItem: (key) => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, value),
    removeItem: (key) => storage.delete(key),
  };
  const key = 'kiwi_public_order_key:public-key';
  const invoke = () => submitMobileOrder(info, items, 'branch-1', undefined, undefined, 'public-key');

  global.fetch = async () => ({ ok: true, status: 201, json: async () => ({ public_reference: 'PI-001', status: 'PENDING_REVIEW', version: 1, total_cents: 6500 }) });
  const persisted = await invoke();
  assert.equal(persisted.kind, 'public_order_intent');
  assert.equal(persisted.status, 'PENDING_REVIEW');
  assert.equal(persisted.public_reference, 'PI-001');
  assert.equal('folio' in persisted, false);
  assert.equal('id' in persisted, false);
  assert.equal('created_at' in persisted, false);
  assert.equal(storage.has(key), false);
  assert.equal(hasPendingMobileOrder('public-key'), false);

  for (const response of [
    { ok: false, status: 500, text: async () => 'server error' },
    { ok: false, status: 422, json: async () => ({}) },
    { ok: false, status: 422, json: async () => ({ code: 'unknown' }) },
    { ok: true, status: 200, json: async () => ({ public_reference: 'PI-002', status: 'PENDING_REVIEW', total_cents: 'invalid' }) },
  ]) {
    global.fetch = async () => response;
    await assert.rejects(invoke);
    assert.equal(hasPendingMobileOrder('public-key'), true);
  }
  global.fetch = async () => { throw new Error('timeout'); };
  await assert.rejects(invoke);
  assert.equal(hasPendingMobileOrder('public-key'), true);

  global.fetch = async () => ({ ok: false, status: 409, json: async () => ({ detail: { code: 'idempotency_conflict' } }) });
  await assert.rejects(invoke);
  assert.equal(hasPendingMobileOrder('public-key'), true);

  for (const [status, code] of [[429, 'public_order_rate_limited'], [503, 'public_order_unavailable']]) {
    global.fetch = async () => ({ ok: false, status, json: async () => ({ detail: { code } }) });
    await assert.rejects(invoke);
    assert.equal(hasPendingMobileOrder('public-key'), true);
  }

  global.fetch = async () => ({ ok: false, status: 422, json: async () => ({ detail: { code: 'public_order_schema_invalid' } }) });
  await assert.rejects(invoke);
  assert.equal(hasPendingMobileOrder('public-key'), false);
  global.fetch = originalFetch;
  global.localStorage = originalStorage;
});

test('Uncertain mobile order retries its original body and receipt after inputs change', async () => {
  const originalInfo = {
    name: 'Cliente original', phone: '5511223344', order_type: 'takeaway',
    address_street: '', address_number: '', address_neighborhood: '', address_notes: '',
    payment_method: 'cash', cash_amount: '200', order_notes: 'Sin cubiertos',
  };
  const originalItems = [{
    cart_id: 'line-original',
    product: { id: 'prod-1', name: 'Jugo original', price_cents: 6500 },
    quantity: 2,
    notes: 'Sin popote',
    modifiers: [{ option_id: 'extra-1', selection_kind: 'modifier', name: 'Avena', price_delta_cents: 500 }],
    line_total_cents: 14000,
  }];
  const changedInfo = { ...originalInfo, name: 'Cliente editado', phone: '5588776655', order_notes: 'Con cubiertos' };
  const changedItems = [{ ...originalItems[0], cart_id: 'line-edited', quantity: 1 }];
  const originalFetch = global.fetch;
  const originalStorage = global.localStorage;
  const storage = new Map();
  global.localStorage = {
    getItem: (key) => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, value),
    removeItem: (key) => storage.delete(key),
  };
  const requests = [];
  global.fetch = async (_url, options) => {
    requests.push({ body: options.body, key: options.headers['Idempotency-Key'] });
    if (requests.length === 1) throw new Error('timeout');
    return { ok: true, status: 201, json: async () => ({ public_reference: 'PI-RECOVERED', status: 'PENDING_REVIEW', version: 1, total_cents: 14500 }) };
  };
  try {
    await assert.rejects(() => submitMobileOrder(originalInfo, originalItems, 'branch-1', 'Sucursal original', undefined, 'public-key', '5215500000001', true));
    assert.equal(hasPendingMobileOrder('public-key'), true);
    const persistedKey = requests[0].key;

    // A fresh invocation over the same storage models a page reload.
    const recovered = await submitMobileOrder(changedInfo, changedItems, 'branch-1', 'Sucursal editada', undefined, 'public-key', '5215500000002', true);
    assert.equal(requests[1].body, requests[0].body);
    assert.equal(requests[1].key, persistedKey);
    assert.equal(recovered.public_reference, 'PI-RECOVERED');
    assert.deepEqual(recovered.customer_info, originalInfo);
    assert.deepEqual(recovered.items, originalItems);
    assert.ok(recovered.whatsapp_url.startsWith('https://wa.me/5215500000001?text='));
    assert.match(decodeURIComponent(recovered.whatsapp_url), /SUCURSAL ORIGINAL/);
    assert.equal(hasPendingMobileOrder('public-key'), false);
  } finally {
    global.fetch = originalFetch;
    global.localStorage = originalStorage;
  }
});

test('Legacy idempotency key without its original payload blocks submission and stays pending', async () => {
  const originalFetch = global.fetch;
  const originalStorage = global.localStorage;
  const storage = new Map([['restaurantos_public_order_key:public-key', 'legacy-attempt-key']]);
  global.localStorage = {
    getItem: (key) => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, value),
    removeItem: (key) => storage.delete(key),
  };
  let requests = 0;
  global.fetch = async () => { requests += 1; throw new Error('must not send'); };
  try {
    assert.equal(hasPendingMobileOrder('public-key'), true);
    await assert.rejects(
      () => submitMobileOrder({ name: 'Cliente', phone: '5511223344', order_type: 'takeaway', address_street: '', address_number: '', address_neighborhood: '', address_notes: '', payment_method: 'cash' }, [], 'branch-1', undefined, undefined, 'public-key'),
      (error) => error.code === 'pending_mobile_order_legacy',
    );
    assert.equal(requests, 0);
    assert.equal(storage.get('restaurantos_public_order_key:public-key'), 'legacy-attempt-key');
  } finally {
    global.fetch = originalFetch;
    global.localStorage = originalStorage;
  }
});

test('Queued cross-tab submit cannot create a second order after the first succeeds', async () => {
  const originalInfo = {
    name: 'Cliente A', phone: '5511223344', order_type: 'takeaway',
    address_street: '', address_number: '', address_neighborhood: '', address_notes: '', payment_method: 'cash',
  };
  const changedInfo = { ...originalInfo, name: 'Cliente B' };
  const items = [{ cart_id: 'line-1', product: { id: 'prod-1', name: 'Jugo', price_cents: 6500 }, quantity: 1, line_total_cents: 6500 }];
  const originalFetch = global.fetch;
  const originalStorage = global.localStorage;
  const storage = new Map();
  global.localStorage = {
    getItem: (key) => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, value),
    removeItem: (key) => storage.delete(key),
  };
  let releaseFetch;
  let markStarted;
  const started = new Promise((resolveStarted) => { markStarted = resolveStarted; });
  const held = new Promise((resolveFetch) => { releaseFetch = resolveFetch; });
  let requestCount = 0;
  global.fetch = async () => {
    requestCount += 1;
    markStarted();
    await held;
    return { ok: true, status: 201, json: async () => ({ public_reference: 'PI-ONCE', status: 'PENDING_REVIEW', version: 1, total_cents: 6500 }) };
  };
  try {
    const first = submitMobileOrder(originalInfo, items, 'branch-1', undefined, undefined, 'public-key');
    await started;
    const second = submitMobileOrder(changedInfo, items, 'branch-1', undefined, undefined, 'public-key');
    const third = submitMobileOrder(changedInfo, items, 'branch-1', undefined, undefined, 'public-key');
    releaseFetch();
    const firstResult = await first;
    assert.equal(firstResult.public_reference, 'PI-ONCE');
    await assert.rejects(second, (error) => error.code === 'mobile_order_already_completed');
    await assert.rejects(third, (error) => error.code === 'mobile_order_already_completed');
    assert.equal(requestCount, 1);
  } finally {
    global.fetch = originalFetch;
    global.localStorage = originalStorage;
  }
});

test('A stale cart epoch cannot resubmit after another tab completed the order', async () => {
  const info = {
    name: 'Cliente A', phone: '5511223344', order_type: 'takeaway',
    address_street: '', address_number: '', address_neighborhood: '', address_notes: '', payment_method: 'cash',
  };
  const items = [{ cart_id: 'line-1', product: { id: 'prod-1', name: 'Jugo', price_cents: 6500 }, quantity: 1, line_total_cents: 6500 }];
  const originalFetch = global.fetch;
  const originalStorage = global.localStorage;
  const storage = new Map();
  global.localStorage = {
    getItem: (key) => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, value),
    removeItem: (key) => storage.delete(key),
  };
  let requestCount = 0;
  global.fetch = async () => {
    requestCount += 1;
    return { ok: true, status: 201, json: async () => ({ public_reference: 'PI-ONCE', status: 'PENDING_REVIEW', version: 1, total_cents: 6500 }) };
  };
  try {
    const staleCartEpoch = mobileOrderTimestamp() - 1000;
    await submitMobileOrder(info, items, 'branch-1', undefined, undefined, 'public-key', undefined, undefined, staleCartEpoch);
    await assert.rejects(
      () => submitMobileOrder(info, items, 'branch-1', undefined, undefined, 'public-key', undefined, undefined, staleCartEpoch),
      (error) => error.code === 'mobile_order_already_completed',
    );
    assert.equal(requestCount, 1);
  } finally {
    global.fetch = originalFetch;
    global.localStorage = originalStorage;
  }
});

test('Cleanup failure after persisted success replays the original key despite completion fence', async () => {
  const originalFetch = global.fetch;
  const originalStorage = global.localStorage;
  const storage = new Map();
  let failCleanup = true;
  global.localStorage = {
    getItem: key => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, value),
    removeItem: key => { if (failCleanup && key.startsWith('restaurantos_pending_mobile_order:')) throw new Error('storage'); storage.delete(key); },
  };
  const calls = [];
  global.fetch = async (_url, options) => {
    calls.push(options);
    return { ok: true, status: 201, json: async () => ({ public_reference: 'PI-SAME', status: 'PENDING_REVIEW', version: 1, total_cents: 5500 }) };
  };
  const info = { name: 'QA', phone: '5551234567', order_type: 'takeaway', address_street: '', address_number: '', address_neighborhood: '', address_notes: '', payment_method: 'cash' };
  const epoch = mobileOrderTimestamp();
  try {
    await assert.rejects(() => submitMobileOrder(info, [], 'branch', undefined, undefined, 'cleanup-key', undefined, undefined, epoch), error => error.code === 'pending_mobile_order_cleanup_failed');
    failCleanup = false;
    const result = await submitMobileOrder({ ...info, name: 'Changed' }, [], 'branch', undefined, undefined, 'cleanup-key', undefined, undefined, epoch);
    assert.equal(result.customer_info.name, 'QA');
    assert.equal(calls.length, 2);
    assert.equal(calls[0].body, calls[1].body);
    assert.equal(calls[0].headers['Idempotency-Key'], calls[1].headers['Idempotency-Key']);
    assert.equal(hasPendingMobileOrder('cleanup-key'), false);
  } finally { global.fetch = originalFetch; global.localStorage = originalStorage; }
});

test('Mobile order is not sent when local recovery storage fails', async () => {
  const originalFetch = global.fetch;
  const originalStorage = global.localStorage;
  let requests = 0;
  global.localStorage = {
    getItem: () => null,
    setItem: () => { throw new Error('quota'); },
    removeItem: () => {},
  };
  global.fetch = async () => { requests += 1; throw new Error('must not send'); };
  try {
    await assert.rejects(
      () => submitMobileOrder({ name: 'Cliente', phone: '5511223344', order_type: 'takeaway', address_street: '', address_number: '', address_neighborhood: '', address_notes: '', payment_method: 'cash' }, [], 'branch-1', undefined, undefined, 'public-key'),
      (error) => error.code === 'pending_mobile_order_storage_unavailable',
    );
    assert.equal(requests, 0);
  } finally {
    global.fetch = originalFetch;
    global.localStorage = originalStorage;
  }
});

test('Keyed mobile order fails closed when cross-tab locking is unavailable', async () => {
  const originalFetch = global.fetch;
  const originalStorage = global.localStorage;
  const originalLocks = globalThis.navigator.locks;
  Object.defineProperty(globalThis.navigator, 'locks', { configurable: true, value: undefined });
  global.localStorage = {
    getItem: () => null,
    setItem: () => {},
    removeItem: () => {},
  };
  let requests = 0;
  global.fetch = async () => { requests += 1; throw new Error('must not send'); };
  try {
    await assert.rejects(
      () => submitMobileOrder({ name: 'Cliente', phone: '5511223344', order_type: 'takeaway', address_street: '', address_number: '', address_neighborhood: '', address_notes: '', payment_method: 'cash' }, [], 'branch-1', undefined, undefined, 'public-key'),
      (error) => error.code === 'mobile_order_lock_unavailable',
    );
    assert.equal(requests, 0);
  } finally {
    global.fetch = originalFetch;
    global.localStorage = originalStorage;
    Object.defineProperty(globalThis.navigator, 'locks', { configurable: true, value: originalLocks });
  }
});

test('Public intent sends selected catalog modifiers, not synthetic size notes or client totals', async () => {
  const info = {
    name: 'Cliente de prueba', phone: '5511223344', order_type: 'takeaway',
    address_street: '', address_number: '', address_neighborhood: '', address_notes: '',
    payment_method: 'cash', order_notes: '',
  };
  const items = [{
    cart_id: 'line-with-modifier',
    product: { id: 'prod-1', name: 'Jugo', price_cents: 6500 },
    quantity: 2,
    notes: 'Sin popote',
    modifiers: [{ option_id: 'option-extra', selection_kind: 'modifier', text: 'bien frío', price_delta_cents: 300 }],
    line_total_cents: 13600,
  }];
  const originalFetch = global.fetch;
  const originalStorage = global.localStorage;
  const storage = new Map();
  global.localStorage = { getItem: (key) => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value), removeItem: (key) => storage.delete(key) };
  let requestBody;
  global.fetch = async (_url, options) => {
    requestBody = JSON.parse(options.body);
    return { ok: true, status: 201, json: async () => ({ public_reference: 'PI-MODIFIER', status: 'PENDING_REVIEW', version: 1, total_cents: 14200 }) };
  };
  const result = await submitMobileOrder(info, items, 'branch-1', undefined, undefined, 'public-key');
  assert.equal(result.total_cents, 14200);
  assert.deepEqual(requestBody.lines, [{
    product_id: 'prod-1', quantity: 2, notes: 'Sin popote',
    modifiers: [{ option_id: 'option-extra', text: 'bien frío' }],
  }]);
  assert.equal('total_cents' in requestBody, false);
  assert.equal(JSON.stringify(requestBody).includes('Regular'), false);
  global.fetch = originalFetch;
  global.localStorage = originalStorage;
});

test('Pending public-intent modal is semantically distinct from an operational order', () => {
  const source = readFileSync(join(root, 'apps/mobile-web/src/components/OrderSuccessModal.tsx'), 'utf8');
  const resultTypes = readFileSync(join(root, 'apps/mobile-web/src/types.ts'), 'utf8');
  assert.match(resultTypes, /kind: 'public_order_intent'/);
  assert.match(resultTypes, /kind: 'operational_order'/);
  assert.match(source, /pendingReview \? 'Referencia' : 'Folio de Orden'/);
  assert.match(source, /pendingReview \? 'Pendiente de revisión' : 'Enviado al Punto de Venta y Cocina'/);
  assert.match(source, /Aún no es un pedido operativo/);
  assert.match(source, /pendingReview \? '¡Solicitud recibida!' : '¡Pedido Registrado y Enviado!'/);
});

test('Product modal uses only catalog modifier groups and enforces their boundaries', () => {
  const source = readFileSync(join(root, 'apps/mobile-web/src/components/ProductModal.tsx'), 'utf8');
  assert.doesNotMatch(source, /\['Regular', 'Mediano', 'Grande'\]/);
  // Cardinalities moved to the shared validator, executed by the cart regression suite.
  assert.match(source, /validateCartDraft\(product, quantity, selectedModifierList\)/);
  assert.match(source, /group\.maximum_selections/);
  assert.match(source, /option_id: option\.id/);
  assert.match(source, /setModifierText/);
});

test('Mobile catalog uses the selected public key rather than the legacy branch catalog', async () => {
  const originalFetch = global.fetch;
  let requestedUrl = '';
  global.fetch = async (url) => {
    requestedUrl = url;
    return { ok: true, json: async () => ({ branch_id: 'branch-b', categories: [], items: [{ id: 'b-only', name: 'B', sku: 'B', price_cents: 1234 }] }) };
  };
  const catalog = await fetchMobileMenu('public-key-b');
  assert.match(requestedUrl, /\/public\/branches\/public-key-b\/catalog$/);
  assert.deepEqual(catalog.products.map((product) => product.id), ['b-only']);
  global.fetch = originalFetch;
});

test('Mobile upsell request is branch scoped and preserves an empty fallback', async () => {
  const originalFetch = global.fetch;
  let requestBody;
  global.fetch = async (_url, options) => {
    requestBody = JSON.parse(options.body);
    return { ok: true, json: async () => ({ recommendations: [] }) };
  };

  const result = await fetchOrderUpsellRecommendations(['product-food'], 'branch-centro');

  assert.deepEqual(requestBody, {
    current_product_ids: ['product-food'],
    branch_id: 'branch-centro',
  });
  assert.deepEqual(result, []);

  global.fetch = async () => ({ ok: false, status: 503 });
  assert.deepEqual(
    await fetchOrderUpsellRecommendations(['product-food'], 'branch-centro'),
    [],
  );
  global.fetch = originalFetch;
});

test('Cart recommendations rely on backend authority and clear stale state', () => {
  const source = readFileSync(join(root, 'apps/mobile-web/src/components/CartDrawer.tsx'), 'utf8');
  assert.doesNotMatch(source, /const isBeverage/);
  assert.doesNotMatch(source, /Intelligent Dynamic Category Pairing Fallback/);
  assert.doesNotMatch(source, /Favorito de nuestros clientes/);
  assert.match(source, /setAiRecs\(\[\]\);[\s\S]*fetchOrderUpsellRecommendations/);
  assert.match(source, /fetchOrderUpsellRecommendations\(ids, selectedBranch\?\.id\)/);
});

test('Cart AI recommendations show product photograph if configured, falling back to category icon', () => {
  const source = readFileSync(join(root, 'apps/mobile-web/src/components/CartDrawer.tsx'), 'utf8');
  const styles = readFileSync(join(root, 'apps/mobile-web/src/index.css'), 'utf8');

  assert.match(source, /const getRecommendationIcon = \(product: Product/);
  assert.match(source, /className="cart-upsell-card-icon"/);
  assert.match(source, /aria-hidden="true"/);
  assert.match(source, /className="cart-upsell-card-img"/);
  assert.match(styles, /\.cart-upsell-card-img\s*\{/);
});


test('Catalog photographs and nutrition are never inferred from a legacy SKU', async () => {
  const previousFetch = globalThis.fetch;
  globalThis.fetch = async () => ({ ok: true, json: async () => ({ items: [
    { id: 'own-product', name: 'Jugo Verde', sku: 'JUG-VER', price_cents: 5000 },
    { id: 'own-photo', name: 'Own dish', price_cents: 6000, image_url: '/uploads/own-dish.jpg' },
  ] }) });
  try {
    const { products } = await fetchMobileMenu('tenant-branch-key');
    assert.equal(products[0].image_url, '');
    assert.equal(products[0].calories, undefined);
    assert.equal(products[0].prep_time, undefined);
    assert.equal(products[1].image_url, '/uploads/own-dish.jpg');
  } finally { globalThis.fetch = previousFetch; }
});

test('Mobile checkout form has standard 1-tap HTML5 autofill attributes and returning customer recognition', () => {
  const source = readFileSync(join(root, 'apps/mobile-web/src/components/CartDrawer.tsx'), 'utf8');

  // Standard HTML5 autofill attributes for zero-friction 1-tap browser filling
  assert.match(source, /id="cart-checkout-form"/);
  assert.match(source, /method="post"/);
  assert.match(source, /autoComplete="on"/);
  assert.match(source, /htmlFor="customer-name"/);
  assert.match(source, /id="customer-name"/);
  assert.match(source, /autoComplete="name"/);
  assert.match(source, /htmlFor="customer-phone"/);
  assert.match(source, /id="customer-phone"/);
  assert.match(source, /name="tel"/);
  assert.match(source, /autoComplete="tel"/);
  assert.match(source, /inputMode="tel"/);
  assert.match(source, /htmlFor="customer-street"/);
  assert.match(source, /id="customer-street"/);
  assert.match(source, /autoComplete="street-address"/);
  assert.match(source, /id="customer-number"/);
  assert.match(source, /autoComplete="address-line2"/);
  assert.match(source, /id="customer-neighborhood"/);
  assert.match(source, /autoComplete="address-level3"/);

  // 1-Tap native contact picker API and returning customer profile integration
  assert.match(source, /handle1TapAutofill/);
  assert.match(source, /btn-cart-1tap-autofill/);
  assert.match(source, /getSavedCustomerProfile/);
  assert.match(source, /saveCustomerProfile/);
  assert.match(source, /cart-returning-customer-card/);
  assert.match(source, /⚡ Recordado/);
});

test('Persistent customer profile saves and retrieves across mimenu network', () => {
  const store = new Map();
  globalThis.window = {
    localStorage: {
      getItem: (key) => store.get(key) || null,
      setItem: (key, val) => store.set(key, String(val)),
      removeItem: (key) => store.delete(key),
      clear: () => store.clear(),
    },
  };
  globalThis.localStorage = globalThis.window.localStorage;

  try {
    // 1. Initially empty
    assert.equal(getSavedCustomerProfile(), null);

    // 2. Save profile
    saveCustomerProfile({
      name: '  Ana Brenda  ',
      phone: '  +526671234567 ',
      street: 'Av. Las Palmas',
      number: '102',
      neighborhood: 'Chapultepec',
      address_notes: 'Casa blanca de 2 pisos',
    });

    // Verify written to primary mimenu key and legacy key
    assert.ok(store.has(MIMENU_CUSTOMER_PROFILE_KEY));
    assert.ok(store.has(LEGACY_CUSTOMER_PROFILE_KEY));

    // 3. Load profile
    const loaded = getSavedCustomerProfile();
    assert.ok(loaded);
    assert.equal(loaded.name, 'Ana Brenda');
    assert.equal(loaded.phone, '+526671234567');
    assert.equal(loaded.street, 'Av. Las Palmas');
    assert.equal(loaded.number, '102');
    assert.equal(loaded.neighborhood, 'Chapultepec');
    assert.equal(loaded.address_notes, 'Casa blanca de 2 pisos');
    assert.ok(loaded.last_updated_at);

    // 4. Fallback to legacy key if primary missing
    store.delete(MIMENU_CUSTOMER_PROFILE_KEY);
    const legacyLoaded = getSavedCustomerProfile();
    assert.ok(legacyLoaded);
    assert.equal(legacyLoaded.name, 'Ana Brenda');
  } finally {
    delete globalThis.window;
    delete globalThis.localStorage;
  }
});

test('OrderSuccessModal displays silent onboarding persistent profile confirmation and loyalty teaser', () => {
  const source = readFileSync(join(root, 'apps/mobile-web/src/components/OrderSuccessModal.tsx'), 'utf8');

  assert.match(source, /order-success-profile-card/);
  assert.match(source, /Datos recordados en mimenu/);
  assert.match(source, /Próximamente: Vincula con Google para ganar puntos y recompensas/);
});
