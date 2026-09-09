export interface PresentedOrderModifier {
  label: string;
  priceDeltaCents: number;
  priceLabel: string | null;
}

const FALLBACK_LABEL = 'Instrucción sin etiqueta';

const firstText = (...candidates: unknown[]): string | null => {
  for (const candidate of candidates) {
    if (typeof candidate !== 'string') continue;
    const label = candidate.trim().replace(/^(?:\+\s*)+/, '').trim();
    if (label) return label;
  }
  return null;
};

const firstMoneyAmount = (...candidates: unknown[]): number => {
  for (const candidate of candidates) {
    if (typeof candidate === 'number' && Number.isSafeInteger(candidate)) return candidate;
  }
  return 0;
};

const formatMxnDelta = (priceDeltaCents: number): string | null => {
  if (priceDeltaCents === 0) return null;
  const sign = priceDeltaCents > 0 ? '+' : '-';
  return `${sign}$${(Math.abs(priceDeltaCents) / 100).toFixed(2)}`;
};

/** Normalizes current API snapshots and historical aliases without rewriting them. */
export const formatOrderModifier = (modifier: unknown): PresentedOrderModifier => {
  if (typeof modifier === 'string') {
    const label = firstText(modifier) ?? FALLBACK_LABEL;
    return { label, priceDeltaCents: 0, priceLabel: null };
  }

  const snapshot = modifier && typeof modifier === 'object' ? modifier as Record<string, unknown> : {};
  const label = firstText(snapshot.kitchen_text, snapshot.option_name, snapshot.name, snapshot.text) ?? FALLBACK_LABEL;
  const priceDeltaCents = firstMoneyAmount(snapshot.price_delta_cents, snapshot.price_cents);
  return { label, priceDeltaCents, priceLabel: formatMxnDelta(priceDeltaCents) };
};
