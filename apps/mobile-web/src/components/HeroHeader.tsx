import React, { useRef, useState, useEffect, useCallback } from 'react';
import { Category, BranchInfo } from '../types';
import { getCategoryCover, getCategoryIcon } from '../imageMap';
import { Search, X, MapPin, ChevronDown, ChevronLeft, ChevronRight, Navigation } from 'lucide-react';

interface HeroHeaderProps {
  categories: Category[];
  activeCategoryId: string;
  onSelectCategory: (categoryId: string) => void;
  onCategoryCardClick?: (categoryId: string) => void;
  productsCountByCategory?: Record<string, number>;
  searchQuery: string;
  onSearchChange: (query: string) => void;
  selectedBranch: BranchInfo | null;
  onOpenBranchSelector: () => void;
  onRefreshLocation?: () => void;
  isLoadingLocation?: boolean;
}

export const HeroHeader: React.FC<HeroHeaderProps> = ({
  categories,
  activeCategoryId,
  onSelectCategory,
  onCategoryCardClick,
  productsCountByCategory = {},
  searchQuery,
  onSearchChange,
  selectedBranch,
  onOpenBranchSelector,
  onRefreshLocation,
  isLoadingLocation = false,
}) => {
  const carouselRef = useRef<HTMLDivElement>(null);
  const [activeIndex, setActiveIndex] = useState(0);

  // Sync active index when activeCategoryId changes
  useEffect(() => {
    const idx = categories.findIndex((c) => c.id === activeCategoryId);
    if (idx !== -1) {
      setActiveIndex(idx);
    }
  }, [activeCategoryId, categories]);

  // Handle scroll to calculate visible card index
  const handleScroll = useCallback(() => {
    const el = carouselRef.current;
    if (!el || categories.length === 0) return;
    const scrollLeft = el.scrollLeft;
    const itemWidth = el.clientWidth;
    if (itemWidth === 0) return;
    const newIdx = Math.min(
      categories.length - 1,
      Math.max(0, Math.round(scrollLeft / itemWidth))
    );
    setActiveIndex(newIdx);
  }, [categories.length]);

  const scrollToCategoryIndex = (index: number) => {
    const el = carouselRef.current;
    if (!el) return;
    const cards = el.querySelectorAll<HTMLElement>('.hero-panoramic-card');
    if (cards[index]) {
      cards[index].scrollIntoView({
        behavior: 'smooth',
        inline: 'start',
        block: 'nearest',
      });
    }
    setActiveIndex(index);
    if (categories[index]) {
      onSelectCategory(categories[index].id);
    }
  };

  const handleScrollLeft = (e: React.MouseEvent) => {
    e.stopPropagation();
    scrollToCategoryIndex(Math.max(0, activeIndex - 1));
  };

  const handleScrollRight = (e: React.MouseEvent) => {
    e.stopPropagation();
    scrollToCategoryIndex(Math.min(categories.length - 1, activeIndex + 1));
  };

  const distanceText = selectedBranch?.distance_km !== undefined && selectedBranch?.distance_km !== null
    ? (selectedBranch.distance_km < 0.1
        ? 'Estás aquí'
        : selectedBranch.distance_km < 1
        ? `${Math.round(selectedBranch.distance_km * 1000)}m`
        : `${selectedBranch.distance_km}km`)
    : null;

  if (categories.length === 0) return null;

  return (
    <header className="mobile-hero-header" aria-label="Cabecera principal con menú panorámico">
      {/* Top Floating Glassmorphic Location & Branch Bar */}
      <div className="hero-top-nav-bar">
        {/* Brand Identity / Logo badge */}
        <div className="hero-brand-badge" title={selectedBranch ? selectedBranch.name : 'RestaurantOS'}>
          <span className="hero-brand-emoji" role="img" aria-label="Restaurante">🍽️</span>
          <span className="hero-brand-name">{selectedBranch ? selectedBranch.name : 'RestaurantOS'}</span>
        </div>

        {/* Branch / Location Selector Capsule */}
        <button
          type="button"
          className="hero-location-capsule"
          onClick={onOpenBranchSelector}
          aria-label="Cambiar sucursal"
        >
          <div className="hero-location-icon-wrap">
            <MapPin size={15} className="hero-location-pin" />
          </div>
          <div className="hero-location-text-group">
            <span className="hero-location-eyebrow">Tu sucursal</span>
            <div className="hero-location-title-row">
              <span className="hero-location-branch-name">
                {selectedBranch ? selectedBranch.name : 'Elegir sucursal'}
              </span>
              {distanceText && (
                <span className="hero-distance-tag">{distanceText}</span>
              )}
              <ChevronDown size={13} className="hero-chevron-icon" />
            </div>
          </div>
        </button>

        {/* Quick GPS Location Refresh Button */}
        {onRefreshLocation && (
          <button
            type="button"
            className={`hero-gps-action-btn ${isLoadingLocation ? 'loading' : ''}`}
            onClick={onRefreshLocation}
            title="Actualizar ubicación GPS"
            aria-label="Actualizar ubicación GPS"
            disabled={isLoadingLocation}
          >
            <Navigation size={16} className={isLoadingLocation ? 'spin-icon' : ''} />
          </button>
        )}
      </div>

      {/* Horizontal Category Panoramic Hero Carousel */}
      <div
        ref={carouselRef}
        className="hero-panoramic-carousel"
        role="tablist"
        aria-label="Galería de categorías"
        onScroll={handleScroll}
      >
        {categories.map((cat, idx) => {
          const isAll = cat.id === 'all' || cat.name === 'Todos';
          const isActive = activeCategoryId === cat.id || (activeCategoryId === '' && isAll);
          const cover = getCategoryCover(cat.name);
          const icon = getCategoryIcon(cat.name);
          const count = productsCountByCategory[cat.id] || (isAll ? 'Todo el menú' : '');

          return (
            <div
              key={cat.id}
              className={`hero-panoramic-card ${isActive ? 'active' : ''}`}
              role="tabpanel"
              aria-label={`Categoría ${cat.name}`}
            >
              {/* Background Food Image & Dual Scrims */}
              <div className="hero-card-media">
                <img
                  src={cover}
                  alt={cat.name}
                  className="hero-card-img"
                  loading={idx === 0 ? 'eager' : 'lazy'}
                />
                <div className="hero-scrim-top" />
                <div className="hero-scrim-bottom" />
              </div>

              {/* Middle Hero Content: Tag, Title, Count & Slide Controls */}
              <div className="hero-card-overlay-content">
                <div className="hero-card-middle-row">
                  <div className="hero-card-info-wrap">
                    <div className="hero-category-tag-pill">
                      <span className="hero-category-icon">{icon}</span>
                      <span className="hero-category-name">{cat.name}</span>
                    </div>
                    <h1 className="hero-card-title">{cat.name}</h1>
                    {count && (
                      <p className="hero-card-subtitle">
                        {typeof count === 'number' ? `${count} platillos frescos disponibles` : count}
                      </p>
                    )}
                  </div>

                  <div className="hero-carousel-nav-arrows">
                    <button
                      type="button"
                      className="hero-arrow-btn"
                      onClick={handleScrollLeft}
                      disabled={activeIndex === 0}
                      aria-label="Categoría anterior"
                    >
                      <ChevronLeft size={18} />
                    </button>
                    <button
                      type="button"
                      className="hero-arrow-btn"
                      onClick={handleScrollRight}
                      disabled={activeIndex === categories.length - 1}
                      aria-label="Siguiente categoría"
                    >
                      <ChevronRight size={18} />
                    </button>
                  </div>
                </div>

                <div className="hero-card-status-chip">
                  <span>{idx + 1} / {categories.length}</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Integrated Search Bar at Bottom of Hero */}
      <div className="hero-integrated-search-container">
        <div className="hero-search-bar-pill">
          <Search size={18} className="hero-search-icon" />
          <input
            type="search"
            className="hero-search-input"
            placeholder="Buscar platillos, jugos, smoothies, bowls..."
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
          />
          {searchQuery.trim().length > 0 && (
            <button
              type="button"
              className="hero-search-clear-btn"
              onClick={() => onSearchChange('')}
              aria-label="Limpiar búsqueda"
            >
              <X size={14} />
            </button>
          )}
        </div>
      </div>
    </header>
  );
};
