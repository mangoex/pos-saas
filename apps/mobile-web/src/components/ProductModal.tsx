import React, { useState, useEffect, useMemo, useRef } from 'react';
import { X, Heart, Plus, Minus, ShoppingBag, Flame, Clock, ChefHat, Share2, Check } from 'lucide-react';
import { Product, SelectedModifier, CommunityPhoto, CartItem } from '../types';
import { formatMoney, fetchProductCommunityPhotos } from '../api';
import { getProductIconMeta, getProductImage } from '../imageMap';
import { calculateLineTotal, currentModifiers, validateCartDraft } from '../utils/cartPersonalization';

interface ProductModalProps {
  product: Product;
  isLiked: boolean;
  onToggleLike: (productId: string) => void;
  onClose: () => void;
  onAddToCart: (product: Product, quantity: number, notes?: string, modifiers?: SelectedModifier[]) => void;
  publicKey?: string | null;
  restaurantName?: string;
  initialItem?: CartItem;
  onSave?: (quantity: number, notes: string, modifiers: SelectedModifier[]) => void;
  blockedReason?: string;
}

export const ProductModal: React.FC<ProductModalProps> = ({
  product,
  isLiked,
  onToggleLike,
  onClose,
  onAddToCart,
  publicKey,
  restaurantName,
  initialItem,
  onSave,
  blockedReason,
}) => {
  const isEditing = Boolean(initialItem && onSave);
  const dialogRef = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  useEffect(() => { onCloseRef.current = onClose; }, [onClose]);
  const [quantity, setQuantity] = useState(initialItem?.quantity ?? 1);
  const [notes, setNotes] = useState(initialItem?.notes ?? '');
  const [selectedModifiers, setSelectedModifiers] = useState<Record<string, SelectedModifier>>(() => {
    const current = currentModifiers(product, initialItem?.modifiers ?? []);
    return Object.fromEntries(current.map((modifier) => [modifier.option_id, modifier]));
  });
  const [modifierError, setModifierError] = useState('');
  const [shareToast, setShareToast] = useState<string | null>(null);
  const [communityPhotos, setCommunityPhotos] = useState<CommunityPhoto[]>(product.community_photos || []);

  useEffect(() => {
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const returnToCartId = initialItem?.cart_id;
    const dialog = dialogRef.current;
    const focusableSelector = 'button:not(:disabled), input:not(:disabled), textarea:not(:disabled), select:not(:disabled), [href], [tabindex]:not([tabindex="-1"])';
    const focusFirst = () => dialog?.querySelector<HTMLElement>(focusableSelector)?.focus();
    focusFirst();

    const trapFocus = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== 'Tab' || !dialog) return;
      const focusable = Array.from(dialog.querySelectorAll<HTMLElement>(focusableSelector));
      if (focusable.length === 0) {
        event.preventDefault();
        dialog.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && (document.activeElement === first || !dialog.contains(document.activeElement))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (document.activeElement === last || !dialog.contains(document.activeElement))) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', trapFocus);
    return () => {
      document.removeEventListener('keydown', trapFocus);
      window.requestAnimationFrame(() => {
        const cartEditTrigger = returnToCartId
          ? Array.from(document.querySelectorAll<HTMLElement>('[data-cart-edit-trigger]'))
            .find((element) => element.dataset.cartEditTrigger === returnToCartId)
          : null;
        const target = cartEditTrigger ?? previousFocus;
        if (target?.isConnected) target.focus();
      });
    };
  }, []);

  useEffect(() => {
    const current = currentModifiers(product, initialItem?.modifiers ?? []);
    setQuantity(initialItem?.quantity ?? 1);
    setNotes(initialItem?.notes ?? '');
    setSelectedModifiers(Object.fromEntries(current.map((modifier) => [modifier.option_id, modifier])));
    setModifierError('');
  }, [product.id, initialItem?.cart_id]);

  useEffect(() => {
    if (publicKey && (!product.community_photos || product.community_photos.length === 0)) {
      fetchProductCommunityPhotos(publicKey, product.id).then((photos) => {
        if (photos && photos.length > 0) {
          setCommunityPhotos(photos);
        }
      });
    }
  }, [publicKey, product.id, product.community_photos]);

  const handleShare = async () => {
    const currentUrl = new URL(window.location.href);
    currentUrl.searchParams.set('dish', product.id);
    const shareUrl = currentUrl.toString();
    const shareTitle = product.name;
    const shareText = `¡Mira este delicioso platillo${restaurantName ? ` en ${restaurantName}` : ''}!: ${product.name}`;

    if (typeof navigator !== 'undefined' && navigator.share) {
      try {
        await navigator.share({
          title: shareTitle,
          text: shareText,
          url: shareUrl,
        });
        return;
      } catch (err: any) {
        if (err?.name === 'AbortError') return;
      }
    }

    // Fallback: Copy to clipboard
    try {
      if (typeof navigator !== 'undefined' && navigator.clipboard) {
        await navigator.clipboard.writeText(shareUrl);
        setShareToast('¡Enlace copiado al portapapeles!');
        setTimeout(() => setShareToast(null), 3000);
        return;
      }
    } catch {
      // ignore
    }

    // Fallback to WhatsApp
    const waUrl = `https://api.whatsapp.com/send?text=${encodeURIComponent(`${shareText} ${shareUrl}`)}`;
    window.open(waUrl, '_blank');
  };

  const selectedModifierList = useMemo(() => Object.values(selectedModifiers), [selectedModifiers]);
  const staleModifiers = useMemo(() => {
    const availableIds = new Set((product.modifier_groups ?? []).flatMap((group) => group.options.map((option) => option.id)));
    return selectedModifierList.filter((modifier) => !availableIds.has(modifier.option_id));
  }, [product.modifier_groups, selectedModifierList]);
  const validationMessage = blockedReason || (staleModifiers.length > 0
    ? 'Algunas opciones ya no están disponibles. Quítalas o cancela la edición.'
    : validateCartDraft(product, quantity, selectedModifierList));
  const totalCents = calculateLineTotal(product, quantity, selectedModifierList);
  const currentOriginalLineTotal = initialItem
    ? calculateLineTotal(product, initialItem.quantity, currentModifiers(product, initialItem.modifiers ?? []))
    : null;
  const linePriceChanged = initialItem && currentOriginalLineTotal !== null && currentOriginalLineTotal !== initialItem.line_total_cents;
  const iconMeta = getProductIconMeta(product);
  const productImg = product.image_url || getProductImage(product);

  const toggleModifier = (groupId: string, option: SelectedModifier, maximum: number) => {
    setModifierError('');
    setSelectedModifiers((current) => {
      if (current[option.option_id]) {
        const { [option.option_id]: _removed, ...rest } = current;
        return rest;
      }
      const inGroup = Object.values(current).filter((selection) => {
        const sourceGroup = product.modifier_groups?.find((group) => group.options.some((candidate) => candidate.id === selection.option_id));
        return sourceGroup?.id === groupId;
      }).length;
      if (inGroup >= maximum) {
        setModifierError('Esta opción ya alcanzó el máximo permitido.');
        return current;
      }
      return { ...current, [option.option_id]: option };
    });
  };

  const setModifierText = (optionId: string, text: string) => {
    setSelectedModifiers((current) => current[optionId]
      ? { ...current, [optionId]: { ...current[optionId], text } }
      : current);
  };

  const handleSave = () => {
    if (validationMessage) {
      setModifierError(validationMessage);
      return;
    }
    if (isEditing) {
      onSave?.(quantity, notes.trim(), selectedModifierList);
      return;
    }
    onAddToCart(product, quantity, notes.trim() || undefined, selectedModifierList);
    onClose();
  };

  return (
    <div className={`product-modal-backdrop ${isEditing ? 'product-modal-editing-backdrop' : ''}`} onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <div
        ref={dialogRef}
        className="product-modal-bottom-sheet"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="product-modal-title"
        tabIndex={-1}
      >
        <div
          className={`product-modal-hero-visual ${productImg ? 'has-img' : 'product-modal-icon-hero'}`}
          style={productImg ? {} : {
            background: iconMeta.bgGradient,
            borderBottom: `2px solid ${iconMeta.borderColor}`,
          }}
        >
          {product.is_promo && (
            <div className="product-card-promo-ribbon" style={{ top: 12, left: 12 }}>
              <span>🔥</span>
              <span>{product.promo_badge_text || 'PROMOCIÓN'}</span>
            </div>
          )}
          {productImg ? (
            <>
              <img
                src={productImg}
                alt={product.name}
                className="product-modal-hero-img"
              />
              <div className="product-modal-hero-gradient" />
            </>
          ) : (
            <div className="product-modal-icon-avatar-large">
              <span className="product-modal-icon-large-emoji" role="img" aria-label={iconMeta.badgeLabel}>
                {iconMeta.emoji}
              </span>
              <span className="product-modal-icon-badge-pill" style={{ color: iconMeta.textColor }}>
                {iconMeta.badgeLabel}
              </span>
            </div>
          )}

          <button
            type="button"
            className="product-modal-close-btn"
            onClick={onClose}
            aria-label="Cerrar modal"
          >
            <X size={20} />
          </button>

          <button
            type="button"
            className="product-modal-share-btn"
            onClick={handleShare}
            aria-label="Compartir este platillo"
          >
            <Share2 size={18} />
          </button>

          <button
            type="button"
            className={`product-modal-fav-btn ${isLiked ? 'liked' : ''}`}
            onClick={() => onToggleLike(product.id)}
            aria-label={isLiked ? 'Quitar de favoritos' : 'Agregar a favoritos'}
          >
            <Heart
              size={20}
              fill={isLiked ? '#ef4444' : 'none'}
              color={isLiked ? '#ef4444' : '#ffffff'}
            />
          </button>
        </div>

        <div className="product-modal-content-body">
          <div className="product-modal-title-row">
            <div className="product-modal-title-left">
              <span className="product-modal-category-chip">
                {product.category_name || 'Especialidad'}
              </span>
              <h2 className="product-modal-name" id="product-modal-title">{isEditing ? 'Editar producto' : product.name}</h2>
              {isEditing && <p className="product-modal-edit-product-name">{product.name}</p>}
            </div>
            <div className="product-modal-price-tag">
              {product.is_promo && product.promo_price_cents && product.promo_price_cents < product.price_cents ? (
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end' }}>
                  <span style={{ textDecoration: 'line-through', fontSize: '0.8rem', color: '#94a3b8', fontWeight: 500, lineHeight: 1 }}>
                    {formatMoney(product.price_cents)}
                  </span>
                  <span style={{ color: '#ea580c', fontWeight: 800 }}>
                    {formatMoney(product.promo_price_cents)}
                  </span>
                </div>
              ) : (
                formatMoney(product.price_cents)
              )}
            </div>
          </div>

          <div className="product-modal-badges-bar">
            {product.calories && (
              <span className="product-modal-meta-chip">
                <Flame size={14} className="chip-icon-flame" />
                <span>{product.calories}</span>
              </span>
            )}
            {product.prep_time && (
              <span className="product-modal-meta-chip">
                <Clock size={14} className="chip-icon-clock" />
                <span>{product.prep_time}</span>
              </span>
            )}
            <span className="product-modal-meta-chip">
              <ChefHat size={14} className="chip-icon-chef" />
              <span>{product.station === 'cocina' ? 'Cocina' : 'Barra'}</span>
            </span>
          </div>

          {product.description && (
            <div className="product-modal-section">
              <span className="product-modal-section-heading">Descripción</span>
              <p className="product-modal-description-text">{product.description}</p>
            </div>
          )}

          {communityPhotos.length > 0 && (
            <div className="product-modal-section">
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                <span className="product-modal-section-heading">📸 Fotos de Comensales ({communityPhotos.length})</span>
                <span style={{ fontSize: '11px', color: '#047857', fontWeight: 700, background: '#ecfdf5', padding: '2px 8px', borderRadius: '12px' }}>
                  ✓ Verificadas
                </span>
              </div>
              <div className="community-photos-carousel">
                {communityPhotos.map((photo, i) => (
                  <div key={photo.id || i} className="community-photo-card">
                    <img src={photo.image_url} alt={product.name} className="community-photo-img" />
                    <div className="community-photo-meta">
                      <span className="community-photo-author">Por {photo.customer_name}</span>
                      {photo.caption && <p className="community-photo-caption">"{photo.caption}"</p>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {(product.modifier_groups ?? []).map((group) => (
            <div className="product-modal-section" key={group.id}>
              <span className="product-modal-section-heading">
                {group.name}{group.is_required ? ' *' : ''}
              </span>
              <div className="product-modal-quick-choices-grid">
                {group.options.map((option) => {
                  const selected = selectedModifiers[option.id];
                  return (
                    <div key={option.id}>
                      <button
                        type="button"
                        className={`product-modal-choice-pill ${selected ? 'active' : ''}`}
                        aria-pressed={Boolean(selected)}
                        onClick={() => toggleModifier(group.id, {
                          option_id: option.id,
                          name: option.name,
                          price_delta_cents: option.price_delta_cents,
                          selection_kind: option.selection_kind,
                        }, group.maximum_selections)}
                      >
                        {option.name}{option.price_delta_cents ? ` (${option.price_delta_cents > 0 ? '+' : ''}${formatMoney(option.price_delta_cents)})` : ''}
                      </button>
                      {selected && option.selection_kind === 'modifier' && (
                        <input
                          type="text"
                          className="product-modal-notes-input"
                          placeholder="Detalle para cocina (si aplica)"
                          value={selected.text ?? ''}
                          maxLength={240}
                          onChange={(event) => setModifierText(option.id, event.target.value)}
                        />
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
          {staleModifiers.length > 0 && (
            <div className="product-modal-option-conflict" role="alert">
              <p>Estas opciones seleccionadas ya no aparecen en el catálogo actual. Revísalas antes de guardar:</p>
              {staleModifiers.map((modifier) => (
                <div className="product-modal-obsolete-option" key={modifier.option_id}>
                  <span>{modifier.name}</span>
                  <button
                    type="button"
                    onClick={() => setSelectedModifiers((current) => {
                      const { [modifier.option_id]: _removed, ...remaining } = current;
                      return remaining;
                    })}
                    aria-label={`Quitar opción obsoleta ${modifier.name}`}
                  >
                    Quitar opción
                  </button>
                </div>
              ))}
            </div>
          )}
          {(validationMessage || modifierError) && staleModifiers.length === 0 && (
            <p role="alert" className="product-modal-validation-message">{validationMessage || modifierError}</p>
          )}
          {linePriceChanged && initialItem && (
            <p className="product-modal-price-change-notice" role="status">
              El total de esta línea cambió con el catálogo actual: {formatMoney(initialItem.line_total_cents)} → {formatMoney(currentOriginalLineTotal)}. Revisa el nuevo total y guarda los cambios.
            </p>
          )}

          <div className="product-modal-section">
            <label className="product-modal-section-heading" htmlFor="modal-notes-input">
              Instrucciones Especiales
            </label>
            <textarea
              id="modal-notes-input"
              className="product-modal-notes-input"
              rows={2}
              placeholder="Ej: Sin cebolla, salsa aparte, bien frío, etc..."
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              maxLength={200}
            />
          </div>
        </div>

        <div className="product-modal-sticky-footer">
          <div className="product-modal-quantity-stepper">
            <button
              type="button"
              className="product-modal-stepper-btn"
              onClick={() => setQuantity(Math.max(1, quantity - 1))}
              disabled={quantity <= 1}
              aria-label="Disminuir cantidad"
            >
              <Minus size={16} />
            </button>
            <span className="product-modal-stepper-count">{quantity}</span>
            <button
              type="button"
              className="product-modal-stepper-btn"
              onClick={() => setQuantity(Math.min(99, quantity + 1))}
              aria-label="Aumentar cantidad"
            >
              <Plus size={16} />
            </button>
          </div>

          <div className="product-modal-footer-actions">
            {isEditing && (
              <button type="button" className="product-modal-cancel-edit-btn" onClick={onClose}>
                Cancelar
              </button>
            )}
            <button
              type="button"
              className="product-modal-add-cart-btn"
              onClick={handleSave}
              disabled={Boolean(validationMessage)}
            >
              <ShoppingBag size={19} />
              <span>{isEditing ? 'Guardar cambios' : 'Agregar'} • {formatMoney(totalCents)}</span>
            </button>
          </div>
        </div>

        {shareToast && (
          <div className="share-toast-notification">
            <Check size={16} color="#10b981" />
            <span>{shareToast}</span>
          </div>
        )}
      </div>
    </div>
  );
};
