import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const source = new URL('../../apps/landing-web/src/', import.meta.url);
const html = readFileSync(new URL('index.html', source), 'utf8');
const script = readFileSync(new URL('app.js', source), 'utf8');
const listeners = [];
let mounts = 0;
const mobile = { matches: true, addEventListener: (_, fn) => listeners.push(fn) };
const element = { dataset: {}, style: { setProperty() {} }, querySelector() {} };
const window = {
  matchMedia: query => query.includes('860px') ? mobile : { matches: false },
  addEventListener() {}, requestAnimationFrame() { return 1; },
  ScrollCraft: { mount() { mounts++; } },
};
vm.runInNewContext(script, {
  window, document: {
    documentElement: element, body: element,
    querySelector: () => element, querySelectorAll: () => [],
  },
});
assert.equal(mounts, 0, 'a mobile visit must not initialize the video/scroll engine');
mobile.matches = false;
listeners.forEach(fn => fn());
assert.equal(mounts, 1, 'desktop becomes available after widening the viewport');
mobile.matches = true;
listeners.forEach(fn => fn());
mobile.matches = false;
listeners.forEach(fn => fn());
assert.equal(mounts, 1, 'resizing must not duplicate the desktop engine');
const compact = html.match(/<main class="mobile-landing"[\s\S]*?<\/main>/)?.[0];
assert.ok(compact, 'mobile acquisition content is present without JavaScript');
assert.match(compact, /href="\/admin\/register\?plan=trial"/);
assert.match(compact, /href="\/admin\/login"/);
assert.doesNotMatch(compact, /<video|data-sc-/);
console.log('Mobile landing: deferred engine, resize lifecycle and acquisition links passed.');
