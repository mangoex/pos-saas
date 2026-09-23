/** Empty means no notice. The upper bound is PostgreSQL INTEGER, not a business limit. */
export function parsePickupGraceMinutes(raw: string): number | null {
  const text = raw.trim();
  if (!text) return null;
  const minutes = Number(text);
  if (!/^\d+$/.test(text) || !Number.isInteger(minutes) || minutes < 1 || minutes > 2147483647) {
    throw new Error('Ingresa minutos enteros positivos o deja el campo vacío.');
  }
  return minutes;
}

export function pickupGraceMessage(orderType: string, minutes?: number | null): string | null {
  if (orderType !== 'takeaway' || !Number.isInteger(minutes) || !minutes || minutes < 1 || minutes > 2147483647) return null;
  return `Respetaremos tu pedido durante ${minutes} ${minutes === 1 ? 'minuto' : 'minutos'} después de tu hora programada para recoger.`;
}
