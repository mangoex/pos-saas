import React, { useState } from 'react';
import { X, Heart, Plus, Minus, ShoppingBag, Flame, Clock, ChefHat } from 'lucide-react';
import { Product, SelectedModifier } from '../types';
import { formatMoney } from '../api';
import { getProductIconMeta, getProductImage } from '../imageMap';

interface ProductModalProps {
  product: Product;
  isLiked: boolean;
  onToggleLike: (productId: string) => void;
  onClose: () => void;
  onAddToCart: (product: Product, quantity: number, notes?: string, modifiers?: SelectedModifier[]) => void;
}

export const ProductModal: React.FC<ProductModalProps> = ({
  product,
  isLiked,
  onToggleLike,
  onClose,
  onAddToCart,
}) => {
  const [quantity, setQuantity] = useState(1);
  const [notes, setNotes] = useState('');
  const [selectedModifiers, setSelectedModifiers] = useState<Record<string, SelectedModifier>>({});
  const [modifierError, setModifierError] = useState('');

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
            className={`product-modal-fav-btn ${isLiked ? 'liked' : ''}`}
            onClick={() => onToggleLike(product.id)}
            aria-label={isLiked ? 'Quitar de favoritos' : 'Agregar a favoritos'}
          >
            <Heart
              size={20}
              fill={isLiked ? '#ef4444' : 'none'}
              color={isLiked ? '#ef4444' : '#0f172a'}
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
      </div>
    </div>
  );
};
