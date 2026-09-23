// In-memory admin + customer fixture. No credentials or production services.
// node tests/browser/pickup-grace-fixture.mjs
import { createRequire } from 'node:module';
import { resolve, dirname } from 'node:path';
import { pathToFileURL } from 'node:url';
import { branch } from './mobile-cart-fixture.mjs';
const require = createRequire(resolve('apps/admin-web/package.json'));
const { createServer } = await import(pathToFileURL(require.resolve('vite')).href);
const { default: react } = await import(pathToFileURL(require.resolve('@vitejs/plugin-react')).href);
branch.pickup_grace_minutes = process.env.QA_UPLOADED_COVERS === '1' ? 30 : null;
branch.service_schedule = Array.from({length: 7}, (_, day_index) => ({day_index, is_open:true, open_time:'00:00', close_time:'23:59'}));
const entry = '/@fs/' + resolve('tests/browser/pickup-settings-entry.tsx').replaceAll('\\', '/');
const server = await createServer({
  resolve: { alias: Object.fromEntries(['react', 'react-dom', '@tanstack/react-query'].map(name => [name, dirname(require.resolve(`${name}/package.json`))])) },
  configFile: false, root: resolve('apps/admin-web'), plugins: [react(), {
    name: 'pickup-qa', configureServer(vite) {
      vite.middlewares.use(async (req, res, next) => {
        if (req.url === '/qa-pickup') {
          res.setHeader('Content-Type', 'text/html');
          return res.end(await vite.transformIndexHtml(req.url, `<html><head><meta name="viewport" content="width=device-width,initial-scale=1" /></head><body style="margin:0;font-family:Arial;color:#fff"><div id="root"></div><script type="module" src="${entry}"></script></body></html>`));
        }
        if (!req.url?.startsWith('/api/')) return next();
        let body = {};
        if (req.url === '/api/v1/branches') body = [branch];
        else if (req.url === '/api/v1/branches/qa-branch' && req.method === 'PUT') {
          let raw = ''; for await (const chunk of req) raw += chunk;
          Object.assign(branch, JSON.parse(raw)); body = branch;
        } else if (req.url.includes('/organization/profile')) body = { id: 'qa', name: 'QA', plan: 'lite', subscription_status: 'active' };
        else if (req.url.includes('/saas/links')) body = { name: 'QA', canonical_slug: 'qa', canonical_menu_url: 'http://127.0.0.1:4174/menu/', links: { menu: 'http://127.0.0.1:4174/menu/' } };
        res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify(body));
      });
    },
  }], server: { host: '127.0.0.1', port: 4175, strictPort: true },
});
await server.listen();
console.log('Admin QA: http://127.0.0.1:4175/qa-pickup');
