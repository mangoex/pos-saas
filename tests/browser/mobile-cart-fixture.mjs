// Local synthetic API for MOB-CART-001 browser QA. No production services are used.
// Run: node tests/browser/mobile-cart-fixture.mjs; open http://127.0.0.1:4174/menu/
import { createRequire } from 'node:module';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
const require = createRequire(resolve('apps/mobile-web/package.json'));
const { createServer } = await import(pathToFileURL(require.resolve('vite')).href);
const group = { id: 'extras', name: 'Extras', is_required: false, minimum_selections: 0, maximum_selections: 2, options: [
  { id: 'milk', name: 'Leche de aceituna', price_delta_cents: 2500, selection_kind: 'modifier' },
  { id: 'sugar', name: 'Azúcar mascabado', price_delta_cents: 0, selection_kind: 'modifier' },
] };
const products = [
  { id: 'coffee', sku: 'coffee', name: 'Capuchino 12oz', price_cents: 5500, category_name: 'Cafetería', modifier_groups: [group] },
  { id: 'plain', sku: 'plain', name: 'Café sin extras', price_cents: 4500, category_name: 'Cafetería', modifier_groups: [] },
  { id: 'required', sku: 'required', name: 'Café obligatorio', price_cents: 5500, category_name: 'Cafetería', modifier_groups: [{ ...group, minimum_selections: 1, is_required: true }] },
];
const branch = { id: 'qa-branch', public_key: 'qa-key', code: 'QA', name: 'Sucursal QA', status: 'active', has_active_shift: true, dine_in_enabled: true, accepts_cash_payments: true, accepts_card_payments: true };
const server = await createServer({
  root: resolve('apps/mobile-web'), server: { host: '127.0.0.1', port: 4174, strictPort: true },
  plugins: [{ name: 'synthetic-mobile-api', configureServer(vite) {
    vite.middlewares.use((req, res, next) => {
      if (!req.url?.startsWith('/api/')) return next();
      let body = {};
      if (req.url.includes('storefront')) body = { organization: { id: `qa-org-${req.url.split('/').at(-1)}`, name: 'Menú QA', public_slug: 'qa' }, branches: [branch], selected_branch_id: branch.id };
      else if (req.url.includes('catalog')) body = { items: products, categories: [{ id: 'coffee-category', name: 'Cafetería' }], has_active_shift: true };
      else if (req.url.includes('trending')) body = { trending_dishes: [] };
      else if (req.url.includes('community-photos')) body = { photos: [] };
      else if (req.url.includes('recommendations')) body = { recommendations: [] };
      else if (req.url.includes('order-intents')) { res.statusCode = 503; body = { detail: { code: 'database_unavailable' } }; }
      res.setHeader('Content-Type', 'application/json');
      res.end(JSON.stringify(body));
    });
  } }],
});
await server.listen();
console.log('Synthetic mobile QA: http://127.0.0.1:4174/menu/');
