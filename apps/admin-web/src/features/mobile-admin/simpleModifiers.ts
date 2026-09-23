import { centsToMxn, mxnToCentsExact } from '../catalog/ingredientVariationMoney';

export interface SimpleModifierOption {
  name: string;
  price_delta_cents: number;
}

export interface SimpleModifiersProductSnapshot {
  id: string;
  name: string;
  description?: string | null;
  sku: string;
  category_name: string;
  station: string;
  price_cents: number | null;
  image_url: string | null;
  status: string;
  is_promo: boolean;
  promo_price_cents: number | null;
  promo_badge_text: string | null;
}

export interface SimpleModifiersResponse {
  options: SimpleModifierOption[];
  revision: string;
  editable: boolean;
  product: SimpleModifiersProductSnapshot;
}

export interface SimpleModifiersPayload {
  options: SimpleModifierOption[];
  expected_revision: string | null;
}

export interface RequestSequence {
  current: number;
}

export type ProductSnapshotFields = Omit<SimpleModifiersProductSnapshot, 'id'>;

export function productSnapshotToForm(product: SimpleModifiersProductSnapshot) {
  return {
    name: product.name,
    description: product.description ?? '',
    sku: product.sku,
    category_name: product.category_name,
    station: product.station,
    price: product.price_cents === null ? '' : centsToMxn(product.price_cents),
    is_promo: product.is_promo,
    promo_price: product.promo_price_cents === null ? '' : centsToMxn(product.promo_price_cents),
    promo_badge_text: product.promo_badge_text ?? '',
    image_url: product.image_url || '',
    status: product.status,
  };
}

export function buildProductFieldsForSave(
  form: {
    name: string;
    description: string;
    sku: string;
    category_name: string;
    station: string;
    status: string;
    image_url: string;
    is_promo: boolean;
    promo_badge_text: string;
  },
  priceCents: number,
  promoPriceCents: number | null,
  baseline: ProductSnapshotFields | null,
): ProductSnapshotFields | Partial<ProductSnapshotFields> {
  const next: ProductSnapshotFields = {
    name: form.name.trim(),
    description: form.description.trim(),
    sku: form.sku.trim(),
    category_name: form.category_name.trim(),
    station: form.station,
    price_cents: priceCents,
    image_url: form.image_url.trim() || null,
    status: form.status,
    is_promo: form.is_promo,
    promo_price_cents: promoPriceCents,
    promo_badge_text: form.is_promo
      ? form.promo_badge_text.trim() || (baseline ? baseline.promo_badge_text : 'PROMO')
      : null,
  };
  return baseline ? buildChangedProductFields(next, baseline) : next;
}

export function buildChangedProductFields(
  next: ProductSnapshotFields,
  baseline: ProductSnapshotFields,
): Partial<ProductSnapshotFields> {
  const changed: Partial<ProductSnapshotFields> = {};
  for (const key of [
    'name', 'description', 'sku', 'category_name', 'station', 'price_cents', 'image_url', 'status',
    'is_promo', 'promo_price_cents', 'promo_badge_text',
  ] as const) {
    if (key === 'description' && (next[key] ?? '') === (baseline[key] ?? '')) continue;
    if (next[key] !== baseline[key]) changed[key] = next[key] as never;
  }
  return changed;
}

export function positiveMxnToCentsExact(value: string, label: string): number {
  const cents = mxnToCentsExact(value);
  if (cents <= 0) throw new Error(`${label} debe ser mayor a $0.00.`);
  return cents;
}

export async function runLatestSimpleModifiersRequest(
  sequence: RequestSequence,
  load: () => Promise<unknown>,
  onLoaded: (response: SimpleModifiersResponse) => void,
  onError: (error: unknown) => void,
): Promise<void> {
  const requestId = ++sequence.current;
  try {
    const response = parseSimpleModifiersResponse(await load());
    if (requestId !== sequence.current) return;
    onLoaded(response);
  } catch (error) {
    if (requestId !== sequence.current) return;
    onError(error);
  }
}

export function parseSimpleModifierText(text: string): SimpleModifierOption[] {
  const options: SimpleModifierOption[] = [];
  const names = new Set<string>();

  for (const [index, rawLine] of text.split(/\r?\n/).entries()) {
    const line = rawLine.trim();
    if (!line) continue;

    const commaCount = (line.match(/,/g) ?? []).length;
    if (commaCount > 1) {
      throw new Error(`La línea ${index + 1} contiene demasiadas comas.`);
    }

    const [rawName, rawPrice] = line.split(',');
    const name = rawName.trim();
    if (!name) throw new Error(`Escribe el nombre del modificador en la línea ${index + 1}.`);
    if ([...name].length > 120) throw new Error(`El nombre del modificador en la línea ${index + 1} supera 120 caracteres.`);

    const normalizedName = name.toLowerCase();
    if (names.has(normalizedName)) throw new Error(`El modificador "${name}" está duplicado.`);
    names.add(normalizedName);

    const price = rawPrice?.trim() ?? '';
    let priceDeltaCents = 0;
    if (price) {
      try {
        priceDeltaCents = mxnToCentsExact(price);
      } catch (error) {
        const reason = error instanceof Error ? error.message : 'El precio no es válido.';
        throw new Error(`Precio inválido en la línea ${index + 1}: ${reason}`);
      }
      if (priceDeltaCents > 2_147_483_647) {
        throw new Error(`El precio en la línea ${index + 1} excede el máximo permitido.`);
      }
    }
    if (options.length >= 100) throw new Error('Se permiten hasta 100 modificadores simples.');
    options.push({ name, price_delta_cents: priceDeltaCents });
  }

  return options;
}

export function buildSimpleModifiersPayload(
  text: string,
  expectedRevision: string | null,
): SimpleModifiersPayload {
  return {
    options: parseSimpleModifierText(text),
    expected_revision: expectedRevision,
  };
}

export function parseSimpleModifiersResponse(value: unknown): SimpleModifiersResponse {
  if (!value || typeof value !== 'object') throw new Error('La respuesta de modificadores no es válida.');
  const response = value as Partial<SimpleModifiersResponse>;
  if (!Array.isArray(response.options) || typeof response.revision !== 'string' || typeof response.editable !== 'boolean') {
    throw new Error('La respuesta de modificadores no contiene el contrato esperado.');
  }
  if (response.options.length > 100) throw new Error('La respuesta excede los 100 modificadores permitidos.');
  const options = response.options.map((option) => {
    if (
      !option || typeof option.name !== 'string' || !option.name.trim() ||
      [...option.name].length > 120 || !Number.isSafeInteger(option.price_delta_cents) ||
      option.price_delta_cents < 0 || option.price_delta_cents > 2_147_483_647
    ) {
      throw new Error('La respuesta incluye un modificador no válido.');
    }
    return { name: option.name, price_delta_cents: option.price_delta_cents };
  });
  const product = parseSimpleModifiersProductSnapshot(response.product);
  return { options, revision: response.revision, editable: response.editable, product };
}

function parseSimpleModifiersProductSnapshot(value: unknown): SimpleModifiersProductSnapshot {
  if (!value || typeof value !== 'object') throw new Error('La respuesta no contiene el producto actualizado.');
  const product = value as Partial<SimpleModifiersProductSnapshot>;
  const isNullableMoney = (amount: unknown) => amount === null || (Number.isSafeInteger(amount) && Number(amount) >= 0);
  if (
    typeof product.id !== 'string' || !product.id || typeof product.name !== 'string' ||
    !(product.description == null || typeof product.description === 'string') ||
    typeof product.sku !== 'string' || typeof product.category_name !== 'string' ||
    typeof product.station !== 'string' || !isNullableMoney(product.price_cents) ||
    !(product.image_url === null || typeof product.image_url === 'string') ||
    typeof product.status !== 'string' || typeof product.is_promo !== 'boolean' ||
    !isNullableMoney(product.promo_price_cents) ||
    !(product.promo_badge_text === null || typeof product.promo_badge_text === 'string')
  ) {
    throw new Error('La respuesta incluye un producto actualizado no válido.');
  }
  return product as SimpleModifiersProductSnapshot;
}

export function simpleModifierOptionsToText(options: SimpleModifierOption[]): string {
  return options.map(({ name, price_delta_cents }) => (
    price_delta_cents > 0 ? `${name}, ${centsToMxn(price_delta_cents)}` : name
  )).join('\n');
}

export function newDraftProductSku(randomUuid: () => string = () => crypto.randomUUID()): string {
  const hex = randomUuid().replace(/-/g, '').slice(0, 13);
  if (!/^[0-9a-f]{13}$/i.test(hex)) throw new Error('No se pudo generar un SKU numérico.');
  return BigInt(`0x${hex}`).toString().padStart(16, '0');
}
