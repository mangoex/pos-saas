import React, { useRef, useState, useEffect, useCallback } from 'react';
import { Category } from '../types';
import { getCategoryIcon } from '../imageMap';
import { CategoryArtwork } from './CategoryArtwork';
import { ChevronLeft, ChevronRight } from 'lucide-react';

interface CategoryStoriesProps {
  categories: Category[];
  activeCategoryId: string;
  onSelectCategory: (categoryId: string) => void;
  onCategoryCardClick?: (categoryId: string) => void;
  productsCountByCategory?: Record<string, number>;
}

export const CategoryStories: React.FC<CategoryStoriesProps> = ({
  categories,
  activeCategoryId,
  onSelectCategory,
  onCategoryCardClick,
  productsCountByCategory = {},
}) => {
  const carouselRef = useRef<HTMLDivElement>(null);
  const [activeIndex, setActiveIndex] = useState(0);

  // Sync active index when activeCategoryId changes
  useEffect(() => {
    const idx = categories.findIndex((c) => c.id === activeCategoryId);
    if (idx !== -1) {
      setActiveIndex(idx);
      const carousel = carouselRef.current;
      carousel?.scrollTo({ left: idx * carousel.clientWidth, behavior: 'smooth' });
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
    const cards = el.querySelectorAll<HTMLElement>('.category-hero-card');
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

  if (categories.length === 0) return null;

  return (
    <section className="category-carousel-section" aria-label="Menú de categorías">
      <div
        ref={carouselRef}
        className="category-stories-carousel"
        role="tablist"
        aria-label="Categorías de productos"
        onScroll={handleScroll}
      >
        {categories.map((cat, idx) => {
          const isAll = cat.id === 'all';
          const isActive = activeCategoryId === cat.id || (activeCategoryId === '' && isAll);
          const icon = getCategoryIcon(cat.name);
          const isClosed = cat.name.toLowerCase().includes('cerrado');
          const count = productsCountByCategory[cat.id] || (isAll ? (isClosed ? 'Puedes explorar nuestro menú mientras abrimos' : 'Todo el menú') : '');

          return (
            <button
              key={cat.id}
              type="button"
              className={`category-hero-card ${isActive ? 'active' : ''}`}
              onClick={() => {
                onSelectCategory(cat.id);
                scrollToCategoryIndex(idx);
                if (onCategoryCardClick) {
                  onCategoryCardClick(cat.id);
                }
              }}
              role="tab"
              aria-selected={isActive}
              aria-label={`Categoría ${cat.name}`}
            >
              <div className="category-hero-bg-wrapper">
                <CategoryArtwork
                  category={cat}
                  className="category-hero-img"
                  loading={idx === 0 ? 'eager' : 'lazy'}
                />
                <div className="category-hero-scrim" />
              </div>

              <div className="category-hero-content">
                {/* Top Glassmorphic Navigation Row */}
                <div className="category-hero-top-row">
                  <div className="category-hero-pill-badge">
                    <span className="category-hero-icon-pill">{icon}</span>
                    <span className="category-hero-tagline">{cat.name}</span>
                  </div>

                  <div className="category-hero-nav-actions">
                    <button
                      type="button"
                      className="category-glass-nav-btn"
                      onClick={handleScrollLeft}
                      disabled={activeIndex === 0}
                      aria-label="Categoría anterior"
                      title="Categoría anterior"
                    >
                      <ChevronLeft size={18} />
                    </button>
                    <button
                      type="button"
                      className="category-glass-nav-btn"
                      onClick={handleScrollRight}
                      disabled={activeIndex === categories.length - 1}
                      aria-label="Siguiente categoría"
                      title="Siguiente categoría"
                    >
                      <ChevronRight size={18} />
                    </button>
                  </div>
                </div>

                {/* Bottom Hero Info */}
                <div className="category-hero-bottom-info">
                  <div className="category-hero-text-group">
                    <h2 className="category-hero-title">{cat.name}</h2>
                    {count && (
                      <span className="category-hero-count-chip">
                        {typeof count === 'number' ? `${count} platillos disponibles` : count}
                      </span>
                    )}
                  </div>
                  <div className="category-hero-status-indicator">
                    <span className="category-hero-index-chip">
                      {idx + 1} / {categories.length}
                    </span>
                  </div>
                </div>
              </div>
            </button>
          );
        })}
      </div>

      {/* Indicador de movimiento horizontal / pills de navegación */}
      <div className="category-scroll-indicator-wrap" aria-label="Indicador de posición horizontal">
        <div className="category-scroll-indicator-track">
          {categories.map((cat, idx) => {
            const isDotActive = activeIndex === idx;
            return (
              <button
                key={`dot-${cat.id}`}
                type="button"
                className={`category-indicator-pill ${isDotActive ? 'active' : ''}`}
                onClick={() => {
                  scrollToCategoryIndex(idx);
                }}
                aria-label={`Ir a categoría ${cat.name}`}
                title={cat.name}
              />
            );
          })}
        </div>
      </div>
    </section>
  );
};
