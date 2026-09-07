import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const read = path => readFileSync(resolve(root, path), 'utf8');
const cache = new Map();
let failedUrl = null;
const react = {
  createElement: (type, props, ...children) => ({ type, props: { ...props, children } }),
  useState: () => [failedUrl, value => { failedUrl = value; }],
};
function load(path) {
  if (cache.has(path)) return cache.get(path);
  const code = ts.transpileModule(read(path), { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
    jsx: ts.JsxEmit.React, esModuleInterop: true,
  } }).outputText;
  const module = { exports: {} };
  new Function('require', 'module', 'exports', code)(name => {
    if (name === 'react') return react;
    if (name === 'lucide-react') return {};
    const target = resolve(root, dirname(path), name);
    return load(existsSync(target + '.ts') ? target + '.ts' : target + '.tsx');
  }, module, module.exports);
  cache.set(path, module.exports);
  return module.exports;
}
const imageMap = load('apps/mobile-web/src/imageMap.ts');
assert.equal(imageMap.getCategoryImageUrl('javascript:alert(1)'), '');
assert.equal(imageMap.getCategoryImageUrl('https://user:password@example.com/a'), '');
assert.equal(imageMap.getCategoryImageUrl(' https://example.com/a.jpg '), 'https://example.com/a.jpg');

const api = load('apps/mobile-web/src/api.ts');
const originalFetch = globalThis.fetch;
try {
  globalThis.fetch = async () => new Response(JSON.stringify({
    menu_home: { name: 'Nuestra carta', image_url: 'https://example.com/hero.jpg' },
    categories: [{ id: 'c1', name: 'Nuestra carta', image_url: 'https://example.com/tacos.jpg' },
                 { id: 'c2', name: 'Todos' }],
    items: [{ id: 'p1', name: 'Taco', category_id: 'c1', category_name: 'Nuestra carta', price_cents: 3000 }],
  }));
  const catalog = await api.fetchMobileMenu('public-key');
  assert.equal(catalog.categories[0].id, 'all');
  assert.equal(catalog.categories[0].name, 'Nuestra carta');
  assert.equal(catalog.categories[0].image_url, 'https://example.com/hero.jpg');
  assert.deepEqual(catalog.categories.map(c => c.id), ['all', 'c1', 'c2']);
  assert.equal(catalog.categories[1].image_url, 'https://example.com/tacos.jpg');
  globalThis.fetch = async () => new Response(JSON.stringify({ categories: [], items: [] }));
  assert.equal((await api.fetchMobileMenu('other-key')).categories[0].name, 'Todos');
} finally { globalThis.fetch = originalFetch; }

const { CategoryArtwork } = load('apps/mobile-web/src/components/CategoryArtwork.tsx');
const category = { id: 'all', name: 'Nuestra carta', image_url: 'https://example.com/hero.jpg' };
let image = CategoryArtwork({ category });
assert.equal(image.props.src, category.image_url);
image.props.onError();
image = CategoryArtwork({ category });
assert.match(image.props.src, /^data:image\/svg\+xml/);
assert.equal(image.props.onError, undefined, 'fallback must not loop on error');
assert.equal(CategoryArtwork({ category, circle: true }).type, 'span');
assert.equal(CategoryArtwork({ category: { ...category, image_url: 'https://example.com/new.jpg' } }).props.src, 'https://example.com/new.jpg');
const scrolls = [];
react.useRef = () => ({ current: { clientWidth: 390, scrollTo: position => scrolls.push(position.left) } });
react.useEffect = effect => effect();
react.useCallback = callback => callback;
const { HeroHeader } = load('apps/mobile-web/src/components/HeroHeader.tsx');
HeroHeader({ categories: [{id:'all',name:'Carta'},{id:'tacos',name:'Tacos'}], activeCategoryId:'tacos', selectedBranch:null, searchQuery:'' });
assert.deepEqual(scrolls, [390], 'selecting a circle must move the hero to that category');
for (const component of ['HeroHeader', 'CategoryCircles', 'CategoryStories']) {
  const source = read(`apps/mobile-web/src/components/${component}.tsx`);
  assert.match(source, /CategoryArtwork/);
  assert.doesNotMatch(source, /cat.name === 'Todos'/, 'display name must not decide all-products identity');
}
assert.match(read('apps/admin-web/src/features/catalog/CategoriesList.tsx'), /image_url: data.image_url/);
assert.match(read('apps/admin-web/src/features/catalog/MenuHomeEditor.tsx'), /\/catalog\/menu-home/);
console.log('Category pictures, renamed master category, tenant switch and image fallback passed');
