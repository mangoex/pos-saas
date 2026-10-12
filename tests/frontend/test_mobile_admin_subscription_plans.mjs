import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import vm from 'node:vm';
import test from 'node:test';

const require = createRequire(import.meta.url);
const ts = require('typescript');

test('subscription plan catalog defines Esencial, Conecta, and Control with exact features and checkout links', () => {
  const exports = {};
  const source = readFileSync('apps/admin-web/src/features/auth/subscriptionPlans.ts', 'utf8');
  vm.runInNewContext(ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText, { exports });

  assert.ok(Array.isArray(exports.SUBSCRIPTION_PLANS), 'SUBSCRIPTION_PLANS must be exported as an array');
  assert.equal(exports.SUBSCRIPTION_PLANS.length, 3, 'Must define exactly 3 subscription packages');

  const [esencial, conecta, control] = exports.SUBSCRIPTION_PLANS;

  assert.equal(esencial.code, 'starter_349');
  assert.equal(esencial.name, 'Esencial');
  assert.equal(esencial.priceMxn, 349);
  assert.match(esencial.features, /Menú digital, pedidos, caja, QR\/enlace, promociones, disponibilidad y administración desde celular\./i);

  assert.equal(conecta.code, 'conecta_699');
  assert.equal(conecta.name, 'Conecta');
  assert.equal(conecta.priceMxn, 699);
  assert.equal(conecta.checkoutUrl, 'https://mpago.la/2b3VRu1');
  assert.match(conecta.features, /Todo Esencial \+ integraciones con Uber Eats\/DiDi\/Rappi cuando estén disponibles \+ pedidos centralizados \+ sincronización de catálogo\/disponibilidad\./i);

  assert.equal(control.code, 'control_999');
  assert.equal(control.name, 'Control');
  assert.equal(control.priceMxn, 999);
  assert.equal(control.checkoutUrl, 'https://mpago.la/1yS6YdX');
  assert.match(control.features, /Todo Conecta \+ inventarios, recetas, subrecetas, costos, mermas, consumo de insumos, márgenes y reportes operativos\./i);
});

test('MobileBranchSettingsTab and SubscriptionStatus render plan dropdown and MP links', () => {
  const tabSource = readFileSync('apps/admin-web/src/features/mobile-admin/MobileBranchSettingsTab.tsx', 'utf8');
  assert.match(tabSource, /SUBSCRIPTION_PLANS/, 'MobileBranchSettingsTab must use SUBSCRIPTION_PLANS');
  assert.match(tabSource, /aria-label="Plan de suscripción"/, 'MobileBranchSettingsTab must contain plan dropdown');
  assert.match(tabSource, /selectedPlan\.checkoutUrl/, 'MobileBranchSettingsTab must render MP checkout link');

  const statusSource = readFileSync('apps/admin-web/src/features/auth/SubscriptionStatus.tsx', 'utf8');
  assert.match(statusSource, /SUBSCRIPTION_PLANS/, 'SubscriptionStatus must use SUBSCRIPTION_PLANS');
  assert.match(statusSource, /aria-label="Plan de suscripción"/, 'SubscriptionStatus must contain plan dropdown');
  assert.match(statusSource, /selectedPlan\?\.checkoutUrl/, 'SubscriptionStatus must render MP checkout link');
});

test('Register form provides Esencial, Conecta, and Control plan options', () => {
  const registerSource = readFileSync('apps/admin-web/src/features/auth/Register.tsx', 'utf8');

  assert.match(registerSource, /Esencial — \$349\/mes/, 'Register plan options must include Esencial');
  assert.match(registerSource, /Conecta — \$699\/mes/, 'Register plan options must include Conecta');
  assert.match(registerSource, /Control — \$999\/mes/, 'Register plan options must include Control');
});
