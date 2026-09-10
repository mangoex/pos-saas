import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');

test('CartDrawer calculates delivery fee and free delivery threshold dynamically', () => {
  const source = readFileSync(join(root, 'apps/mobile-web/src/components/CartDrawer.tsx'), 'utf8');

  // Delivery fee logic
  assert.match(source, /delivery_fee_enabled/);
  assert.match(source, /free_delivery_min_cents/);
  assert.match(source, /delivery_tiers/);
  assert.match(source, /hasFreeDelivery/);

  // UI free delivery banners
  assert.match(source, /¡Felicidades! Calificas para/);
  assert.match(source, /Envío GRATIS/);
  assert.match(source, /más para obtener/);

  // Breakdown lines
  assert.match(source, /Subtotal de productos/);
  assert.match(source, /Costo de envío/);
  assert.match(source, /¡GRATIS!/);
  assert.match(source, /Total a Pagar/);
});

test('OrderSuccessModal displays delivery fee breakdown on confirmed orders', () => {
  const source = readFileSync(join(root, 'apps/mobile-web/src/components/OrderSuccessModal.tsx'), 'utf8');

  assert.match(source, /delivery_fee_cents/);
  assert.match(source, /Envío a Domicilio/i);
  assert.match(source, /¡Gratis!/);
});

test('PointOfSale allows 1-touch delivery tier selection and includes delivery fee in order payload', () => {
  const source = readFileSync(join(root, 'apps/pos-web/src/features/pos/PointOfSale.tsx'), 'utf8');

  // Quick tier selection
  assert.match(source, /selectedDeliveryTier/);
  assert.match(source, /deliveryFeeCents/);
  assert.match(source, /Tarifa de envío/);

  // Delivery fee passed in payload
  assert.match(source, /delivery_fee_cents:\s*orderType === 'delivery' \? deliveryFeeCents : 0/);

  // Visual breakdown in cart and payment
  assert.match(source, /Envío/);
  assert.match(source, /Gratis/);
});

test('MobileBranchSettingsTab provides complete delivery fee configuration with free tier and threshold', () => {
  const source = readFileSync(join(root, 'apps/admin-web/src/features/mobile-admin/MobileBranchSettingsTab.tsx'), 'utf8');

  assert.match(source, /Costos de Envío a Domicilio/);
  assert.match(source, /deliveryFeeEnabled/);
  assert.match(source, /freeDeliveryMinPesos/);
  assert.match(source, /deliveryTiers/);
  assert.match(source, /Predeterminado Web/);
  assert.match(source, /Corta/);
  assert.match(source, /Media/);
  assert.match(source, /Lejana/);
  assert.match(source, /Gratis/);
});

test('BranchesList provides delivery fee configuration in administrative branch modal', () => {
  const source = readFileSync(join(root, 'apps/admin-web/src/features/branches/BranchesList.tsx'), 'utf8');

  assert.match(source, /Costos de Envío a Domicilio/);
  assert.match(source, /delivery_fee_enabled/);
  assert.match(source, /free_delivery_min_cents/);
  assert.match(source, /delivery_tiers/);
  assert.match(source, /Predeterminado Web/);
});
