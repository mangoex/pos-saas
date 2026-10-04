import React, { useState } from 'react';
import { Category } from '../types';
import { getCategoryCover, getCategoryIcon, getCategoryImageUrl } from '../imageMap';
import closedEstablishmentHero from '../assets/closed_establishment_hero.jpg';

/** A broken remote photograph must not leave an empty hero or navigation button. */
export function CategoryArtwork({ category, className, loading = 'lazy', circle = false }: {
  category: Category; className?: string; loading?: 'eager' | 'lazy'; circle?: boolean;
}) {
  const isClosed = (category.name || '').toLowerCase().includes('cerrado');
  const url = isClosed ? closedEstablishmentHero : getCategoryImageUrl(category.image_url);
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  const photograph = Boolean((url && url !== failedUrl) || isClosed);

  if (circle && !photograph && !isClosed) {
    return <span className="category-circle-emoji" aria-hidden="true">{getCategoryIcon(category.name)}</span>;
  }
  return <img src={isClosed ? closedEstablishmentHero : (photograph ? url : getCategoryCover(category.name))} alt={category.name}
    className={className} loading={loading} referrerPolicy="no-referrer"
    onError={photograph && !isClosed ? () => setFailedUrl(url) : undefined}
    style={circle ? { width: '100%', height: '100%', objectFit: 'cover', borderRadius: '50%' } : undefined} />;
}
