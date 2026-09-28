import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';
import vm from 'node:vm';
import test from 'node:test';

const require = createRequire(import.meta.url);
const ts = require('typescript');
const root = resolve(import.meta.dirname, '../..');
const source = readFileSync(resolve(root, 'apps/mobile-web/src/components/CartDrawer.tsx'), 'utf8');
const handler = source.slice(source.indexOf('  const handleSubmit ='), source.indexOf('\n  return (', source.indexOf('  const handleSubmit =')));
const compiled = ts.transpileModule(`${handler}\nglobalThis.submit = handleSubmit;`, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText;

function setup(overrides = {}) {
  const sent = [];
  const errors = [];
  const context = {
    setFormError: message => errors.push(message), isBranchClosed: false,
    isSubmitting: false, editingBlockedReason: undefined, editingItem: false, items: [{}],
    submittingRef: { current: false }, setValidatingPickup: () => {},
    branchKey: 'branch-a', checkoutContextRef: { current: 'branch-a:takeaway' },
    name: 'Cliente', phone: '5511223344', orderType: 'takeaway', street: '', number: '',
    neighborhood: '', addressNotes: '', orderNotes: '', tableNumber: '',
    selectedDay: { date: '2026-09-28', name: 'Lunes', dateNumber: 28, monthName: 'sep', isToday: true, disabled: false },
    currentDaySchedule: { is_open: true, open_time: '16:00', close_time: '18:00' },
    pickupTime: '16:15', pickupOptions: { configured: true },
    refreshPickup: async () => ({ configured: true, days: [{ date: '2026-09-28', slots: [{ value: '16:30' }] }] }),
    validatePickupSelection: (data, date, time) => {
      if (!data.days.some(day => day.date === date && day.slots.some(slot => slot.value === time))) throw new Error('pickup_slot_unavailable');
    },
    paymentMethod: 'cash', cashAmount: '', deliveryFeeCents: 0, appliedCoupon: null, discountCents: 0,
    saveCustomerProfile: () => {}, onSubmitOrder: info => sent.push(info),
    ...overrides,
  };
  vm.createContext(context);
  vm.runInContext(compiled, context);
  return { context, sent, errors, submit: () => context.submit({ preventDefault() {} }) };
}

test('expired selection never reaches order submission after server refresh', async () => {
  const fixture = setup();
  await fixture.submit();
  assert.equal(fixture.sent.length, 0);
  assert.ok(fixture.errors.some(error => /horario/i.test(error)));
});

test('network failure blocks a new scheduled order and leaves a visible error', async () => {
  const fixture = setup({ refreshPickup: async () => { throw new Error('offline'); } });
  await fixture.submit();
  assert.equal(fixture.sent.length, 0);
  assert.ok(fixture.errors.some(Boolean));
});

test('branch or order mode changes during revalidation prevent submission', async () => {
  for (const nextContext of ['branch-b:takeaway', 'branch-a:delivery', '']) {
    let finish;
    const fixture = setup({ refreshPickup: () => new Promise(resolve => { finish = resolve; }) });
    const pending = fixture.submit();
    fixture.context.checkoutContextRef.current = nextContext;
    finish({ configured: true, days: [{ date: '2026-09-28', slots: [{ value: '16:15' }] }] });
    await pending;
    assert.equal(fixture.sent.length, 0);
  }
});

test('double submit revalidates once and sends the selected pair and matching note', async () => {
  let finish;
  let loads = 0;
  const fixture = setup({ refreshPickup: () => { loads++; return new Promise(resolve => { finish = resolve; }); } });
  const first = fixture.submit();
  await fixture.submit();
  finish({ configured: true, days: [{ date: '2026-09-28', slots: [{ value: '16:15' }] }] });
  await first;
  assert.equal(loads, 1);
  assert.equal(fixture.sent.length, 1);
  assert.equal(fixture.sent[0].pickup_date, '2026-09-28');
  assert.equal(fixture.sent[0].pickup_time, '16:15');
  assert.match(fixture.sent[0].order_notes, /2026-09-28 a las 16:15/);
});
