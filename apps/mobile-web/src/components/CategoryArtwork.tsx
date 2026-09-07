import React, { useState } from 'react';
import { Category } from '../types';
import { getCategoryCover, getCategoryIcon, getCategoryImageUrl } from '../imageMap';

/** A broken remote photograph must not leave an empty hero or navigation button. */
export function CategoryArtwork({ category, className, loading = 'lazy', circle = false }: {
  category: Category; className?: string; loading?: 'eager' | 'lazy'; circle?: boolean;
}) {
  const url = getCategoryImageUrl(category.image_url);
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  const photograph = url && url !== failedUrl;
  if (circle && !photograph) {
    return <span className="category-circle-emoji" aria-hidden="true">{getCategoryIcon(category.name)}</span>;
  }
  return <img src={photograph ? url : getCategoryCover(category.name)} alt={category.name}
    className={className} loading={loading} referrerPolicy="no-referrer"
    onError={photograph ? () => setFailedUrl(url) : undefined}
    style={circle ? { width: '100%', height: '100%', objectFit: 'cover', borderRadius: '50%' } : undefined} />;
}
