import React from 'react';
import { Compass, Flame, Heart, ShoppingBag } from 'lucide-react';

export type NavTab = 'explore' | 'trending' | 'favorites' | 'cart';

interface BottomNavProps {
  currentTab: NavTab;
  onSelectTab: (tab: NavTab) => void;
  cartCount: number;
  favoritesCount: number;
}

export const BottomNav: React.FC<BottomNavProps> = ({
  currentTab,
  onSelectTab,
  cartCount,
  favoritesCount,
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
          className={`mobile-nav-btn ${currentTab === 'trending' ? 'active' : ''}`}
          onClick={() => onSelectTab('trending')}
        >
          <Flame
            size={22}
            color={currentTab === 'trending' ? '#f59e0b' : 'currentColor'}
            strokeWidth={currentTab === 'trending' ? 2.5 : 2}
          />
          <span>Tendencias</span>
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
