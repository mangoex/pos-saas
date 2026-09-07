import React, { useRef, useEffect } from 'react';
import { Category } from '../types';
import { CategoryArtwork } from './CategoryArtwork';

interface CategoryCirclesProps {
  categories: Category[];
  activeCategoryId: string;
  onSelectCategory: (categoryId: string) => void;
  productsCountByCategory?: Record<string, number>;
}

export const CategoryCircles: React.FC<CategoryCirclesProps> = ({
  categories,
  activeCategoryId,
  onSelectCategory,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);

  // Auto-scroll the active circle into view smoothly
  useEffect(() => {
    if (!containerRef.current) return;
    const activeEl = containerRef.current.querySelector<HTMLElement>('.category-circle-btn.active');
    if (activeEl) {
      activeEl.scrollIntoView({
        behavior: 'smooth',
        inline: 'center',
        block: 'nearest',
      });
    }
  }, [activeCategoryId]);

  if (categories.length === 0) return null;

  return (
    <section className="category-circles-section" aria-label="Explorar por categoría">
      <div
        ref={containerRef}
        className="category-circles-scroll"
        role="tablist"
        aria-label="Categorías circulares"
      >
        {categories.map((cat) => {
          const isAll = cat.id === 'all';
          const isActive = activeCategoryId === cat.id || (activeCategoryId === '' && isAll);

          return (
            <button
              key={cat.id}
              type="button"
              className={`category-circle-btn ${isActive ? 'active' : ''}`}
              onClick={() => onSelectCategory(cat.id)}
              role="tab"
              aria-selected={isActive}
              aria-label={`Filtrar por ${cat.name}`}
            >
              <div className="category-circle-avatar">
                <CategoryArtwork category={cat} circle />
              </div>
              <span className="category-circle-label">{cat.name}</span>
            </button>
          );
        })}
      </div>
    </section>
  );
};
