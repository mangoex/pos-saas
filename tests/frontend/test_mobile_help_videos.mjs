import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');

// 1. MobileHelpVideosModal existence and content
const modalPath = join(root, 'apps/admin-web/src/features/mobile-admin/MobileHelpVideosModal.tsx');
assert.equal(existsSync(modalPath), true, 'MobileHelpVideosModal.tsx must exist');
const modalCode = readFileSync(modalPath, 'utf8');

// YouTube IDs check
const expectedYoutubeIds = [
  'PpdcuCMAfPg', // Configurando el nombre
  'alaNrdtrP3k', // Editando productos
  'odb00yMa6Nk', // Creando el menú
  'qCWxvZHO_og', // Configurando envío a domicilio
  'htqLte7J7pU', // Cupones de descuento
  '5J94AFGaC9U', // Editando categorías
  't0255cZ6n_Y', // Aceptando pedidos
  'PQQQFGwhA9k', // Portada y pedidos por voz
];

for (const id of expectedYoutubeIds) {
  assert.match(modalCode, new RegExp(id), `MobileHelpVideosModal must include video with YouTube ID ${id}`);
}

assert.match(modalCode, /scrollSnapType|scroll-snap-type/, 'Must support horizontal scroll-snap carousel');
assert.match(modalCode, /img\.youtube\.com\/vi\//, 'Must load lightweight YouTube thumbnail images for mobile performance');
assert.match(modalCode, /<iframe/, 'Must provide an embedded video player for playback');

// 2. MobileAdminShell integration
const shellPath = join(root, 'apps/admin-web/src/features/mobile-admin/MobileAdminShell.tsx');
const shellCode = readFileSync(shellPath, 'utf8');

assert.match(shellCode, /MobileHelpVideosModal/, 'MobileAdminShell must import or reference MobileHelpVideosModal');
assert.match(shellCode, /<MobileHelpVideosModal/, 'MobileAdminShell must render MobileHelpVideosModal');

// 3. Tab headers or Shell have access to open help videos
assert.match(shellCode, /onOpenHelpVideos|isHelpModalOpen|setIsHelpModalOpen/, 'MobileAdminShell must manage help modal state');

console.log('✓ All Mobile Help Videos tests PASSED!');
