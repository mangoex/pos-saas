import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { Button, Modal } from '@restaurantos/ui';
import { fetchApi, ApiError } from '@restaurantos/api-client';
import { ShoppingBag, Search, Plus, Minus, Coffee, CupSoda, Sandwich, Salad, Wheat, Package, Utensils, Users, UserRound, X, Check, Banknote, CreditCard, Landmark, Trash2, Bike, Mic, Send, Sparkles, LayoutGrid, Star } from 'lucide-react';
import { usePosSession } from '../../session';
import { formatMxnCents } from './cartMoney';
import {
  resolveEditableLineProduct,
  type EditableCatalogProduct,
  type EditableLineSnapshot,
} from './editableOrderRestore';
import {
  catalogProjectionState,
  CATALOG_MENU_GROUPS,
  categoriesForCatalogMenuGroup,
  filterProductsForCategoryOption,
  productsForCatalogMenuGroup,
  resolveCategoryOptionState,
  transitionCatalogNavigation,
  type CatalogMenuGroupId,
  type CategorySelectionGroup,
} from './categoryOptionFlow';
import { productCardPresentation } from './productCardPresentation';
import { appendDictationText, ASSISTED_DICTATION_SILENCE_MS, shouldRestartDictation } from './assistedDictation';
import { modifierSelectionsMeetMinimums, progressiveCatalogStage } from './progressiveCatalogFlow';
import {
  isAssistedDraftComplete,
  selectedForQuestion,
  toggleAssistedOption,
  type AssistedOrderDraft,
} from './assistedOrderDraft';

const getProductIcon = (category: string, size: number = 40) => {
  const cat = (category || '').toLowerCase();
  if (cat.includes('café') || cat.includes('matcha')) return <Coffee size={size} strokeWidth={1.5} />;
  if (cat.includes('jugo') || cat.includes('agua') || cat.includes('bebida') || cat.includes('smoothie') || cat.includes('extracto') || cat.includes('drink')) return <CupSoda size={size} strokeWidth={1.5} />;
  if (cat.includes('ensalada')) return <Salad size={size} strokeWidth={1.5} />;
  if (cat.includes('panadería') || cat.includes('pan') || cat.includes('dessert')) return <Wheat size={size} strokeWidth={1.5} />;
  if (cat.includes('emparedado') || cat.includes('sando') || cat.includes('burger')) return <Sandwich size={size} strokeWidth={1.5} />;
  if (cat.includes('combo')) return <Package size={size} strokeWidth={1.5} />;
  return <Utensils size={size} strokeWidth={1.5} />;
};

const getCatalogGroupIcon = (groupId: CatalogMenuGroupId) => {
  if (groupId === 'all') return <LayoutGrid size={24} strokeWidth={1.7} />;
  if (groupId === 'food') return <Utensils size={24} strokeWidth={1.7} />;
  if (groupId === 'drinks') return <CupSoda size={24} strokeWidth={1.7} />;
  if (groupId === 'favorites') return <Star size={24} strokeWidth={1.7} />;
  return <Package size={24} strokeWidth={1.7} />;
};

type Product = EditableCatalogProduct & {
  category_id?: string;
  status?: string;
  is_available?: boolean;
  selection?: {
    group_id: string;
    group_code: string;
    group_name: string;
    value_id: string;
    value_code: string;
    value_name: string;
    value_display_order: number;
  } | null;
};

interface PosCategory {
  id: string;
  name: string;
  display_order: number;
  selection_group?: CategorySelectionGroup | null;
}

interface CartItem extends Product {
  lineId: string;
  quantity: number;
  modifiers: SelectedModifier[];
  commentPresets: SelectedOrderComment[];
  ingredientExtras: SelectedIngredientExtra[];
}

interface OrderQuote {
  schema_version: 'order-quote.v1';
  branch_id: string;
  currency: 'MXN';
  lines: Array<{
    product_id: string;
    quantity: number;
    unit_price_cents: number;
    modifier_total_cents: number;
    line_total_cents: number;
  }>;
  subtotal_cents: number;
  adjustment_cents: number;
  adjustment_reason: string | null;
  tax_cents: number | null;
  total_cents: number;
}

type QuoteState = 'idle' | 'loading' | 'ready' | 'error';
type CheckoutState = 'idle' | 'submitting' | 'error';

const buildOrderLines = (items: CartItem[]) => items.map((item) => ({
  product_id: item.id,
  quantity: item.quantity,
  notes: '',
  modifiers: item.modifiers.map((modifier) => ({
    option_id: modifier.option_id,
    text: modifier.text,
  })),
  comment_preset_ids: item.commentPresets.map((comment) => comment.id),
  ingredient_extras: item.ingredientExtras.map((extra) => ({
    extra_id: extra.extra_id,
    portions: extra.portions,
  })),
}));

interface IngredientExtra { extra_id: string; id?: string; name: string; portion_quantity: string; sale_price_cents: number; station: 'kitchen' | 'drinks' | 'packing'; unit_code?: string; }
interface SelectedIngredientExtra extends IngredientExtra { portions: number; }
interface SelectedOrderComment { id: string; text: string; }
interface ModifierOption { id: string; name: string; effect_type: string; price_delta_cents: number; kitchen_text: string; variation_kind?: 'ingredient_extra' | 'order_comment'; variation_id?: string; action?: 'add'; }
interface ModifierGroup { id: string; name: string; minimum_selections: number; maximum_selections: number; options: ModifierOption[]; }
interface SelectedModifier { option_id: string; option_name: string; price_delta_cents: number; text?: string; }
interface EditableOrderLine extends EditableLineSnapshot {
  id: string;
  quantity: number;
  selected_modifiers: Array<Record<string, any>>;
}
interface EditableOrder {
  id: string;
  folio: string;
  version: number;
  owner_name?: string;
  order_type: string;
  payment_method_intent?: PaymentMethod | null;
  editable: boolean;
  edit_block_reason?: string | null;
  lines: EditableOrderLine[];
}

export function shouldAddProductWithoutModifiers(groups: ModifierGroup[]): boolean {
  return groups.length === 0;
}

export function toggleIngredientVariationSelection(selected: string[], options: ModifierOption[], optionId: string): string[] {
  if (selected.includes(optionId)) return selected.filter((id) => id !== optionId);
  const option = options.find((item) => item.id === optionId);
  if (!option?.variation_id) return [...selected, optionId];
  return [...selected.filter((id) => options.find((item) => item.id === id)?.variation_id !== option.variation_id), optionId];
}

interface PosCustomerAddress {
  id: string;
  alias: string;
  street: string;
  exterior_number: string;
  interior_number?: string | null;
  neighborhood: string;
  postal_code?: string;
  city?: string;
  municipality?: string;
  state?: string;
  is_default: boolean;
  status: string;
}

interface PosCustomer {
  id: string;
  name: string;
  addresses: PosCustomerAddress[];
  legacy_address_reference?: string | null;
  phones?: { captured_number?: string; normalized_number?: string }[];
}

interface PosCustomerPage {
  items: PosCustomer[];
  total: number;
}

interface DeliveryDriver {
  id: string;
  name: string;
  phone: string;
  motorcycle_plate: string;
}

type CustomerLookupStatus = 'idle' | 'searching' | 'found' | 'not-found' | 'error';
type BrowserSpeechRecognition = { lang: string; interimResults: boolean; continuous: boolean; onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null; onend: (() => void) | null; onerror: ((event: { error?: string }) => void) | null; start: () => void; stop: () => void; };
type BrowserSpeechRecognitionConstructor = new () => BrowserSpeechRecognition;

const ORDER_TYPES = [
  { value: 'dine-in', label: 'En sucursal' },
  { value: 'takeout', label: 'Para llevar' },
  { value: 'delivery', label: 'A domicilio' },
] as const;

const PAYMENT_METHODS = [
  { value: 'cash', label: 'Efectivo', description: 'Pago en caja', icon: Banknote },
  { value: 'debit_card', label: 'Débito', description: 'Tarjeta de débito', icon: CreditCard },
  { value: 'credit_card', label: 'Crédito', description: 'Tarjeta de crédito', icon: CreditCard },
  { value: 'transfer', label: 'Transferencia', description: 'Transferencia bancaria', icon: Landmark },
] as const;

type PaymentMethod = typeof PAYMENT_METHODS[number]['value'];

type RecoveredOrder = { id: string; folio: string; total_cents: number };
type PendingCheckout = {
  schemaVersion: 1;
  branchId: string;
  registerId: string;
  orderKey: string;
  paymentKey: string;
  paymentMethod: PaymentMethod;
  requiresPayment: boolean;
};

const PENDING_CHECKOUT_STORAGE_KEY = 'pos_pending_checkout_v1';
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function readPendingCheckout(): PendingCheckout | null {
  try {
    const raw = sessionStorage.getItem(PENDING_CHECKOUT_STORAGE_KEY);
    if (!raw) return null;
    const candidate = JSON.parse(raw) as Partial<PendingCheckout>;
    const validPaymentMethod = PAYMENT_METHODS.some(
      (method) => method.value === candidate.paymentMethod,
    );
    if (
      candidate.schemaVersion !== 1
      || typeof candidate.branchId !== 'string' || !UUID_PATTERN.test(candidate.branchId)
      || typeof candidate.registerId !== 'string' || !candidate.registerId.trim()
      || typeof candidate.orderKey !== 'string' || !UUID_PATTERN.test(candidate.orderKey)
      || typeof candidate.paymentKey !== 'string' || !UUID_PATTERN.test(candidate.paymentKey)
      || typeof candidate.requiresPayment !== 'boolean'
      || !validPaymentMethod
    ) {
      clearPendingCheckout();
      return null;
    }
    return candidate as PendingCheckout;
  } catch {
    clearPendingCheckout();
    return null;
  }
}

function clearPendingCheckout() {
  try {
    sessionStorage.removeItem(PENDING_CHECKOUT_STORAGE_KEY);
  } catch {
    // A disabled storage backend must not crash logout or the POS render.
  }
}

function validMexicanPhone(value: string): string {
  const digits = value.replace(/\D/g, '');
  if (digits.length === 10) return digits;
  if (digits.length === 12 && digits.startsWith('52')) return digits;
  return '';
}

const orderErrorMessage = (code?: string, message?: string) => {
  if (code === 'cash_shift_required') {
    return 'La caja no está abierta. Ve a Configuración > Turno y Caja, configura esta terminal y abre un turno antes de cobrar.';
  }
  if (code === 'permission_denied') {
    return 'Tu usuario no tiene permiso para crear pedidos o cobrar en esta sucursal.';
  }
  if (code === 'actor_required') {
    return 'Tu sesión expiró. Inicia sesión otra vez para continuar en el POS.';
  }
  if (code === 'product_unavailable') {
    return 'Uno de los productos no está disponible en la sucursal actual.';
  }
  return message || 'Error al crear la orden.';
};

const PointOfSale = () => {
  const [searchParams] = useSearchParams();
  const { editOrderId: routeEditOrderId = '' } = useParams<{ editOrderId?: string }>();
  // Keep old bookmarked links working while the explicit route is the
  // authoritative way to carry the selected order into edit mode.
  const editOrderId = routeEditOrderId || searchParams.get('edit_order_id') || '';
  const { session, state: sessionState } = usePosSession();
  const branchId = session?.active_branch?.id || '';

  const [activeMenuGroup, setActiveMenuGroup] = useState<CatalogMenuGroupId>('all');
  const [activeCategory, setActiveCategory] = useState('');
  const [favoriteProductIds, setFavoriteProductIds] = useState<string[]>([]);
  const [selectedOptionValueId, setSelectedOptionValueId] = useState('');
  const [isPaymentOpen, setPaymentOpen] = useState(false);
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod | null>(null);
  const [cart, setCart] = useState<CartItem[]>([]);
  const [orderQuote, setOrderQuote] = useState<OrderQuote | null>(null);
  const [quoteState, setQuoteState] = useState<QuoteState>('idle');
  const [checkoutState, setCheckoutState] = useState<CheckoutState>('idle');
  const [quoteError, setQuoteError] = useState('');
  const [modifierProduct, setModifierProduct] = useState<Product | null>(null);
  const [modifierGroups, setModifierGroups] = useState<ModifierGroup[]>([]);
  const [activeModifierGroupId, setActiveModifierGroupId] = useState('');
  const [modifierSelections, setModifierSelections] = useState<Record<string, string[]>>({});
  const [modifierText, setModifierText] = useState<Record<string, string>>({});
  const [modifierError, setModifierError] = useState('');
  const [modifierLoadError, setModifierLoadError] = useState('');
  const [modifierQuantity, setModifierQuantity] = useState(1);
  const [extraModalOpen, setExtraModalOpen] = useState(false);
  const [availableExtras, setAvailableExtras] = useState<IngredientExtra[]>([]);
  const [extraTargetLineId, setExtraTargetLineId] = useState('');
  const [extraSelections, setExtraSelections] = useState<Record<string, number>>({});
  const [extraError, setExtraError] = useState('');
  const [extrasLoading, setExtrasLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [assistedCaptureOpen, setAssistedCaptureOpen] = useState(false);
  const [assistedText, setAssistedText] = useState('');
  const [assistedDraft, setAssistedDraft] = useState<AssistedOrderDraft | null>(null);
  const [assistedDictating, setAssistedDictating] = useState(false);
  const [assistedLoading, setAssistedLoading] = useState(false);
  const [assistedError, setAssistedError] = useState('');
  const assistedRecognitionRef = useRef<BrowserSpeechRecognition | null>(null);
  const assistedDictationStoppedRef = useRef(true);
  const assistedDictationLastResultRef = useRef(0);
  const assistedDictationRestartRef = useRef<number | null>(null);
  const assistedDictationDeadlineRef = useRef<number | null>(null);
  const assistedTextRef = useRef('');

  const [ownerName, setOwnerName] = useState('');
  const [orderType, setOrderType] = useState('dine-in');
  const [customerPhone, setCustomerPhone] = useState('');
  const [searchResults, setSearchResults] = useState<PosCustomer[]>([]);
  const [customerLookupStatus, setCustomerLookupStatus] = useState<CustomerLookupStatus>('idle');
  const [customerSearchError, setCustomerSearchError] = useState('');
  const [newCustomerName, setNewCustomerName] = useState('');
  const [newCustomerEmail, setNewCustomerEmail] = useState('');
  const [creatingCustomer, setCreatingCustomer] = useState(false);
  const [createCustomerError, setCreateCustomerError] = useState('');
  const [isCourtesyModalOpen, setIsCourtesyModalOpen] = useState(false);
  const [adjustmentAuthorizationId, setAdjustmentAuthorizationId] = useState<string | null>(null);
  const [courtesyReason, setCourtesyReason] = useState('');
  const [tempCourtesyType, setTempCourtesyType] = useState<'percent' | 'fixed' | 'courtesy'>('percent');
  const [tempCourtesyValue, setTempCourtesyValue] = useState('10');
  const [tempReason, setTempReason] = useState('Cortesía de la casa');
  const [supervisorPin, setSupervisorPin] = useState('');
  const [pinError, setPinError] = useState('');
  const [selectedCustomer, setSelectedCustomer] = useState<PosCustomer | null>(null);
  const [upsellRecs, setUpsellRecs] = useState<Array<{ product_id: string; product_name: string; price_cents: number; reason: string }>>([]);
  const [selectedAddressId, setSelectedAddressId] = useState('');
  const [showAddressForm, setShowAddressForm] = useState(false);
  const [availableDrivers, setAvailableDrivers] = useState<DeliveryDriver[]>([]);
  const [selectedDriverId, setSelectedDriverId] = useState('');
  const [driverPickerOpen, setDriverPickerOpen] = useState(false);
  const [driversLoading, setDriversLoading] = useState(false);
  const [driversError, setDriversError] = useState('');
  const searchControllerRef = useRef<AbortController | null>(null);
  const checkoutIntentRef = useRef<{ fingerprint: string; key: string; paymentKey: string } | null>(null);
  const checkoutRecoveryStartedRef = useRef(false);

  useEffect(() => {
    if (!selectedCustomer) {
      setUpsellRecs([]);
      return;
    }
    const currentProductIds = cart.map((c) => c.id).filter(Boolean);
    fetchApi('/admin-ai/customer-recommendations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        customer_id: selectedCustomer.id,
        current_product_ids: currentProductIds,
      }),
    })
      .then((res: any) => {
        if (res?.recommendations) {
          setUpsellRecs(res.recommendations);
        }
      })
      .catch(() => setUpsellRecs([]));
  }, [selectedCustomer, cart.length]);

  useEffect(() => {
    if (!branchId || sessionState.status !== 'ok' || checkoutRecoveryStartedRef.current) return;
    const pendingCheckout = readPendingCheckout();
    if (!pendingCheckout) return;
    if (pendingCheckout.branchId !== branchId) {
      setCheckoutState('error');
      alert('Hay un cobro pendiente de otra sucursal. Vuelve a esa sucursal para recuperarlo.');
      return;
    }
    checkoutRecoveryStartedRef.current = true;

    const recoverCheckout = async () => {
      setCheckoutState('submitting');
      try {
        const orderData = await fetchApi<RecoveredOrder>('/orders/recover', {
          method: 'POST',
          headers: { 'Idempotency-Key': pendingCheckout.orderKey },
          body: JSON.stringify({}),
        });
        if (pendingCheckout.requiresPayment) {
          await fetchApi(`/orders/${orderData.id}/payments`, {
            method: 'POST',
            headers: { 'Idempotency-Key': pendingCheckout.paymentKey },
            body: JSON.stringify({
              amount_cents: orderData.total_cents,
              method: pendingCheckout.paymentMethod,
              register_id: pendingCheckout.registerId,
            }),
          });
          alert(`¡Venta recuperada y finalizada! Orden #${orderData.folio}`);
        } else {
          alert(`Pedido #${orderData.folio} recuperado como pendiente de pago.`);
        }
        clearPendingCheckout();
        checkoutIntentRef.current = null;
        setCart([]);
        setPaymentOpen(false);
        setPaymentMethod(null);
        setCheckoutState('idle');
      } catch (reason) {
        if (reason instanceof ApiError && reason.code === 'order_create_not_found') {
          clearPendingCheckout();
          alert('La solicitud anterior no creó un pedido. Puedes capturarlo nuevamente.');
          setCheckoutState('idle');
          return;
        }
        setCheckoutState('error');
        alert(
          reason instanceof ApiError
            ? `No fue posible recuperar el cobro pendiente: ${reason.message}`
            : 'No fue posible recuperar el cobro pendiente. Reintenta al volver a abrir el POS.',
        );
      }
    };
    void recoverCheckout();
  }, [branchId, sessionState.status]);

  useEffect(() => {
    if (!branchId || cart.length === 0) {
      setOrderQuote(null);
      setQuoteState('idle');
      setQuoteError('');
      return undefined;
    }
    const controller = new AbortController();
    setOrderQuote(null);
    setQuoteState('loading');
    setQuoteError('');
    const timeout = window.setTimeout(async () => {
      try {
        const quote = await fetchApi<OrderQuote>('/orders/quote', {
          method: 'POST',
          signal: controller.signal,
          body: JSON.stringify({
            branch_id: branchId,
            lines: buildOrderLines(cart),
            adjustment_authorization_id: adjustmentAuthorizationId || undefined,
          }),
        });
        setOrderQuote(quote);
        setQuoteState('ready');
      } catch (error) {
        if (controller.signal.aborted) return;
        if (adjustmentAuthorizationId) {
          setAdjustmentAuthorizationId(null);
          setCourtesyReason('');
        }
        setOrderQuote(null);
        setQuoteState('error');
        setQuoteError(
          error instanceof ApiError ? error.message : 'No fue posible calcular el total.',
        );
      }
    }, 180);
    return () => {
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [adjustmentAuthorizationId, branchId, cart]);

  const [categories, setCategories] = useState<PosCategory[]>([{ id: '', name: 'Todas', display_order: -1, selection_group: null }]);
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [catalogError, setCatalogError] = useState('');
  const [catalogRetryNonce, setCatalogRetryNonce] = useState(0);
  const [editingOrder, setEditingOrder] = useState<EditableOrder | null>(null);
  const [editLoadError, setEditLoadError] = useState('');
  const favoriteProductStorageKey = session?.user?.id && branchId
    ? `pos_product_favorites_v1:${session.user.id}:${branchId}`
    : '';

  useEffect(() => {
    if (!favoriteProductStorageKey) {
      setFavoriteProductIds([]);
      return;
    }
    try {
      const stored = JSON.parse(window.localStorage.getItem(favoriteProductStorageKey) || '[]');
      setFavoriteProductIds(Array.isArray(stored)
        ? [...new Set(stored.filter((id): id is string => typeof id === 'string'))]
        : []);
    } catch {
      setFavoriteProductIds([]);
    }
  }, [favoriteProductStorageKey]);

  // Cargar catálogo al montar (no precarga clientes)
  useEffect(() => {
    if (!branchId) {
      if (sessionState.status !== 'loading') {
        setCatalogError('La sesión no tiene una sucursal activa. Vuelve a iniciar sesión.');
        setLoading(false);
      }
      return;
    }
    const fetchData = async () => {
      setLoading(true);
      setCatalogError('');
      try {
        const [catData, prodData] = await Promise.all([
          fetchApi<any[]>(`/categories?branch_id=${encodeURIComponent(branchId)}`),
          fetchApi<any[]>(`/catalog/products?branch_id=${encodeURIComponent(branchId)}`),
        ]);
        const mappedCategories: PosCategory[] = Array.isArray(catData)
          ? [{ id: '', name: 'Todas', display_order: -1, selection_group: null }, ...catData]
          : [];
        const mappedProducts: Product[] = Array.isArray(prodData)
          ? prodData
            .filter((p: any) => (
              p.status === 'active'
              && p.is_available !== false
              && Number.isSafeInteger(p.price_cents)
              && p.price_cents > 0
            ))
            .map((p: any) => ({
              id: p.id,
              name: p.name,
              sku: p.sku,
              category: p.category_name,
              category_id: p.category_id,
              price_cents: p.price_cents,
              description: p.description,
              station: p.station,
              image_url: p.image_url,
              selection: p.selection || null,
            }))
          : [];
        setCategories(mappedCategories);
        setProducts(mappedProducts);
        setActiveMenuGroup('all');
        setActiveCategory('');
      } catch (e) {
        console.error('Error al cargar datos del POS:', e);
        setCatalogError('No se pudo cargar el menú de la sucursal.');
        setProducts([]);
      } finally {
        setLoading(false);
      }
    };
    void fetchData();
  }, [branchId, sessionState.status, catalogRetryNonce]);

  useEffect(() => {
    if (!editOrderId) return;
    let cancelled = false;
    setEditLoadError('');
    fetchApi<EditableOrder>(`/orders/${editOrderId}`)
      .then((order) => {
        if (cancelled) return;
        if (!order.editable) {
          setEditLoadError(order.edit_block_reason || 'Este pedido ya no se puede editar.');
          return;
        }
        const productById = new Map(products.map((product) => [product.id, product]));
        const restored = order.lines.map((line) => {
          const product = resolveEditableLineProduct(line, productById);
          const comments: SelectedOrderComment[] = [];
          const extras: SelectedIngredientExtra[] = [];
          const modifiers: SelectedModifier[] = [];
          for (const selected of line.selected_modifiers || []) {
            if (selected.kind === 'order_comment' || selected.selection_kind === 'order_comment') {
              comments.push({ id: String(selected.comment_preset_id || selected.option_id), text: String(selected.kitchen_text || selected.name || '') });
            } else if (selected.kind === 'ingredient_extra' || selected.selection_kind === 'ingredient_extra') {
              extras.push({
                extra_id: String(selected.extra_id || selected.variation_id || selected.option_id),
                name: String(selected.name || selected.kitchen_text || 'Adicional'),
                portion_quantity: String(selected.portion_quantity || '1'),
                sale_price_cents: Number(selected.price_delta_cents || 0),
                station: (selected.station || line.station) as IngredientExtra['station'],
                portions: Number(selected.portions || 1),
              });
            } else {
              modifiers.push({
                option_id: String(selected.option_id || selected.id),
                option_name: String(selected.name || selected.kitchen_text || 'Opción'),
                price_delta_cents: Number(selected.price_delta_cents || 0),
                text: selected.text ? String(selected.text) : undefined,
              });
            }
          }
          return {
            ...product,
            lineId: crypto.randomUUID(),
            quantity: line.quantity,
            modifiers,
            commentPresets: comments,
            ingredientExtras: extras,
          };
        });
        setEditingOrder(order);
        setCart(restored);
        setOwnerName(order.owner_name || '');
        setOrderType(order.order_type);
        setPaymentMethod(order.payment_method_intent || null);
      })
      .catch((error) => {
        if (!cancelled) {
          setEditLoadError(error instanceof ApiError ? error.message : 'No fue posible cargar el pedido.');
        }
      });
    return () => { cancelled = true; };
  }, [editOrderId, products]);

  useEffect(() => {
    if (orderType !== 'delivery') {
      setSelectedDriverId('');
      setDriverPickerOpen(false);
      setDriversError('');
    }
  }, [orderType]);

  // Búsqueda exacta por teléfono con debounce y AbortController
  useEffect(() => {
    const phone = validMexicanPhone(customerPhone);
    if (!branchId || !phone) {
      searchControllerRef.current?.abort();
      setSearchResults([]);
      setCustomerLookupStatus('idle');
      setCustomerSearchError('');
      return undefined;
    }
    setCustomerLookupStatus('searching');
    setCustomerSearchError('');
    searchControllerRef.current?.abort();
    const controller = new AbortController();
    searchControllerRef.current = controller;
    const timer = window.setTimeout(() => {
      const params = new URLSearchParams({
        branch_id: branchId,
        phone,
        limit: '20',
      });
      fetchApi<PosCustomerPage>(`/customers?${params.toString()}`, {
        signal: controller.signal,
      })
        .then((page) => {
          const items = page.items || [];
          if (items.length === 1) {
            selectCustomer(items[0]);
            return;
          }
          setSearchResults(items);
          setCustomerLookupStatus(items.length > 0 ? 'found' : 'not-found');
        })
        .catch((err) => {
          if (err instanceof DOMException && err.name === 'AbortError') return;
          setCustomerSearchError('No fue posible buscar el teléfono. Intenta nuevamente.');
          setCustomerLookupStatus('error');
        });
    }, 300);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [customerPhone, branchId]);

  const selectCustomer = useCallback((customer: PosCustomer) => {
    setSelectedCustomer(customer);
    setOwnerName(customer.name || '');
    setSearchResults([]);
    setCustomerLookupStatus('idle');
    setNewCustomerName('');
    setNewCustomerEmail('');
    setCreateCustomerError('');
    setShowAddressForm(false);
    // Seleccionar domicilio predeterminado o el único activo
    const activeAddresses = (customer.addresses || []).filter((a) => a.status === 'active');
    const defaultAddr = activeAddresses.find((a) => a.is_default);
    if (defaultAddr) {
      setSelectedAddressId(defaultAddr.id);
    } else if (activeAddresses.length === 1) {
      setSelectedAddressId(activeAddresses[0].id);
    } else {
      setSelectedAddressId('');
    }
  }, []);

  const clearCustomer = useCallback(() => {
    setSelectedCustomer(null);
    setOwnerName('');
    setSelectedAddressId('');
    setCustomerPhone('');
    setSearchResults([]);
    setCustomerLookupStatus('idle');
    setNewCustomerName('');
    setNewCustomerEmail('');
    setCreateCustomerError('');
    setShowAddressForm(false);
  }, []);

  const registerCustomer = async () => {
    const phone = validMexicanPhone(customerPhone);
    const name = newCustomerName.trim();
    if (!phone || !name || !branchId) {
      setCreateCustomerError('Captura un teléfono válido y el nombre del cliente.');
      return;
    }
    setCreatingCustomer(true);
    setCreateCustomerError('');
    try {
      const customer = await fetchApi<PosCustomer>('/customers', {
        method: 'POST',
        body: JSON.stringify({
          branch_id: branchId,
          name,
          email: newCustomerEmail.trim() || undefined,
          phones: [{ number: phone, is_primary: true, type: 'mobile' }],
        }),
      });
      selectCustomer(customer);
      if (orderType === 'delivery') setShowAddressForm(true);
    } catch (err) {
      setCreateCustomerError(
        err instanceof ApiError ? err.message : 'No se pudo registrar al cliente.',
      );
    } finally {
      setCreatingCustomer(false);
    }
  };

  const groupedProducts = productsForCatalogMenuGroup(
    products, activeMenuGroup, favoriteProductIds,
  );
  const categoryChoices = categoriesForCatalogMenuGroup(
    categories, products, activeMenuGroup, favoriteProductIds,
  );
  const activeCategoryDetails = categories.find((category) => category.name === activeCategory) || null;
  const activeSelectionGroup = activeCategoryDetails?.selection_group || null;
  const projectionState = catalogProjectionState(Boolean(catalogError), activeSelectionGroup);
  const categoryOptionState = activeSelectionGroup && activeCategoryDetails
    ? resolveCategoryOptionState(activeCategoryDetails, selectedOptionValueId)
    : 'products';
  const activeSelectionValue = activeSelectionGroup?.values.find((value) => value.id === selectedOptionValueId) || null;
  const filteredProducts = categoryOptionState === 'selection-required'
    ? []
    : filterProductsForCategoryOption(
      groupedProducts,
      activeCategoryDetails?.id || '',
      activeSelectionValue?.id || '',
      searchQuery,
    );
  const catalogStage = progressiveCatalogStage({
    hasCategory: Boolean(activeCategoryDetails),
    selectionRequired: categoryOptionState === 'selection-required',
    hasModifierProduct: Boolean(modifierProduct),
    startsAtProducts: activeMenuGroup === 'favorites',
  });
  const activeModifierGroup = modifierGroups.find((group) => group.id === activeModifierGroupId)
    || modifierGroups[0]
    || null;
  const modifierMinimumsMet = modifierSelectionsMeetMinimums(modifierGroups, modifierSelections);

  const addToCart = (product: Product, modifiers: SelectedModifier[] = [], commentPresets: SelectedOrderComment[] = [], ingredientExtras: SelectedIngredientExtra[] = [], quantity: number = 1) => {
    const safeQuantity = Math.max(1, Math.min(99, Math.trunc(quantity)));
    setCart(prev => {
      const existing = modifiers.length === 0 && commentPresets.length === 0 && ingredientExtras.length === 0 ? prev.find(item => item.id === product.id && item.modifiers.length === 0 && item.commentPresets.length === 0 && item.ingredientExtras.length === 0) : undefined;
      if (existing) {
        return prev.map(item => item.lineId === existing.lineId ? { ...item, quantity: item.quantity + safeQuantity } : item);
      }
      return [...prev, {
        ...product,
        lineId: crypto.randomUUID(),
        quantity: safeQuantity,
        modifiers,
        commentPresets,
        ingredientExtras,
      }];
    });
  };

  const closeAssistedCapture = () => {
    assistedDictationStoppedRef.current = true;
    if (assistedDictationRestartRef.current) window.clearTimeout(assistedDictationRestartRef.current);
    if (assistedDictationDeadlineRef.current) window.clearTimeout(assistedDictationDeadlineRef.current);
    try {
      assistedRecognitionRef.current?.stop();
    } catch {
      // The browser may reject stop() when recognition never reached the active state.
    }
    assistedRecognitionRef.current = null;
    assistedTextRef.current = '';
    setAssistedDictating(false);
    setAssistedCaptureOpen(false);
    setAssistedText('');
    setAssistedDraft(null);
    setAssistedLoading(false);
    setAssistedError('');
  };

  const stopAssistedDictation = () => {
    assistedDictationStoppedRef.current = true;
    if (assistedDictationRestartRef.current) window.clearTimeout(assistedDictationRestartRef.current);
    if (assistedDictationDeadlineRef.current) window.clearTimeout(assistedDictationDeadlineRef.current);
    try {
      assistedRecognitionRef.current?.stop();
    } catch {
      // The browser may reject stop() when recognition never reached the active state.
    }
    assistedRecognitionRef.current = null;
    setAssistedDictating(false);
  };

  useEffect(() => () => {
    assistedDictationStoppedRef.current = true;
    if (assistedDictationRestartRef.current) window.clearTimeout(assistedDictationRestartRef.current);
    if (assistedDictationDeadlineRef.current) window.clearTimeout(assistedDictationDeadlineRef.current);
    try {
      assistedRecognitionRef.current?.stop();
    } catch {
      // The browser may reject stop() when recognition never reached the active state.
    }
    assistedRecognitionRef.current = null;
  }, []);

  const previewAssistedCapture = async () => {
    setAssistedLoading(true);
    setAssistedError('');
    try {
      const draft = await fetchApi<AssistedOrderDraft>('/orders/assisted-draft', {
        method: 'POST',
        body: JSON.stringify({ branch_id: branchId, text: assistedText.trim() }),
      });
      setAssistedDraft(draft);
    } catch (reason) {
      setAssistedDraft(null);
      setAssistedError(reason instanceof ApiError ? reason.message : 'Pedido asistido no está disponible. Captura el pedido manualmente.');
    } finally {
      setAssistedLoading(false);
    }
  };

  const toggleAssistedDictation = () => {
    const stopDictation = stopAssistedDictation;
    if (!assistedDictationStoppedRef.current) {
      stopDictation();
      return;
    }
    const recognitionConstructor = (window as unknown as { SpeechRecognition?: BrowserSpeechRecognitionConstructor; webkitSpeechRecognition?: BrowserSpeechRecognitionConstructor }).SpeechRecognition
      || (window as unknown as { webkitSpeechRecognition?: BrowserSpeechRecognitionConstructor }).webkitSpeechRecognition;
    if (!recognitionConstructor) return;
    assistedDictationStoppedRef.current = false;
    assistedTextRef.current = assistedText;
    const armDeadline = () => {
      if (assistedDictationDeadlineRef.current) window.clearTimeout(assistedDictationDeadlineRef.current);
      assistedDictationDeadlineRef.current = window.setTimeout(stopDictation, ASSISTED_DICTATION_SILENCE_MS);
    };
    const startRecognition = () => {
      const sessionBase = assistedTextRef.current.trim();
      const recognition = new recognitionConstructor();
      recognition.lang = 'es-MX';
      recognition.interimResults = true;
      recognition.continuous = true;
      recognition.onresult = (event) => {
        if (assistedRecognitionRef.current !== recognition) return;
        const transcript = Array.from(event.results).map((result) => result[0]?.transcript || '').join('');
        assistedDictationLastResultRef.current = Date.now();
        if (transcript.trim()) armDeadline();
        const nextText = appendDictationText(sessionBase, transcript);
        assistedTextRef.current = nextText;
        setAssistedText(nextText);
        setAssistedDraft(null);
        setAssistedError('');
      };
      recognition.onerror = (event) => {
        if (assistedRecognitionRef.current !== recognition) return;
        if ((event.error || '') !== 'no-speech') stopDictation();
      };
      recognition.onend = () => {
        if (assistedRecognitionRef.current !== recognition) return;
        assistedRecognitionRef.current = null;
        if (shouldRestartDictation(Date.now(), assistedDictationLastResultRef.current, assistedDictationStoppedRef.current)) {
          assistedDictationRestartRef.current = window.setTimeout(startRecognition, 0);
        } else setAssistedDictating(false);
      };
      assistedRecognitionRef.current = recognition;
      setAssistedDictating(true);
      try {
        recognition.start();
      } catch {
        stopDictation();
      }
    };
    assistedDictationLastResultRef.current = Date.now();
    armDeadline();
    startRecognition();
  };

  const applyAssistedCapture = () => {
    if (!assistedDraft || !isAssistedDraftComplete(assistedDraft)) return;
    const resolved = assistedDraft.lines.map((line) => ({ line, product: products.find((product) => product.id === line.product_id) }))
      .filter((item): item is { line: NonNullable<typeof assistedDraft>['lines'][number]; product: Product } => Boolean(item.product));
    if (resolved.length !== assistedDraft.lines.length) return;
    if (assistedDraft.phone) {
      setSelectedCustomer(null);
      setSelectedAddressId('');
      setSearchResults([]);
      setCustomerLookupStatus('idle');
    }
    if (assistedDraft.customer_name) setOwnerName(assistedDraft.customer_name);
    if (assistedDraft.phone) setCustomerPhone(assistedDraft.phone);
    if (assistedDraft.order_type) setOrderType(assistedDraft.order_type);
    resolved.forEach(({ line, product }) => {
      const comments = line.selected_options.filter((option) => option.kind === 'comment')
        .map((option) => ({ id: option.option_id, text: option.option_name }));
      const modifiers = line.selected_options.filter((option) => option.kind === 'modifier')
        .map((option) => ({ option_id: option.option_id, option_name: option.option_name, price_delta_cents: option.price_delta_cents }));
      addToCart(product, modifiers, comments, [], line.quantity);
    });
    closeAssistedCapture();
  };

  const resetModifierModal = () => {
    setModifierProduct(null);
    setModifierGroups([]);
    setActiveModifierGroupId('');
    setModifierSelections({});
    setModifierText({});
    setModifierQuantity(1);
    setModifierError('');
    setModifierLoadError('');
  };

  const resetCatalogTransientState = () => {
    resetModifierModal();
  };

  const changeActiveCategory = (category: PosCategory) => {
    const next = transitionCatalogNavigation({
      categoryId: activeCategoryDetails?.id || '', valueId: selectedOptionValueId,
      cart, search: searchQuery,
      transient: { modifierProductId: modifierProduct?.id || null, groups: modifierGroups.map((group) => group.id), selections: modifierSelections, error: modifierError },
    }, category.id, '');
    if (next.transient.modifierProductId === null) resetCatalogTransientState();
    setActiveCategory(category.name);
    setSelectedOptionValueId(next.valueId);
    setSearchQuery(next.search);
  };

  const changeActiveMenuGroup = (groupId: CatalogMenuGroupId) => {
    const next = transitionCatalogNavigation({
      categoryId: activeCategoryDetails?.id || '', valueId: selectedOptionValueId,
      cart, search: searchQuery,
      transient: { modifierProductId: modifierProduct?.id || null, groups: modifierGroups.map((group) => group.id), selections: modifierSelections, error: modifierError },
    }, '', '');
    if (next.transient.modifierProductId === null) resetCatalogTransientState();
    setActiveMenuGroup(groupId);
    setActiveCategory('');
    setSelectedOptionValueId(next.valueId);
    setSearchQuery(next.search);
  };

  const toggleFavoriteProduct = (productId: string) => {
    const next = favoriteProductIds.includes(productId)
      ? favoriteProductIds.filter((id) => id !== productId)
      : [...favoriteProductIds, productId];
    setFavoriteProductIds(next);
    if (favoriteProductStorageKey) {
      try {
        window.localStorage.setItem(favoriteProductStorageKey, JSON.stringify(next));
      } catch {
        // Favorites are a local convenience; storage failure must not block catalog navigation.
      }
    }
  };

  const changeCategoryOption = (valueId: string) => {
    if (!activeCategoryDetails) return;
    const next = transitionCatalogNavigation({
      categoryId: activeCategoryDetails.id, valueId: selectedOptionValueId,
      cart, search: searchQuery,
      transient: { modifierProductId: modifierProduct?.id || null, groups: modifierGroups.map((group) => group.id), selections: modifierSelections, error: modifierError },
    }, activeCategoryDetails.id, valueId);
    if (next.transient.modifierProductId === null) resetCatalogTransientState();
    setSelectedOptionValueId(next.valueId);
    setSearchQuery(next.search);
  };

  useEffect(() => {
    if (activeSelectionGroup && categoryOptionState === 'selection-required' && selectedOptionValueId) {
      setSelectedOptionValueId('');
    }
  }, [activeSelectionGroup, categoryOptionState, selectedOptionValueId]);

  const closeExtraModal = () => {
    setExtraModalOpen(false);
    setExtraTargetLineId('');
    setExtraSelections({});
    setExtraError('');
  };

  const openIngredientExtras = async () => {
    if (cart.length === 0) return;
    setExtraModalOpen(true);
    setExtraError('');
    setExtraTargetLineId(cart.length === 1 ? cart[0].lineId : '');
    setExtraSelections(cart.length === 1 ? Object.fromEntries(cart[0].ingredientExtras.map((extra) => [extra.extra_id, extra.portions])) : {});
    setExtrasLoading(true);
    try {
      const extras = await fetchApi<IngredientExtra[]>(`/catalog/ingredient-extras/available?branch_id=${encodeURIComponent(branchId)}`);
      setAvailableExtras(Array.isArray(extras) ? extras.filter((extra) => (
        Number.isSafeInteger(extra.sale_price_cents) && extra.sale_price_cents >= 0
      )) : []);
    } catch (error) {
      setExtraError(error instanceof ApiError ? error.message : 'No fue posible cargar los ingredientes adicionales.');
      setAvailableExtras([]);
    } finally {
      setExtrasLoading(false);
    }
  };

  const selectExtraTarget = (lineId: string) => {
    setExtraTargetLineId(lineId);
    const line = cart.find((item) => item.lineId === lineId);
    setExtraSelections(Object.fromEntries((line?.ingredientExtras || []).map((extra) => [extra.extra_id, extra.portions])));
    setExtraError('');
  };

  const removeIngredientExtra = (lineId: string, extraId: string) => {
    setCart((current) => current.map((item) => item.lineId === lineId ? { ...item, ingredientExtras: item.ingredientExtras.filter((extra) => extra.extra_id !== extraId) } : item));
  };

  const updateExtraSelection = (extra: IngredientExtra, portions: number) => {
    setExtraSelections((current) => {
      const next = { ...current };
      if (portions <= 0) delete next[extra.extra_id || extra.id || ''];
      else next[extra.extra_id || extra.id || ''] = Math.min(99, Math.max(0, Math.trunc(portions)));
      return next;
    });
  };

  const applyIngredientExtras = () => {
    if (!extraTargetLineId) {
      setExtraError('Selecciona la línea del pedido que recibirá los ingredientes adicionales.');
      return;
    }
    const selected = availableExtras.flatMap((extra) => {
      const extraId = extra.extra_id || extra.id || '';
      const portions = extraSelections[extraId] || 0;
      return portions > 0 ? [{ ...extra, extra_id: extraId, portions }] : [];
    });
    setCart((current) => current.map((item) => item.lineId === extraTargetLineId ? { ...item, ingredientExtras: selected } : item));
    closeExtraModal();
  };

  const selectProduct = async (product: Product) => {
    try {
      const groups = await fetchApi<ModifierGroup[]>(
        `/products/${product.id}/modifiers?branch_id=${encodeURIComponent(branchId)}`,
      );
      if (!Array.isArray(groups) || shouldAddProductWithoutModifiers(groups)) {
        resetModifierModal();
        addToCart(product);
        return;
      }
      setModifierProduct(product);
      setModifierGroups(groups);
      setActiveModifierGroupId(groups[0]?.id || '');
      setModifierSelections({});
      setModifierQuantity(1);
      setModifierText({});
      setModifierError('');
      setModifierLoadError('');
    } catch {
      setModifierProduct(product);
      setModifierGroups([]);
      setActiveModifierGroupId('');
      setModifierLoadError('No fue posible cargar las variaciones del producto.');
    }
  };

  const toggleModifier = (group: ModifierGroup, optionId: string) => {
    setModifierSelections((current) => {
      const selected = current[group.id] || [];
      if (selected.includes(optionId)) return { ...current, [group.id]: selected.filter((id) => id !== optionId) };
      if (group.options.find((option) => option.id === optionId)?.variation_kind === 'ingredient_extra') return { ...current, [group.id]: toggleIngredientVariationSelection(selected, group.options, optionId) };
      if (group.maximum_selections === 1) return { ...current, [group.id]: [optionId] };
      if (selected.length >= group.maximum_selections) return current;
      return { ...current, [group.id]: [...selected, optionId] };
    });
  };

  const confirmModifiers = () => {
    if (!modifierProduct) return;
    const invalid = modifierGroups.find((group) => (modifierSelections[group.id] || []).length < group.minimum_selections);
    if (invalid) {
      setModifierError(`Selecciona al menos ${invalid.minimum_selections} opción(es) en ${invalid.name}.`);
      return;
    }
    const selected = modifierGroups.flatMap((group) => (modifierSelections[group.id] || []).map((optionId) => {
      const option = group.options.find((item) => item.id === optionId)!;
      return { option_id: option.id, option_name: option.name, price_delta_cents: option.price_delta_cents, text: option.effect_type === 'instruction' ? modifierText[option.id] : undefined };
    }));
    const commentOptionIds = new Set(
      modifierGroups.flatMap((group) => group.options)
        .filter((option) => option.variation_kind === 'order_comment')
        .map((option) => option.id),
    );
    const commentPresets = selected
      .filter((selection) => commentOptionIds.has(selection.option_id))
      .map((selection) => ({ id: selection.option_id, text: selection.option_name }));
    const modifiers = selected.filter((selection) => !commentOptionIds.has(selection.option_id));
    addToCart(modifierProduct, modifiers, commentPresets, [], modifierQuantity);
    resetModifierModal();
  };

  const updateQuantity = (lineId: string, delta: number) => {
    setCart(prev => prev.flatMap(item => {
      if (item.lineId === lineId) {
        const newQty = item.quantity + delta;
        return newQty > 0 ? [{ ...item, quantity: newQty }] : [];
      }
      return [item];
    }));
  };

  const removeCartLine = (lineId: string) => {
    setCart((current) => current.filter((item) => item.lineId !== lineId));
  };

  const openDriverPicker = async () => {
    if (!branchId) return;
    setDriverPickerOpen(true);
    setDriversLoading(true);
    setDriversError('');
    try {
      const drivers = await fetchApi<DeliveryDriver[]>(
        `/delivery/drivers/available?branch_id=${encodeURIComponent(branchId)}`,
      );
      setAvailableDrivers(Array.isArray(drivers) ? drivers : []);
    } catch (reason) {
      setDriversError(
        reason instanceof ApiError
          ? reason.message
          : 'No fue posible cargar los repartidores.',
      );
      setAvailableDrivers([]);
    } finally {
      setDriversLoading(false);
    }
  };

  const processTransaction = async () => {
    if (checkoutState === 'submitting') return;
    const unresolvedCheckout = readPendingCheckout();
    if (unresolvedCheckout) {
      alert('Hay un cobro pendiente de recuperación. Resuélvelo antes de iniciar otra venta.');
      return;
    }
    const registerId = (localStorage.getItem('pos_register_id') || '').trim();
    if (!paymentMethod && !editingOrder) return;
    if (!branchId) {
      alert('No hay sucursal asignada para este POS. Inicia sesión de nuevo o configura la sucursal.');
      return;
    }
    if (!editingOrder && !registerId) {
      alert('No hay una caja configurada. Ve a Configuración > Turno y Caja antes de crear el pedido.');
      return;
    }

    const payload = {
      owner_name: ownerName || 'Cliente General',
      customer_id: selectedCustomer?.id || undefined,
      delivery_address_id: selectedAddressId || undefined,
      payment_method_intent: orderType === 'dine-in' ? undefined : paymentMethod,
      driver_id: orderType === 'delivery' && selectedDriverId ? selectedDriverId : undefined,
      order_type: orderType,
      branch_id: branchId || undefined,
      register_id: registerId,
      adjustment_authorization_id: adjustmentAuthorizationId || undefined,
      lines: buildOrderLines(cart),
    };
    const fingerprint = JSON.stringify(payload);
    const checkoutIntent = checkoutIntentRef.current?.fingerprint === fingerprint
      ? checkoutIntentRef.current
      : { fingerprint, key: crypto.randomUUID(), paymentKey: crypto.randomUUID() };
    checkoutIntentRef.current = checkoutIntent;
    if (!editingOrder) {
      const pendingCheckout: PendingCheckout = {
        schemaVersion: 1,
        branchId,
        registerId,
        orderKey: checkoutIntent.key,
        paymentKey: checkoutIntent.paymentKey,
        paymentMethod: paymentMethod as PaymentMethod,
        requiresPayment: orderType === 'dine-in',
      };
      try {
        sessionStorage.setItem(PENDING_CHECKOUT_STORAGE_KEY, JSON.stringify(pendingCheckout));
      } catch {
        alert('Este navegador no permite conservar el intento de cobro. No se creó ningún pedido.');
        return;
      }
    }
    setCheckoutState('submitting');

    try {
      if (editingOrder) {
        await fetchApi(`/orders/${editingOrder.id}/amendments`, {
          method: 'POST',
          headers: { 'Idempotency-Key': crypto.randomUUID() },
          body: JSON.stringify({ expected_version: editingOrder.version, lines: payload.lines }),
        });
        alert(`Pedido #${editingOrder.folio} actualizado.`);
        checkoutIntentRef.current = null;
        setCheckoutState('idle');
        window.location.href = '/pos/history';
        return;
      }
      const orderData = await fetchApi<{ id: string; folio: string; total_cents: number }>(
        '/orders',
        {
          method: 'POST',
          headers: { 'Idempotency-Key': checkoutIntent.key },
          body: JSON.stringify(payload),
        },
      );
      if (orderType !== 'dine-in') {
        clearPendingCheckout();
        checkoutIntentRef.current = null;
        alert(`Pedido #${orderData.folio} guardado como pendiente de pago.`);
        setCart([]);
        setAdjustmentAuthorizationId(null);
        setCourtesyReason('');
        setPaymentOpen(false);
        setPaymentMethod(null);
        setSelectedDriverId('');
        setAvailableDrivers([]);
        clearCustomer();
        setCheckoutState('idle');
        return;
      }
      // Cobro inmediato en sucursal
      try {
        await fetchApi(`/orders/${orderData.id}/payments`, {
          method: 'POST',
          headers: { 'Idempotency-Key': checkoutIntent.paymentKey },
          body: JSON.stringify({
            amount_cents: orderData.total_cents,
            method: paymentMethod,
            register_id: registerId,
          }),
        });
      } catch (payErr) {
        const msg = payErr instanceof ApiError ? payErr.message : 'Error desconocido';
        alert(`Orden creada, pero el pago falló: ${msg}`);
        setCheckoutState('idle');
        return;
      }
      alert(`¡Venta finalizada! Orden #${orderData.folio}`);
      clearPendingCheckout();
      checkoutIntentRef.current = null;
      setCart([]);
      setAdjustmentAuthorizationId(null);
      setCourtesyReason('');
      setPaymentOpen(false);
      setPaymentMethod(null);
      setSelectedDriverId('');
      setAvailableDrivers([]);
      clearCustomer();
      setCheckoutState('idle');
    } catch (err) {
      if (err instanceof ApiError && err.status < 500) {
        clearPendingCheckout();
        checkoutIntentRef.current = null;
      }
      setCheckoutState('error');
      if (err instanceof ApiError) {
        alert(orderErrorMessage(err.code, err.message));
      } else {
        alert('Error de conexión.');
      }
    }
  };

  const totalCents = orderQuote?.total_cents ?? 0;
  const subtotalCents = orderQuote?.subtotal_cents ?? 0;
  const effectiveCourtesyCents = orderQuote?.adjustment_cents ?? 0;

  const handleApplyCourtesy = async () => {
    if (!supervisorPin || supervisorPin.trim().length < 4) {
      setPinError('Ingresa el PIN o código del supervisor o administrador.');
      return;
    }
    setPinError('');
    try {
      const authorization = await fetchApi<{
        authorization_id: string;
        quote: OrderQuote;
      }>('/orders/adjustments/authorize', {
        method: 'POST',
        body: JSON.stringify({
          supervisor_pin: supervisorPin.trim(),
          branch_id: branchId,
          lines: buildOrderLines(cart),
          adjustment: {
            type: tempCourtesyType,
            value: tempCourtesyType === 'courtesy' ? '100' : tempCourtesyValue,
            reason: tempReason.trim() || 'Ajuste autorizado',
          },
        }),
      });
      setAdjustmentAuthorizationId(authorization.authorization_id);
      setOrderQuote(authorization.quote);
      setQuoteState('ready');
      setCourtesyReason(authorization.quote.adjustment_reason || tempReason);
      setIsCourtesyModalOpen(false);
      setSupervisorPin('');
    } catch (authErr) {
      setPinError(
        authErr instanceof ApiError
          ? authErr.message
          : 'No fue posible autorizar el ajuste con el backend.',
      );
    }
  };

  const handleClearCourtesy = () => {
    setAdjustmentAuthorizationId(null);
    setCourtesyReason('');
    setIsCourtesyModalOpen(false);
    setSupervisorPin('');
    setPinError('');
  };

  const activeAddresses = (selectedCustomer?.addresses || []).filter((a) => a.status === 'active');
  const selectedDriver = availableDrivers.find((driver) => driver.id === selectedDriverId);
  const canCheckout = Boolean(
    editingOrder ||
      orderType !== 'delivery' ||
      (selectedCustomer && selectedAddressId),
  );

  return (
    <div className="pos-sale-screen">
      <header className="pos-sale-header">
        <div className="pos-sale-brand">
          <span className="pos-sale-mark">R</span>
          <div>
            <strong>RestaurantOS POS — <span style={{ color: '#10b981' }}>{session?.user?.display_name || ''}</span></strong>
            <small>Venta rápida</small>
          </div>
        </div>
        <label className="pos-sale-search">
          <Search size={19} />
          <input type="search" placeholder="Buscar producto…" value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} />
        </label>
        <div className="pos-sale-branch">
          <span>📍 {session?.active_branch?.name || 'Sucursal activa'}</span>
          <button
            type="button"
            className="pos-assisted-trigger"
            onClick={() => setAssistedCaptureOpen(true)}
            aria-label="Abrir Pedido asistido"
            title="Pedido asistido"
          >
            <UserRound size={20} aria-hidden="true" />
          </button>
        </div>
      </header>

      <div className="pos-sale-workspace">
        <main className="pos-sale-catalog">
          {editingOrder && <div className="pos-sale-edit-banner">Editando pedido <strong>#{editingOrder.folio}</strong> · Guardar no confirma el pago.</div>}
          {editLoadError && <div role="alert" className="pos-sale-feedback error">{editLoadError}</div>}
          <nav className="pos-sale-menu" aria-label="Grupos del menú">
            {CATALOG_MENU_GROUPS.map((group) => {
              const isActive = activeMenuGroup === group.id;
              return (
                <button key={group.id} type="button" className={isActive ? 'active' : ''} aria-pressed={isActive} onClick={() => changeActiveMenuGroup(group.id)}>
                  {getCatalogGroupIcon(group.id)}
                  <span>{group.label}</span>
                </button>
              );
            })}
          </nav>

          {loading ? <section className="pos-sale-products" aria-label="Estado del catálogo"><div role="status" className="pos-sale-feedback">Cargando menú...</div></section>
            : projectionState === 'error' ? <section className="pos-sale-products" aria-label="Estado del catálogo"><div role="alert" className="pos-sale-feedback error">{catalogError}<button type="button" className="pos-sale-retry-control" onClick={() => setCatalogRetryNonce((current) => current + 1)}>Reintentar</button></div></section>
            : <>
          {catalogStage === 'categories' && <section className="pos-sale-category-panel" aria-label={`Categorías de ${CATALOG_MENU_GROUPS.find((group) => group.id === activeMenuGroup)?.label || 'TODO'}`}>
            <div className="pos-sale-category-heading">
              <span>Categorías</span>
              <strong>{categoryChoices.length} disponibles</strong>
            </div>
            {categoryChoices.length === 0 ? (
              <div role="status" className="pos-sale-category-empty">
                No hay categorías disponibles en este grupo.
              </div>
            ) : (
              <div className="pos-sale-category-grid">
                {categoryChoices.map((cat) => {
                  const isActive = activeCategory === cat.name;
                  return (
                    <div key={cat.id || cat.name} className={`pos-sale-category-card${isActive ? ' active' : ''}`}>
                      <button type="button" className="pos-sale-category-select" aria-pressed={isActive} onClick={() => changeActiveCategory(cat)}>
                        {getProductIcon(cat.name, 42)}
                        <span>{cat.name}</span>
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
          </section>}

          {catalogStage !== 'categories' && catalogStage !== 'modifiers' && <section className="pos-sale-products" aria-label="Productos disponibles">
            <div className="pos-sale-progressive-context">
              {activeMenuGroup === 'favorites' ? <span>Productos favoritos</span> : <>
                <span>{activeCategoryDetails?.name}</span>
                <button type="button" onClick={() => changeActiveMenuGroup(activeMenuGroup)}>Cambiar categoría</button>
                {activeSelectionValue && <button type="button" onClick={() => changeCategoryOption('')}>Cambiar {activeSelectionGroup?.name}</button>}
              </>}
            </div>
            <div className="pos-sale-products-heading">
              <div><span>{categoryOptionState === 'selection-required' && activeSelectionGroup ? <>Selecciona {activeSelectionGroup.name}</> : activeSelectionValue ? `${activeSelectionGroup?.name}: ${activeSelectionValue.name}` : 'Selecciona un producto'}</span><strong>{categoryOptionState === 'selection-required' ? activeSelectionGroup?.values.length || 0 : filteredProducts.length} disponibles</strong></div>
              {activeSelectionValue && <button type="button" className="pos-sale-selection-control" aria-label={`Cambiar ${activeSelectionGroup?.name || 'opción'}`} onClick={() => changeCategoryOption('')}>Cambiar</button>}
            </div>
            <div className="pos-sale-products-grid">
              {categoryOptionState === 'selection-required' && activeSelectionGroup ? (
                projectionState === 'selection-empty' ? (
                  <div role="status" className="pos-sale-feedback">No hay opciones disponibles para {activeSelectionGroup.name}. <button type="button" className="pos-sale-retry-control" onClick={() => setCatalogRetryNonce((current) => current + 1)}>Reintentar</button></div>
                ) : activeSelectionGroup.values.map((value) => (
                  <button type="button" key={value.id} className="pos-sale-product-card" aria-label={`Seleccionar ${value.name}`} aria-pressed={false} onClick={() => changeCategoryOption(value.id)}>
                    <div className="pos-sale-product-visual">{getProductIcon(activeCategory, 48)}</div><span>{value.name}</span>
                  </button>
                ))
              ) : filteredProducts.length === 0 ? (
                <div className="pos-sale-feedback">{activeMenuGroup === 'favorites' ? 'Aún no hay productos favoritos. Usa la estrella de un producto para agregarlo aquí.' : 'No hay productos.'}</div>
              ) : (
                filteredProducts.map((product) => {
                  const presentation = productCardPresentation(product.image_url);
                  const isFavorite = favoriteProductIds.includes(product.id);
                  return (
                    <div
                      key={product.id}
                      className={`pos-sale-product-card pos-sale-product-card-shell pos-sale-product-card--${presentation === 'image' ? 'with-image' : 'without-image'}`}
                    >
                      <button type="button" className="pos-sale-product-card-select" onClick={() => void selectProduct(product)}>
                        <div className={`pos-sale-product-visual pos-sale-product-visual--${presentation === 'image' ? 'with-image' : 'fallback'}`}>
                          {presentation === 'image' ? <img src={product.image_url} alt={product.name} /> : getProductIcon(product.category, 32)}
                        </div>
                        <span>{product.name}</span>
                        <strong>{formatMxnCents(product.price_cents)}</strong>
                      </button>
                      <button type="button" className="pos-sale-product-favorite" aria-label={`${isFavorite ? 'Quitar' : 'Agregar'} ${product.name} ${isFavorite ? 'de' : 'a'} favoritos`} aria-pressed={isFavorite} onClick={() => toggleFavoriteProduct(product.id)}>
                        <Star size={18} strokeWidth={1.8} fill={isFavorite ? 'currentColor' : 'none'} aria-hidden="true" />
                      </button>
                    </div>
                  );
                })
              )}
            </div>
          </section>}

          {catalogStage === 'modifiers' && <section className="pos-sale-complements is-open" aria-label="Complementos del producto">
            <div className="pos-sale-complements-header">
              <div><span>Complementos</span><strong>{modifierProduct ? modifierProduct.name : 'Personaliza tu producto'}</strong></div>
              {modifierProduct && <button type="button" onClick={resetModifierModal} aria-label="Cerrar complementos"><X size={17} /></button>}
            </div>
            {!modifierProduct ? (
              <p className="pos-sale-complements-empty">Selecciona un producto con opciones para ver aquí sus complementos e indicaciones.</p>
            ) : modifierLoadError ? (
              <div role="alert" className="pos-sale-complements-error"><span>{modifierLoadError}</span><button type="button" onClick={() => void selectProduct(modifierProduct)}>Reintentar</button></div>
            ) : (
              <div className="pos-sale-complement-content">
                <div className="pos-sale-progressive-context">
                  <span>{activeMenuGroup === 'favorites' ? 'FAVORITOS' : `${activeCategoryDetails?.name || ''}${activeSelectionValue ? ` · ${activeSelectionValue.name}` : ''}`}</span>
                  <button type="button" onClick={resetModifierModal}>Volver a productos</button>
                </div>
                <div className="pos-sale-modifier-tabs" role="tablist" aria-label="Grupos de complementos">
                  {modifierGroups.map((group) => (
                    <button
                      key={group.id}
                      type="button"
                      role="tab"
                      aria-selected={activeModifierGroup?.id === group.id}
                      className={activeModifierGroup?.id === group.id ? 'active' : ''}
                      onClick={() => setActiveModifierGroupId(group.id)}
                    >
                      <strong>{group.name}</strong>
                      <small>{group.minimum_selections > 0 ? `Obligatorio · ${group.minimum_selections}-${group.maximum_selections}` : `Opcional · hasta ${group.maximum_selections}`}</small>
                    </button>
                  ))}
                </div>
                {activeModifierGroup && <section className="pos-sale-complement-group-panel" role="tabpanel">
                  <div className="pos-sale-complement-group-title">
                    <strong>{activeModifierGroup.name}</strong>
                    <small>{activeModifierGroup.minimum_selections > 0 ? `Obligatorio · mínimo ${activeModifierGroup.minimum_selections}, máximo ${activeModifierGroup.maximum_selections}` : `Opcional · máximo ${activeModifierGroup.maximum_selections}`}</small>
                  </div>
                  <div className="pos-sale-complement-options">
                    {activeModifierGroup.options.map((option) => {
                          const checked = (modifierSelections[activeModifierGroup.id] || []).includes(option.id);
                          return (
                            <div key={option.id} className="pos-sale-complement-option">
                              <button type="button" className={checked ? 'active' : ''} aria-pressed={checked} onClick={() => toggleModifier(activeModifierGroup, option.id)}>
                                {checked && <Check size={15} />}
                                {option.name}{option.price_delta_cents > 0 ? ' +' + formatMxnCents(option.price_delta_cents) : ''}
                              </button>
                              {checked && option.effect_type === 'instruction' && (
                                <input value={modifierText[option.id] || ''} onChange={(event) => setModifierText({ ...modifierText, [option.id]: event.target.value })} placeholder="Instrucción para cocina" maxLength={240} />
                              )}
                            </div>
                          );
                    })}
                  </div>
                </section>}
                <div className="pos-sale-complement-action">
                  {modifierError && <span>{modifierError}</span>}
                  <button type="button" onClick={confirmModifiers} disabled={!modifierMinimumsMet}>Agregar al pedido</button>
                </div>
              </div>
            )}
          </section>}
            </>}
        </main>

        <aside className="pos-sale-cart">
          <div className="pos-sale-cart-heading">
            <div><span>Cuenta actual</span><strong>Detalle del pedido</strong></div>
            <div className="pos-sale-cart-actions">
              <button type="button" onClick={() => setPaymentOpen(true)}><Users size={17} /><span>{selectedCustomer?.name || 'Cliente'}</span></button>
              <button type="button" onClick={() => void openIngredientExtras()} disabled={cart.length === 0 || extrasLoading}><Plus size={17} /><span>Adicionales</span></button>
            </div>
          </div>

          <div className="pos-sale-order-types">
            {ORDER_TYPES.map((type) => (
              <button key={type.value} type="button" className={orderType === type.value ? 'active' : ''} onClick={() => setOrderType(type.value)}>{type.label}</button>
            ))}
          </div>

          {selectedCustomer && upsellRecs.length > 0 && (
            <div style={{ margin: '8px 12px 0', padding: '10px 12px', background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: '12px', fontSize: '0.82rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#15803d', fontWeight: 700, marginBottom: '6px' }}>
                <Sparkles size={15} color="#16a34a" />
                <span>Sugerencia IA para {selectedCustomer.name.split(' ')[0]}:</span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
                {upsellRecs.slice(0, 2).map((rec) => {
                  const matchedProd = products.find((p) => p.id === rec.product_id);
                  return (
                    <div key={rec.product_id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: '#ffffff', padding: '6px 10px', borderRadius: '8px', border: '1px solid #dcfce7', boxShadow: '0 1px 2px rgba(0,0,0,0.03)' }}>
                      <div>
                        <strong style={{ color: '#15803d', display: 'block', fontSize: '0.85rem' }}>{rec.product_name}</strong>
                        <span style={{ color: '#64748b', fontSize: '0.75rem' }}>{rec.reason} · +{formatMxnCents(rec.price_cents)}</span>
                      </div>
                      {matchedProd && (
                        <button
                          type="button"
                          onClick={() => addToCart(matchedProd)}
                          style={{ background: '#16a34a', color: '#ffffff', border: 'none', borderRadius: '6px', padding: '4px 10px', fontSize: '0.78rem', fontWeight: 700, cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: '3px' }}
                        >
                          <Plus size={13} />
                          Agregar
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          <div className="pos-sale-cart-items">
            {cart.length === 0 ? (
              <div className="pos-sale-empty-cart">
                <span><ShoppingBag size={32} /></span>
                <strong>La cuenta está vacía</strong>
                <p>Toca un producto para agregarlo</p>
              </div>
            ) : (
              cart.map((item, index) => (
                <div key={item.lineId} className="pos-sale-cart-item">
                  <div className="pos-sale-cart-icon">{item.image_url ? <img src={item.image_url} alt={item.name} /> : getProductIcon(item.category, 22)}</div>
                  <div className="pos-sale-cart-copy">
                    <strong>{item.name}</strong>
                    <span>{formatMxnCents(item.price_cents)}</span>
                    {item.commentPresets.map((comment) => <small key={comment.id}>Comentario: {comment.text}</small>)}
                    {item.modifiers.map((modifier) => <small key={modifier.option_id}>+ {modifier.text || modifier.option_name}</small>)}
                    {item.ingredientExtras.map((extra) => (
                      <small key={extra.extra_id}>
                        + {extra.name} × {extra.portions}
                        <button type="button" aria-label={`Quitar ${extra.name}`} onClick={() => removeIngredientExtra(item.lineId, extra.extra_id)}><X size={12} /></button>
                      </small>
                    ))}
                  </div>
                  <div className="pos-sale-cart-controls">
                    <strong>{orderQuote?.lines[index] ? formatMxnCents(orderQuote.lines[index].line_total_cents) : '—'}</strong>
                    <div>
                      <button type="button" onClick={() => updateQuantity(item.lineId, -1)} aria-label="Restar producto"><Minus size={14} /></button>
                      <span>{item.quantity}</span>
                      <button type="button" onClick={() => updateQuantity(item.lineId, 1)} aria-label="Sumar producto"><Plus size={14} /></button>
                      <button type="button" className="remove" onClick={() => removeCartLine(item.lineId)} aria-label={`Eliminar ${item.name} del pedido`}><Trash2 size={14} /></button>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>

          <div className="pos-sale-summary">
            <div><span>Subtotal</span><span>{orderQuote ? formatMxnCents(subtotalCents) : '—'}</span></div>
            {effectiveCourtesyCents > 0 && (
              <div style={{ color: '#059669', fontWeight: 600 }}>
                <span>Cortesía / Descuento ({courtesyReason})</span>
                <span>-{formatMxnCents(effectiveCourtesyCents)}</span>
              </div>
            )}
            <div><span>Impuesto</span><span>{orderQuote?.tax_cents == null ? 'No determinado' : formatMxnCents(orderQuote.tax_cents)}</span></div>
            <div className="total"><strong>Total</strong><strong>{orderQuote ? formatMxnCents(totalCents) : '—'}</strong></div>
            {quoteState === 'loading' && <div><span>Calculando total en servidor…</span></div>}
            {quoteState === 'error' && <div role="alert"><span>{quoteError}</span></div>}
          </div>

          <div style={{ padding: '0 16px 8px' }}>
            <Button
              variant="secondary"
              size="sm"
              style={{ width: '100%', fontSize: '0.82rem', padding: '8px' }}
              disabled={cart.length === 0 || quoteState !== 'ready'}
              onClick={() => setIsCourtesyModalOpen(true)}
            >
              {effectiveCourtesyCents > 0 ? '✓ Modificar Cortesía / Ajuste' : '🏷️ Aplicar Cortesía / Descuento'}
            </Button>
          </div>

          <button
            type="button"
            className="pos-sale-pay"
            onClick={() => {
              setPaymentMethod(null);
              setPaymentOpen(true);
            }}
            disabled={cart.length === 0 || quoteState !== 'ready'}
          >
            {editingOrder
              ? 'Guardar cambios'
              : orderType === 'dine-in'
                ? `Pagar ${cart.length > 0 ? formatMxnCents(totalCents) : ''}`
                : `Guardar pedido pendiente ${cart.length > 0 ? formatMxnCents(totalCents) : ''}`}
          </button>
        </aside>
      </div>
      <Modal isOpen={assistedCaptureOpen} onClose={closeAssistedCapture} title="Pedido asistido" size="lg">
        <div className="pos-assisted-dialog">
          <div className="pos-assisted-intro">
            <span><Sparkles size={22} aria-hidden="true" /></span>
            <div>
              <strong>Cuéntame el pedido como te lo dijeron</strong>
              <p>Te preguntaré cualquier dato obligatorio que falte antes de agregarlo.</p>
            </div>
          </div>

          <label className="pos-assisted-composer" htmlFor="assisted-order-text">
            <span>Solicitud del cliente</span>
            <textarea
              id="assisted-order-text"
              value={assistedText}
              onChange={(event) => {
                stopAssistedDictation();
                assistedTextRef.current = event.target.value;
                setAssistedText(event.target.value);
                setAssistedDraft(null);
                setAssistedError('');
              }}
              rows={4}
              maxLength={1000}
              autoFocus
              placeholder="Ej. Pedido para Miguel González con teléfono 6672013019: un baguette BBQ sin cebolla para recoger."
            />
            <small>{assistedText.length}/1000</small>
          </label>

          <div className="pos-assisted-compose-actions">
            {typeof window !== 'undefined' && ('SpeechRecognition' in window || 'webkitSpeechRecognition' in window) ? (
              <button type="button" className={assistedDictating ? 'is-recording' : ''} aria-pressed={assistedDictating} onClick={toggleAssistedDictation} title="El navegador solicitará permiso para usar el micrófono">
                <Mic size={18} aria-hidden="true" />{assistedDictating ? 'Detener' : 'Dictar'}
              </button>
            ) : <small>Este navegador no ofrece dictado · puedes escribir normalmente.</small>}
            <button type="button" className="primary" onClick={() => void previewAssistedCapture()} disabled={!assistedText.trim() || assistedLoading}>
              {assistedLoading ? <span className="pos-assisted-loader" aria-hidden="true" /> : <Send size={18} aria-hidden="true" />}
              {assistedLoading ? 'Interpretando…' : 'Interpretar pedido'}
            </button>
          </div>

          {assistedError && <div className="pos-assisted-error" role="alert"><strong>No pude interpretar el pedido</strong><span>{assistedError}</span></div>}

          {assistedDraft && (
            <section className="pos-assisted-conversation" aria-live="polite">
              <div className="pos-assisted-bubble user"><span>Tú</span><p>{assistedText}</p></div>
              <div className="pos-assisted-bubble assistant">
                <span>Asistente</span>
                <strong>{assistedDraft.lines.map((line) => `${line.quantity} × ${line.product_name}`).join(' · ')}</strong>
                <p>
                  {[assistedDraft.customer_name || 'Cliente por confirmar', assistedDraft.phone || 'Sin teléfono', assistedDraft.order_type === 'takeout' ? 'Para llevar' : assistedDraft.order_type === 'delivery' ? 'A domicilio' : 'Modalidad sin cambio'].join(' · ')}
                </p>
              </div>

              {assistedDraft.questions.map((question) => {
                const selected = selectedForQuestion(assistedDraft, question);
                return (
                  <fieldset className="pos-assisted-question" key={`${question.line_index}-${question.group_id}`}>
                    <legend>{question.prompt}</legend>
                    <small>Selecciona {question.minimum_selections === question.maximum_selections ? question.minimum_selections : `${question.minimum_selections} a ${question.maximum_selections}`}</small>
                    <div>
                      {question.options.map((option) => {
                        const active = selected.some((item) => item.option_id === option.id);
                        return (
                          <button
                            type="button"
                            key={option.id}
                            className={active ? 'active' : ''}
                            aria-pressed={active}
                            onClick={() => setAssistedDraft((current) => current ? toggleAssistedOption(current, question, option) : current)}
                          >
                            {active && <Check size={15} aria-hidden="true" />}{option.name}
                            {option.price_delta_cents > 0 && <small>+{formatMxnCents(option.price_delta_cents)}</small>}
                          </button>
                        );
                      })}
                    </div>
                  </fieldset>
                );
              })}

              <div className={isAssistedDraftComplete(assistedDraft) ? 'pos-assisted-status ready' : 'pos-assisted-status pending'}>
                {isAssistedDraftComplete(assistedDraft) ? <Check size={18} aria-hidden="true" /> : <Sparkles size={18} aria-hidden="true" />}
                <span>{isAssistedDraftComplete(assistedDraft) ? 'Pedido completo y listo para agregar' : 'Faltan respuestas obligatorias'}</span>
              </div>
            </section>
          )}

          <div className="pos-assisted-footer">
            <button type="button" className="secondary" onClick={closeAssistedCapture}>Cancelar</button>
            <button type="button" className="primary" onClick={applyAssistedCapture} disabled={!isAssistedDraftComplete(assistedDraft) || assistedLoading}>Agregar al pedido</button>
          </div>
        </div>
      </Modal>
      <Modal
        isOpen={isCourtesyModalOpen}
        onClose={() => setIsCourtesyModalOpen(false)}
        title="Autorización de Cortesía o Descuento"
      >
        <div style={{ display: 'grid', gap: 14 }}>
          <p style={{ margin: 0, color: '#64748b', fontSize: '0.85rem' }}>
            El backend calculará el ajuste y emitirá una autorización de un solo uso vinculada a este carrito.
          </p>
          {pinError && <div role="alert" style={{ color: '#b91c1c', fontSize: '0.85rem' }}>{pinError}</div>}
          <div>
            <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: 6 }}>
              Tipo de aplicación
            </label>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
              {([
                ['percent', 'Porcentaje (%)'],
                ['fixed', 'Monto fijo ($)'],
                ['courtesy', 'Cortesía 100%'],
              ] as const).map(([kind, label]) => (
                <button
                  key={kind}
                  type="button"
                  style={{
                    padding: '8px',
                    borderRadius: 8,
                    border: `1px solid ${tempCourtesyType === kind ? '#10b981' : '#cbd5e1'}`,
                    background: tempCourtesyType === kind ? '#ecfdf5' : '#fff',
                    fontWeight: tempCourtesyType === kind ? 700 : 500,
                    cursor: 'pointer',
                  }}
                  onClick={() => {
                    setTempCourtesyType(kind);
                    if (kind === 'courtesy') setTempReason('Cortesía 100% autorizada');
                  }}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          {tempCourtesyType !== 'courtesy' && (
            <label>
              {tempCourtesyType === 'percent' ? 'Porcentaje de ajuste (%)' : 'Monto de ajuste ($ MXN)'}
              <input
                type="number"
                min="0"
                max={tempCourtesyType === 'percent' ? '100' : undefined}
                step="any"
                value={tempCourtesyValue}
                onChange={(event) => setTempCourtesyValue(event.target.value)}
                style={{ width: '100%', padding: '10px 12px', border: '1px solid #cbd5e1', borderRadius: 8 }}
              />
            </label>
          )}
          <label>
            Motivo / razón *
            <select
              value={tempReason}
              onChange={(event) => setTempReason(event.target.value)}
              style={{ width: '100%', padding: '10px 12px', border: '1px solid #cbd5e1', borderRadius: 8 }}
            >
              <option value="Cortesía de la casa">Cortesía de la casa</option>
              <option value="Cortesía por demora / error">Cortesía por demora / inconformidad</option>
              <option value="Descuento de empleado">Descuento de empleado (personal)</option>
              <option value="Promoción comercial">Promoción comercial / convenio</option>
              <option value="Autorización de Gerencia">Autorización de Gerencia</option>
              <option value="Cortesía 100% autorizada">Cortesía 100% autorizada</option>
            </select>
          </label>
          <label>
            PIN o código de supervisor *
            <input
              type="password"
              maxLength={64}
              placeholder="••••"
              value={supervisorPin}
              onChange={(event) => setSupervisorPin(event.target.value)}
              style={{ width: '100%', padding: '10px 12px', border: '1px solid #cbd5e1', borderRadius: 8 }}
            />
          </label>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, marginTop: 8 }}>
            {effectiveCourtesyCents > 0 ? (
              <Button variant="secondary" onClick={handleClearCourtesy} style={{ color: '#dc2626' }}>
                Quitar cortesía
              </Button>
            ) : <span />}
            <div style={{ display: 'flex', gap: 8 }}>
              <Button variant="secondary" onClick={() => setIsCourtesyModalOpen(false)}>Cancelar</Button>
              <Button variant="primary" onClick={() => void handleApplyCourtesy()}>Autorizar y aplicar</Button>
            </div>
          </div>
        </div>
      </Modal>
      <Modal isOpen={extraModalOpen} onClose={closeExtraModal} title="Ingredientes adicionales">
        <div style={{ display: 'grid', gap: 14, maxHeight: '65vh', overflowY: 'auto' }}>
          <p style={{ margin: 0, color: '#64748b' }}>Los adicionales son corporativos y se aplican a una línea específica del pedido. El backend recalcula precio, cantidad e inventario al confirmar.</p>
          {cart.length > 1 ? <label>Línea destino<select value={extraTargetLineId} onChange={(event) => selectExtraTarget(event.target.value)} style={{ width: '100%', padding: 10, border: '1px solid #cbd5e1', borderRadius: 8 }}><option value="">Selecciona una línea</option>{cart.map((item) => <option key={item.lineId} value={item.lineId}>{item.name} · {item.quantity} pieza(s)</option>)}</select></label> : <p style={{ margin: 0 }}><strong>Línea destino:</strong> {cart[0]?.name}</p>}
          {extraError && <div role="alert" style={{ color: '#b91c1c' }}>{extraError}</div>}
          {extrasLoading ? <p>Cargando ingredientes adicionales…</p> : availableExtras.length === 0 ? <p style={{ color: '#64748b' }}>No hay ingredientes adicionales corporativos disponibles.</p> : <div style={{ display: 'grid', gap: 8 }}>{availableExtras.map((extra) => { const extraId = extra.extra_id || extra.id || ''; const portions = extraSelections[extraId] || 0; return <div key={extraId} style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center', padding: 10, border: `1px solid ${portions > 0 ? '#10b981' : '#e2e8f0'}`, borderRadius: 8 }}><div><strong>{extra.name}</strong><div style={{ color: '#64748b', fontSize: 13 }}>{extra.portion_quantity} {extra.unit_code || 'unidad'} · {formatMxnCents(extra.sale_price_cents)} · {extra.station}</div></div><div style={{ display: 'flex', alignItems: 'center', gap: 8 }}><button type="button" aria-label={`Quitar ${extra.name}`} onClick={() => updateExtraSelection(extra, portions - 1)} disabled={portions === 0} style={{ width: 32, height: 32 }}>−</button><span aria-label={`Porciones de ${extra.name}`}>{portions}</span><button type="button" aria-label={`Agregar ${extra.name}`} onClick={() => updateExtraSelection(extra, portions + 1)} style={{ width: 32, height: 32 }}>+</button></div></div>; })}</div>}
          <button type="button" onClick={applyIngredientExtras} disabled={extrasLoading || availableExtras.length === 0} style={{ padding: 14, border: 0, borderRadius: 8, background: '#10b981', color: '#fff', fontWeight: 700 }}>Aplicar a la línea</button>
        </div>
      </Modal>
      {/* Payment Modal */}
      <Modal isOpen={isPaymentOpen} onClose={() => setPaymentOpen(false)} title="Cobrar pedido">
        {/* Cliente seleccionado o búsqueda */}
        {selectedCustomer ? (
          <div style={{ marginBottom: 16, padding: 12, borderRadius: 8, border: '1px solid #e2e8f0', background: '#f8fafc' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <strong>{selectedCustomer.name}</strong>
              <button
                onClick={clearCustomer}
                aria-label="Quitar cliente seleccionado"
                style={{ border: 'none', background: 'transparent', cursor: 'pointer', color: '#64748b' }}
              >
                <X size={16} />
              </button>
            </div>
            {selectedCustomer.phones && selectedCustomer.phones.length > 0 && (
              <div style={{ fontSize: '0.8rem', color: '#64748b' }}>
                {selectedCustomer.phones[0].captured_number || selectedCustomer.phones[0].normalized_number}
              </div>
            )}
            {selectedCustomer.legacy_address_reference && (
              <div style={{ marginTop: 8, padding: 8, borderRadius: 6, border: '1px dashed #cbd5e1', fontSize: '0.8rem', color: '#64748b' }}>
                <strong>Domicilio heredado por confirmar:</strong> {selectedCustomer.legacy_address_reference}
                <div style={{ marginTop: 4 }}>
                  No se usará para entregar hasta que captures y guardes un domicilio estructurado.
                </div>
              </div>
            )}
          </div>
        ) : (
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: 8 }}>
              Teléfono del cliente
            </label>
            <input
              type="tel"
              inputMode="tel"
              autoComplete="tel"
              value={customerPhone}
              onChange={(e) => {
                setCustomerPhone(e.target.value);
                setNewCustomerName('');
                setNewCustomerEmail('');
                setCreateCustomerError('');
              }}
              placeholder="10 dígitos, por ejemplo 6691234567"
              style={{ width: '100%', padding: '12px 16px', borderRadius: 12, border: '1px solid var(--glass-border)' }}
            />
            {!validMexicanPhone(customerPhone) && customerPhone.trim() && (
              <div style={{ color: '#64748b', fontSize: '0.8rem', marginTop: 8 }}>
                Completa un teléfono mexicano de 10 dígitos.
              </div>
            )}
            {customerLookupStatus === 'searching' && (
              <div style={{ color: '#64748b', fontSize: '0.85rem', marginTop: 8 }}>
                Buscando el teléfono…
              </div>
            )}
            {customerSearchError && <div style={{ color: '#dc2626', fontSize: '0.85rem', marginTop: 8 }}>{customerSearchError}</div>}
            {customerLookupStatus === 'found' && searchResults.length > 0 && (
              <section
                aria-label="Clientes encontrados por teléfono"
                style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 6 }}
              >
                {searchResults.map((c) => {
                  const phone = c.phones?.[0]?.captured_number || c.phones?.[0]?.normalized_number || '';
                  const addrCount = (c.addresses || []).filter((a) => a.status === 'active').length;
                  return (
                    <button
                      key={c.id}
                      type="button"
                      onClick={() => selectCustomer(c)}
                      style={{ textAlign: 'left', padding: '10px 12px', border: '1px solid #cbd5e1', borderRadius: 8, background: '#fff', cursor: 'pointer' }}
                    >
                      <div style={{ fontWeight: 600 }}>{c.name}</div>
                      <div style={{ fontSize: '0.75rem', color: '#64748b' }}>
                        {phone && <span>{phone} · </span>}
                        {addrCount} domicilio(s)
                      </div>
                    </button>
                  );
                })}
              </section>
            )}
            {customerLookupStatus === 'not-found' && (
              <div style={{ marginTop: 12, padding: 12, borderRadius: 8, border: '1px solid #d1fae5', background: '#f0fdf4' }}>
                <strong style={{ fontSize: '0.9rem', color: '#166534' }}>
                  Teléfono no registrado
                </strong>
                <p style={{ margin: '4px 0 10px', color: '#64748b', fontSize: '0.8rem' }}>
                  Captura el nombre para dar de alta al cliente sin perder esta venta.
                </p>
                <div style={{ display: 'grid', gap: 8 }}>
                  <input
                    type="text"
                    value={newCustomerName}
                    onChange={(e) => setNewCustomerName(e.target.value)}
                    placeholder="Nombre completo"
                    autoComplete="name"
                    style={{ width: '100%', padding: '10px 12px', borderRadius: 8, border: '1px solid #d1d5db', boxSizing: 'border-box' }}
                  />
                  <input
                    type="email"
                    value={newCustomerEmail}
                    onChange={(e) => setNewCustomerEmail(e.target.value)}
                    placeholder="Correo (opcional)"
                    autoComplete="email"
                    style={{ width: '100%', padding: '10px 12px', borderRadius: 8, border: '1px solid #d1d5db', boxSizing: 'border-box' }}
                  />
                  {createCustomerError && (
                    <div style={{ color: '#dc2626', fontSize: '0.8rem' }}>{createCustomerError}</div>
                  )}
                  <button
                    type="button"
                    onClick={() => void registerCustomer()}
                    disabled={creatingCustomer || !newCustomerName.trim()}
                    style={{ padding: '10px 12px', border: 0, borderRadius: 8, background: '#10b981', color: '#fff', fontWeight: 700, cursor: creatingCustomer || !newCustomerName.trim() ? 'not-allowed' : 'pointer', opacity: creatingCustomer || !newCustomerName.trim() ? 0.6 : 1 }}
                  >
                    {creatingCustomer ? 'Registrando…' : 'Registrar y seleccionar cliente'}
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Domicilios para delivery */}
        {orderType === 'delivery' && selectedCustomer && (
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: 8 }}>Domicilio de entrega</label>
            {activeAddresses.length === 0 ? (
              <p style={{ color: '#64748b', fontSize: '0.85rem' }}>Este cliente todavía no tiene domicilios confirmados.</p>
            ) : (
              <div style={{ display: 'grid', gap: 8 }}>
                {activeAddresses.map((a) => (
                  <button
                    key={a.id}
                    type="button"
                    onClick={() => setSelectedAddressId(a.id)}
                    style={{
                      padding: '10px 12px',
                      borderRadius: 8,
                      border: `1px solid ${selectedAddressId === a.id ? '#10b981' : '#d1d5db'}`,
                      background: selectedAddressId === a.id ? '#ecfdf5' : '#fff',
                      textAlign: 'left',
                      cursor: 'pointer',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                      <strong>{a.alias}</strong>
                      {a.is_default && <span style={{ color: '#047857', fontSize: '0.75rem' }}>Predeterminado</span>}
                    </div>
                    <div style={{ color: '#475569', fontSize: '0.82rem', marginTop: 2 }}>
                      {a.street} {a.exterior_number}
                      {a.interior_number ? ` Int. ${a.interior_number}` : ''}, {a.neighborhood}
                    </div>
                  </button>
                ))}
              </div>
            )}
            {!showAddressForm && (
              <button onClick={() => setShowAddressForm(true)} style={{ marginTop: 8, padding: '6px 12px', border: '1px solid #10b981', borderRadius: 6, background: '#fff', color: '#10b981', cursor: 'pointer', fontSize: '0.85rem' }}>
                + Agregar domicilio
              </button>
            )}
            {showAddressForm && (
              <CustomerAddressForm
                customerId={selectedCustomer.id}
                branchId={branchId}
                legacyAddressReference={selectedCustomer.legacy_address_reference || ''}
                onSaved={(addr) => {
                  setSelectedCustomer((prev) => prev ? { ...prev, addresses: [...(prev.addresses || []), addr] } : prev);
                  setSelectedAddressId(addr.id);
                  setShowAddressForm(false);
                }}
                onCancel={() => setShowAddressForm(false)}
              />
            )}
          </div>
        )}

        {orderType === 'delivery' && !editingOrder && (
          <section style={{ marginBottom: 16, padding: 12, border: '1px solid #d1fae5', borderRadius: 10, background: '#f7fefb' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
              <div>
                <strong style={{ display: 'block', fontSize: '.9rem' }}>Repartidor</strong>
                <span style={{ color: '#64748b', fontSize: '.78rem' }}>Opcional · sólo aparecen activos de esta sucursal</span>
              </div>
              <button
                type="button"
                onClick={() => void openDriverPicker()}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '8px 11px', border: '1px solid #10b981', borderRadius: 8, background: '#fff', color: '#047857', fontWeight: 700, cursor: 'pointer' }}
              >
                <Bike size={17} />
                {selectedDriverId ? 'Cambiar repartidor' : 'Asignar repartidor'}
              </button>
            </div>
            {selectedDriverId && (
              <div style={{ marginTop: 10, padding: 10, borderRadius: 8, background: '#ecfdf5', color: '#065f46' }}>
                <strong>{selectedDriver?.name || 'Repartidor asignado'}</strong>
                {selectedDriver && (
                  <div style={{ marginTop: 2, fontSize: '.78rem' }}>
                    {selectedDriver.motorcycle_plate}
                    {' · '}
                    {selectedDriver.phone}
                  </div>
                )}
              </div>
            )}
            {driverPickerOpen && (
              <div style={{ marginTop: 10, display: 'grid', gap: 7 }}>
                {driversLoading ? (
                  <span style={{ color: '#64748b', fontSize: '.82rem' }}>Cargando repartidores…</span>
                ) : driversError ? (
                  <div role="alert" style={{ color: '#b91c1c', fontSize: '.82rem' }}>
                    {driversError}{' '}
                    <button type="button" onClick={() => void openDriverPicker()}>Reintentar</button>
                  </div>
                ) : availableDrivers.length === 0 ? (
                  <span style={{ color: '#64748b', fontSize: '.82rem' }}>No hay repartidores activos en esta sucursal.</span>
                ) : (
                  availableDrivers.map((driver) => (
                    <button
                      key={driver.id}
                      type="button"
                      aria-pressed={selectedDriverId === driver.id}
                      onClick={() => {
                        setSelectedDriverId(driver.id);
                        setDriverPickerOpen(false);
                      }}
                      style={{ display: 'flex', justifyContent: 'space-between', gap: 12, padding: 10, border: `1px solid ${selectedDriverId === driver.id ? '#10b981' : '#d1d5db'}`, borderRadius: 8, background: selectedDriverId === driver.id ? '#ecfdf5' : '#fff', textAlign: 'left', cursor: 'pointer' }}
                    >
                      <strong>{driver.name}</strong>
                      <span style={{ color: '#64748b', fontSize: '.78rem' }}>{driver.motorcycle_plate} · {driver.phone}</span>
                    </button>
                  ))
                )}
              </div>
            )}
          </section>
        )}

        {/* Validación delivery */}
        {orderType === 'delivery' && !editingOrder && !canCheckout && (
          <div style={{ marginBottom: 12, color: '#b91c1c', fontSize: '0.85rem' }}>
            {!selectedCustomer ? 'Falta seleccionar cliente. ' : ''}
            {!selectedAddressId ? 'Falta seleccionar domicilio de entrega.' : ''}
          </div>
        )}

        <div style={{ marginBottom: 16 }}>
          <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-muted)', marginBottom: 8 }}>Nombre del cliente</label>
          <input
            type="text"
            value={ownerName}
            onChange={(e) => setOwnerName(e.target.value)}
            placeholder="Ej. Juan Pérez"
            style={{ width: '100%', padding: '12px 16px', borderRadius: '12px', border: '1px solid var(--glass-border)', fontSize: '1rem', outline: 'none' }}
          />
        </div>
        <section className="pos-payment-methods" aria-labelledby="payment-method-title">
          <div className="pos-payment-heading">
            <div><span>Paso final</span><strong id="payment-method-title">¿Cómo pagará el cliente?</strong></div>
            <strong>{orderQuote ? formatMxnCents(totalCents) : '—'}</strong>
          </div>
          <div className="pos-payment-grid">
            {PAYMENT_METHODS.map((method) => {
              const Icon = method.icon;
              const selected = paymentMethod === method.value;
              return (
                <button key={method.value} type="button" className={selected ? 'active' : ''} aria-pressed={selected} onClick={() => setPaymentMethod(method.value)}>
                  <span><Icon size={21} /></span>
                  <div><strong>{method.label}</strong><small>{method.description}</small></div>
                  {selected && <Check size={17} />}
                </button>
              );
            })}
          </div>
        </section>
        <button
          onClick={() => void processTransaction()}
          disabled={checkoutState === 'submitting' || !canCheckout || quoteState !== 'ready' || (!paymentMethod && !editingOrder)}
          className="pos-payment-confirm"
        >
          {checkoutState === 'submitting'
            ? 'Procesando…'
            : editingOrder
            ? 'Guardar cambios sin confirmar pago'
            : paymentMethod
              ? orderType === 'dine-in'
                ? `Confirmar cobro · ${formatMxnCents(totalCents)}`
                : `Guardar pendiente · ${formatMxnCents(totalCents)}`
              : 'Selecciona un método de pago'}
        </button>
      </Modal>
    </div>
  );
};

// ---------------------------------------------------------------------------
// CustomerAddressForm — crear domicilio desde el checkout
// ---------------------------------------------------------------------------

interface CustomerAddressFormProps {
  customerId: string;
  branchId: string;
  legacyAddressReference: string;
  onSaved: (addr: PosCustomerAddress) => void;
  onCancel: () => void;
}

function CustomerAddressForm({
  customerId,
  branchId,
  legacyAddressReference,
  onSaved,
  onCancel,
}: CustomerAddressFormProps) {
  const [form, setForm] = useState({
    alias: '',
    street: '',
    exterior_number: '',
    interior_number: '',
    neighborhood: '',
    postal_code: '',
    city: '',
    municipality: '',
    state: '',
    cross_streets: '',
    references: '',
    delivery_instructions: '',
    is_default: false,
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const set = (key: keyof typeof form, value: string | boolean) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const submit = async () => {
    const required = ['alias', 'street', 'exterior_number', 'neighborhood', 'postal_code', 'city', 'municipality', 'state'];
    if (required.some((f) => !String(form[f as keyof typeof form]).trim())) {
      setError('Completa todos los campos obligatorios.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      const result = await fetchApi<PosCustomerAddress>(
        `/customers/${encodeURIComponent(customerId)}/addresses`,
        { method: 'POST', body: JSON.stringify({ ...form, branch_id: branchId }) },
      );
      onSaved(result);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError('No se pudo guardar el domicilio.');
      }
    } finally {
      setSaving(false);
    }
  };

  const inputStyle: React.CSSProperties = {
    width: '100%',
    padding: '8px 12px',
    borderRadius: 6,
    border: '1px solid #d1d5db',
    fontSize: '0.9rem',
    boxSizing: 'border-box',
  };

  return (
    <div style={{ marginTop: 8, padding: 12, border: '1px solid #e2e8f0', borderRadius: 8, display: 'grid', gap: 8 }}>
      <input placeholder="Alias (ej. Casa)" value={form.alias} onChange={(e) => set('alias', e.target.value)} style={inputStyle} />
      <input placeholder="Calle" value={form.street} onChange={(e) => set('street', e.target.value)} style={inputStyle} />
      <div style={{ display: 'flex', gap: 8 }}>
        <input placeholder="No. exterior" value={form.exterior_number} onChange={(e) => set('exterior_number', e.target.value)} style={inputStyle} />
        <input placeholder="No. interior (opcional)" value={form.interior_number} onChange={(e) => set('interior_number', e.target.value)} style={inputStyle} />
      </div>
      <input placeholder="Colonia" value={form.neighborhood} onChange={(e) => set('neighborhood', e.target.value)} style={inputStyle} />
      <input placeholder="Código postal" value={form.postal_code} onChange={(e) => set('postal_code', e.target.value)} style={inputStyle} />
      <input placeholder="Ciudad" value={form.city} onChange={(e) => set('city', e.target.value)} style={inputStyle} />
      <input placeholder="Municipio" value={form.municipality} onChange={(e) => set('municipality', e.target.value)} style={inputStyle} />
      <input placeholder="Estado" value={form.state} onChange={(e) => set('state', e.target.value)} style={inputStyle} />
      <input placeholder="Entre calles (opcional)" value={form.cross_streets} onChange={(e) => set('cross_streets', e.target.value)} style={inputStyle} />
      <input placeholder="Referencias (opcional)" value={form.references} onChange={(e) => set('references', e.target.value)} style={inputStyle} />
      {legacyAddressReference && form.references !== legacyAddressReference && (
        <button
          type="button"
          onClick={() => set('references', legacyAddressReference)}
          style={{ justifySelf: 'start', padding: '6px 10px', border: '1px solid #10b981', borderRadius: 6, background: '#fff', color: '#047857', cursor: 'pointer' }}
        >
          Copiar domicilio heredado a Referencias
        </button>
      )}
      <textarea
        placeholder="Instrucciones de entrega (opcional)"
        value={form.delivery_instructions}
        onChange={(e) => set('delivery_instructions', e.target.value)}
        style={{ ...inputStyle, minHeight: 64, resize: 'vertical' }}
      />
      <label style={{ fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: 4 }}>
        <input type="checkbox" checked={form.is_default} onChange={(e) => set('is_default', e.target.checked)} />
        Marcar como predeterminado
      </label>
      {error && <div style={{ color: '#dc2626', fontSize: '0.85rem' }}>{error}</div>}
      <div style={{ display: 'flex', gap: 8 }}>
        <button onClick={() => void submit()} disabled={saving} style={{ flex: 1, padding: '8px', borderRadius: 6, border: 'none', background: '#10b981', color: '#fff', cursor: 'pointer', fontWeight: 600 }}>
          {saving ? 'Guardando…' : 'Guardar domicilio'}
        </button>
        <button onClick={onCancel} style={{ padding: '8px 16px', borderRadius: 6, border: '1px solid #d1d5db', background: '#fff', cursor: 'pointer' }}>
          Cancelar
        </button>
      </div>
    </div>
  );
}

export default PointOfSale;
