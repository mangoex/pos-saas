import { Product, Category, CustomerOrderInfo, CreatedOrderResult, CartItem, BranchInfo } from './types';
import { getProductImage, getProductNutritionMeta } from './imageMap';

const API_BASE_URL = '/api/v1';

export async function fetchPublicBranches(lat?: number, lng?: number): Promise<BranchInfo[]> {
  try {
    const params = new URLSearchParams();
    if (lat !== undefined && lng !== undefined) {
      params.set('lat', String(lat));
      params.set('lng', String(lng));
    }
    const url = `${API_BASE_URL}/public/branches${params.toString() ? `?${params.toString()}` : ''}`;
    const res = await fetch(url, { headers: { 'Cache-Control': 'no-cache' } });
    if (!res.ok) throw new Error(`Branches HTTP ${res.status}`);
    const data = await res.json();
    return Array.isArray(data) ? data : [];
  } catch (err) {
    console.warn('Could not load public branches:', err);
    return [];
  }
}

// Seed catalog fallback to guarantee 100% fail-safe display if API server is not running
const BACKUP_CATALOG: Product[] = [
  {
    id: 'prod-jug-ver',
    name: 'Jugo Verde',
    sku: 'JUG-VER',
    category_name: 'Jugos y Extractos',
    price_cents: 6500,
    description: 'Naranja, piña, pepino, apio y nopal recién extraídos.',
    station: 'barra',
  },
  {
    id: 'prod-ext-roj',
    name: 'Extracto Rojo',
    sku: 'EXT-ROJ',
    category_name: 'Jugos y Extractos',
    price_cents: 6300,
    description: 'Fresco sabor de pepino con apio, betabel, limón y dulce de manzana roja.',
    station: 'barra',
  },
  {
    id: 'prod-smo-ros',
    name: 'Smoothie Rosa',
    sku: 'SMO-ROS',
    category_name: 'Smoothies y Licuados',
    price_cents: 9000,
    description: 'Fresa con leche de almendra, miel de abeja, dátil, chía y espinaca.',
    station: 'barra',
  },
  {
    id: 'prod-mat-pin',
    name: 'Maccha Pinku (con fresa)',
    sku: 'MAT-PIN',
    category_name: 'Café y Matcha',
    price_cents: 13000,
    description: 'Matcha ceremonial japonés en capas sobre leche de avena y puré natural de fresa.',
    station: 'barra',
  },
  {
    id: 'prod-ens-fru',
    name: 'Ensalada Frutos Rojos',
    sku: 'ENS-FRU',
    category_name: 'Ensaladas',
    price_cents: 12500,
    description: 'Lechuga orgánica, fresa, arándanos, queso panela, cacahuates garapiñados y aderezo balsámico.',
    station: 'cocina',
  },
  {
    id: 'prod-san-kyo',
    name: 'Sando Kyoto Pollo BBQ',
    sku: 'SAN-KYO-BBQ',
    category_name: 'Emparedados y Sandos',
    price_cents: 12000,
    description: 'Sándwich estilo japonés en pan brioche grueso, pollo crujiente con glaseado BBQ y col fresca.',
    station: 'cocina',
  },
  {
    id: 'prod-pan-cue',
    name: 'Cuernito Jamón/Phila',
    sku: 'PAN-CUE',
    category_name: 'Panadería',
    price_cents: 3800,
    description: 'Croissant artesanal dorado horneado relleno de jamón ahumado y queso Philadelphia.',
    station: 'barra',
  },
  {
    id: 'prod-com-lig',
    name: 'Combo Ligero',
    sku: 'COM-LIG',
    category_name: 'Combos',
    price_cents: 10500,
    description: 'Sándwich básico artesanal + fresco jugo de naranja del día + dulce galleta con chispas.',
    station: 'barra',
  }
];

const DEFAULT_CATEGORIES: Category[] = [
  { id: 'all', name: 'Todos' },
  { id: 'c1', name: 'Jugos y Extractos' },
  { id: 'c2', name: 'Smoothies y Licuados' },
  { id: 'c3', name: 'Café y Matcha' },
  { id: 'c4', name: 'Ensaladas' },
  { id: 'c5', name: 'Emparedados y Sandos' },
  { id: 'c6', name: 'Panadería' },
  { id: 'c7', name: 'Combos' },
];

let activeBranchId: string | undefined = undefined;

export async function fetchMobileMenu(publicKey?: string | null): Promise<{ products: Product[]; categories: Category[] }> {
  try {
    const catalogUrl = publicKey
      ? `${API_BASE_URL}/public/branches/${publicKey}/catalog`
      : `${API_BASE_URL}/public/catalog`;
    const res = await fetch(catalogUrl, {
      headers: { 'Cache-Control': 'no-cache' },
    });

    if (!res.ok) {
      throw new Error(`Public catalog HTTP ${res.status}`);
    }

    const data = await res.json();
    if (data.branch_id) {
      activeBranchId = data.branch_id;
    }

    // A successful API response is authoritative: never invent a price for its rows.
    const rawProducts = Array.isArray(data.items)
      ? data.items.filter((item: unknown) => (
        typeof (item as { price_cents?: unknown }).price_cents === 'number'
        && Number.isInteger((item as { price_cents: number }).price_cents)
      ))
      : BACKUP_CATALOG;
    const categories: Category[] = [{ id: 'all', name: 'Todos' }];
    const seenCatNames = new Set<string>(['Todos']);

    if (Array.isArray(data.categories) && data.categories.length > 0) {
      data.categories.forEach((c: any) => {
        if (c.name && !seenCatNames.has(c.name)) {
          seenCatNames.add(c.name);
          categories.push({ id: c.id, name: c.name, display_order: c.display_order });
        }
      });
    }

    const products: Product[] = rawProducts.map((p: any) => {
      const catName = p.category_name || 'General';
      if (!seenCatNames.has(catName)) {
        seenCatNames.add(catName);
        categories.push({ id: `cat-${catName.toLowerCase().replace(/\s+/g, '-')}`, name: catName });
      }

      const meta = getProductNutritionMeta(p.name || '');
      return {
        id: p.id,
        name: p.name,
        sku: p.sku || p.id,
        category_name: catName,
        category_id: p.category_id,
        price_cents: p.price_cents,
        description: p.description || '',
        station: p.station || 'barra',
        image_url: getProductImage(p),
        calories: meta.calories,
        prep_time: meta.prep_time,
        tags: [meta.tag],
        is_available: p.is_available !== false,
        modifier_groups: Array.isArray(p.modifier_groups)
          ? p.modifier_groups
            .filter((group: unknown) => (
              typeof (group as { id?: unknown }).id === 'string'
              && typeof (group as { name?: unknown }).name === 'string'
              && Array.isArray((group as { options?: unknown }).options)
            ))
            .map((group: any) => ({
              id: group.id,
              name: group.name,
              is_required: group.is_required === true,
              minimum_selections: Number.isInteger(group.minimum_selections) ? group.minimum_selections : 0,
              maximum_selections: Number.isInteger(group.maximum_selections) ? group.maximum_selections : 0,
              options: group.options.filter((option: unknown) => (
                typeof (option as { id?: unknown }).id === 'string'
                && typeof (option as { name?: unknown }).name === 'string'
                && Number.isInteger((option as { price_delta_cents?: unknown }).price_delta_cents)
                && typeof (option as { selection_kind?: unknown }).selection_kind === 'string'
              )),
            }))
          : [],
      };
    });

    return { products, categories };
  } catch (err) {
    console.warn('Loading fallback catalog:', err);
    const products: Product[] = BACKUP_CATALOG.map(p => {
      const meta = getProductNutritionMeta(p.name);
      return {
        ...p,
        image_url: getProductImage(p),
        calories: meta.calories,
        prep_time: meta.prep_time,
        tags: [meta.tag],
        is_available: true,
      };
    });
    return { products, categories: DEFAULT_CATEGORIES };
  }
}

export function formatMoney(cents: number): string {
  return `$${(cents / 100).toFixed(2)} MXN`;
}

export function buildWhatsAppLink(
  folio: string,
  info: CustomerOrderInfo,
  items: CartItem[],
  totalCents: number,
  restaurantPhone: string | undefined,
  branchName?: string
): string | undefined {
  if (!restaurantPhone) return undefined;
  const methodLabel = {
    cash: `Efectivo ${info.cash_amount ? `(Paga con: $${info.cash_amount})` : ''}`,
    card: 'Tarjeta (Al recibir)',
    transfer: 'Transferencia Bancaria',
  }[info.payment_method];

  let typeLabel = '🛍️ Para Recoger en Barra';
  if (info.order_type === 'dine-in') {
    typeLabel = '🍽️ Para Comer Aquí (en Barra)';
  } else if (info.order_type === 'delivery') {
    typeLabel = '🛵 Envío a Domicilio';
  }

  const brandTitle = branchName ? branchName.toUpperCase() : 'RESTAURANTE';
  let text = `🍽️ *NUEVO PEDIDO - ${brandTitle}*\n`;
  text += `📋 *Folio:* #${folio}\n`;
  if (branchName) {
    text += `📍 *Sucursal:* ${branchName}\n`;
  }
  text += `👤 *Cliente:* ${info.name}\n`;
  text += `📱 *Teléfono:* ${info.phone}\n`;
  text += `📦 *Modalidad:* ${typeLabel}\n`;

  if (info.order_type === 'delivery') {
    const colPrefix = info.address_neighborhood.toLowerCase().startsWith('col') ? '' : 'Col. ';
    text += `📍 *Dirección:* ${info.address_street} #${info.address_number}, ${colPrefix}${info.address_neighborhood}\n`;
    if (info.address_notes) text += `📌 *Referencias:* ${info.address_notes}\n`;
  }

  text += `💳 *Método de Pago:* ${methodLabel}\n\n`;
  text += `🛒 *DETALLE DEL PEDIDO:*\n`;

  items.forEach((item) => {
    text += `• ${item.quantity}x ${item.product.name} (${formatMoney(item.product.price_cents)})\n`;
    if (item.notes) {
      text += `   ↳ _Nota: ${item.notes}_\n`;
    }
  });

  text += `\n💰 *TOTAL A PAGAR:* *${formatMoney(totalCents)}*\n`;
  if (info.order_notes) {
    text += `📝 *Comentarios Adicionales:* ${info.order_notes}\n`;
  }
  text += `\n✨ _Pedido generado desde el Menú Digital_`;

  return `https://wa.me/${restaurantPhone}?text=${encodeURIComponent(text)}`;
}

export async function submitMobileOrder(
  info: CustomerOrderInfo,
  items: CartItem[],
  branchId?: string,
  branchName?: string,
  customerCoords?: { lat: number; lng: number },
  publicKey?: string | null,
): Promise<CreatedOrderResult> {
  const deliveryAddressText = info.order_type === 'delivery'
    ? `${info.address_street} #${info.address_number}, Col. ${info.address_neighborhood}${info.address_notes ? ` (Ref: ${info.address_notes})` : ''}`
    : undefined;
  const apiOrderType = info.order_type === 'dine-in'
    ? 'dine-in'
    : info.order_type === 'delivery' ? 'delivery' : 'takeout';

  // Normalize phone number for API schema
  let cleanPhone = info.phone.trim().replace(/[^\d+]/g, '');
  if (!cleanPhone.startsWith('+')) {
    cleanPhone = cleanPhone.replace(/^0+/, '');
  }

  // Server authority: the opaque key is projected only while guarded capture is enabled.
  const useIntent = typeof publicKey === 'string' && publicKey.length > 0;
  if (useIntent && !publicKey) throw new Error('public_order_unavailable');

  const storageKey = publicKey ? `restaurantos_public_order_key:${publicKey}` : '';
  const legacyStorageKey = publicKey ? `kiwi_public_order_key:${publicKey}` : '';
  const idempotencyKey = useIntent
    ? (localStorage.getItem(storageKey) || localStorage.getItem(legacyStorageKey) || crypto.randomUUID())
    : undefined;
  if (useIntent && idempotencyKey) localStorage.setItem(storageKey, idempotencyKey);
  const response = await fetch(useIntent ? `${API_BASE_URL}/public/branches/${publicKey}/order-intents` : `${API_BASE_URL}/public/orders`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : {}) },
    body: JSON.stringify(useIntent ? {
      customer_name: info.name.trim(),
      customer_phone: cleanPhone,
      order_type: apiOrderType,
      delivery_address: deliveryAddressText ? { address_text: deliveryAddressText, notes: info.order_notes || undefined } : undefined,
      order_notes: info.order_notes?.trim() || undefined,
      lines: items.map(item => ({
        product_id: item.product.id || item.product.sku,
        quantity: item.quantity,
        notes: item.notes || undefined,
        modifiers: (item.modifiers ?? []).map(({ option_id, text }) => ({
          option_id,
          ...(text?.trim() ? { text: text.trim() } : {}),
        })),
      })),
    } : {
      owner_name: info.name.trim(),
      customer_phone: cleanPhone,
      order_type: apiOrderType,
      branch_id: branchId || activeBranchId,
      customer_lat: customerCoords?.lat,
      customer_lng: customerCoords?.lng,
      delivery_address: deliveryAddressText,
      payment_method_intent: info.payment_method,
      order_notes: info.order_notes?.trim() || undefined,
      lines: items.map(item => ({
        product_id: item.product.id || item.product.sku,
        quantity: item.quantity,
        notes: item.notes || '',
      })),
    }),
  });
  if (!response.ok) {
    if (useIntent && response.status === 409) {
      try {
        const errorBody = await response.json() as { detail?: { code?: unknown } };
        if (errorBody.detail?.code === 'idempotency_conflict') localStorage.removeItem(storageKey);
      } catch { /* retain the key when the rejection cannot be classified */ }
    }
    let errorDetail = '';
    try {
      const errJson = await response.json();
      errorDetail = JSON.stringify(errJson);
    } catch {
      // ignore
    }
    console.error('Order submission error:', response.status, errorDetail);
    throw new Error(`public_order_rejected_${response.status}`);
  }

  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new Error('public_order_invalid_response');
  }
  if (useIntent) {
    const intent = data as { public_reference?: unknown; status?: unknown; version?: unknown; total_cents?: unknown };
    if (
      typeof intent.public_reference !== 'string'
      || intent.status !== 'PENDING_REVIEW'
      || !Number.isInteger(intent.version)
      || !Number.isInteger(intent.total_cents)
    ) throw new Error('public_order_invalid_response');
    const totalCents = intent.total_cents as number;
    localStorage.removeItem(storageKey);
    return {
      kind: 'public_order_intent',
      public_reference: intent.public_reference,
      status: 'PENDING_REVIEW',
      version: intent.version as number,
      customer_info: info,
      items,
      total_cents: totalCents,
    };
  }
  if (!data || typeof data !== 'object' || typeof (data as { id?: unknown }).id !== 'string' || typeof (data as { folio?: unknown }).folio !== 'string' || typeof (data as { created_at?: unknown }).created_at !== 'string' || !Number.isInteger((data as { total_cents?: unknown }).total_cents)) throw new Error('public_order_invalid_response');
  const persisted = data as { id: string; folio: string; created_at: string; total_cents: number; whatsapp_phone?: unknown; };
  const whatsappUrl = buildWhatsAppLink(
    persisted.folio, info, items, persisted.total_cents,
    typeof persisted.whatsapp_phone === 'string' ? persisted.whatsapp_phone : undefined,
    branchName,
  );
  return {
    kind: 'operational_order',
    folio: persisted.folio,
    id: persisted.id,
    created_at: persisted.created_at,
    customer_info: info,
    items,
    total_cents: persisted.total_cents,
    ...(whatsappUrl ? { whatsapp_url: whatsappUrl } : {}),
  };
}

export async function submitCustomerFeedback(payload: {
  branch_id: string;
  rating: number;
  order_folio?: string;
  customer_name?: string;
  comment?: string;
}): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE_URL}/public/feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    return res.ok;
  } catch (err) {
    console.warn('Could not submit customer feedback:', err);
    return false;
  }
}

export async function fetchOrderUpsellRecommendations(
  productIds: string[],
  branchId?: string,
  customerId?: string,
): Promise<Array<{ product_id: string; product_name: string; price_cents: number; reason: string }>> {
  try {
    const res = await fetch(`${API_BASE_URL}/public/order-upsell-recommendations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        current_product_ids: productIds,
        branch_id: branchId || undefined,
        customer_id: customerId || undefined,
      }),
    });
    if (!res.ok) return [];
    const data = await res.json();
    return Array.isArray(data?.recommendations) ? data.recommendations : [];
  } catch (err) {
    console.warn('Could not fetch dynamic upsell recommendations:', err);
    return [];
  }
}
