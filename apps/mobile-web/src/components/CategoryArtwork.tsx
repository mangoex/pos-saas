import React, { useState } from 'react';
import { Category } from '../types';
import {
  getCategoryCover,
  getCategoryIcon,
  getCategoryImageUrl,
  CLOSED_ESTABLISHMENT_HERO_MEDIA,
  closedEstablishmentHeroFallback,
} from '../imageMap';

/** A broken remote photograph must not leave an empty hero or navigation button. */
export function CategoryArtwork({ category, className, loading = 'lazy', circle = false }: {
  category: Category; className?: string; loading?: 'eager' | 'lazy'; circle?: boolean;
}) {
  const isClosed = (category.name || '').toLowerCase().includes('cerrado');
  const url = isClosed ? CLOSED_ESTABLISHMENT_HERO_MEDIA : getCategoryImageUrl(category.image_url);
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  const photograph = Boolean((url && url !== failedUrl) || isClosed);

  if (circle && !photograph && !isClosed) {
    return <span className="category-circle-emoji" aria-hidden="true">{getCategoryIcon(category.name)}</span>;
  }

  const resolvedSrc = isClosed
    ? (failedUrl === CLOSED_ESTABLISHMENT_HERO_MEDIA ? closedEstablishmentHeroFallback : CLOSED_ESTABLISHMENT_HERO_MEDIA)
    : (photograph ? url : getCategoryCover(category.name));

  return (
    <img
      src={resolvedSrc}
      alt={category.name}
      className={className}
      loading={loading}
      referrerPolicy="no-referrer"
      onError={isClosed
        ? (failedUrl !== CLOSED_ESTABLISHMENT_HERO_MEDIA ? () => setFailedUrl(CLOSED_ESTABLISHMENT_HERO_MEDIA) : undefined)
        : (photograph ? () => setFailedUrl(url) : undefined)
      }
      style={circle ? { width: '100%', height: '100%', objectFit: 'cover', borderRadius: '50%' } : undefined}
    />
  );
}
