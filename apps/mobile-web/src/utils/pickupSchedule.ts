import type { DaySchedule } from '../types';

export interface PickupTimeSlot {
  value: string; // "16:00" (24h)
  label: string; // "16:00 (04:00 PM)"
}

export interface PickupScheduleOptions {
  isToday?: boolean;
  referenceDate?: Date;
  intervalMinutes?: number;
  leadTimeMinutes?: number;
}

export function formatTimeSlotLabel(timeStr: string): string {
  const parts = timeStr.split(':');
  if (parts.length < 2) return timeStr;
  const hours = parseInt(parts[0], 10);
  const minutes = parseInt(parts[1], 10);
  if (isNaN(hours) || isNaN(minutes)) return timeStr;

  const period = hours >= 12 ? 'PM' : 'AM';
  const displayHours = hours % 12 === 0 ? 12 : hours % 12;
  const padH = String(displayHours).padStart(2, '0');
  const padM = String(minutes).padStart(2, '0');
  return `${timeStr} (${padH}:${padM} ${period})`;
}

/**
 * Generates available pickup time slots strictly bounded by the branch's service schedule.
 * If isToday is true, slots prior to the current time (+ lead time) are excluded.
 */
export function generatePickupTimeSlots(
  schedule: DaySchedule | null | undefined,
  options: PickupScheduleOptions = {}
): PickupTimeSlot[] {
  if (!schedule || schedule.is_open === false) {
    return [];
  }

  const openTime = schedule.open_time || '09:00';
  const closeTime = schedule.close_time || '22:00';

  const [openH, openM] = openTime.split(':').map((v) => parseInt(v, 10));
  const [closeH, closeM] = closeTime.split(':').map((v) => parseInt(v, 10));

  if (isNaN(openH) || isNaN(openM) || isNaN(closeH) || isNaN(closeM)) {
    return [];
  }

  const interval = Math.max(5, options.intervalMinutes ?? 15);
  const openMinutes = openH * 60 + openM;
  const closeMinutes = closeH * 60 + closeM;

  if (openMinutes >= closeMinutes) {
    return [];
  }

  let startMinutes = openMinutes;

  if (options.isToday) {
    const refDate = options.referenceDate ?? new Date();
    const leadTime = options.leadTimeMinutes ?? 15;
    const currentMins = refDate.getHours() * 60 + refDate.getMinutes() + leadTime;
    const rounded = Math.ceil(currentMins / interval) * interval;
    startMinutes = Math.max(openMinutes, rounded);
  }

  if (startMinutes > closeMinutes) {
    return [];
  }

  const slots: PickupTimeSlot[] = [];
  for (let mins = startMinutes; mins <= closeMinutes; mins += interval) {
    const hh = String(Math.floor(mins / 60)).padStart(2, '0');
    const mm = String(mins % 60).padStart(2, '0');
    const timeValue = `${hh}:${mm}`;
    slots.push({
      value: timeValue,
      label: formatTimeSlotLabel(timeValue),
    });
  }

  return slots;
}

/**
 * Validates or falls back to the first available slot when the selected day changes
 * or the currently chosen time is outside the permitted operating window.
 */
export function getInitialPickupTime(currentTime: string, availableSlots: PickupTimeSlot[]): string {
  if (!availableSlots || availableSlots.length === 0) {
    return '';
  }
  const match = availableSlots.find((s) => s.value === currentTime);
  if (match) {
    return currentTime;
  }
  return availableSlots[0].value;
}
