import React, { useState, useMemo, useEffect } from 'react';
import { X, Plus, Minus, Trash2, Banknote, CreditCard, ArrowRightLeft, Send, ShoppingBag, MapPin, User, Phone, CheckCircle2, Utensils, Bike, Sparkles, Coffee, CupSoda, Sandwich, Salad, Wheat, Package } from 'lucide-react';
import { CartItem, CustomerOrderInfo, OrderType, PaymentMethod, BranchInfo, Product } from '../types';
import { formatMoney, fetchOrderUpsellRecommendations } from '../api';
import { getProductIconMeta, getProductImage } from '../imageMap';

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
  onOpenBranchSelector,
  onClose,
  onUpdateQuantity,
  onRemoveItem,
  onQuickAddProduct,
  onSubmitOrder,
  isSubmitting,
  submitError,
}) => {
  const [orderType, setOrderType] = useState<OrderType>(initialOrderType);
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [street, setStreet] = useState('');
  const [number, setNumber] = useState('');
  const [neighborhood, setNeighborhood] = useState('');
  const [addressNotes, setAddressNotes] = useState('');
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod>('cash');
  const [cashAmount, setCashAmount] = useState('');
  const [orderNotes, setOrderNotes] = useState('');
  const [formError, setFormError] = useState('');
  const [aiRecs, setAiRecs] = useState<Array<{ product_id: string; product_name: string; price_cents: number; reason: string }>>([]);

  const totalCents = items.reduce((acc, item) => acc + item.line_total_cents, 0);

  const cartProductIdsKey = items.map((i) => i.product.id).sort().join(',');
  const selectedBranchId = selectedBranch?.id;

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

    if (!name.trim()) {
      setFormError('Por favor ingresa tu nombre completo.');
      return;
    }
    if (!phone.trim() || phone.trim().length < 8) {
      setFormError('Por favor ingresa un número de teléfono celular válido.');
      return;
    }
    if (orderType === 'delivery') {
      if (!street.trim() || !number.trim() || !neighborhood.trim()) {
        setFormError('Para entrega a domicilio, ingresa calle, número y colonia.');
        return;
      }
    }

    const orderInfo: CustomerOrderInfo = {
      name: name.trim(),
      phone: phone.trim(),
      order_type: orderType,
      address_street: street.trim(),
      address_number: number.trim(),
      address_neighborhood: neighborhood.trim(),
      address_notes: addressNotes.trim(),
      payment_method: paymentMethod,
      cash_amount: paymentMethod === 'cash' ? cashAmount.trim() : undefined,
      order_notes: orderNotes.trim(),
    };

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

        <form onSubmit={handleSubmit} className="cart-drawer-form-body">
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
                      const upsellImg = prod.image_url || getProductImage(prod);
                      return (
                        <div key={prod.id} className="cart-upsell-card">
                          <div
                            className="cart-upsell-card-thumb"
                            style={{
                              background: iconMeta.bgGradient,
                              borderColor: iconMeta.borderColor,
                            }}
                          >
                            {upsellImg ? (
                              <img
                                src={upsellImg}
                                alt={prod.name}
                                className="cart-upsell-card-img"
                                onError={(e) => { (e.currentTarget as HTMLElement).style.display = 'none'; }}
                              />
                            ) : (
                              <span className="cart-upsell-card-icon" aria-hidden="true">
                                {getRecommendationIcon(prod)}
                              </span>
                            )}
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

              {/* Branch Information card */}
              <div className="cart-form-section">
                <label className="cart-form-section-label">Sucursal de Preparación</label>
                <div className="cart-branch-card-modern">
                  <div className="cart-branch-left">
                    <div className="cart-branch-icon-badge">
                      <MapPin size={18} />
                    </div>
                    <div className="cart-branch-info-col">
                      <div className="cart-branch-name-row">
                        <span className="cart-branch-name-title">
                          {selectedBranch ? selectedBranch.name : 'Sucursal asignada'}
                        </span>
                        {selectedBranch?.distance_km !== undefined && selectedBranch?.distance_km !== null && (
                          <span className="cart-branch-distance-pill">
                            {selectedBranch.distance_km < 0.1
                              ? 'Estás aquí'
                              : selectedBranch.distance_km < 1
                              ? `${Math.round(selectedBranch.distance_km * 1000)}m`
                              : `${selectedBranch.distance_km}km`}
                          </span>
                        )}
                      </div>
                      {selectedBranch?.street && (
                        <span className="cart-branch-address-sub">
                          {selectedBranch.street} {selectedBranch.exterior_number ? `#${selectedBranch.exterior_number}` : ''}
                          {selectedBranch.neighborhood ? `, Col. ${selectedBranch.neighborhood}` : ''}
                        </span>
                      )}
                      {selectedBranch?.cross_streets && (
                        <span className="cart-branch-cross-streets">
                          🛣️ Entre: {selectedBranch.cross_streets}
                        </span>
                      )}
                    </div>
                  </div>
                  {onOpenBranchSelector && (
                    <button
                      type="button"
                      onClick={onOpenBranchSelector}
                      className="btn-cart-change-branch"
                    >
                      Cambiar
                    </button>
                  )}
                </div>
              </div>

              {/* Order Mode selector (Social Style like Image 3) */}
              <div className="cart-form-section">
                <label className="cart-form-section-label">Modalidad de consumo</label>
                <div className="social-mode-selector-container" role="tablist" aria-label="Modalidad de consumo">
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
                    <span className="social-mode-card-label">Llevar</span>
                  </button>

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
                </div>
              </div>

              {/* Customer Info */}
              <div className="cart-form-section">
                <label className="cart-form-section-label">Tus Datos de Contacto</label>
                <div className="cart-form-fields-grid">
                  <div className="cart-input-wrapper">
                    <User size={16} className="cart-input-icon" />
                    <input
                      type="text"
                      className="cart-input-field"
                      placeholder="Tu nombre completo *"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      required
                    />
                  </div>

                  <div className="cart-input-wrapper">
                    <Phone size={16} className="cart-input-icon" />
                    <input
                      type="tel"
                      className="cart-input-field"
                      placeholder="Teléfono Celular *"
                      value={phone}
                      onChange={(e) => setPhone(e.target.value)}
                      required
                    />
                  </div>
                </div>
              </div>

              {/* Delivery Address if delivery mode */}
              {orderType === 'delivery' && (
                <div className="cart-form-section">
                  <label className="cart-form-section-label">Dirección de Entrega</label>
                  <div className="cart-form-fields-grid">
                    <div className="cart-input-wrapper">
                      <MapPin size={16} className="cart-input-icon" />
                      <input
                        type="text"
                        className="cart-input-field"
                        placeholder="Calle *"
                        value={street}
                        onChange={(e) => setStreet(e.target.value)}
                        required
                      />
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.5fr', gap: '8px' }}>
                      <input
                        type="text"
                        className="cart-input-field no-icon"
                        placeholder="No. Ext / Int *"
                        value={number}
                        onChange={(e) => setNumber(e.target.value)}
                        required
                      />
                      <input
                        type="text"
                        className="cart-input-field no-icon"
                        placeholder="Colonia *"
                        value={neighborhood}
                        onChange={(e) => setNeighborhood(e.target.value)}
                        required
                      />
                    </div>

                    <input
                      type="text"
                      className="cart-input-field no-icon"
                      placeholder="Referencias de entrega (ej: Portón café, timbre blanco)"
                      value={addressNotes}
                      onChange={(e) => setAddressNotes(e.target.value)}
                    />
                  </div>
                </div>
              )}

              {/* Payment Methods */}
              <div className="cart-form-section">
                <label className="cart-form-section-label">Forma de Pago</label>
                <div className="cart-payment-methods-grid">
                  <button
                    type="button"
                    className={`cart-payment-method-pill ${paymentMethod === 'cash' ? 'active' : ''}`}
                    onClick={() => setPaymentMethod('cash')}
                  >
                    <Banknote size={18} />
                    <span>Efectivo</span>
                  </button>

                  <button
                    type="button"
                    className={`cart-payment-method-pill ${paymentMethod === 'card' ? 'active' : ''}`}
                    onClick={() => setPaymentMethod('card')}
                  >
                    <CreditCard size={18} />
                    <span>Tarjeta (Terminal)</span>
                  </button>

                  <button
                    type="button"
                    className={`cart-payment-method-pill ${paymentMethod === 'transfer' ? 'active' : ''}`}
                    onClick={() => setPaymentMethod('transfer')}
                  >
                    <ArrowRightLeft size={18} />
                    <span>Transferencia</span>
                  </button>
                </div>

                {paymentMethod === 'cash' && (
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

              {/* Financial summary breakdown */}
              <div className="cart-financial-summary-card">
                <div className="cart-summary-line">
                  <span>Subtotal de productos</span>
                  <span>{formatMoney(totalCents)}</span>
                </div>
                <div className="cart-summary-line">
                  <span>Costo de envío</span>
                  <span style={{ color: '#16a34a', fontWeight: 700 }}>
                    {orderType === 'takeaway' ? 'No aplica' : 'Gratis'}
                  </span>
                </div>
                <div className="cart-summary-total-line">
                  <strong>Total a Pagar</strong>
                  <strong className="cart-total-value">{formatMoney(totalCents)}</strong>
                </div>
              </div>

              <div className="cart-submit-sticky-bar">
                {submitError && <p className="cart-form-error-alert" role="alert">{submitError}</p>}
                <button
                  type="submit"
                  className="btn-cart-submit-order"
                  disabled={isSubmitting || items.length === 0}
                >
                  <Send size={18} />
                  <span>
                    {isSubmitting ? 'Enviando pedido…' : `Enviar Pedido • ${formatMoney(totalCents)}`}
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
