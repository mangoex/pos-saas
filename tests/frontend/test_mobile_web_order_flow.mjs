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

let buildWhatsAppLink;
let fetchMobileMenu;
let fetchOrderUpsellRecommendations;
let submitMobileOrder;

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

test('Public intent retries retain their key except persisted success and explicit conflict', async () => {
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

  storage.set(key, 'retry-after-conflict');
  global.fetch = async () => ({ ok: false, status: 409, json: async () => ({ detail: { code: 'idempotency_conflict' } }) });
  await assert.rejects(invoke);
  assert.equal(storage.has(key), false);

  for (const response of [
    { ok: false, status: 500, text: async () => 'server error' },
    { ok: true, status: 200, json: async () => ({ public_reference: 'PI-002', status: 'PENDING_REVIEW', total_cents: 'invalid' }) },
  ]) {
    storage.set(key, 'retain-retry-key');
    global.fetch = async () => response;
    await assert.rejects(invoke);
    assert.equal(storage.get(key), 'retain-retry-key');
  }
  storage.set(key, 'retain-timeout-key');
  global.fetch = async () => { throw new Error('timeout'); };
  await assert.rejects(invoke);
  assert.equal(storage.get(key), 'retain-timeout-key');
  global.fetch = originalFetch;
  global.localStorage = originalStorage;
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
  assert.match(source, /group\.minimum_selections/);
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

test('Cart AI recommendations use category icons instead of product photos', () => {
  const source = readFileSync(join(root, 'apps/mobile-web/src/components/CartDrawer.tsx'), 'utf8');
  const styles = readFileSync(join(root, 'apps/mobile-web/src/index.css'), 'utf8');

  assert.match(source, /const getRecommendationIcon = \(product: Product/);
  assert.match(source, /className="cart-upsell-card-icon"/);
  assert.match(source, /aria-hidden="true"/);
  assert.doesNotMatch(source, /className="cart-upsell-card-img"/);
  assert.doesNotMatch(styles, /\.cart-upsell-card-img\s*\{/);
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
