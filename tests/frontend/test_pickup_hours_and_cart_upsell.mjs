import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdtempSync, rmSync, readFileSync, existsSync } from 'node:fs';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');

test('pickupSchedule utility generates slots strictly within branch service window and filters past times on today', () => {
  const tmp = mkdtempSync(join(tmpdir(), 'pickup-sched-'));
  try {
    execFileSync(process.execPath, [
      join(root, 'node_modules/typescript/bin/tsc'),
      '--target', 'ES2022',
      '--module', 'CommonJS',
      '--skipLibCheck',
      '--outDir', tmp,
      join(root, 'apps/mobile-web/src/utils/pickupSchedule.ts'),
    ]);

    const jsPath = existsSync(join(tmp, 'utils/pickupSchedule.js'))
      ? join(tmp, 'utils/pickupSchedule.js')
      : join(tmp, 'pickupSchedule.js');
    const { generatePickupTimeSlots, getInitialPickupTime } = createRequire(import.meta.url)(jsPath);

    // Scenario 1: Monday configured from 16:00 to 18:00 (Future day / not today)
    const mondaySchedule = {
      day_index: 0,
      day_name: 'Lunes',
      is_open: true,
      open_time: '16:00',
      close_time: '18:00',
    };

    const futureSlots = generatePickupTimeSlots(mondaySchedule, { isToday: false, intervalMinutes: 15 });
    assert.ok(futureSlots.length > 0, 'Must generate slots for open future day');

    // Verify all slots are strictly between 16:00 and 18:00
    for (const slot of futureSlots) {
      assert.ok(slot.value >= '16:00', `Slot ${slot.value} must be >= 16:00`);
      assert.ok(slot.value <= '18:00', `Slot ${slot.value} must be <= 18:00`);
    }

    // Exact expected slots
    const expectedValues = ['16:00', '16:15', '16:30', '16:45', '17:00', '17:15', '17:30', '17:45', '18:00'];
    assert.deepEqual(futureSlots.map((s) => s.value), expectedValues);

    // Scenario 2: Today when currentTime is before opening (e.g. 10:00)
    const slotsTodayEarly = generatePickupTimeSlots(mondaySchedule, {
      isToday: true,
      referenceDate: new Date('2026-09-21T10:00:00'),
      intervalMinutes: 15,
    });
    assert.deepEqual(slotsTodayEarly.map((s) => s.value), expectedValues);

    // Scenario 3: Today when currentTime is during service (e.g. 16:20)
    const slotsTodayMid = generatePickupTimeSlots(mondaySchedule, {
      isToday: true,
      referenceDate: new Date('2026-09-21T16:20:00'),
      intervalMinutes: 15,
      leadTimeMinutes: 15,
    });
    // 16:20 + 15 min = 16:35 -> next slot 16:45
    assert.ok(slotsTodayMid.every((s) => s.value >= '16:45' && s.value <= '18:00'));

    // Scenario 4: Closed day
    const closedSchedule = { ...mondaySchedule, is_open: false };
    assert.deepEqual(generatePickupTimeSlots(closedSchedule, { isToday: false }), []);

    // Scenario 5: getInitialPickupTime selects first available slot or retains current if valid
    assert.equal(getInitialPickupTime('12:00', futureSlots), '16:00', 'Must fallback to first valid slot if current is out of range');
    assert.equal(getInitialPickupTime('16:30', futureSlots), '16:30', 'Must preserve current time if within range');
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
});

test('CartDrawer uses select input with restricted slots for pickup time', () => {
  const source = readFileSync(join(root, 'apps/mobile-web/src/components/CartDrawer.tsx'), 'utf8');

  // Must import pickupSchedule helpers
  assert.match(source, /generatePickupTimeSlots/);

  // Must render select element with id="pickup-time-input" and className="pickup-time-field"
  assert.match(source, /<select[^>]*id="pickup-time-input"/);
  assert.match(source, /className="pickup-time-field"/);

  // Must render available time slot options
  assert.match(source, /availablePickupSlots/);

  // Must auto-adjust pickupTime when selected day changes if out of bounds
  assert.match(source, /getInitialPickupTime/);
});

test('CartDrawer renders product photograph in cart-upsell suggestions if configured, falling back to icon', () => {
  const source = readFileSync(join(root, 'apps/mobile-web/src/components/CartDrawer.tsx'), 'utf8');
  const css = readFileSync(join(root, 'apps/mobile-web/src/index.css'), 'utf8');

  // In cart-upsell section, checks product image
  assert.match(source, /cart-upsell-card/);
  assert.match(source, /prod\.image_url\s*\|\|\s*getProductImage\(prod\)/);
  assert.match(source, /cart-upsell-card-img/);
  assert.match(source, /getRecommendationIcon/);

  // CSS must style the cart-upsell-card-img properly
  assert.match(css, /\.cart-upsell-card-img\s*\{[^}]*object-fit:\s*cover/);
});
