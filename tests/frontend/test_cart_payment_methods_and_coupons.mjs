import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');

test('MobileCashShiftTab provides payment methods configuration with Cash (default true), Card, and Bank Transfer fields', () => {
  const source = readFileSync(join(root, 'apps/admin-web/src/features/mobile-admin/MobileCashShiftTab.tsx'), 'utf8');

  // Controls for Cash, Card, and Transfer
  assert.match(source, /Métodos de Cobro y Pagos/i);
  assert.match(source, /acceptsCashPayments/);
  assert.match(source, /acceptsCardPayments/);
  assert.match(source, /bankTransferInfo/);

  // Bank transfer input fields: Banco, Titular, Cuenta, CLABE
  assert.match(source, /bank_name/);
  assert.match(source, /account_holder/);
  assert.match(source, /account_number/);
  assert.match(source, /clabe/);

  // Default state for Cash is true
  assert.match(source, /useState\(true\)/);
});

test('Mobile web types declare payment methods and BankTransferInfo on BranchInfo', () => {
  const source = readFileSync(join(root, 'apps/mobile-web/src/types.ts'), 'utf8');

  assert.match(source, /export interface BankTransferInfo/);
  assert.match(source, /accepts_cash_payments\?: boolean/);
  assert.match(source, /accepts_card_payments\?: boolean/);
  assert.match(source, /bank_transfer_info\?: BankTransferInfo/);
});

test('CartDrawer conditionally hides coupon input if no coupons are active and configured', () => {
  const source = readFileSync(join(root, 'apps/mobile-web/src/components/CartDrawer.tsx'), 'utf8');

  // Must check if coupons are configured before showing "¿Tienes un cupón de descuento?"
  assert.match(source, /hasConfiguredCoupons/);
  assert.match(source, /selectedBranch\?\.coupons/);
  assert.match(source, /hasConfiguredCoupons &&/);
});

test('CartDrawer conditionally displays Cash, Card, and Transfer payment options and renders bank info on transfer', () => {
  const source = readFileSync(join(root, 'apps/mobile-web/src/components/CartDrawer.tsx'), 'utf8');

  // Cash pill conditioned on accepts_cash_payments !== false
  assert.match(source, /isCashEnabled/);
  assert.match(source, /isCardEnabled/);
  assert.match(source, /isTransferEnabled/);

  // Bank transfer info display when transfer is selected
  assert.match(source, /Datos para Transferencia/);
  assert.match(source, /bank_name/);
  assert.match(source, /clabe/);
});

test('Mobile web styles cart items with wider and more spacious layout', () => {
  const source = readFileSync(join(root, 'apps/mobile-web/src/index.css'), 'utf8');

  assert.match(source, /\.cart-item-modern-card\s*\{[^}]*padding:\s*(1[2-8]px|1rem)/);
});
