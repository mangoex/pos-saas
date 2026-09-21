import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');

test('MobileCashShiftTab provides Horarios y Caja Automática section with 7 days and $500 default', () => {
  const source = readFileSync(join(root, 'apps/admin-web/src/features/mobile-admin/MobileCashShiftTab.tsx'), 'utf8');

  // Interface & default schedule
  assert.match(source, /export interface DayScheduleForm/);
  assert.match(source, /DEFAULT_SCHEDULE:\s*DayScheduleForm\[\]/);
  assert.match(source, /const \[autoCashOpeningPesos, setAutoCashOpeningPesos\] = useState\('500'\)/);
  assert.match(source, /const \[autoCashShiftEnabled, setAutoCashShiftEnabled\] = useState\(false\)/);

  // Section title & copy action
  assert.match(source, /Horarios y Caja Automática/);
  assert.match(source, /Apertura y Cierre Automático de Caja/);
  assert.match(source, /Fondo Inicial Automático \(\$ MXN\)/);
  assert.match(source, /handleCopyScheduleToAllOpenDays/);
  assert.match(source, /Copiar a todos/);

  // Open/closed toggles and time fields per day
  assert.match(source, /Cerrado \/ Descanso/);
  assert.match(source, /Hora Apertura/);
  assert.match(source, /Hora Cierre/);
  assert.match(source, /Guardar Horarios y Caja Automática/);
});

test('Mobile digital menu types declare DaySchedule and service_schedule on BranchInfo', () => {
  const source = readFileSync(join(root, 'apps/mobile-web/src/types.ts'), 'utf8');

  assert.match(source, /export interface DaySchedule/);
  assert.match(source, /service_schedule\?: DaySchedule\[\]/);
});

test('CartDrawer restricts closed days and enforces operating hours on pickup times', () => {
  const source = readFileSync(join(root, 'apps/mobile-web/src/components/CartDrawer.tsx'), 'utf8');

  // scheduleByDay mapping
  assert.match(source, /const scheduleByDay = useMemo/);
  assert.match(source, /selectedBranch\?\.service_schedule/);

  // Disabled and isClosed check
  assert.match(source, /const isClosed = daySchedule \? daySchedule\.is_open === false : false/);
  assert.match(source, /const disabled = isPast \|\| isClosed/);

  // Auto fallback to first non-disabled day
  assert.match(source, /const firstAvailable = weekDayOptions\.find\(\(d\) => !d\.disabled\)/);

  // Min/max on pickup time input
  assert.match(source, /min=\{currentDaySchedule\?\.is_open \? currentDaySchedule\.open_time : undefined\}/);
  assert.match(source, /max=\{currentDaySchedule\?\.is_open \? currentDaySchedule\.close_time : undefined\}/);

  // Filter quick chips to not exceed closing time
  assert.match(source, /return `\$\{hh\}:\$\{mm\}` <= currentDaySchedule\.close_time/);

  // Validation in handleSubmit
  assert.match(source, /se encuentra cerrado para pedidos/);
  assert.match(source, /Por favor elige una hora dentro de este rango/);

  // Hours displayed in summary badge
  assert.match(source, /Horario de servicio/);
});
