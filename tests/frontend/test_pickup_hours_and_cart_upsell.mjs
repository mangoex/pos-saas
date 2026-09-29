import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import test from 'node:test';

const root = resolve(import.meta.dirname, '../..');

test('CartDrawer consumes server slots with explicit selection; browser does not calculate availability', () => {
  const source = readFileSync(resolve(root, 'apps/mobile-web/src/components/CartDrawer.tsx'), 'utf8');
  const hook = readFileSync(resolve(root, 'apps/mobile-web/src/hooks/usePickupOptions.ts'), 'utf8');
  assert.match(source, /usePickupOptions\(branchKey, orderType === 'takeaway'\)/);
  assert.match(source, /<select[^>]*id="pickup-time-input"/);
  assert.match(source, /className="pickup-time-field"/);
  assert.match(source, /availablePickupSlots\.map/);
  assert.match(source, /validatePickupSelection\(freshOptions, requestedDate, requestedTime\)/);
  assert.doesNotMatch(source, /generatePickupTimeSlots|getHours\(|getMinutes\(|getDay\(/);
  assert.match(hook, /setInterval\(refreshVisible, 60_000\)/);
  assert.match(hook, /addEventListener\('focus', refreshVisible\)/);
  assert.match(hook, /addEventListener\('visibilitychange', refreshVisible\)/);
});

test('CartDrawer renders product photograph in cart-upsell suggestions if configured, falling back to icon', () => {
  const source = readFileSync(resolve(root, 'apps/mobile-web/src/components/CartDrawer.tsx'), 'utf8');
  const css = readFileSync(resolve(root, 'apps/mobile-web/src/index.css'), 'utf8');
  assert.match(source, /cart-upsell-card/);
  assert.match(source, /prod\.image_url\s*\|\|\s*getProductImage\(prod\)/);
  assert.match(source, /cart-upsell-card-img/);
  assert.match(source, /getRecommendationIcon/);
  assert.match(css, /\.cart-upsell-card-img\s*\{[^}]*object-fit:\s*cover/);
});
