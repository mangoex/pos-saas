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
} finally { rmSync(tmp, { recursive: true, force: true }); }
