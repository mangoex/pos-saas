import React, { useState, useMemo } from 'react';
import { Flame, Heart, ShoppingBag, Share2, Sparkles, Trophy, Star, Check } from 'lucide-react';
import { TrendingDish, Product } from '../types';
import { formatMoney } from '../api';
import { getProductImage, getProductIconMeta } from '../imageMap';

interface TrendingFeedProps {
  trendingDishes?: TrendingDish[];
  dishes?: TrendingDish[];
  isLoading?: boolean;
  likedProductIds: Set<string>;
  onToggleLike: (productId: string) => void;
  onOpenDetail: (product: Product) => void;
  onQuickAdd: (product: Product) => void;
  onExploreMenu?: () => void;
  publicKey?: string | null;
  restaurantName?: string;
}

export const TrendingFeed: React.FC<TrendingFeedProps> = ({
  trendingDishes: propTrendingDishes,
  dishes: propDishes,
  isLoading = false,
  likedProductIds,
  onToggleLike,
  onOpenDetail,
  onQuickAdd,
  onExploreMenu,
  publicKey,
  restaurantName,
}) => {
  const trendingDishes = propTrendingDishes || propDishes || [];
  const [filterStation, setFilterStation] = useState<'all' | 'cocina' | 'barra'>('all');
  const [shareToast, setShareToast] = useState<string | null>(null);

  const filteredDishes = useMemo(() => {
    if (filterStation === 'all') return trendingDishes;
    return trendingDishes.filter((dish) => {
      const station = (dish.station || 'cocina').toLowerCase();
      if (filterStation === 'cocina') return station === 'cocina' || station === 'kitchen' || station === 'alimentos';
      if (filterStation === 'barra') return station === 'barra' || station === 'bar' || station === 'bebidas';
      return true;
    });
  }, [trendingDishes, filterStation]);

  const handleShare = async (e: React.MouseEvent, dish: TrendingDish) => {
    e.stopPropagation();
    const currentUrl = new URL(window.location.href);
    currentUrl.searchParams.set('dish', dish.id);
    const shareUrl = currentUrl.toString();
    const shareTitle = dish.name;
    const shareText = `¡Mira este platillo tendencia${restaurantName ? ` en ${restaurantName}` : ''}!: ${dish.name} - ${dish.badge}`;

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

    // Fallback: clipboard
    try {
      if (typeof navigator !== 'undefined' && navigator.clipboard) {
        await navigator.clipboard.writeText(shareUrl);
        setShareToast(`¡Enlace copiado para ${dish.name}!`);
        setTimeout(() => setShareToast(null), 3000);
        return;
      }
    } catch {
      // ignore
    }

    const waUrl = `https://api.whatsapp.com/send?text=${encodeURIComponent(`${shareText} ${shareUrl}`)}`;
    window.open(waUrl, '_blank');
  };

  const getRankBadgeStyle = (rank: number) => {
    if (rank === 1) return { bg: 'linear-gradient(135deg, #f59e0b, #d97706)', text: '#ffffff', icon: '👑' };
    if (rank === 2) return { bg: 'linear-gradient(135deg, #94a3b8, #64748b)', text: '#ffffff', icon: '🥈' };
    if (rank === 3) return { bg: 'linear-gradient(135deg, #b45309, #78350f)', text: '#ffffff', icon: '🥉' };
    return { bg: '#f1f5f9', text: '#334155', icon: `#${rank}` };
  };

  return (
    <div className="trending-feed-container" style={{ padding: '16px 16px 80px', maxWidth: '640px', margin: '0 auto' }}>
      {/* Hero Header */}
      <div
        style={{
          background: 'linear-gradient(135deg, #0f172a 0%, #1e293b 100%)',
          borderRadius: '24px',
          padding: '24px 20px',
          color: '#ffffff',
          marginBottom: '20px',
          boxShadow: '0 10px 25px -5px rgba(15, 23, 42, 0.3)',
          position: 'relative',
          overflow: 'hidden',
        }}
      >
        <div style={{ position: 'absolute', top: '-10px', right: '-10px', opacity: 0.15, transform: 'rotate(15deg)' }}>
          <Flame size={140} color="#f59e0b" />
        </div>
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', background: 'rgba(245, 158, 11, 0.2)', border: '1px solid rgba(245, 158, 11, 0.4)', padding: '4px 12px', borderRadius: '9999px', fontSize: '12px', fontWeight: 700, color: '#f59e0b', marginBottom: '10px' }}>
          <Sparkles size={14} />
          <span>Comunidad y Tendencias mimenu</span>
        </div>
        <h1 style={{ fontSize: '24px', fontWeight: 800, margin: '0 0 6px', letterSpacing: '-0.02em' }}>
          🔥 Lo Más Pedido
        </h1>
        <p style={{ fontSize: '13px', color: '#94a3b8', margin: 0, lineHeight: 1.4 }}>
          Los platillos favoritos y más solicitados de {restaurantName || 'nuestra cocina'}. ¡Basado en pedidos reales!
        </p>
      </div>

      {/* Filter Chips */}
      <div style={{ display: 'flex', gap: '8px', overflowX: 'auto', paddingBottom: '12px', marginBottom: '12px' }}>
        <button
          type="button"
          onClick={() => setFilterStation('all')}
          style={{
            padding: '8px 16px',
            borderRadius: '9999px',
            border: 'none',
            background: filterStation === 'all' ? '#0f172a' : '#f1f5f9',
            color: filterStation === 'all' ? '#ffffff' : '#475569',
            fontWeight: 700,
            fontSize: '13px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            whiteSpace: 'nowrap',
            transition: 'all 0.15s ease',
          }}
        >
          <Trophy size={14} />
          <span>Todos los Favoritos</span>
        </button>

        <button
          type="button"
          onClick={() => setFilterStation('cocina')}
          style={{
            padding: '8px 16px',
            borderRadius: '9999px',
            border: 'none',
            background: filterStation === 'cocina' ? '#0f172a' : '#f1f5f9',
            color: filterStation === 'cocina' ? '#ffffff' : '#475569',
            fontWeight: 700,
            fontSize: '13px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            whiteSpace: 'nowrap',
            transition: 'all 0.15s ease',
          }}
        >
          <span>🍳 Platillos y Cocina</span>
        </button>

        <button
          type="button"
          onClick={() => setFilterStation('barra')}
          style={{
            padding: '8px 16px',
            borderRadius: '9999px',
            border: 'none',
            background: filterStation === 'barra' ? '#0f172a' : '#f1f5f9',
            color: filterStation === 'barra' ? '#ffffff' : '#475569',
            fontWeight: 700,
            fontSize: '13px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            whiteSpace: 'nowrap',
            transition: 'all 0.15s ease',
          }}
        >
          <span>🍹 Bebidas y Barra</span>
        </button>
      </div>

      {/* Dishes List */}
      {filteredDishes.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '40px 20px', color: '#64748b' }}>
          <p style={{ fontSize: '15px', fontWeight: 600 }}>Aún no hay tendencias registradas en esta categoría.</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {filteredDishes.map((dish) => {
            const isLiked = likedProductIds.has(dish.id);
            const rankStyle = getRankBadgeStyle(dish.rank);
            const img = dish.image_url || getProductImage(dish);
            const iconMeta = getProductIconMeta(dish);
            const comPhotosCount = dish.community_photos?.length || 0;

            return (
              <div
                key={dish.id}
                onClick={() => onOpenDetail(dish)}
                style={{
                  background: '#ffffff',
                  borderRadius: '20px',
                  border: '1px solid #e2e8f0',
                  boxShadow: '0 4px 12px rgba(0, 0, 0, 0.04)',
                  overflow: 'hidden',
                  cursor: 'pointer',
                  transition: 'transform 0.15s ease, box-shadow 0.15s ease',
                  position: 'relative',
                }}
              >
                {/* Ranking Tag on Image */}
                <div style={{ position: 'relative', height: '170px', width: '100%', background: '#f8fafc' }}>
                  {img ? (
                    <img
                      src={img}
                      alt={dish.name}
                      style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                    />
                  ) : (
                    <div
                      style={{
                        width: '100%',
                        height: '100%',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        background: iconMeta.bgGradient,
                        fontSize: '52px',
                      }}
                    >
                      {iconMeta.emoji}
                    </div>
                  )}

                  {/* Gradient Overlay for Readability */}
                  <div
                    style={{
                      position: 'absolute',
                      inset: 0,
                      background: 'linear-gradient(to top, rgba(15, 23, 42, 0.7) 0%, transparent 60%)',
                    }}
                  />

                  {/* Rank Badge */}
                  <div
                    style={{
                      position: 'absolute',
                      top: '12px',
                      left: '12px',
                      background: rankStyle.bg,
                      color: rankStyle.text,
                      padding: '4px 12px',
                      borderRadius: '9999px',
                      fontSize: '12px',
                      fontWeight: 800,
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px',
                      boxShadow: '0 4px 10px rgba(0,0,0,0.25)',
                    }}
                  >
                    <span>{rankStyle.icon}</span>
                    <span>#{dish.rank} Top</span>
                  </div>

                  {/* Action Icons (Share + Favorite) */}
                  <div style={{ position: 'absolute', top: '12px', right: '12px', display: 'flex', gap: '8px' }}>
                    <button
                      type="button"
                      onClick={(e) => handleShare(e, dish)}
                      style={{
                        width: '34px',
                        height: '34px',
                        borderRadius: '50%',
                        border: 'none',
                        background: 'rgba(15, 23, 42, 0.65)',
                        backdropFilter: 'blur(6px)',
                        color: '#ffffff',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        cursor: 'pointer',
                      }}
                      aria-label="Compartir platillo"
                    >
                      <Share2 size={16} />
                    </button>

                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onToggleLike(dish.id);
                      }}
                      style={{
                        width: '34px',
                        height: '34px',
                        borderRadius: '50%',
                        border: 'none',
                        background: 'rgba(15, 23, 42, 0.65)',
                        backdropFilter: 'blur(6px)',
                        color: isLiked ? '#ef4444' : '#ffffff',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        cursor: 'pointer',
                      }}
                      aria-label={isLiked ? 'Quitar de favoritos' : 'Agregar a favoritos'}
                    >
                      <Heart size={16} fill={isLiked ? '#ef4444' : 'none'} />
                    </button>
                  </div>

                  {/* Social Proof Chip on Image Bottom */}
                  <div
                    style={{
                      position: 'absolute',
                      bottom: '12px',
                      left: '12px',
                      background: 'rgba(255, 255, 255, 0.95)',
                      padding: '4px 10px',
                      borderRadius: '8px',
                      fontSize: '12px',
                      fontWeight: 800,
                      color: '#0f172a',
                      boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                    }}
                  >
                    <span>{dish.badge}</span>
                  </div>
                </div>

                {/* Body Content */}
                <div style={{ padding: '14px 16px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '6px' }}>
                    <div>
                      <span style={{ fontSize: '11px', color: '#64748b', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                        {dish.category_name || 'Especialidad'}
                      </span>
                      <h3 style={{ fontSize: '16px', fontWeight: 800, color: '#0f172a', margin: '2px 0 0' }}>
                        {dish.name}
                      </h3>
                    </div>
                    <span style={{ fontSize: '16px', fontWeight: 800, color: '#0f172a' }}>
                      {formatMoney(dish.price_cents)}
                    </span>
                  </div>

                  {dish.description && (
                    <p style={{ fontSize: '12px', color: '#64748b', margin: '0 0 12px', lineHeight: 1.4 }}>
                      {dish.description}
                    </p>
                  )}

                  {/* Community Photos Indicator if present */}
                  {comPhotosCount > 0 && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '12px', fontSize: '12px', color: '#047857', fontWeight: 700, background: '#f0fdf4', padding: '4px 8px', borderRadius: '8px', width: 'fit-content' }}>
                      <span>📸 {comPhotosCount} foto{comPhotosCount > 1 ? 's' : ''} de comensales verificadas</span>
                    </div>
                  )}

                  {/* Bottom Row: Satisfaction + Quick Add */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: '8px', borderTop: '1px solid #f1f5f9' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '12px', color: '#ca8a04', fontWeight: 700 }}>
                      <Star size={14} fill="#eab308" color="#ca8a04" />
                      <span>{dish.satisfaction_score || 98}% satisfacción</span>
                    </div>

                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onQuickAdd(dish);
                      }}
                      style={{
                        background: '#0f172a',
                        color: '#ffffff',
                        border: 'none',
                        borderRadius: '9999px',
                        padding: '8px 16px',
                        fontSize: '12px',
                        fontWeight: 700,
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px',
                        boxShadow: '0 2px 8px rgba(15, 23, 42, 0.15)',
                      }}
                    >
                      <ShoppingBag size={14} />
                      <span>Agregar</span>
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Share Toast */}
      {shareToast && (
        <div className="share-toast-notification">
          <Check size={16} color="#10b981" />
          <span>{shareToast}</span>
        </div>
      )}
    </div>
  );
};
