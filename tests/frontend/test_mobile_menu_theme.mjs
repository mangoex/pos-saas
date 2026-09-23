import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdtempSync, rmSync } from 'node:fs';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
const root = resolve(import.meta.dirname, '../..');
const tmp = mkdtempSync(join(tmpdir(), 'menu-theme-'));
try {
  execFileSync(process.execPath, [join(root, 'node_modules/typescript/bin/tsc'), '--target', 'ES2022', '--module', 'CommonJS', '--skipLibCheck', '--outDir', tmp, join(root, 'apps/mobile-web/src/utils/menuTheme.ts')]);
  const { resolveMenuTheme } = createRequire(import.meta.url)(join(tmp, 'menuTheme.js'));
  for (const palette of ['orange', 'green', 'blue', 'tinto']) {
    for (const appearance of ['light', 'dark', null]) assert.equal(resolveMenuTheme(palette, appearance).palette, palette);
  }
  assert.deepEqual(resolveMenuTheme('unknown', 'dark'), { palette: 'orange', appearance: 'dark' });
  assert.deepEqual(resolveMenuTheme(undefined, undefined), { palette: 'orange', appearance: 'light' });
  console.log('PASS: four palettes, legacy appearance and safe fallback');
  execFileSync(process.execPath, [join(root, 'node_modules/typescript/bin/tsc'), '--target', 'ES2022', '--module', 'CommonJS', '--skipLibCheck', '--outDir', tmp, join(root, 'apps/mobile-web/src/imageMap.ts')]);
  const { getCategoryImageUrl } = createRequire(import.meta.url)(join(tmp, 'imageMap.js'));
  for (const format of ['jpeg', 'jpg', 'png', 'webp', 'gif']) {
    const photo = `data:image/${format};base64,aGVsbG8=`;
    assert.equal(getCategoryImageUrl(photo), photo, 'admin uploads must remain visible');
  }
  assert.equal(getCategoryImageUrl(' https://example.com/photo.jpg '), 'https://example.com/photo.jpg');
  assert.equal(getCategoryImageUrl('data:image/png;base64,' + 'A'.repeat(2 * 1024 * 1024)), '');
  for (const value of ['data:image/svg+xml;base64,aGVsbG8=', 'data:text/html;base64,aGVsbG8=', 'javascript:alert(1)', 'https://user:pass@example.com/a', 'data:image/png;base64,???', '', null]) {
    assert.equal(getCategoryImageUrl(value), '');
  }
  console.log('PASS: uploaded raster photos, remote photos and unsafe URL rejection');
} finally { rmSync(tmp, { recursive: true, force: true }); }
