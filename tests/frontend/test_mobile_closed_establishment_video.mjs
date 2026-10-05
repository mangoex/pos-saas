import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import ts from 'typescript';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const read = (path) => readFileSync(resolve(root, path), 'utf8');

const EXPECTED_MEDIA_URL =
  'https://res.cloudinary.com/dfvnyhur4/image/upload/v1791233300/gemini_generated_video_b41e5510-ezgif.com-video-to-webp-converter_muyy7a.webp';

test('imageMap exports exact closed establishment video/webp URL', () => {
  const source = read('apps/mobile-web/src/imageMap.ts');
  assert.match(
    source,
    /export const CLOSED_ESTABLISHMENT_HERO_MEDIA =\s*['"]https:\/\/res\.cloudinary\.com\/dfvnyhur4\/image\/upload\/v1791233300\/gemini_generated_video_b41e5510-ezgif\.com-video-to-webp-converter_muyy7a\.webp['"]/,
    'imageMap must define and export CLOSED_ESTABLISHMENT_HERO_MEDIA'
  );
  assert.match(
    source,
    /if \(cat\.includes\('cerrado'\)\) \{\s*return CLOSED_ESTABLISHMENT_HERO_MEDIA;/,
    'getCategoryCover must return CLOSED_ESTABLISHMENT_HERO_MEDIA for cerrado'
  );
});

test('api.ts assigns CLOSED_ESTABLISHMENT_HERO_MEDIA when has_active_shift is false (caja cerrada)', () => {
  const apiSource = read('apps/mobile-web/src/api.ts');
  assert.match(
    apiSource,
    /import \{[^}]*CLOSED_ESTABLISHMENT_HERO_MEDIA[^}]*\} from '\.\/imageMap';/,
    'api.ts must import CLOSED_ESTABLISHMENT_HERO_MEDIA'
  );
  assert.match(
    apiSource,
    /image_url:\s*isClosed\s*\?\s*CLOSED_ESTABLISHMENT_HERO_MEDIA\s*:/,
    'api.ts must set image_url to CLOSED_ESTABLISHMENT_HERO_MEDIA when isClosed (caja cerrada)'
  );
});

test('HeroHeader sets image_url to CLOSED_ESTABLISHMENT_HERO_MEDIA when isClosed is true', () => {
  const heroSource = read('apps/mobile-web/src/components/HeroHeader.tsx');
  assert.match(
    heroSource,
    /import \{[^}]*CLOSED_ESTABLISHMENT_HERO_MEDIA[^}]*\} from '\.\.\/imageMap';/,
    'HeroHeader must import CLOSED_ESTABLISHMENT_HERO_MEDIA'
  );
  assert.match(
    heroSource,
    /effectiveCat\s*=\s*\(isClosed\s*&&\s*isAll\)\s*\?\s*\{\s*\.\.\.cat,\s*name:\s*'Cerrado por el momento',\s*image_url:\s*CLOSED_ESTABLISHMENT_HERO_MEDIA\s*\}/,
    'HeroHeader must assign CLOSED_ESTABLISHMENT_HERO_MEDIA to effectiveCat when isClosed and isAll'
  );
});

test('CategoryArtwork renders CLOSED_ESTABLISHMENT_HERO_MEDIA when category is closed with fallback support', () => {
  const artworkSource = read('apps/mobile-web/src/components/CategoryArtwork.tsx');
  assert.match(
    artworkSource,
    /CLOSED_ESTABLISHMENT_HERO_MEDIA/,
    'CategoryArtwork must use CLOSED_ESTABLISHMENT_HERO_MEDIA'
  );
  assert.match(
    artworkSource,
    /isClosed \? CLOSED_ESTABLISHMENT_HERO_MEDIA : getCategoryImageUrl\(category\.image_url\)/,
    'CategoryArtwork must set url to CLOSED_ESTABLISHMENT_HERO_MEDIA when isClosed'
  );
  assert.match(
    artworkSource,
    /failedUrl === CLOSED_ESTABLISHMENT_HERO_MEDIA \? closedEstablishmentHeroFallback : CLOSED_ESTABLISHMENT_HERO_MEDIA/,
    'CategoryArtwork must fall back to closedEstablishmentHeroFallback if media fails'
  );
});
