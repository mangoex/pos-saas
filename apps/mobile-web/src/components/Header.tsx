import React from 'react';
import { Search, X, Bike, ShoppingBag, Utensils, MapPin, ChevronDown } from 'lucide-react';
import { OrderType, BranchInfo } from '../types';

interface HeaderProps {
  orderType: OrderType;
  onToggleOrderType: (type: OrderType) => void;
  searchQuery: string;
  onSearchChange: (query: string) => void;
  selectedBranch: BranchInfo | null;
  onOpenBranchSelector: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  orderType,
  onToggleOrderType,
  searchQuery,
  onSearchChange,
  selectedBranch,
  onOpenBranchSelector,
}) => {
  const distanceText = selectedBranch?.distance_km !== undefined && selectedBranch?.distance_km !== null
    ? (selectedBranch.distance_km < 0.1
        ? 'Estás aquí'
        : selectedBranch.distance_km < 1
        ? `${Math.round(selectedBranch.distance_km * 1000)}m`
        : `${selectedBranch.distance_km}km`)
    : null;

  return (
    <header className="mobile-app-header">
      {/* Branch location selector banner */}
      <div
        className="mobile-header-location-bar"
        onClick={onOpenBranchSelector}
        role="button"
        tabIndex={0}
        aria-label="Cambiar sucursal"
      >
        <div className="location-bar-left">
          <MapPin size={14} className="location-pin-icon" />
          <span className="location-branch-name">
            {selectedBranch ? selectedBranch.name : 'Elige tu sucursal'}
          </span>
          {distanceText && (
            <span className="location-distance-chip">
              {distanceText}
            </span>
          )}
        </div>
        <div className="location-bar-right">
          <span>Cambiar</span>
          <ChevronDown size={13} />
        </div>
      </div>

      <div className="mobile-header-top-row">
        <div className="mobile-brand-identity">
          <div className="mobile-brand-logo-badge">🍽️</div>
          <div className="mobile-brand-text">
            <h1 className="mobile-brand-title">{selectedBranch ? selectedBranch.name : 'RestaurantOS'}</h1>
            <span className="mobile-brand-subtitle">{selectedBranch ? 'Menú Digital' : 'Fresh Food & Drinks'}</span>
          </div>
        </div>

        <div className="mobile-order-type-capsule" role="tablist" aria-label="Modalidad de pedido">
          <button
            type="button"
            className={`mobile-order-type-pill ${orderType === 'dine-in' ? 'active' : ''}`}
            onClick={() => onToggleOrderType('dine-in')}
            role="tab"
            aria-selected={orderType === 'dine-in'}
            title="Comer aquí en barra"
          >
            <Utensils size={13} />
            <span>Comer aquí</span>
          </button>

          <button
            type="button"
            className={`mobile-order-type-pill ${orderType === 'takeaway' ? 'active' : ''}`}
            onClick={() => onToggleOrderType('takeaway')}
            role="tab"
            aria-selected={orderType === 'takeaway'}
            title="Para llevar"
          >
            <ShoppingBag size={13} />
            <span>Llevar</span>
          </button>

          <button
            type="button"
            className={`mobile-order-type-pill ${orderType === 'delivery' ? 'active' : ''}`}
            onClick={() => onToggleOrderType('delivery')}
            role="tab"
            aria-selected={orderType === 'delivery'}
            title="Envío a domicilio"
          >
            <Bike size={13} />
            <span>Envío</span>
          </button>
        </div>
      </div>

      <div className="mobile-search-bar-wrapper">
        <Search size={18} className="mobile-search-icon" />
        <input
          type="search"
          className="mobile-search-input"
          placeholder="Buscar platillos, jugos, smoothies, bowls..."
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
        />
        {searchQuery.trim().length > 0 && (
          <button
            type="button"
            className="mobile-search-clear-btn"
            onClick={() => onSearchChange('')}
            aria-label="Limpiar búsqueda"
          >
            <X size={14} />
          </button>
        )}
      </div>
    </header>
  );
};
