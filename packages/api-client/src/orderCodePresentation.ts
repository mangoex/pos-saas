const PUBLIC_INTENT_REFERENCE = /^PI-([0-9A-F]{32})$/i;
const UUID_REFERENCE = /^[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-([0-9A-F]{12})$/i;
const COMPACT_UUID_REFERENCE = /^([0-9A-F]{32})$/i;

const shortSuffix = (value: string): string => value.slice(-6).toUpperCase();

/** Keeps human folios intact while hiding internal identifiers in operational views. */
export const formatOrderCode = (folio: unknown): string => {
  if (typeof folio !== 'string' || !folio.trim()) return 'PEDIDO';
  const value = folio.trim();

  const publicIntent = value.match(PUBLIC_INTENT_REFERENCE);
  if (publicIntent) return `WEB-${shortSuffix(publicIntent[1])}`;

  const uuid = value.match(UUID_REFERENCE);
  if (uuid) return `PED-${shortSuffix(uuid[1])}`;

  const compactUuid = value.match(COMPACT_UUID_REFERENCE);
  if (compactUuid) return `PED-${shortSuffix(compactUuid[1])}`;

  return value;
};
