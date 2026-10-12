import type { PickupOptions } from '../types';

export function formatTimeSlotLabel(value: string): string {
  const [hours, minutes] = value.split(':').map(Number);
  return `${value} (${String(hours % 12 || 12).padStart(2, '0')}:${String(minutes).padStart(2, '0')} ${hours >= 12 ? 'PM' : 'AM'})`;
}

/** Validate transport shape; Python alone determines the available dates and times. */
export function parsePickupOptions(value: unknown): PickupOptions {
  const record = (input: unknown): input is Record<string, unknown> => typeof input === 'object' && input !== null;
  if (!record(value) || typeof value.generated_at !== 'string' || !Number.isFinite(Date.parse(value.generated_at))
    || typeof value.timezone !== 'string' || !value.timezone || typeof value.configured !== 'boolean'
    || !Array.isArray(value.days) || value.days.length !== 7) throw new Error('pickup_options_invalid');
  const dates = new Set<string>();
  let previousDate = 0;
  for (const day of value.days) {
    const date = record(day) && typeof day.date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(day.date)
      ? Date.parse(`${day.date}T00:00:00Z`)
      : Number.NaN;
    const expectedDayIndex = Number.isFinite(date) ? (new Date(date).getUTCDay() + 6) % 7 : -1;
    if (!record(day) || day.day_index !== expectedDayIndex || !Number.isFinite(date)
      || new Date(date).toISOString().slice(0, 10) !== day.date || dates.has(day.date)
      || (previousDate !== 0 && date !== previousDate + 24 * 60 * 60 * 1000)
      || typeof day.is_today !== 'boolean' || typeof day.is_past !== 'boolean'
      || typeof day.is_closed !== 'boolean' || !Array.isArray(day.slots)) throw new Error('pickup_options_invalid');
    dates.add(day.date);
    previousDate = date;
    const times = new Set<string>();
    for (const slot of day.slots) {
      if (!record(slot) || typeof slot.value !== 'string' || !/^([01]\d|2[0-3]):[0-5]\d$/.test(slot.value)
        || times.has(slot.value) || typeof slot.scheduled_at !== 'string' || !Number.isFinite(Date.parse(slot.scheduled_at))
        || day.is_closed || day.is_past || !value.configured) throw new Error('pickup_options_invalid');
      times.add(slot.value);
    }
  }
  return value as unknown as PickupOptions;
}

export function validatePickupSelection(options: PickupOptions, date: string, time: string): void {
  if (!options.configured && !date && !time) return;
  if (!options.configured || !options.days.some(day => day.date === date && !day.is_closed && !day.is_past
    && day.slots.some(slot => slot.value === time))) throw new Error('pickup_slot_unavailable');
}

/** Latest request wins even when an aborted transport eventually resolves. */
export function createPickupOptionsLoader(
  fetcher: (key: string, signal: AbortSignal) => Promise<PickupOptions>,
  publish: (key: string, data: PickupOptions) => void,
) {
  let revision = 0;
  let controller: AbortController | undefined;
  return {
    async load(key: string): Promise<PickupOptions> {
      const request = ++revision;
      controller?.abort();
      controller = new AbortController();
      try {
        const data = await fetcher(key, controller.signal);
        if (request !== revision) throw new Error('pickup_request_superseded');
        publish(key, data);
        return data;
      } catch (error) {
        if (request !== revision) throw new Error('pickup_request_superseded');
        throw error;
      }
    },
    dispose() {
      revision++;
      controller?.abort();
    },
  };
}
