import React from 'react';
import { Compass, Mic, Heart, ShoppingBag } from 'lucide-react';

export type NavTab = 'explore' | 'trending' | 'favorites' | 'cart';

interface BottomNavProps {
  currentTab: NavTab;
  onSelectTab: (tab: NavTab) => void;
  cartCount: number;
  favoritesCount: number;
  onOpenVoiceModal?: () => void;
}

export const BottomNav: React.FC<BottomNavProps> = ({
  currentTab,
  onSelectTab,
  cartCount,
  favoritesCount,
  onOpenVoiceModal,
}) => {
  return (
    <nav className="mobile-bottom-nav" role="navigation" aria-label="Navegación principal">
      <div className="mobile-bottom-nav-glass">
        <button
          type="button"
          className={`mobile-nav-btn ${currentTab === 'explore' ? 'active' : ''}`}
          onClick={() => onSelectTab('explore')}
        >
          <Compass size={22} strokeWidth={currentTab === 'explore' ? 2.5 : 2} />
          <span>Menú</span>
        </button>

        <button
          type="button"
          className="mobile-nav-btn"
          onClick={onOpenVoiceModal}
        >
          <Mic size={22} strokeWidth={2} />
          <span>Dictar</span>
        </button>

        <button
          type="button"
          className={`mobile-nav-btn ${currentTab === 'favorites' ? 'active' : ''}`}
          onClick={() => onSelectTab('favorites')}
        >
          <div className="mobile-nav-icon-container">
            <Heart
              size={22}
              fill={currentTab === 'favorites' ? '#ef4444' : 'none'}
              strokeWidth={currentTab === 'favorites' ? 2.5 : 2}
            />
            {favoritesCount > 0 && (
              <span className="mobile-nav-badge-count">{favoritesCount}</span>
            )}
          </div>
          <span>Favoritos</span>
        </button>

        <button
          type="button"
          className={`mobile-nav-btn ${currentTab === 'cart' ? 'active' : ''}`}
          onClick={() => onSelectTab('cart')}
        >
          <div className="mobile-nav-icon-container">
            <ShoppingBag size={22} strokeWidth={currentTab === 'cart' ? 2.5 : 2} />
            {cartCount > 0 && (
              <span className="mobile-nav-badge-count green">{cartCount}</span>
            )}
          </div>
          <span>Carrito</span>
        </button>
      </div>
    </nav>
  );
};
