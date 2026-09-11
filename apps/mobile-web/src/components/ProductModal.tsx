import React, { useState, useEffect } from 'react';
import { X, Heart, Plus, Minus, ShoppingBag, Flame, Clock, ChefHat, Share2, Check } from 'lucide-react';
import { Product, SelectedModifier, CommunityPhoto } from '../types';
import { formatMoney, fetchProductCommunityPhotos } from '../api';
import { getProductIconMeta, getProductImage } from '../imageMap';

interface ProductModalProps {
  product: Product;
  isLiked: boolean;
  onToggleLike: (productId: string) => void;
  onClose: () => void;
  onAddToCart: (product: Product, quantity: number, notes?: string, modifiers?: SelectedModifier[]) => void;
  publicKey?: string | null;
  restaurantName?: string;
}

export const ProductModal: React.FC<ProductModalProps> = ({
  product,
  isLiked,
  onToggleLike,
  onClose,
  onAddToCart,
  publicKey,
  restaurantName,
}) => {
  const [quantity, setQuantity] = useState(1);
  const [notes, setNotes] = useState('');
  const [selectedModifiers, setSelectedModifiers] = useState<Record<string, SelectedModifier>>({});
  const [modifierError, setModifierError] = useState('');
  const [shareToast, setShareToast] = useState<string | null>(null);
  const [communityPhotos, setCommunityPhotos] = useState<CommunityPhoto[]>(product.community_photos || []);

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

  const modifierDeltaCents = Object.values(selectedModifiers).reduce(
    (sum, modifier) => sum + modifier.price_delta_cents,
    0,
  );
  const totalCents = (product.price_cents + modifierDeltaCents) * quantity;
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

  const handleAdd = () => {
    const incompleteGroup = (product.modifier_groups ?? []).find((group) => {
      const count = group.options.filter((option) => selectedModifiers[option.id]).length;
      return count < group.minimum_selections;
    });
    if (incompleteGroup) {
      setModifierError(`${incompleteGroup.name} requiere una selección.`);
      return;
    }
    onAddToCart(product, quantity, notes.trim() || undefined, Object.values(selectedModifiers));
    onClose();
  };

  return (
    <div className="product-modal-backdrop" onClick={onClose}>
      <div
        className="product-modal-bottom-sheet"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={product.name}
      >
        <div
          className={`product-modal-hero-visual ${productImg ? 'has-img' : 'product-modal-icon-hero'}`}
          style={productImg ? {} : {
            background: iconMeta.bgGradient,
            borderBottom: `2px solid ${iconMeta.borderColor}`,
          }}
        >
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
              <h2 className="product-modal-name">{product.name}</h2>
            </div>
            <div className="product-modal-price-tag">
              {formatMoney(product.price_cents)}
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
          {modifierError && <p role="alert" className="cart-item-notes-text">{modifierError}</p>}

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

          <button
            type="button"
            className="product-modal-add-cart-btn"
            onClick={handleAdd}
          >
            <ShoppingBag size={19} />
            <span>Agregar • {formatMoney(totalCents)}</span>
          </button>
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
