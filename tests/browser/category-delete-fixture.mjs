// In-memory category editor fixture. No credentials or production services.
// node tests/browser/category-delete-fixture.mjs
import { createRequire } from 'node:module';
import { resolve, dirname } from 'node:path';
import { pathToFileURL } from 'node:url';
const branch = {id: 'qa-branch', name: 'QA'};
let categories = [{id:'coffee',name:'Cafe',status:'active'}, {id:'other',name:'Otra',status:'active'}, {id:'error',name:'Error QA',status:'active'}];
let products = [{id:'latte',name:'LATTE QA',sku:'LATTE',category_id:'coffee',category_name:'Cafe',price_cents:4500,status:'active'}, {id:'plain',name:'OTHER QA',sku:'OTHER',category_id:'other',category_name:'Otra',price_cents:2000,status:'active'}];
const require = createRequire(resolve('apps/admin-web/package.json'));
const { createServer } = await import(pathToFileURL(require.resolve('vite')).href);
const { default: react } = await import(pathToFileURL(require.resolve('@vitejs/plugin-react')).href);
const entry = '/@fs/' + resolve('tests/browser/category-delete-entry.tsx').replaceAll('\\', '/');
const server = await createServer({
  resolve: { alias: Object.fromEntries(['react', 'react-dom', '@tanstack/react-query'].map(name => [name, dirname(require.resolve(`${name}/package.json`))])) },
  configFile: false, root: resolve('apps/admin-web'), plugins: [react(), {
    name: 'category-qa', configureServer(vite) {
      vite.middlewares.use(async (req, res, next) => {
        if (req.url === '/qa-category') {
          res.setHeader('Content-Type', 'text/html');
          return res.end(await vite.transformIndexHtml(req.url, `<html><head><meta name="viewport" content="width=device-width,initial-scale=1" /></head><body style="margin:0;font-family:Arial"><div id="root"></div><script type="module" src="${entry}"></script></body></html>`));
        }
        if (!req.url?.startsWith('/api/')) return next();
        let body = {};
        if (req.url === '/api/v1/categories') body = categories;
        else if (req.url === '/api/v1/catalog/products') body = products;
        else if (req.url === '/api/v1/catalog/menu-home') body = {name:'Todos',image_url:''};
        else if (req.method === 'DELETE' && req.url.startsWith('/api/v1/categories/')) {
          const id = req.url.split('/').at(-1).split('?')[0];
          if (id === 'error') { res.statusCode = 409; body = {detail:{code:'synthetic_error',message:'Error de prueba al eliminar'}}; }
          else { categories = categories.filter(c => c.id !== id); products = products.filter(p => p.category_id !== id); body = {id,status:'archived'}; }
        }
        else if (req.url === '/api/v1/branches') body = [branch];
        res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify(body));
      });
    },
  }], server: { host: '127.0.0.1', port: 4176, strictPort: true },
});
await server.listen();
console.log('Admin QA: http://127.0.0.1:4176/qa-category');
