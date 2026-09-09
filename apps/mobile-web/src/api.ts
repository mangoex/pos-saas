import { Product, Category, CustomerOrderInfo, CreatedOrderResult, CartItem, BranchInfo, Storefront } from './types';
import { getProductImage } from './imageMap';

const API_BASE_URL = '/api/v1';

/** Resolves a public menu to one tenant before any catalog request is made. */
export async function fetchStorefront(identifier: string): Promise<Storefront> {
  const res = await fetch(`${API_BASE_URL}/public/storefronts/${encodeURIComponent(identifier)}`, {
    headers: { 'Cache-Control': 'no-cache' },
  });
  if (!res.ok) throw new Error(`storefront_resolution_${res.status}`);
  const data = await res.json() as Storefront;
  if (!data?.organization?.id || !data.organization.public_slug || !Array.isArray(data.branches)) {
    throw new Error('storefront_invalid_response');
  }
  return data;
}

/** Resolves a wildcard storefront from backend-bound Host context. */
export async function fetchStorefrontContext(): Promise<Storefront> {
  const res = await fetch(`${API_BASE_URL}/public/storefront-context`, {
    headers: { 'Cache-Control': 'no-cache' },
  });
  if (!res.ok) throw new Error(`storefront_context_${res.status}`);
  const data = await res.json() as Storefront;
  if (!data?.organization?.id || !data.organization.public_slug || !Array.isArray(data.branches)) {
    throw new Error('storefront_invalid_response');
  }
  return data;
}

export async function fetchPublicBranches(lat?: number, lng?: number, restaurant?: string | null): Promise<BranchInfo[]> {
  try {
    const params = new URLSearchParams();
    if (lat !== undefined && lng !== undefined) {
      params.set('lat', String(lat));
      params.set('lng', String(lng));
    }
    if (restaurant) {
      params.set('restaurant', restaurant);
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

export async function fetchMobileTheme(restaurant?: string | null): Promise<'light' | 'dark' | null> {
  try {
    const params = new URLSearchParams();
    if (restaurant) {
      params.set('restaurant', restaurant);
    }
    const url = `${API_BASE_URL}/public/mobile-theme${params.toString() ? `?${params.toString()}` : ''}`;
    const res = await fetch(url, { headers: { 'Cache-Control': 'no-cache' } });
    if (!res.ok) return null;
    const data = await res.json();
    return data?.mobile_theme === 'dark' || data?.mobile_theme === 'light' ? data.mobile_theme : null;
  } catch {
    return null;
  }
}

export interface PublicRestaurantInfo {
  id: string;
  name: string;
  slug: string;
  business_type?: string;
  branches_count: number;
  branches: Array<{
    id: string;
    name: string;
    slug?: string;
    public_key?: string;
  }>;
}

export async function fetchPublicRestaurantInfo(slug: string): Promise<PublicRestaurantInfo | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/public/restaurants/${encodeURIComponent(slug)}`, {
      headers: { 'Cache-Control': 'no-cache' },
    });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export async function fetchMobileMenu(publicKey?: string | null): Promise<{ products: Product[]; categories: Category[] }> {
  try {
    if (!publicKey) throw new Error('storefront_branch_key_required');
    const catalogUrl = `${API_BASE_URL}/public/branches/${encodeURIComponent(publicKey)}/catalog`;
    const res = await fetch(catalogUrl, {
      headers: { 'Cache-Control': 'no-cache' },
    });

    if (!res.ok) {
      throw new Error(`Public catalog HTTP ${res.status}`);
    }

    const data = await res.json();
    // A successful API response is authoritative: never invent a price for its rows.
    const rawProducts = Array.isArray(data.items)
      ? data.items.filter((item: unknown) => (
        typeof (item as { price_cents?: unknown }).price_cents === 'number'
        && Number.isInteger((item as { price_cents: number }).price_cents)
      ))
      : [];
    const categories: Category[] = [{
      id: 'all',
      name: typeof data.menu_home?.name === 'string' && data.menu_home.name.trim() ? data.menu_home.name : 'Todos',
      image_url: typeof data.menu_home?.image_url === 'string' ? data.menu_home.image_url : null,
    }];
    const seenCatNames = new Set<string>();
    const seenCatIds = new Set<string>(['all']);

    if (Array.isArray(data.categories) && data.categories.length > 0) {
      data.categories.forEach((c: any) => {
        if (c.name && c.id && !seenCatIds.has(c.id)) {
          seenCatIds.add(c.id);
          seenCatNames.add(c.name);
          categories.push({ id: c.id, name: c.name, display_order: c.display_order, image_url: c.image_url });
        }
      });
    }

    const products: Product[] = rawProducts.map((p: any) => {
      const catName = p.category_name || 'General';
      if (!seenCatNames.has(catName)) {
        seenCatNames.add(catName);
        categories.push({ id: `cat-${catName.toLowerCase().replace(/\s+/g, '-')}`, name: catName });
      }

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
    throw err;
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

  let rawPhone = restaurantPhone.trim().replace(/[^\d+]/g, '');
  if (!rawPhone) return undefined;
  if (rawPhone.startsWith('+')) {
    rawPhone = rawPhone.slice(1);
  } else if (rawPhone.length === 10) {
    rawPhone = `52${rawPhone}`;
  }

  const methodLabel = {
    cash: `Efectivo ${info.cash_amount ? `(Paga con: $${info.cash_amount})` : ''}`,
    card: 'Tarjeta (Al recibir)',
    transfer: 'Transferencia Bancaria',
  }[info.payment_method];

  let typeLabel = '🛍️ Para Recoger en Barra';
  if (info.order_type === 'dine-in') {
    typeLabel = `🍽️ Para Comer Aquí${info.table_number ? ` (Mesa: ${info.table_number})` : ' (en Barra / Mesa)'}`;
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
    if (item.modifiers && item.modifiers.length > 0) {
      item.modifiers.forEach((mod) => {
        const delta = mod.price_delta_cents > 0 ? ` (+${formatMoney(mod.price_delta_cents)})` : '';
        text += `   ↳ _Adicional: ${mod.name}${delta}_\n`;
      });
    }
    if (item.notes) {
      text += `   ↳ _Nota: ${item.notes}_\n`;
    }
  });

  text += `\n💰 *TOTAL A PAGAR:* *${formatMoney(totalCents)}*\n`;
  if (info.order_notes) {
    text += `📝 *Comentarios Adicionales:* ${info.order_notes}\n`;
  }
  text += `\n✨ _Pedido registrado en Menú Digital_`;

  return `https://wa.me/${rawPhone}?text=${encodeURIComponent(text)}`;
}

export async function submitMobileOrder(
  info: CustomerOrderInfo,
  items: CartItem[],
  branchId?: string,
  branchName?: string,
  customerCoords?: { lat: number; lng: number },
  publicKey?: string | null,
  branchPhone?: string,
  whatsappOrderingEnabled?: boolean,
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
  const effectiveKey = publicKey || branchId;
  const useIntent = typeof effectiveKey === 'string' && effectiveKey.length > 0;

  const storageKey = effectiveKey ? `restaurantos_public_order_key:${effectiveKey}` : '';
  const legacyStorageKey = effectiveKey ? `kiwi_public_order_key:${effectiveKey}` : '';
  const idempotencyKey = useIntent
    ? (localStorage.getItem(storageKey) || localStorage.getItem(legacyStorageKey) || crypto.randomUUID())
    : undefined;
  if (useIntent && idempotencyKey) localStorage.setItem(storageKey, idempotencyKey);
  const targetUrl = useIntent
    ? `${API_BASE_URL}/public/branches/${effectiveKey}/order-intents`
    : `${API_BASE_URL}/public/orders`;
  const fullOrderNotes = [
    info.order_notes?.trim(),
    info.order_type === 'dine-in' && info.table_number?.trim() ? `Mesa: ${info.table_number.trim()}` : null,
    info.payment_method === 'cash' && info.cash_amount?.trim() ? `Paga con: $${info.cash_amount.trim()}` : null,
  ].filter(Boolean).join(' | ') || undefined;

  const response = await fetch(targetUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : {}) },
    body: JSON.stringify(useIntent ? {
      customer_name: info.name.trim(),
      customer_phone: cleanPhone,
      order_type: apiOrderType,
      table_number: info.order_type === 'dine-in' ? (info.table_number?.trim() || undefined) : undefined,
      payment_method: info.payment_method || undefined,
      cash_amount: info.payment_method === 'cash' ? (info.cash_amount?.trim() || undefined) : undefined,
      delivery_address: deliveryAddressText ? { address_text: deliveryAddressText, notes: fullOrderNotes } : undefined,
      order_notes: fullOrderNotes,
      lines: items.map(item => ({
        product_id: item.product.id || item.product.sku,
        quantity: item.quantity,
        notes: item.notes?.trim() || undefined,
        modifiers: (item.modifiers ?? []).map(({ option_id, text }) => ({
          option_id,
          ...(text?.trim() ? { text: text.trim() } : {}),
        })),
      })),
    } : {
      owner_name: info.name.trim(),
      customer_phone: cleanPhone,
      order_type: apiOrderType,
      branch_id: branchId,
      customer_lat: customerCoords?.lat,
      customer_lng: customerCoords?.lng,
      delivery_address: deliveryAddressText,
      payment_method_intent: info.payment_method,
      table_number: info.order_type === 'dine-in' ? (info.table_number?.trim() || undefined) : undefined,
      cash_amount: info.payment_method === 'cash' ? (info.cash_amount?.trim() || undefined) : undefined,
      order_notes: fullOrderNotes,
      lines: items.map(item => ({
        product_id: item.product.id || item.product.sku,
        quantity: item.quantity,
        notes: item.notes?.trim() || '',
      })),
    }),
  });
  if (!response.ok) {
    if (useIntent && response.status === 409) {
      try {
        const errorBody = await response.json() as { detail?: { code?: unknown } };
        if (errorBody.detail?.code === 'idempotency_conflict') {
          localStorage.removeItem(storageKey);
          if (legacyStorageKey) localStorage.removeItem(legacyStorageKey);
        }
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
    const intent = data as { public_reference?: unknown; status?: unknown; version?: unknown; total_cents?: unknown; whatsapp_phone?: unknown; whatsapp_url?: unknown };
    if (
      typeof intent.public_reference !== 'string'
      || intent.status !== 'PENDING_REVIEW'
      || !Number.isInteger(intent.version)
      || !Number.isInteger(intent.total_cents)
    ) throw new Error('public_order_invalid_response');
    const totalCents = intent.total_cents as number;
    localStorage.removeItem(storageKey);
    if (legacyStorageKey) localStorage.removeItem(legacyStorageKey);

    const effectivePhone = typeof intent.whatsapp_phone === 'string' && intent.whatsapp_phone.trim()
      ? intent.whatsapp_phone
      : (typeof branchPhone === 'string' && branchPhone.trim() ? branchPhone : undefined);

    const whatsappUrl = (whatsappOrderingEnabled === true && effectivePhone)
      ? (typeof intent.whatsapp_url === 'string' && intent.whatsapp_url
          ? intent.whatsapp_url
          : buildWhatsAppLink(intent.public_reference, info, items, totalCents, effectivePhone, branchName))
      : undefined;

    return {
      kind: 'public_order_intent',
      public_reference: intent.public_reference,
      status: 'PENDING_REVIEW',
      version: intent.version as number,
      customer_info: info,
      items,
      total_cents: totalCents,
      ...(whatsappUrl ? { whatsapp_url: whatsappUrl } : {}),
    };
  }
  if (!data || typeof data !== 'object' || typeof (data as { id?: unknown }).id !== 'string' || typeof (data as { folio?: unknown }).folio !== 'string' || typeof (data as { created_at?: unknown }).created_at !== 'string' || !Number.isInteger((data as { total_cents?: unknown }).total_cents)) throw new Error('public_order_invalid_response');
  const persisted = data as { id: string; folio: string; created_at: string; total_cents: number; whatsapp_phone?: unknown; };

  const effectivePhone = typeof persisted.whatsapp_phone === 'string' && persisted.whatsapp_phone.trim()
    ? persisted.whatsapp_phone
    : (typeof branchPhone === 'string' && branchPhone.trim() ? branchPhone : undefined);

  const whatsappUrl = (whatsappOrderingEnabled === true && effectivePhone)
    ? buildWhatsAppLink(persisted.folio, info, items, persisted.total_cents, effectivePhone, branchName)
    : undefined;

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
