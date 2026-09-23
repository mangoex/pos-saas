import { Product, Category, CustomerOrderInfo, CreatedOrderResult, CartItem, BranchInfo, Storefront, SavedCustomerProfile, TrendingDish, CommunityPhoto } from './types';
import { getProductImage } from './imageMap';
import {
  clearPendingMobileOrder,
  hasMobileOrderCompletedSince,
  markMobileOrderCompleted,
  mobileOrderTimestamp,
  readPendingMobileOrder,
  savePendingMobileOrder,
  withMobileOrderSubmissionLock,
} from './pendingMobileOrder';
import type { PendingMobileOrder } from './pendingMobileOrder';

export { hasPendingMobileOrder, mobileOrderTimestamp } from './pendingMobileOrder';

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

export interface CouponValidationResult {
  valid: boolean;
  code?: string;
  discount_percentage?: number;
  discount_cents?: number;
  message?: string;
}

export async function validateBranchCoupon(
  branchKey: string,
  couponCode: string,
  subtotalCents: number,
): Promise<CouponValidationResult> {
  try {
    const res = await fetch(`${API_BASE_URL}/public/branches/${encodeURIComponent(branchKey)}/validate-coupon`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        code: couponCode.trim().toUpperCase(),
        subtotal_cents: subtotalCents,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      const msg = err?.detail?.message || err?.message || 'Cupón no válido para esta sucursal';
      return { valid: false, message: msg };
    }
    const data = await res.json();
    return {
      valid: Boolean(data.valid),
      code: data.code,
      discount_percentage: data.discount_percentage,
      discount_cents: data.discount_cents,
      message: data.message,
    };
  } catch {
    return { valid: false, message: 'No fue posible validar el cupón en este momento.' };
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

export async function fetchMobileMenu(publicKey?: string | null): Promise<{ products: Product[]; categories: Category[]; has_active_shift?: boolean }> {
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
    const isClosed = data.has_active_shift === false;
    const defaultHomeName = isClosed ? 'Cerrado por el momento' : 'Todos';
    const categories: Category[] = [{
      id: 'all',
      name: isClosed
        ? 'Cerrado por el momento'
        : (typeof data.menu_home?.name === 'string' && data.menu_home.name.trim() ? data.menu_home.name : defaultHomeName),
      image_url: isClosed ? null : (typeof data.menu_home?.image_url === 'string' ? data.menu_home.image_url : null),
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
        is_promo: Boolean(p.is_promo),
        promo_price_cents: typeof p.promo_price_cents === 'number' ? p.promo_price_cents : null,
        promo_badge_text: typeof p.promo_badge_text === 'string' ? p.promo_badge_text : null,
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

    return { products, categories, has_active_shift: typeof data.has_active_shift === 'boolean' ? data.has_active_shift : undefined };
  } catch (err) {
    throw err;
  }
}

export async function fetchTrendingDishes(publicKey?: string | null): Promise<TrendingDish[]> {
  try {
    if (!publicKey) return [];
    const url = `${API_BASE_URL}/public/branches/${encodeURIComponent(publicKey)}/trending-dishes`;
    const res = await fetch(url, { headers: { 'Cache-Control': 'no-cache' } });
    if (!res.ok) return [];
    const data = await res.json();
    return Array.isArray(data.trending_dishes) ? data.trending_dishes : [];
  } catch (err) {
    console.warn('Could not load trending dishes:', err);
    return [];
  }
}

export async function submitCommunityPhoto(
  publicKey: string,
  payload: {
    product_id: string;
    order_folio?: string;
    customer_name: string;
    customer_phone?: string;
    image_url: string;
    caption?: string;
  },
): Promise<{ id: string; status: string; discount_code: string; message: string }> {
  const url = `${API_BASE_URL}/public/branches/${encodeURIComponent(publicKey)}/community-photos`;
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.message || errorData.detail || `Error al subir foto: HTTP ${res.status}`);
  }
  return await res.json();
}

export async function fetchProductCommunityPhotos(
  publicKey: string,
  productId: string,
): Promise<CommunityPhoto[]> {
  try {
    const url = `${API_BASE_URL}/public/branches/${encodeURIComponent(publicKey)}/products/${encodeURIComponent(productId)}/community-photos`;
    const res = await fetch(url, { headers: { 'Cache-Control': 'no-cache' } });
    if (!res.ok) return [];
    const data = await res.json();
    return Array.isArray(data) ? data : [];
  } catch {
    return [];
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

  if (info.coupon_code && info.discount_cents && info.discount_cents > 0) {
    text += `\n🎟️ *Cupón Aplicado:* ${info.coupon_code} (-${formatMoney(info.discount_cents)})\n`;
  }

  text += `\n💰 *TOTAL A PAGAR:* *${formatMoney(totalCents)}*\n`;
  if (info.order_notes) {
    text += `📝 *Comentarios Adicionales:* ${info.order_notes}\n`;
  }
  text += `\n✨ _Pedido registrado en Menú Digital_`;

  return `https://wa.me/${rawPhone}?text=${encodeURIComponent(text)}`;
}

async function submitMobileOrderAttempt(
  info: CustomerOrderInfo,
  items: CartItem[],
  branchId?: string,
  branchName?: string,
  customerCoords?: { lat: number; lng: number },
  publicKey?: string | null,
  branchPhone?: string,
  whatsappOrderingEnabled?: boolean,
  invocationStartedAt = mobileOrderTimestamp(),
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

  const targetUrl = useIntent
    ? `${API_BASE_URL}/public/branches/${effectiveKey}/order-intents`
    : `${API_BASE_URL}/public/orders`;
  const fullOrderNotes = [
    info.order_notes?.trim(),
    info.order_type === 'dine-in' && info.table_number?.trim() ? `Mesa: ${info.table_number.trim()}` : null,
    info.payment_method === 'cash' && info.cash_amount?.trim() ? `Paga con: $${info.cash_amount.trim()}` : null,
  ].filter(Boolean).join(' | ') || undefined;

  const intentPayload = {
      customer_name: info.name.trim(),
      customer_phone: cleanPhone,
      order_type: apiOrderType,
      coupon_code: info.coupon_code || undefined,
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
    };
  const operationalPayload = {
      owner_name: info.name.trim(),
      customer_phone: cleanPhone,
      order_type: apiOrderType,
      coupon_code: info.coupon_code || undefined,
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
    };

  let idempotencyKey: string | undefined;
  let requestBody: string;
  let receiptInfo = info;
  let receiptItems = items;
  let receiptBranchName = branchName;
  let receiptBranchPhone = branchPhone;
  let receiptWhatsAppEnabled = whatsappOrderingEnabled;

  if (useIntent && effectiveKey) {
    const pending = readPendingMobileOrder(effectiveKey);
    const completedBeforeLockRelease = hasMobileOrderCompletedSince(effectiveKey, invocationStartedAt);
    if (completedBeforeLockRelease === null) {
      const err = new Error('No se pudo verificar el estado local del pedido. No se envió otra solicitud.');
      (err as any).code = 'pending_mobile_order_storage_unavailable';
      throw err;
    }
    if (completedBeforeLockRelease && pending.kind !== 'record') {
      const err = new Error('El pedido se confirmó en otra pestaña mientras esperabas. Revisa esa confirmación antes de enviar otro.');
      (err as any).code = 'mobile_order_already_completed';
      throw err;
    }
    if (pending.kind === 'legacy') {
      const err = new Error(
        'Hay un envío anterior con una clave guardada pero sin sus datos originales. El carrito permanece protegido. Confirma con la sucursal si recibieron el pedido antes de iniciar otro.',
      );
      (err as any).code = 'pending_mobile_order_legacy';
      throw err;
    }
    if (pending.kind === 'unavailable') {
      const err = new Error('No se pudo guardar o leer la recuperación del pedido. No se envió una solicitud nueva.');
      (err as any).code = 'pending_mobile_order_storage_unavailable';
      throw err;
    }

    if (pending.kind === 'record') {
      ({
        idempotencyKey,
        requestBody,
        customerInfo: receiptInfo,
        items: receiptItems,
        branchName: receiptBranchName,
        branchPhone: receiptBranchPhone,
        whatsappOrderingEnabled: receiptWhatsAppEnabled,
      } = pending.attempt);
    } else {
      idempotencyKey = crypto.randomUUID();
      requestBody = JSON.stringify(intentPayload);
      let attempt: PendingMobileOrder;
      try {
        attempt = {
          version: 1 as const,
          idempotencyKey,
          requestBody,
          customerInfo: JSON.parse(JSON.stringify(info)) as CustomerOrderInfo,
          items: JSON.parse(JSON.stringify(items)) as CartItem[],
          ...(branchName ? { branchName } : {}),
          ...(branchPhone ? { branchPhone } : {}),
          whatsappOrderingEnabled: whatsappOrderingEnabled === true,
        };
      } catch {
        const err = new Error('No se pudo guardar la información necesaria para recuperar el pedido. No se envió.');
        (err as any).code = 'pending_mobile_order_storage_unavailable';
        throw err;
      }
      if (!savePendingMobileOrder(effectiveKey, attempt)) {
        const err = new Error('No se pudo guardar la recuperación del pedido. No se envió una solicitud nueva.');
        (err as any).code = 'pending_mobile_order_storage_unavailable';
        throw err;
      }
    }
  } else {
    requestBody = JSON.stringify(operationalPayload);
  }

  const response = await fetch(targetUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : {}) },
    body: requestBody,
  });
  if (!response.ok) {
    let errorDetail: any = null;
    try {
      errorDetail = await response.json();
    } catch {
      // ignore
    }

    const detailCode = errorDetail?.detail?.code || errorDetail?.code;
    const detailMsg = errorDetail?.detail?.message || errorDetail?.message;

    const definitiveNoPersistCodes = new Set([
      'public_order_schema_invalid',
      'product_unavailable',
      'coupon_invalid',
      'dine_in_disabled',
    ]);
    const definitelyRejectedBeforePersist = typeof detailCode === 'string' && definitiveNoPersistCodes.has(detailCode);
    if (useIntent && effectiveKey && definitelyRejectedBeforePersist) {
      clearPendingMobileOrder(effectiveKey);
    }

    let userMessage = 'No fue posible confirmar el pedido en este momento.';
    if (response.status === 422 || detailCode === 'public_order_schema_invalid') {
      userMessage = 'Los datos del pedido o el número de teléfono no son válidos. Verifica la información.';
    } else if (response.status === 429 || detailCode === 'public_order_rate_limited') {
      userMessage = 'Demasiadas solicitudes. Por favor espera un momento antes de volver a intentar.';
    } else if (response.status === 409 || detailCode === 'idempotency_conflict') {
      userMessage = 'No se pudo confirmar el resultado del envío anterior. El carrito sigue protegido; vuelve a intentar el envío guardado o confirma con la sucursal antes de iniciar otro.';
    } else if (detailCode === 'public_order_unavailable') {
      userMessage = 'El servicio de pedidos en línea no está disponible temporalmente para esta sucursal.';
    } else if (detailCode === 'product_unavailable') {
      userMessage = 'Uno o más productos del carrito ya no están disponibles. Revisa tu pedido.';
    } else if (detailCode === 'database_unavailable' || response.status === 503) {
      userMessage = 'El sistema se encuentra temporalmente ocupado. Por favor intenta de nuevo en unos momentos.';
    } else if (detailMsg && typeof detailMsg === 'string') {
      userMessage = detailMsg;
    }

    console.error('Order submission error:', response.status, typeof detailCode === 'string' ? detailCode : 'unknown');
    const err = new Error(userMessage);
    (err as any).code = detailCode;
    (err as any).status = response.status;
    throw err;
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

    const effectivePhone = typeof intent.whatsapp_phone === 'string' && intent.whatsapp_phone.trim()
      ? intent.whatsapp_phone
      : (typeof receiptBranchPhone === 'string' && receiptBranchPhone.trim() ? receiptBranchPhone : undefined);

    const whatsappUrl = (receiptWhatsAppEnabled === true && effectivePhone)
      ? (typeof intent.whatsapp_url === 'string' && intent.whatsapp_url
          ? intent.whatsapp_url
          : buildWhatsAppLink(intent.public_reference, receiptInfo, receiptItems, totalCents, effectivePhone, receiptBranchName))
      : undefined;

    const result: CreatedOrderResult = {
      kind: 'public_order_intent',
      public_reference: intent.public_reference,
      status: 'PENDING_REVIEW',
      version: intent.version as number,
      customer_info: receiptInfo,
      items: receiptItems,
      total_cents: totalCents,
      coupon_code: receiptInfo.coupon_code,
      discount_cents: receiptInfo.discount_cents,
      ...(whatsappUrl ? { whatsapp_url: whatsappUrl } : {}),
    };
    if (effectiveKey && !markMobileOrderCompleted(effectiveKey, mobileOrderTimestamp())) {
      const err = new Error('El pedido se recibió, pero no se pudo guardar el cierre local. Vuelve a intentar el envío guardado.');
      (err as any).code = 'pending_mobile_order_cleanup_failed';
      throw err;
    }
    if (effectiveKey && !clearPendingMobileOrder(effectiveKey)) {
      const err = new Error('El pedido se recibió, pero no se pudo cerrar su recuperación local. Vuelve a intentar el envío guardado.');
      (err as any).code = 'pending_mobile_order_cleanup_failed';
      throw err;
    }
    return result;
  }
  if (!data || typeof data !== 'object' || typeof (data as { id?: unknown }).id !== 'string' || typeof (data as { folio?: unknown }).folio !== 'string' || typeof (data as { created_at?: unknown }).created_at !== 'string' || !Number.isInteger((data as { total_cents?: unknown }).total_cents)) throw new Error('public_order_invalid_response');
  const persisted = data as { id: string; folio: string; created_at: string; total_cents: number; whatsapp_phone?: unknown; };

  const effectivePhone = typeof persisted.whatsapp_phone === 'string' && persisted.whatsapp_phone.trim()
    ? persisted.whatsapp_phone
    : (typeof receiptBranchPhone === 'string' && receiptBranchPhone.trim() ? receiptBranchPhone : undefined);

  const whatsappUrl = (receiptWhatsAppEnabled === true && effectivePhone)
    ? buildWhatsAppLink(persisted.folio, receiptInfo, receiptItems, persisted.total_cents, effectivePhone, receiptBranchName)
    : undefined;

  return {
    kind: 'operational_order',
    folio: persisted.folio,
    id: persisted.id,
    created_at: persisted.created_at,
    customer_info: receiptInfo,
    items: receiptItems,
    total_cents: persisted.total_cents,
    coupon_code: receiptInfo.coupon_code,
    discount_cents: receiptInfo.discount_cents,
    ...(whatsappUrl ? { whatsapp_url: whatsappUrl } : {}),
  };
}

export function submitMobileOrder(
  info: CustomerOrderInfo,
  items: CartItem[],
  branchId?: string,
  branchName?: string,
  customerCoords?: { lat: number; lng: number },
  publicKey?: string | null,
  branchPhone?: string,
  whatsappOrderingEnabled?: boolean,
  cartStartedAt?: number,
): Promise<CreatedOrderResult> {
  const effectiveKey = publicKey || branchId;
  const submit = (invocationStartedAt: number) => submitMobileOrderAttempt(
    info,
    items,
    branchId,
    branchName,
    customerCoords,
    publicKey,
    branchPhone,
    whatsappOrderingEnabled,
    Math.min(
      invocationStartedAt,
      typeof cartStartedAt === 'number' && Number.isFinite(cartStartedAt) ? cartStartedAt : Number.POSITIVE_INFINITY,
    ),
  );
  if (typeof effectiveKey === 'string' && effectiveKey.length > 0) {
    const invocationStartedAt = mobileOrderTimestamp();
    return withMobileOrderSubmissionLock(effectiveKey, () => submit(invocationStartedAt));
  }
  return submit(mobileOrderTimestamp());
}

export async function submitCustomerFeedback(payload: {
  branch_id: string;
  rating: number;
  customer_phone: string;
  order_folio: string;
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

export const MIMENU_CUSTOMER_PROFILE_KEY = 'mimenu:customer_profile';
export const LEGACY_CUSTOMER_PROFILE_KEY = 'restaurantos:customer_profile';

export function getSavedCustomerProfile(): SavedCustomerProfile | null {
  try {
    if (typeof window === 'undefined' || !window.localStorage) return null;
    const raw =
      localStorage.getItem(MIMENU_CUSTOMER_PROFILE_KEY) ||
      localStorage.getItem(LEGACY_CUSTOMER_PROFILE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed.name === 'string' && typeof parsed.phone === 'string') {
      return {
        name: parsed.name.trim(),
        phone: parsed.phone.trim(),
        street: typeof parsed.street === 'string' ? parsed.street.trim() : undefined,
        number: typeof parsed.number === 'string' ? parsed.number.trim() : undefined,
        neighborhood: typeof parsed.neighborhood === 'string' ? parsed.neighborhood.trim() : undefined,
        address_notes: typeof parsed.address_notes === 'string' ? parsed.address_notes.trim() : undefined,
        last_updated_at: typeof parsed.last_updated_at === 'string' ? parsed.last_updated_at : undefined,
      };
    }
    return null;
  } catch {
    return null;
  }
}

export function saveCustomerProfile(
  profile: Partial<SavedCustomerProfile> & { name: string; phone: string },
): void {
  try {
    if (typeof window === 'undefined' || !window.localStorage) return;
    const cleanProfile: SavedCustomerProfile = {
      name: profile.name.trim(),
      phone: profile.phone.trim(),
      street: profile.street?.trim() || undefined,
      number: profile.number?.trim() || undefined,
      neighborhood: profile.neighborhood?.trim() || undefined,
      address_notes: profile.address_notes?.trim() || undefined,
      last_updated_at: new Date().toISOString(),
    };
    localStorage.setItem(MIMENU_CUSTOMER_PROFILE_KEY, JSON.stringify(cleanProfile));
    localStorage.setItem(LEGACY_CUSTOMER_PROFILE_KEY, JSON.stringify(cleanProfile));
  } catch {
    // Storage might be unavailable/full in restricted browser modes
  }
}
