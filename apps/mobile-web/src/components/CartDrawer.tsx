import React, { useState, useMemo, useEffect } from 'react';
import { X, Plus, Minus, Trash2, Banknote, CreditCard, ArrowRightLeft, Send, ShoppingBag, MapPin, User, Phone, CheckCircle2, Utensils, Bike, Sparkles, Coffee, CupSoda, Sandwich, Salad, Wheat, Package, Tag, Navigation, Calendar, Clock, Copy, Check, Building2 } from 'lucide-react';
import { CartItem, CustomerOrderInfo, OrderType, PaymentMethod, BranchInfo, Product } from '../types';
import { formatMoney, fetchOrderUpsellRecommendations, getSavedCustomerProfile, saveCustomerProfile, validateBranchCoupon } from '../api';
import { getProductIconMeta, getProductImage } from '../imageMap';
import { requestBrowserCoordinates, reverseGeocode, formatGpsAddressNotes } from '../utils/geolocation';

const weekDayLetters = ['L', 'M', 'M', 'J', 'V', 'S', 'D'];
const weekDayFullNames = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'];

interface PickupDayOption {
  index: number;
  letter: string;
  name: string;
  dateNumber: number;
  monthName: string;
  isPast: boolean;
  isToday: boolean;
  isClosed?: boolean;
  disabled: boolean;
}

const getRecommendationIcon = (product: Product, size: number = 38) => {
  const category = (product.category_name || '').toLowerCase();
  const name = (product.name || '').toLowerCase();
  const station = (product.station || '').toLowerCase();
  const searchableText = `${category} ${name}`;
  const iconProps = { size, strokeWidth: 1.6 };

  if (searchableText.includes('café') || searchableText.includes('cafe') || searchableText.includes('matcha')) {
    return <Coffee {...iconProps} />;
  }
  if (
    searchableText.includes('jugo')
    || searchableText.includes('agua')
    || searchableText.includes('bebida')
    || searchableText.includes('smoothie')
    || searchableText.includes('extracto')
  ) {
    return <CupSoda {...iconProps} />;
  }
  if (searchableText.includes('ensalada')) return <Salad {...iconProps} />;
  if (searchableText.includes('pan') || searchableText.includes('focaccia') || searchableText.includes('cuernito')) {
    return <Wheat {...iconProps} />;
  }
  if (
    searchableText.includes('emparedado')
    || searchableText.includes('sando')
    || searchableText.includes('sandwich')
    || searchableText.includes('baguette')
  ) {
    return <Sandwich {...iconProps} />;
  }
  if (searchableText.includes('combo') || searchableText.includes('paquete')) return <Package {...iconProps} />;
  if (station === 'barra' || station === 'bar' || station === 'drinks') return <CupSoda {...iconProps} />;
  return <Utensils {...iconProps} />;
};

interface CartDrawerProps {
  items: CartItem[];
  allProducts?: Product[];
  orderType: OrderType;
  selectedBranch: BranchInfo | null;
  hasActiveShift?: boolean;
  onOpenBranchSelector?: () => void;
  onClose: () => void;
  onUpdateQuantity: (cartId: string, delta: number) => void;
  onRemoveItem: (cartId: string) => void;
  onQuickAddProduct?: (product: Product) => void;
  onSubmitOrder: (info: CustomerOrderInfo) => void;
  isSubmitting: boolean;
  submitError: string | null;
}

export const CartDrawer: React.FC<CartDrawerProps> = ({
  items,
  allProducts = [],
  orderType: initialOrderType,
  selectedBranch,
  hasActiveShift,
  onOpenBranchSelector,
  onClose,
  onUpdateQuantity,
  onRemoveItem,
  onQuickAddProduct,
  onSubmitOrder,
  isSubmitting,
  submitError,
}) => {
  const isBranchClosed = hasActiveShift === false || selectedBranch?.has_active_shift === false;
  const initialProfile = useMemo(() => getSavedCustomerProfile(), []);
  const [isReturningCustomer] = useState(
    Boolean(initialProfile?.name && initialProfile?.phone),
  );
  const [isEditingCustomer, setIsEditingCustomer] = useState(false);
  const [supportsNativeContacts, setSupportsNativeContacts] = useState(false);

  useEffect(() => {
    try {
      if (
        typeof window !== 'undefined' &&
        'contacts' in navigator &&
        'ContactsManager' in window &&
        typeof (navigator as any).contacts?.select === 'function'
      ) {
        setSupportsNativeContacts(true);
      }
    } catch {
      setSupportsNativeContacts(false);
    }
  }, []);

  const handle1TapAutofill = async () => {
    try {
      if ((navigator as any).contacts?.select) {
        const selected = await (navigator as any).contacts.select(['name', 'tel'], { multiple: false });
        if (selected && selected.length > 0) {
          const contact = selected[0];
          const rawName = Array.isArray(contact.name) ? contact.name[0] : contact.name;
          const rawTel = Array.isArray(contact.tel) ? contact.tel[0] : contact.tel;
          const pickedName = String(rawName || '').trim();
          const pickedPhone = String(rawTel || '').trim();
          if (pickedName) setName(pickedName);
          if (pickedPhone) setPhone(pickedPhone);
          if (pickedName && pickedPhone) {
            saveCustomerProfile({
              name: pickedName,
              phone: pickedPhone,
              street: street || undefined,
              number: number || undefined,
              neighborhood: neighborhood || undefined,
              address_notes: addressNotes || undefined,
            });
          }
        }
      }
    } catch (err) {
      // Ignored if dismissed or cancelled
    }
  };

  const [orderType, setOrderType] = useState<OrderType>(() => {
    if (initialOrderType === 'dine-in' && selectedBranch?.dine_in_enabled === false) {
      return 'takeaway';
    }
    return initialOrderType;
  });

  // Pickup scheduling state (L, M, M, J, V, S, D and time)
  const currentDayIndex = useMemo(() => {
    return (new Date().getDay() + 6) % 7;
  }, []);

  const scheduleByDay = useMemo(() => {
    const map = new Map<number, any>();
    if (selectedBranch?.service_schedule && Array.isArray(selectedBranch.service_schedule)) {
      for (const s of selectedBranch.service_schedule) {
        map.set(s.day_index, s);
      }
    }
    return map;
  }, [selectedBranch?.service_schedule]);

  const weekDayOptions = useMemo<PickupDayOption[]>(() => {
    const now = new Date();
    const todayIndex = (now.getDay() + 6) % 7;
    const monday = new Date(now);
    monday.setDate(now.getDate() - todayIndex);

    return weekDayLetters.map((letter, idx) => {
      const d = new Date(monday);
      d.setDate(monday.getDate() + idx);
      const isPast = idx < todayIndex;
      const isToday = idx === todayIndex;
      const monthName = d.toLocaleDateString('es-MX', { month: 'short' });
      const daySchedule = scheduleByDay.get(idx);
      const isClosed = daySchedule ? daySchedule.is_open === false : false;
      const disabled = isPast || isClosed;
      return {
        index: idx,
        letter,
        name: weekDayFullNames[idx],
        dateNumber: d.getDate(),
        monthName,
        isPast,
        isToday,
        isClosed,
        disabled,
      };
    });
  }, [scheduleByDay]);

  const [selectedDayIndex, setSelectedDayIndex] = useState<number>(() => {
    return (new Date().getDay() + 6) % 7;
  });

  // Automatically fall back to first non-disabled day if today or selected day is closed
  useEffect(() => {
    const currentOpt = weekDayOptions.find((d) => d.index === selectedDayIndex);
    if (currentOpt?.disabled) {
      const firstAvailable = weekDayOptions.find((d) => !d.disabled);
      if (firstAvailable) {
        setSelectedDayIndex(firstAvailable.index);
      }
    }
  }, [weekDayOptions, selectedDayIndex]);

  const selectedDay = useMemo(() => {
    return weekDayOptions.find((d) => d.index === selectedDayIndex) || weekDayOptions[currentDayIndex] || weekDayOptions[0];
  }, [weekDayOptions, selectedDayIndex, currentDayIndex]);

  const currentDaySchedule = useMemo(() => {
    return scheduleByDay.get(selectedDayIndex) || null;
  }, [scheduleByDay, selectedDayIndex]);

  const [pickupTime, setPickupTime] = useState<string>(() => {
    const d = new Date();
    d.setMinutes(d.getMinutes() + 30);
    const roundedMinutes = Math.ceil(d.getMinutes() / 5) * 5;
    d.setMinutes(roundedMinutes);
    const hh = String(d.getHours()).padStart(2, '0');
    const mm = String(d.getMinutes()).padStart(2, '0');
    return `${hh}:${mm}`;
  });
  const [tableNumber, setTableNumber] = useState('');
  const [name, setName] = useState(initialProfile?.name || '');
  const [phone, setPhone] = useState(initialProfile?.phone || '');
  const [street, setStreet] = useState(initialProfile?.street || '');
  const [number, setNumber] = useState(initialProfile?.number || '');
  const [neighborhood, setNeighborhood] = useState(initialProfile?.neighborhood || '');
  const [addressNotes, setAddressNotes] = useState(initialProfile?.address_notes || '');
  const [isLocatingGps, setIsLocatingGps] = useState(false);
  const [gpsFeedback, setGpsFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  const handleDetectGpsLocation = async () => {
    setGpsFeedback(null);
    setIsLocatingGps(true);
    try {
      const coords = await requestBrowserCoordinates({ enableHighAccuracy: true, timeout: 9000, maximumAge: 30000 });
      const geo = await reverseGeocode(coords.lat, coords.lng);

      if (geo.street) {
        setStreet(geo.street);
      }
      if (geo.number) {
        setNumber(geo.number);
      }
      if (geo.neighborhood) {
        setNeighborhood(geo.neighborhood);
      }

      const updatedNotes = formatGpsAddressNotes(addressNotes, geo.mapsUrl);
      setAddressNotes(updatedNotes);

      if (name.trim() && phone.trim()) {
        saveCustomerProfile({
          name: name.trim(),
          phone: phone.trim(),
          street: geo.street || street || undefined,
          number: geo.number || number || undefined,
          neighborhood: geo.neighborhood || neighborhood || undefined,
          address_notes: updatedNotes || undefined,
        });
      }

      setGpsFeedback({
        type: 'success',
        message: geo.street
          ? `📍 ¡Ubicación detectada! ${geo.street}${geo.number ? ` #${geo.number}` : ''}${geo.neighborhood ? `, Col. ${geo.neighborhood}` : ''}`
          : '📍 ¡Coordenadas GPS obtenidas! Se incluyó tu enlace de ubicación en notas.',
      });
    } catch (err: any) {
      setGpsFeedback({
        type: 'error',
        message: err?.message || 'No fue posible detectar la ubicación GPS.',
      });
    } finally {
      setIsLocatingGps(false);
    }
  };

  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod>('cash');
  const [cashAmount, setCashAmount] = useState('');
  const [orderNotes, setOrderNotes] = useState('');
  const [formError, setFormError] = useState('');
  const [aiRecs, setAiRecs] = useState<Array<{ product_id: string; product_name: string; price_cents: number; reason: string }>>([]);
  const [clabeCopied, setClabeCopied] = useState(false);

  // Payment methods availability based on branch configuration
  const isCashEnabled = selectedBranch?.accepts_cash_payments !== false;
  const isCardEnabled = selectedBranch?.accepts_card_payments === true;
  const bankInfo = selectedBranch?.bank_transfer_info;
  const isTransferEnabled = Boolean(
    bankInfo &&
      bankInfo.is_enabled !== false &&
      bankInfo.bank_name?.trim() &&
      (bankInfo.clabe?.trim() || bankInfo.account_number?.trim())
  );

  // Auto-fallback paymentMethod to available option
  useEffect(() => {
    if (paymentMethod === 'cash' && !isCashEnabled) {
      if (isCardEnabled) setPaymentMethod('card');
      else if (isTransferEnabled) setPaymentMethod('transfer');
    } else if (paymentMethod === 'card' && !isCardEnabled) {
      if (isCashEnabled) setPaymentMethod('cash');
      else if (isTransferEnabled) setPaymentMethod('transfer');
    } else if (paymentMethod === 'transfer' && !isTransferEnabled) {
      if (isCashEnabled) setPaymentMethod('cash');
      else if (isCardEnabled) setPaymentMethod('card');
    }
  }, [paymentMethod, isCashEnabled, isCardEnabled, isTransferEnabled]);

  const handleCopyClabe = (val: string) => {
    if (!val) return;
    try {
      navigator.clipboard?.writeText(val);
      setClabeCopied(true);
      setTimeout(() => setClabeCopied(false), 2500);
    } catch {}
  };

  // Coupon state and branch configuration check
  const hasConfiguredCoupons = Boolean(
    selectedBranch?.coupons &&
      Array.isArray(selectedBranch.coupons) &&
      selectedBranch.coupons.some((c) => c.is_active && Boolean(c.code?.trim()))
  );
  const [couponInput, setCouponInput] = useState('');
  const [appliedCoupon, setAppliedCoupon] = useState<{
    code: string;
    discount_percentage: number;
    discount_cents: number;
  } | null>(null);
  const [couponError, setCouponError] = useState('');
  const [isValidatingCoupon, setIsValidatingCoupon] = useState(false);

  const totalCents = items.reduce((acc, item) => acc + item.line_total_cents, 0);

  // Suggested checkout coupon (only if active and specifically marked for checkout)
  const suggestedCheckoutCoupon = useMemo(() => {
    if (!selectedBranch?.coupons || !Array.isArray(selectedBranch.coupons)) return null;
    return selectedBranch.coupons.find((c) => c.is_active && c.show_in_checkout) || null;
  }, [selectedBranch?.coupons]);

  // Deterministic discount calculation: (total_cents * discount_percentage) // 100
  const discountCents = useMemo(() => {
    if (!appliedCoupon || appliedCoupon.discount_percentage <= 0) return 0;
    return Math.floor((totalCents * appliedCoupon.discount_percentage) / 100);
  }, [appliedCoupon, totalCents]);

  // Delivery fee & Free Delivery threshold calculation
  const deliveryFeeCents = useMemo(() => {
    if (orderType !== 'delivery') return 0;
    if (selectedBranch?.delivery_fee_enabled === false) return 0;

    const threshold = selectedBranch?.free_delivery_min_cents;
    if (threshold != null && threshold > 0 && totalCents >= threshold) {
      return 0;
    }

    const tiers = selectedBranch?.delivery_tiers || [];
    if (tiers.length === 0) return 0;
    const defaultTier = tiers.find((t) => t.is_default_web) || tiers[0];
    return defaultTier ? Math.max(0, defaultTier.fee_cents) : 0;
  }, [orderType, selectedBranch, totalCents]);

  const grandTotalCents = Math.max(0, totalCents - discountCents) + deliveryFeeCents;

  const handleApplyCoupon = async (e?: React.FormEvent, explicitCode?: string) => {
    if (e) e.preventDefault();
    setCouponError('');
    const code = (explicitCode || couponInput).trim().toUpperCase();
    if (!code) {
      setCouponError('Ingresa un código de cupón');
      return;
    }
    const branchKey = selectedBranch?.public_key || selectedBranch?.id;
    if (!branchKey) {
      setCouponError('Sucursal no disponible para validar cupones');
      return;
    }
    setIsValidatingCoupon(true);
    try {
      const res = await validateBranchCoupon(branchKey, code, totalCents);
      if (!res.valid) {
        setCouponError(res.message || 'Cupón no válido o inactivo');
      } else {
        const pct = res.discount_percentage || 0;
        const cents = res.discount_cents ?? Math.floor((totalCents * pct) / 100);
        setAppliedCoupon({
          code: res.code || code,
          discount_percentage: pct,
          discount_cents: cents,
        });
        setCouponInput('');
        setCouponError('');
      }
    } catch {
      setCouponError('Error al validar el cupón');
    } finally {
      setIsValidatingCoupon(false);
    }
  };

  const handleRemoveCoupon = () => {
    setAppliedCoupon(null);
    setCouponError('');
  };

  const freeDeliveryThreshold = selectedBranch?.free_delivery_min_cents;
  const isFreeDeliveryConfigured = selectedBranch?.delivery_fee_enabled !== false && freeDeliveryThreshold != null && freeDeliveryThreshold > 0;
  const hasFreeDelivery = isFreeDeliveryConfigured && totalCents >= freeDeliveryThreshold;
  const freeDeliveryRemaining = isFreeDeliveryConfigured && !hasFreeDelivery ? freeDeliveryThreshold - totalCents : 0;

  const cartProductIdsKey = items.map((i) => i.product.id).sort().join(',');
  const selectedBranchId = selectedBranch?.id;

  useEffect(() => {
    if (orderType === 'delivery' && selectedBranch?.delivery_fee_enabled === false) {
      setOrderType('takeaway');
    }
    if (orderType === 'dine-in' && selectedBranch?.dine_in_enabled === false) {
      setOrderType('takeaway');
    }
  }, [orderType, selectedBranch?.delivery_fee_enabled, selectedBranch?.dine_in_enabled]);

  useEffect(() => {
    setAiRecs([]);
    if (items.length === 0 || !selectedBranchId) {
      return;
    }
    const ids = items.map((i) => i.product.id);
    let isCancelled = false;
    fetchOrderUpsellRecommendations(ids, selectedBranch?.id).then((recs) => {
      if (!isCancelled) {
        setAiRecs(recs);
      }
    });
    return () => {
      isCancelled = true;
    };
  }, [cartProductIdsKey, selectedBranchId]);

  const recommendedProducts = useMemo<Array<Product & { ai_reason?: string }>>(() => {
    if (!allProducts || allProducts.length === 0 || items.length === 0) return [];
    const cartProductIds = new Set(items.map((i) => i.product.id));

    const results: Array<Product & { ai_reason?: string }> = [];
    const seenIds = new Set<string>();

    // 1. Backend recommendations
    for (const recommendation of aiRecs) {
      const product = allProducts.find((candidate) => candidate.id === recommendation.product_id || candidate.sku === recommendation.product_id);
      if (product && !cartProductIds.has(product.id) && !seenIds.has(product.id) && product.is_available !== false) {
        results.push({ ...product, ai_reason: recommendation.reason });
        seenIds.add(product.id);
      }
    }

    // 2. Client-side catalog fallback if fewer than 3 recommendations were found
    if (results.length < 3) {
      const cartHasFood = items.some((item) => {
        const n = (item.product.name + ' ' + (item.product.category_name || '')).toLowerCase();
        return !n.includes('jugo') && !n.includes('bebida') && !n.includes('cafe') && !n.includes('smoothie') && !n.includes('agua') && !n.includes('refresco');
      });

      const candidates = allProducts.filter(
        (p) => !cartProductIds.has(p.id) && !seenIds.has(p.id) && p.is_available !== false
      );

      const sortedCandidates = [...candidates].sort((a, b) => {
        const aName = (a.name + ' ' + (a.category_name || '')).toLowerCase();
        const bName = (b.name + ' ' + (b.category_name || '')).toLowerCase();
        const aIsBev = aName.includes('jugo') || aName.includes('bebida') || aName.includes('cafe') || aName.includes('smoothie') || aName.includes('refresco') || aName.includes('agua');
        const bIsBev = bName.includes('jugo') || bName.includes('bebida') || bName.includes('cafe') || bName.includes('smoothie') || bName.includes('refresco') || bName.includes('agua');
        if (cartHasFood) {
          if (aIsBev && !bIsBev) return -1;
          if (!aIsBev && bIsBev) return 1;
        } else {
          if (!aIsBev && bIsBev) return -1;
          if (aIsBev && !bIsBev) return 1;
        }
        return 0;
      });

      for (const prod of sortedCandidates) {
        if (results.length >= 4) break;
        const pName = (prod.name + ' ' + (prod.category_name || '')).toLowerCase();
        const isBev = pName.includes('jugo') || pName.includes('bebida') || pName.includes('cafe') || pName.includes('smoothie') || pName.includes('refresco') || pName.includes('agua');
        let reason = 'Recomendación especial ⭐';
        if (isBev && cartHasFood) {
          reason = '¿Acompañas con una bebida fresca? 🥤';
        } else if (!isBev && !cartHasFood) {
          reason = 'El complemento ideal para tu orden 🍽️';
        } else if (pName.includes('postre') || pName.includes('galleta') || pName.includes('pan')) {
          reason = 'Un toque dulce delicioso 🍰';
        }
        results.push({ ...prod, ai_reason: reason });
        seenIds.add(prod.id);
      }
    }

    return results.slice(0, 4);
  }, [items, allProducts, aiRecs]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setFormError('');

    if (isBranchClosed) {
      setFormError('La sucursal se encuentra cerrada por el momento y no está recibiendo pedidos. Abriremos pronto.');
      return;
    }

    if (!name.trim()) {
      setFormError('Por favor ingresa tu nombre completo.');
      return;
    }
    const rawDigits = phone.replace(/\D/g, '');
    if (!phone.trim() || rawDigits.length < 10) {
      setFormError('Por favor ingresa un número de teléfono celular válido a 10 dígitos.');
      return;
    }
    if (orderType === 'delivery') {
      if (!street.trim() || !number.trim() || !neighborhood.trim()) {
        setFormError('Para entrega a domicilio, ingresa calle, número y colonia.');
        return;
      }
    }

    let finalOrderNotes = orderNotes.trim();
    if (orderType === 'takeaway') {
      if (selectedDay.disabled) {
        setFormError(`El día seleccionado (${selectedDay.name}) se encuentra cerrado para pedidos.`);
        return;
      }
      if (currentDaySchedule && currentDaySchedule.is_open) {
        const openT = currentDaySchedule.open_time || '09:00';
        const closeT = currentDaySchedule.close_time || '22:00';
        if (pickupTime && (pickupTime < openT || pickupTime > closeT)) {
          setFormError(`El horario de atención para ${selectedDay.name} es de ${openT} a ${closeT} hrs. Por favor elige una hora dentro de este rango.`);
          return;
        }
      }
      const dayLabel = selectedDay.isToday
        ? `Hoy (${selectedDay.name} ${selectedDay.dateNumber} ${selectedDay.monthName})`
        : `${selectedDay.name} ${selectedDay.dateNumber} ${selectedDay.monthName}`;
      const pickupScheduleNote = `📅 Recoger: ${dayLabel} a las ${pickupTime || 'lo antes posible'}`;
      finalOrderNotes = [pickupScheduleNote, finalOrderNotes].filter(Boolean).join(' | ');
    }

    const orderInfo: CustomerOrderInfo = {
      name: name.trim(),
      phone: phone.trim(),
      order_type: orderType,
      table_number: orderType === 'dine-in' ? tableNumber.trim() || undefined : undefined,
      address_street: street.trim(),
      address_number: number.trim(),
      address_neighborhood: neighborhood.trim(),
      address_notes: addressNotes.trim(),
      payment_method: paymentMethod,
      cash_amount: paymentMethod === 'cash' ? cashAmount.trim() : undefined,
      order_notes: finalOrderNotes,
      delivery_fee_cents: deliveryFeeCents,
      coupon_code: appliedCoupon ? appliedCoupon.code : undefined,
      discount_cents: discountCents > 0 ? discountCents : undefined,
    };

    saveCustomerProfile({
      name: name.trim(),
      phone: phone.trim(),
      street: street.trim() || undefined,
      number: number.trim() || undefined,
      neighborhood: neighborhood.trim() || undefined,
      address_notes: addressNotes.trim() || undefined,
    });

    onSubmitOrder(orderInfo);
  };

  return (
    <div className="product-modal-backdrop" onClick={onClose}>
      <div
        className="product-modal-bottom-sheet cart-drawer-sheet"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Carrito de compras"
      >
        <div className="cart-drawer-header">
          <div>
            <h2 className="cart-drawer-title">Tu Pedido</h2>
            <span className="cart-drawer-subtitle">
              {items.length} {items.length === 1 ? 'producto seleccionado' : 'productos seleccionados'}
            </span>
          </div>
          <button
            type="button"
            className="cart-drawer-close-btn"
            onClick={onClose}
            aria-label="Cerrar carrito"
          >
            <X size={18} />
          </button>
        </div>

        <form
          id="cart-checkout-form"
          name="checkout_form"
          method="post"
          action="#"
          autoComplete="on"
          onSubmit={handleSubmit}
          className="cart-drawer-form-body"
        >
          {items.length === 0 ? (
            <div className="cart-empty-view">
              <div className="cart-empty-icon-circle">
                <ShoppingBag size={32} />
              </div>
              <h3>Tu comanda está vacía</h3>
              <p>Agrega deliciosos jugos, platillos o bowls desde el menú.</p>
              <button type="button" className="btn-cart-back-menu" onClick={onClose}>
                Explorar el Menú
              </button>
            </div>
          ) : (
            <>
              {/* Cart items list */}
              <section className="cart-items-modern-list" aria-label="Platillos en el carrito">
                {items.map((item) => {
                  const iconMeta = getProductIconMeta(item.product);
                  const itemImg = item.product.image_url || getProductImage(item.product);
                  return (
                    <div key={item.cart_id} className="cart-item-modern-card">
                      <div
                        className="cart-item-thumbnail-avatar"
                        style={{
                          background: iconMeta.bgGradient,
                          borderColor: iconMeta.borderColor,
                        }}
                      >
                        {itemImg ? (
                          <img
                            src={itemImg}
                            alt={item.product.name}
                            className="cart-item-thumbnail-img"
                            onError={(e) => { (e.currentTarget as HTMLElement).style.display = 'none'; }}
                          />
                        ) : (
                          <span className="cart-item-thumbnail-emoji">{iconMeta.emoji}</span>
                        )}
                      </div>

                      <div className="cart-item-details">
                        <span className="cart-item-name">{item.product.name}</span>
                        <span className="cart-item-price-tag">
                          {formatMoney(item.line_total_cents)}
                        </span>
                        {item.notes && (
                          <span className="cart-item-notes-text">
                            📝 {item.notes}
                          </span>
                        )}
                        {(item.modifiers ?? []).map((modifier) => (
                          <span key={modifier.option_id} className="cart-item-notes-text">
                            + {modifier.name}{modifier.text ? `: ${modifier.text}` : ''}
                          </span>
                        ))}
                      </div>

                      <div className="cart-item-actions-cluster">
                        <div className="cart-item-stepper">
                          <button
                            type="button"
                            className="cart-stepper-btn"
                            onClick={() => onUpdateQuantity(item.cart_id, -1)}
                            aria-label="Disminuir cantidad"
                          >
                            <Minus size={13} />
                          </button>
                          <span className="cart-stepper-count">{item.quantity}</span>
                          <button
                            type="button"
                            className="cart-stepper-btn"
                            onClick={() => onUpdateQuantity(item.cart_id, 1)}
                            aria-label="Aumentar cantidad"
                          >
                            <Plus size={13} />
                          </button>
                        </div>

                        <button
                          type="button"
                          className="cart-item-delete-btn"
                          onClick={() => onRemoveItem(item.cart_id)}
                          aria-label={`Eliminar ${item.product.name}`}
                        >
                          <Trash2 size={16} />
                        </button>
                      </div>
                    </div>
                  );
                })}
              </section>

              {/* AI Cross-selling / Upselling Recommendations */}
              {recommendedProducts.length > 0 && (
                <div className="cart-upsell-container">
                  <div className="cart-upsell-header">
                    <div className="cart-upsell-badge">
                      <Sparkles size={14} />
                      <span>Sugerencias para tu orden</span>
                    </div>
                    <span className="cart-upsell-caption">
                      Basadas en compras de esta sucursal
                    </span>
                  </div>
                  <div className="cart-upsell-scroll-track">
                    {recommendedProducts.map((prod) => {
                      const iconMeta = getProductIconMeta(prod);
                      return (
                        <div key={prod.id} className="cart-upsell-card">
                          <div
                            className="cart-upsell-card-thumb"
                            style={{
                              background: iconMeta.bgGradient,
                              borderColor: iconMeta.borderColor,
                            }}
                          >
                            <span className="cart-upsell-card-icon" aria-hidden="true">
                              {getRecommendationIcon(prod)}
                            </span>
                          </div>
                          <div className="cart-upsell-card-info">
                            <strong className="cart-upsell-card-name" title={prod.name}>{prod.name}</strong>
                            <span className="cart-upsell-card-reason" title={prod.ai_reason}>{prod.ai_reason || 'Recomendación especial'}</span>
                            <span className="cart-upsell-card-price">{formatMoney(prod.price_cents)}</span>
                          </div>
                          <button
                            type="button"
                            className="cart-upsell-quick-add-btn"
                            onClick={() => onQuickAddProduct && onQuickAddProduct(prod)}
                            aria-label={`Agregar ${prod.name} al pedido`}
                          >
                            <Plus size={14} />
                            <span>Agregar</span>
                          </button>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}



              {/* Order Mode selector (Social Style like Image 3) */}
              <div className="cart-form-section">
                <label className="cart-form-section-label">Modalidad de consumo</label>
                <div className="social-mode-selector-container" role="tablist" aria-label="Modalidad de consumo">
                  {selectedBranch?.dine_in_enabled !== false && (
                    <button
                      type="button"
                      className={`social-mode-card-btn ${orderType === 'dine-in' ? 'active' : ''}`}
                      onClick={() => setOrderType('dine-in')}
                      role="tab"
                      aria-selected={orderType === 'dine-in'}
                    >
                      <div className="social-mode-icon-circle">
                        <Utensils size={18} />
                      </div>
                      <span className="social-mode-card-label">Comer aquí</span>
                    </button>
                  )}

                  <button
                    type="button"
                    className={`social-mode-card-btn ${orderType === 'takeaway' ? 'active' : ''}`}
                    onClick={() => setOrderType('takeaway')}
                    role="tab"
                    aria-selected={orderType === 'takeaway'}
                  >
                    <div className="social-mode-icon-circle">
                      <ShoppingBag size={18} />
                    </div>
                    <span className="social-mode-card-label">Recoger</span>
                  </button>

                  {selectedBranch?.delivery_fee_enabled !== false && (
                    <button
                      type="button"
                      className={`social-mode-card-btn ${orderType === 'delivery' ? 'active' : ''}`}
                      onClick={() => setOrderType('delivery')}
                      role="tab"
                      aria-selected={orderType === 'delivery'}
                    >
                      <div className="social-mode-icon-circle">
                        <Bike size={18} />
                      </div>
                      <span className="social-mode-card-label">Envío</span>
                    </button>
                  )}
                </div>
              </div>

              {/* Customer Info */}
              <div className="cart-form-section">
                <div className="cart-customer-section-header">
                  <label className="cart-form-section-label" style={{ marginBottom: 0 }}>
                    Tus Datos de Contacto
                  </label>
                  {isReturningCustomer && (
                    <button
                      type="button"
                      className="btn-cart-toggle-customer"
                      onClick={() => setIsEditingCustomer(!isEditingCustomer)}
                    >
                      {isEditingCustomer ? 'Listo' : 'Editar datos'}
                    </button>
                  )}
                </div>

                {/* 1-Tap Native Contact Picker Button (when supported by browser) */}
                {supportsNativeContacts && (!isReturningCustomer || isEditingCustomer) && (
                  <button
                    type="button"
                    className="btn-cart-1tap-autofill"
                    onClick={handle1TapAutofill}
                  >
                    <Sparkles size={16} color="#059669" />
                    <span>⚡ Autocompletar con mis datos del celular (1-Tap)</span>
                  </button>
                )}

                {/* Returning customer chip if editing and wants to restore */}
                {initialProfile?.name && isEditingCustomer && (
                  <button
                    type="button"
                    className="btn-cart-restore-profile"
                    onClick={() => {
                      setName(initialProfile.name);
                      setPhone(initialProfile.phone);
                      if (initialProfile.street) setStreet(initialProfile.street);
                      if (initialProfile.number) setNumber(initialProfile.number);
                      if (initialProfile.neighborhood) setNeighborhood(initialProfile.neighborhood);
                      if (initialProfile.address_notes) setAddressNotes(initialProfile.address_notes);
                      setIsEditingCustomer(false);
                    }}
                  >
                    <span>Restaurar datos guardados de <strong>{initialProfile.name}</strong></span>
                  </button>
                )}

                {isReturningCustomer && !isEditingCustomer ? (
                  <div className="cart-returning-customer-card">
                    <div className="cart-returning-customer-avatar">
                      <CheckCircle2 size={20} color="#10b981" />
                    </div>
                    <div className="cart-returning-customer-info">
                      <div className="cart-returning-customer-name-row">
                        <span className="cart-returning-customer-name">{name || 'Cliente'}</span>
                        <span className="cart-returning-customer-badge">⚡ Recordado</span>
                      </div>
                      <span className="cart-returning-customer-phone">{phone}</span>
                    </div>
                    <button
                      type="button"
                      className="btn-cart-edit-customer"
                      onClick={() => setIsEditingCustomer(true)}
                    >
                      Cambiar
                    </button>
                  </div>
                ) : (
                  <div className="cart-form-fields-grid">
                    <div className="cart-input-wrapper">
                      <label htmlFor="customer-name" className="cart-accessible-label">
                        Nombre completo
                      </label>
                      <User size={16} className="cart-input-icon" aria-hidden="true" />
                      <input
                        id="customer-name"
                        name="name"
                        type="text"
                        autoComplete="name"
                        autoCapitalize="words"
                        autoCorrect="off"
                        spellCheck={false}
                        className="cart-input-field"
                        placeholder="Tu nombre completo *"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        onInput={(e) => setName((e.target as HTMLInputElement).value)}
                        required
                      />
                    </div>

                    <div className="cart-input-wrapper">
                      <label htmlFor="customer-phone" className="cart-accessible-label">
                        Teléfono celular
                      </label>
                      <Phone size={16} className="cart-input-icon" aria-hidden="true" />
                      <input
                        id="customer-phone"
                        name="tel"
                        type="tel"
                        inputMode="tel"
                        autoComplete="tel"
                        autoCorrect="off"
                        spellCheck={false}
                        className="cart-input-field"
                        placeholder="Teléfono Celular *"
                        value={phone}
                        onChange={(e) => setPhone(e.target.value)}
                        onInput={(e) => setPhone((e.target as HTMLInputElement).value)}
                        required
                      />
                    </div>
                  </div>
                )}
              </div>

              {/* Table or Spot if dine-in mode */}
              {orderType === 'dine-in' && (
                <div className="cart-form-section">
                  <label className="cart-form-section-label">Mesa o Ubicación (opcional)</label>
                  <div className="cart-input-wrapper">
                    <Utensils size={16} className="cart-input-icon" />
                    <input
                      id="customer-table"
                      name="table_number"
                      type="text"
                      autoComplete="off"
                      className="cart-input-field"
                      placeholder="Ej. Mesa 4, Barra principal, etc."
                      value={tableNumber}
                      onChange={(e) => setTableNumber(e.target.value)}
                    />
                  </div>
                </div>
              )}

              {/* Scheduled Pickup Selector (Days of week + Time) if takeaway mode */}
              {orderType === 'takeaway' && (
                <div className="cart-form-section pickup-schedule-section">
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                    <Calendar size={18} color="#ea580c" />
                    <label className="cart-form-section-label" style={{ marginBottom: 0 }}>
                      Día y hora para recoger
                    </label>
                  </div>
                  <p style={{ margin: '0 0 10px', fontSize: '0.775rem', color: '#64748b' }}>
                    Selecciona el día y la hora estimada en que pasarás por tu pedido.
                  </p>

                  {/* Day of Week Selector: L, M, M, J, V, S, D */}
                  <div className="pickup-days-container" role="radiogroup" aria-label="Día de recolección">
                    {weekDayOptions.map((opt) => {
                      const isSelected = selectedDayIndex === opt.index;
                      return (
                        <button
                          key={opt.index}
                          type="button"
                          disabled={opt.disabled}
                          onClick={() => !opt.disabled && setSelectedDayIndex(opt.index)}
                          className={`pickup-day-btn ${isSelected ? 'selected' : ''} ${opt.disabled ? 'disabled' : ''} ${opt.isToday ? 'is-today' : ''}`}
                          title={opt.disabled ? `${opt.name} (${opt.isPast ? 'Día pasado no disponible' : 'Cerrado por horario'})` : opt.name}
                          aria-label={opt.name}
                        >
                          <span className="pickup-day-letter">{opt.letter}</span>
                          <span className="pickup-day-number">{opt.dateNumber}</span>
                          {opt.isToday && <span className="pickup-day-today-pill">Hoy</span>}
                          {opt.isClosed && !opt.isPast && (
                            <span style={{ fontSize: '0.52rem', color: '#94a3b8', fontWeight: 700, lineHeight: 1 }}>Cerrado</span>
                          )}
                        </button>
                      );
                    })}
                  </div>

                  {/* Pickup Time Selector */}
                  <div className="pickup-time-section-block">
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                      <label htmlFor="pickup-time-input" style={{ fontSize: '0.8rem', fontWeight: 700, color: '#334155', display: 'flex', alignItems: 'center', gap: 4 }}>
                        <Clock size={15} color="#ea580c" />
                        Hora estimada de recolección
                      </label>
                      <span style={{ fontSize: '0.75rem', color: '#ea580c', fontWeight: 600 }}>
                        {selectedDay.isToday ? 'Hoy' : selectedDay.name}
                      </span>
                    </div>

                    <div className="pickup-time-input-wrap">
                      <input
                        id="pickup-time-input"
                        type="time"
                        min={currentDaySchedule?.is_open ? currentDaySchedule.open_time : undefined}
                        max={currentDaySchedule?.is_open ? currentDaySchedule.close_time : undefined}
                        value={pickupTime}
                        onChange={(e) => setPickupTime(e.target.value)}
                        onClick={(e) => {
                          try {
                            (e.target as any)?.showPicker?.();
                          } catch {}
                        }}
                        className="pickup-time-field"
                        required={orderType === 'takeaway'}
                      />
                    </div>

                    {/* Quick presets for today */}
                    {selectedDay.isToday && (
                      <div className="pickup-quick-chips">
                        <span style={{ fontSize: '0.72rem', color: '#64748b', fontWeight: 600 }}>Rápido:</span>
                        {[15, 30, 45, 60]
                          .filter((mins) => {
                            if (!currentDaySchedule?.close_time) return true;
                            const d = new Date();
                            d.setMinutes(d.getMinutes() + mins);
                            const hh = String(d.getHours()).padStart(2, '0');
                            const mm = String(d.getMinutes()).padStart(2, '0');
                            return `${hh}:${mm}` <= currentDaySchedule.close_time;
                          })
                          .map((mins) => (
                            <button
                              key={mins}
                              type="button"
                              className="pickup-quick-chip-btn"
                              onClick={() => {
                                const d = new Date();
                                d.setMinutes(d.getMinutes() + mins);
                                const hh = String(d.getHours()).padStart(2, '0');
                                const mm = String(d.getMinutes()).padStart(2, '0');
                                setPickupTime(`${hh}:${mm}`);
                              }}
                            >
                              +{mins < 60 ? `${mins} min` : '1 hora'}
                            </button>
                          ))}
                      </div>
                    )}

                    {/* Selected Summary Badge */}
                    <div className="pickup-summary-badge">
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 2, width: '100%' }}>
                        <span>
                          📅 Pasarás a recoger: <strong>{selectedDay.isToday ? 'Hoy' : selectedDay.name} ({selectedDay.dateNumber} {selectedDay.monthName}) a las {pickupTime || '--:--'} hrs</strong>
                        </span>
                        {currentDaySchedule?.is_open && (
                          <span style={{ fontSize: '0.72rem', color: '#c2410c', fontWeight: 500 }}>
                            ⏰ Horario de servicio {selectedDay.isToday ? 'hoy' : selectedDay.name}: {currentDaySchedule.open_time} a {currentDaySchedule.close_time} hrs
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Pickup Address if takeaway mode */}
              {orderType === 'takeaway' && selectedBranch && (
                <div className="cart-form-section">
                  <div className="cart-customer-section-header">
                    <label className="cart-form-section-label" style={{ marginBottom: 0 }}>
                      Dirección de Recolección
                    </label>
                  </div>
                  <a
                    href={(selectedBranch.latitude && selectedBranch.longitude) ? `https://www.google.com/maps/search/?api=1&query=${selectedBranch.latitude},${selectedBranch.longitude}` : undefined}
                    target={(selectedBranch.latitude && selectedBranch.longitude) ? "_blank" : undefined}
                    rel={(selectedBranch.latitude && selectedBranch.longitude) ? "noopener noreferrer" : undefined}
                    className="cart-returning-customer-card"
                    style={{ marginTop: 12, textDecoration: 'none', display: 'flex', cursor: (selectedBranch.latitude && selectedBranch.longitude) ? 'pointer' : 'default' }}
                  >
                    <div className="cart-returning-customer-avatar">
                      <MapPin size={20} color="#3b82f6" />
                    </div>
                    <div className="cart-returning-customer-info">
                      <div className="cart-returning-customer-name-row">
                        <span className="cart-returning-customer-name" style={{ color: '#0f172a' }}>{selectedBranch.name}</span>
                        {(selectedBranch.latitude && selectedBranch.longitude) && (
                          <span className="cart-returning-customer-badge address">Abrir Mapa</span>
                        )}
                      </div>
                      <span className="cart-returning-customer-phone" style={{ color: '#64748b' }}>
                        {selectedBranch.street} {selectedBranch.exterior_number} {selectedBranch.interior_number ? `Int. ${selectedBranch.interior_number}` : ''}
                        <br />
                        {selectedBranch.neighborhood && `Col. ${selectedBranch.neighborhood}, `}{selectedBranch.city}, {selectedBranch.state}
                      </span>
                      {selectedBranch.cross_streets && <span className="cart-returning-customer-phone" style={{ marginTop: 4, color: '#64748b' }}>Entre: {selectedBranch.cross_streets}</span>}
                    </div>
                  </a>
                </div>
              )}

              {/* Delivery Address if delivery mode */}
              {orderType === 'delivery' && (
                <div className="cart-form-section">
                  <div className="cart-customer-section-header">
                    <label className="cart-form-section-label" style={{ marginBottom: 0 }}>
                      Dirección de Entrega
                    </label>
                    {isReturningCustomer && street && (
                      <button
                        type="button"
                        className="btn-cart-toggle-customer"
                        onClick={() => setIsEditingCustomer(!isEditingCustomer)}
                      >
                        {isEditingCustomer ? 'Listo' : 'Cambiar dirección'}
                      </button>
                    )}
                  </div>

                  {isReturningCustomer && !isEditingCustomer && street ? (
                    <div className="cart-returning-customer-card">
                      <div className="cart-returning-customer-avatar">
                        <MapPin size={20} color="#f59e0b" />
                      </div>
                      <div className="cart-returning-customer-info">
                        <div className="cart-returning-customer-name-row">
                          <span className="cart-returning-customer-name">{street} #{number}</span>
                          <span className="cart-returning-customer-badge address">Casa / Entrega</span>
                        </div>
                        <span className="cart-returning-customer-phone">
                          Col. {neighborhood} {addressNotes ? `• ${addressNotes}` : ''}
                        </span>
                      </div>
                      <button
                        type="button"
                        className="btn-cart-edit-customer"
                        onClick={() => setIsEditingCustomer(true)}
                      >
                        Cambiar
                      </button>
                    </div>
                  ) : (
                    <>
                      {/* Botón de Ubicación GPS */}
                      <button
                        type="button"
                        onClick={handleDetectGpsLocation}
                        disabled={isLocatingGps}
                        className="btn-detect-gps-address"
                      >
                        <Navigation size={15} className={isLocatingGps ? 'spin-icon' : ''} />
                        <span>{isLocatingGps ? 'Obteniendo señal GPS...' : '📍 Usar mi ubicación actual (GPS)'}</span>
                        <span className="gps-pill-auto">Auto</span>
                      </button>

                      {gpsFeedback && (
                        <div
                          className={`gps-feedback-banner ${gpsFeedback.type}`}
                          role="alert"
                        >
                          <span>{gpsFeedback.type === 'success' ? '✅' : '⚠️'}</span>
                          <span>{gpsFeedback.message}</span>
                        </div>
                      )}

                      <div className="cart-form-fields-grid">
                        <div className="cart-input-wrapper">
                          <label htmlFor="customer-street" className="cart-accessible-label">
                            Calle y número
                          </label>
                          <MapPin size={16} className="cart-input-icon" aria-hidden="true" />
                          <input
                            id="customer-street"
                            name="address"
                            type="text"
                            autoComplete="street-address"
                            autoCapitalize="words"
                            className="cart-input-field"
                            placeholder="Calle *"
                            value={street}
                            onChange={(e) => setStreet(e.target.value)}
                            onInput={(e) => setStreet((e.target as HTMLInputElement).value)}
                            required
                          />
                        </div>

                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.5fr', gap: '8px' }}>
                          <div>
                            <label htmlFor="customer-number" className="cart-accessible-label">
                              Número exterior o interior
                            </label>
                            <input
                              id="customer-number"
                              name="address-line2"
                              type="text"
                              autoComplete="address-line2"
                              className="cart-input-field no-icon"
                              placeholder="No. Ext / Int *"
                              value={number}
                              onChange={(e) => setNumber(e.target.value)}
                              onInput={(e) => setNumber((e.target as HTMLInputElement).value)}
                              required
                            />
                          </div>
                          <div>
                            <label htmlFor="customer-neighborhood" className="cart-accessible-label">
                              Colonia
                            </label>
                            <input
                              id="customer-neighborhood"
                              name="address-level3"
                              type="text"
                              autoComplete="address-level3"
                              autoCapitalize="words"
                              className="cart-input-field no-icon"
                              placeholder="Colonia *"
                              value={neighborhood}
                              onChange={(e) => setNeighborhood(e.target.value)}
                              onInput={(e) => setNeighborhood((e.target as HTMLInputElement).value)}
                              required
                            />
                          </div>
                        </div>

                        <div>
                          <label htmlFor="customer-address-notes" className="cart-accessible-label">
                            Referencias de entrega
                          </label>
                          <input
                            id="customer-address-notes"
                            name="address_notes"
                            type="text"
                            autoComplete="off"
                            className="cart-input-field no-icon"
                            placeholder="Referencias de entrega (ej: Portón café, timbre blanco)"
                            value={addressNotes}
                            onChange={(e) => setAddressNotes(e.target.value)}
                            onInput={(e) => setAddressNotes((e.target as HTMLInputElement).value)}
                          />
                        </div>
                      </div>
                    </>
                  )}

                    {isFreeDeliveryConfigured && (
                      hasFreeDelivery ? (
                        <div style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '8px',
                          backgroundColor: '#f0fdf4',
                          border: '1px solid #bbf7d0',
                          color: '#15803d',
                          padding: '10px 14px',
                          borderRadius: '12px',
                          fontSize: '0.86rem',
                          fontWeight: 600,
                          marginTop: '4px',
                        }}>
                          <span style={{ fontSize: '1.2rem' }}>🎉</span>
                          <span>¡Felicidades! Calificas para <strong>Envío GRATIS</strong></span>
                        </div>
                      ) : (
                        <div style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '8px',
                          backgroundColor: '#eff6ff',
                          border: '1px solid #bfdbfe',
                          color: '#1d4ed8',
                          padding: '10px 14px',
                          borderRadius: '12px',
                          fontSize: '0.86rem',
                          fontWeight: 500,
                          marginTop: '4px',
                        }}>
                          <span style={{ fontSize: '1.2rem' }}>🛵</span>
                          <span>Agrega <strong>{formatMoney(freeDeliveryRemaining)}</strong> más para obtener <strong>Envío GRATIS</strong></span>
                        </div>
                      )
                    )}
                  </div>
              )}

              {/* Payment Methods */}
              <div className="cart-form-section">
                <label className="cart-form-section-label">Forma de Pago</label>
                <div className="cart-payment-methods-grid">
                  {isCashEnabled && (
                    <button
                      type="button"
                      className={`cart-payment-method-pill ${paymentMethod === 'cash' ? 'active' : ''}`}
                      onClick={() => setPaymentMethod('cash')}
                    >
                      <Banknote size={18} />
                      <span>Efectivo</span>
                    </button>
                  )}

                  {isCardEnabled && (
                    <button
                      type="button"
                      className={`cart-payment-method-pill ${paymentMethod === 'card' ? 'active' : ''}`}
                      onClick={() => setPaymentMethod('card')}
                    >
                      <CreditCard size={18} />
                      <span>Tarjeta (Terminal)</span>
                    </button>
                  )}

                  {isTransferEnabled && (
                    <button
                      type="button"
                      className={`cart-payment-method-pill ${paymentMethod === 'transfer' ? 'active' : ''}`}
                      onClick={() => setPaymentMethod('transfer')}
                    >
                      <ArrowRightLeft size={18} />
                      <span>Transferencia</span>
                    </button>
                  )}
                </div>

                {paymentMethod === 'cash' && isCashEnabled && (
                  <div style={{ marginTop: '10px' }}>
                    <input
                      type="text"
                      className="cart-input-field no-icon"
                      placeholder="¿Con cuánto vas a pagar? (Para llevar cambio)"
                      value={cashAmount}
                      onChange={(e) => setCashAmount(e.target.value)}
                    />
                  </div>
                )}

                {paymentMethod === 'transfer' && isTransferEnabled && bankInfo && (
                  <div
                    style={{
                      marginTop: 12,
                      padding: '14px 16px',
                      backgroundColor: '#f8fafc',
                      border: '1.5px solid #e2e8f0',
                      borderRadius: 14,
                      boxShadow: '0 1px 3px rgba(0,0,0,0.03)',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                      <Building2 size={18} color="#7c3aed" />
                      <strong style={{ fontSize: '0.9rem', color: '#0f172a' }}>
                        Datos para Transferencia
                      </strong>
                    </div>

                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: '0.84rem' }}>
                      {bankInfo.bank_name && (
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span style={{ color: '#64748b' }}>Banco:</span>
                          <strong style={{ color: '#0f172a' }}>{bankInfo.bank_name}</strong>
                        </div>
                      )}
                      {bankInfo.account_holder && (
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span style={{ color: '#64748b' }}>Titular:</span>
                          <strong style={{ color: '#0f172a' }}>{bankInfo.account_holder}</strong>
                        </div>
                      )}
                      {bankInfo.account_number && (
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span style={{ color: '#64748b' }}>Cuenta:</span>
                          <span style={{ fontWeight: 700, color: '#0f172a', fontFamily: 'monospace' }}>
                            {bankInfo.account_number}
                          </span>
                        </div>
                      )}
                      {bankInfo.clabe && (
                        <div
                          style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                            marginTop: 4,
                            paddingTop: 8,
                            borderTop: '1px dashed #cbd5e1',
                          }}
                        >
                          <div>
                            <span style={{ display: 'block', fontSize: '0.72rem', color: '#64748b', fontWeight: 600 }}>
                              CLABE Interbancaria:
                            </span>
                            <span style={{ fontWeight: 800, color: '#0f172a', fontFamily: 'monospace', fontSize: '0.92rem' }}>
                              {bankInfo.clabe}
                            </span>
                          </div>
                          <button
                            type="button"
                            onClick={() => handleCopyClabe(bankInfo.clabe || '')}
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              gap: 4,
                              border: '1px solid #c4b5fd',
                              background: clabeCopied ? '#f5f3ff' : '#ffffff',
                              color: '#7c3aed',
                              padding: '5px 10px',
                              borderRadius: 8,
                              fontSize: '0.75rem',
                              fontWeight: 700,
                              cursor: 'pointer',
                            }}
                          >
                            {clabeCopied ? <Check size={14} /> : <Copy size={14} />}
                            <span>{clabeCopied ? '¡Copiada!' : 'Copiar'}</span>
                          </button>
                        </div>
                      )}
                    </div>
                    <p style={{ margin: '10px 0 0', fontSize: '0.73rem', color: '#64748b', lineHeight: 1.3 }}>
                      💡 Realiza tu transferencia por el total del pedido y muestra o envía tu comprobante al recibir/recoger.
                    </p>
                  </div>
                )}
              </div>

              {/* Order Notes */}
              <div className="cart-form-section">
                <label className="cart-form-section-label">Comentarios o Indicaciones del Pedido</label>
                <textarea
                  className="cart-input-field no-icon"
                  rows={2}
                  placeholder="Instrucciones generales para el restaurante..."
                  value={orderNotes}
                  onChange={(e) => setOrderNotes(e.target.value)}
                />
              </div>

              {formError && (
                <div className="cart-form-error-alert" role="alert">
                  {formError}
                </div>
              )}

              {/* Coupon input & discount badge */}
              {hasConfiguredCoupons && (
                <div className="cart-form-section" style={{ marginBottom: 14 }}>
                  <label className="cart-form-section-label" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <Tag size={16} color="#059669" />
                    <span>¿Tienes un cupón de descuento?</span>
                  </label>
                  {appliedCoupon ? (
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        backgroundColor: '#ecfdf5',
                        border: '1px solid #a7f3d0',
                        borderRadius: 12,
                        padding: '10px 14px',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ fontSize: '1.2rem' }}>🎉</span>
                        <div>
                          <div style={{ fontWeight: 800, fontSize: '0.9rem', color: '#065f46' }}>
                            Cupón {appliedCoupon.code} aplicado
                          </div>
                          <div style={{ fontSize: '0.78rem', color: '#047857' }}>
                            {appliedCoupon.discount_percentage}% de descuento (-{formatMoney(discountCents)})
                          </div>
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={handleRemoveCoupon}
                        style={{
                          background: 'transparent',
                          border: 'none',
                          color: '#059669',
                          fontWeight: 700,
                          fontSize: '0.8rem',
                          cursor: 'pointer',
                          padding: '4px 8px',
                        }}
                      >
                        Quitar
                      </button>
                    </div>
                  ) : (
                    <div>
                      {suggestedCheckoutCoupon && (
                        <div
                          style={{
                            marginBottom: 10,
                            padding: '10px 12px',
                            backgroundColor: '#ecfdf5',
                            border: '1px dashed #86efac',
                            borderRadius: 10,
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            gap: 8,
                          }}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
                            <span style={{ fontSize: '1.1rem', flexShrink: 0 }}>🏷️</span>
                            <div style={{ fontSize: '0.8rem', color: '#166534', minWidth: 0 }}>
                              <span>Promoción sugerida: </span>
                              <strong style={{ letterSpacing: '0.04em' }}>{suggestedCheckoutCoupon.code}</strong>
                              <span> ({suggestedCheckoutCoupon.discount_percentage}% OFF)</span>
                            </div>
                          </div>
                          <button
                            type="button"
                            onClick={() => {
                              setCouponInput(suggestedCheckoutCoupon.code);
                              handleApplyCoupon(undefined, suggestedCheckoutCoupon.code);
                            }}
                            disabled={isValidatingCoupon}
                            style={{
                              padding: '5px 12px',
                              backgroundColor: '#059669',
                              color: '#ffffff',
                              border: 'none',
                              borderRadius: 8,
                              fontSize: '0.78rem',
                              fontWeight: 700,
                              cursor: isValidatingCoupon ? 'not-allowed' : 'pointer',
                              whiteSpace: 'nowrap',
                              flexShrink: 0,
                            }}
                          >
                            Aplicar
                          </button>
                        </div>
                      )}
                      <div style={{ display: 'flex', gap: 8 }}>
                        <input
                          type="text"
                          placeholder={
                            suggestedCheckoutCoupon
                              ? `Ingresa cupón (ej. ${suggestedCheckoutCoupon.code})`
                              : 'Ingresa tu cupón'
                          }
                          value={couponInput}
                          onChange={(e) => {
                            setCouponInput(e.target.value.toUpperCase());
                            if (couponError) setCouponError('');
                          }}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') {
                              e.preventDefault();
                              handleApplyCoupon();
                            }
                          }}
                          style={{
                            flex: 1,
                            padding: '10px 12px',
                            borderRadius: 10,
                            border: couponError ? '1px solid #ef4444' : '1px solid #cbd5e1',
                            fontSize: '0.88rem',
                            fontWeight: 700,
                            letterSpacing: '0.04em',
                            textTransform: 'uppercase',
                            outline: 'none',
                          }}
                        />
                        <button
                          type="button"
                          onClick={() => handleApplyCoupon()}
                          disabled={isValidatingCoupon || !couponInput.trim()}
                          style={{
                            padding: '0 16px',
                            backgroundColor: '#0f172a',
                            color: '#ffffff',
                            border: 'none',
                            borderRadius: 10,
                            fontSize: '0.85rem',
                            fontWeight: 700,
                            cursor: isValidatingCoupon || !couponInput.trim() ? 'not-allowed' : 'pointer',
                            opacity: isValidatingCoupon || !couponInput.trim() ? 0.6 : 1,
                            flexShrink: 0,
                          }}
                        >
                          {isValidatingCoupon ? 'Validando…' : 'Aplicar'}
                        </button>
                      </div>
                      {couponError && (
                        <p style={{ margin: '6px 0 0', fontSize: '0.78rem', color: '#ef4444', fontWeight: 500 }}>
                          {couponError}
                        </p>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* Financial summary breakdown */}
              <div className="cart-financial-summary-card">
                <div className="cart-summary-line">
                  <span>Subtotal de productos</span>
                  <span>{formatMoney(totalCents)}</span>
                </div>
                {discountCents > 0 && (
                  <div className="cart-summary-line" style={{ color: '#16a34a', fontWeight: 600 }}>
                    <span>Descuento ({appliedCoupon?.code} -{appliedCoupon?.discount_percentage}%)</span>
                    <span>-{formatMoney(discountCents)}</span>
                  </div>
                )}
                {orderType === 'delivery' && (
                  <div className="cart-summary-line">
                    <span>Costo de envío</span>
                    <span style={{ color: deliveryFeeCents === 0 ? '#16a34a' : '#0f172a', fontWeight: 700 }}>
                      {deliveryFeeCents === 0 ? '¡GRATIS!' : formatMoney(deliveryFeeCents)}
                    </span>
                  </div>
                )}
                {orderType !== 'delivery' && (
                  <div className="cart-summary-line">
                    <span>Costo de envío</span>
                    <span style={{ color: '#64748b', fontWeight: 600 }}>No aplica</span>
                  </div>
                )}
                <div className="cart-summary-total-line">
                  <strong>Total a Pagar</strong>
                  <strong className="cart-total-value">{formatMoney(grandTotalCents)}</strong>
                </div>
              </div>

              <div className="cart-submit-sticky-bar">
                {isBranchClosed && (
                  <div
                    className="cart-closed-notice-box"
                    role="alert"
                    style={{
                      marginBottom: '10px',
                      padding: '10px 14px',
                      borderRadius: '12px',
                      backgroundColor: 'rgba(239, 68, 68, 0.08)',
                      border: '1px solid rgba(239, 68, 68, 0.25)',
                      color: '#b91c1c',
                      fontSize: '0.85rem',
                      lineHeight: '1.4',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px',
                    }}
                  >
                    <span style={{ fontSize: '1.1rem' }}>🕒</span>
                    <span>
                      <strong>Caja cerrada por el momento:</strong> Esta sucursal no está recibiendo pedidos en este instante. ¡Abriremos pronto!
                    </span>
                  </div>
                )}
                {submitError && <p className="cart-form-error-alert" role="alert">{submitError}</p>}
                <button
                  type="submit"
                  className={`btn-cart-submit-order ${isBranchClosed ? 'disabled-closed' : ''}`}
                  disabled={isSubmitting || items.length === 0 || isBranchClosed}
                  title={isBranchClosed ? 'Sucursal cerrada por el momento' : undefined}
                >
                  <Send size={18} />
                  <span>
                    {isBranchClosed
                      ? 'Abriremos pronto'
                      : isSubmitting
                      ? 'Enviando pedido…'
                      : `Enviar Pedido • ${formatMoney(grandTotalCents)}`}
                  </span>
                </button>
              </div>
            </>
          )}
        </form>
      </div>
    </div>
  );
};
