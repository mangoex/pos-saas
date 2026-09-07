/** Product photographs belong to the resolved restaurant catalog. */
export function getProductImage(product: { sku?: string; name?: string; category_name?: string; image_url?: string }): string {
  return product.image_url?.trim() || '';
}

/** Generic category artwork has no restaurant-specific photographs or claims. */
export function getCategoryImageUrl(value: string | null | undefined): string {
  if (!value) return '';
  try {
    const url = new URL(value.trim());
    return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password ? value.trim() : '';
  } catch { return ''; }
}

export function getCategoryCover(categoryName: string): string {
  const icon = getCategoryIcon(categoryName);
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="900" height="500" viewBox="0 0 900 500"><defs><linearGradient id="bg" x2="1" y2="1"><stop stop-color="#164e63"/><stop offset="1" stop-color="#0f172a"/></linearGradient></defs><rect width="900" height="500" fill="url(#bg)"/><circle cx="760" cy="70" r="240" fill="#ffffff" opacity=".05"/><text x="450" y="275" text-anchor="middle" font-size="150">${icon}</text></svg>`;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

export function getCategoryIcon(categoryName: string): string {
  const cat = (categoryName || '').toLowerCase();
  if (cat === 'todos' || cat === 'all') return '🍽️';
  if (cat.includes('sushi') || cat.includes('rollo') || cat.includes('gratinado') || cat.includes('natural')) return '🍣';
  if (cat.includes('taco') || cat.includes('asada') || cat.includes('pastor')) return '🌮';
  if (cat.includes('pizza')) return '🍕';
  if (cat.includes('hamburguesa') || cat.includes('burger')) return '🍔';
  if (cat.includes('carne') || cat.includes('corte') || cat.includes('pollo')) return '🥩';
  if (cat.includes('fruta') || cat.includes('cereal') || cat.includes('avena')) return '🍍';
  if (cat.includes('combo') || cat.includes('paquete')) return '🍱';
  if (cat.includes('focaccia')) return '🍞';
  if (cat.includes('omelette') || cat.includes('omelet') || cat.includes('huevo')) return '🍳';
  if (cat.includes('quesadilla')) return '🧀';
  if (cat.includes('ensalada')) return '🥗';
  if (cat.includes('sando') || cat.includes('sandwich') || cat.includes('emparedado') || cat.includes('baguette')) return '🥪';
  if (cat.includes('smoothie') || cat.includes('licuado')) return '🍓';
  if (cat.includes('café') || cat.includes('cafe') || cat.includes('matcha')) return '🍵';
  if (cat.includes('pan') || cat.includes('croissant') || cat.includes('cuernito')) return '🥐';
  if (cat.includes('agua') || cat.includes('bebida') || cat.includes('refresco')) return '🥤';
  if (cat.includes('jugo') || cat.includes('extracto')) return '🧃';
  if (cat.includes('postre') || cat.includes('dulce')) return '🍰';
  if (cat.includes('extra') || cat.includes('adicional')) return '✨';
  return '🍽️';
}

export function detectProductSize(productName: string): string | null {
  const upper = productName.toUpperCase().trim();
  if (/(?:\s+|\()(?:GDE|GRANDE|GD|LARGE|L)(?:\)|\s*$)/i.test(upper)) return 'GDE';
  if (/(?:\s+|\()(?:MED|MEDIANO|MEDIANA|MD|MEDIUM|M)(?:\)|\s*$)/i.test(upper)) return 'MED';
  if (/(?:\s+|\()(?:CH|CHICO|CHICA|CHI|SMALL|S)(?:\)|\s*$)/i.test(upper)) return 'CH';
  if (/(?:\s+|\()(?:1L|1\s*LITRO|LITRO|LT)(?:\)|\s*$)/i.test(upper)) return '1L';
  if (/(?:\s+|\()(?:500ML|1\/2L|1\/2\s*LITRO|MEDIO\s*LITRO)(?:\)|\s*$)/i.test(upper)) return '500ml';
  return null;
}

export function cleanBaseProductName(productName: string): string {
  return productName
    .replace(/(?:\s+|\()(?:GDE|GRANDE|GD|MED|MEDIANO|MEDIANA|MD|CH|CHICO|CHICA|CHI|1L|1\s*LITRO|LITRO|LT|500ML|1\/2L|1\/2\s*LITRO|MEDIO\s*LITRO)(?:\)|\s*$)/gi, '')
    .trim();
}

export interface ProductIconMeta {
  emoji: string;
  badgeLabel: string;
  bgGradient: string;
  borderColor: string;
  textColor: string;
}

export function getProductIconMeta(product: { sku?: string; name?: string; category_name?: string }): ProductIconMeta {
  const name = (product.name || '').toLowerCase();
  const cat = (product.category_name || '').toLowerCase();
  const sku = (product.sku || '').toUpperCase();

  if (cat.includes('fruta') || name.includes('fruta') || name.includes('avena') || name.includes('cereal') || sku.startsWith('FRU')) {
    return {
      emoji: '🍍',
      badgeLabel: 'Frutas & Cereal',
      bgGradient: 'linear-gradient(135deg, #fefce8 0%, #fef08a 100%)',
      borderColor: '#fde047',
      textColor: '#a16207',
    };
  }

  if (cat.includes('focaccia') || name.includes('focaccia')) {
    return {
      emoji: '🍞',
      badgeLabel: 'Focaccia',
      bgGradient: 'linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%)',
      borderColor: '#fde68a',
      textColor: '#b45309',
    };
  }

  if (cat.includes('omelette') || name.includes('omelette') || name.includes('omelet') || name.includes('huevo') || sku.startsWith('OME')) {
    return {
      emoji: '🍳',
      badgeLabel: 'Omelette',
      bgGradient: 'linear-gradient(135deg, #fff7ed 0%, #fed7aa 100%)',
      borderColor: '#fdba74',
      textColor: '#c2410c',
    };
  }

  if (cat.includes('quesadilla') || name.includes('quesadilla') || sku.startsWith('QUE')) {
    return {
      emoji: '🧀',
      badgeLabel: 'Quesadilla',
      bgGradient: 'linear-gradient(135deg, #fefce8 0%, #fef9c3 100%)',
      borderColor: '#fef08a',
      textColor: '#854d0e',
    };
  }

  if (cat.includes('ensalada') || name.includes('ensalada') || sku.startsWith('ENS')) {
    return {
      emoji: '🥗',
      badgeLabel: 'Ensalada',
      bgGradient: 'linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%)',
      borderColor: '#a7f3d0',
      textColor: '#047857',
    };
  }

  if (cat.includes('smoothie') || name.includes('smoothie') || sku.startsWith('SMO') || name.includes('bowl')) {
    return {
      emoji: '🍓',
      badgeLabel: 'Smoothie',
      bgGradient: 'linear-gradient(135deg, #fdf2f8 0%, #fce7f3 100%)',
      borderColor: '#fbcfe8',
      textColor: '#be185d',
    };
  }

  if (cat.includes('sando') || cat.includes('sandwich') || name.includes('sando') || name.includes('sandwich') || name.includes('emparedado') || name.includes('baguette') || sku.startsWith('SAN') || sku.startsWith('EMP')) {
    return {
      emoji: '🥪',
      badgeLabel: 'Sándwich',
      bgGradient: 'linear-gradient(135deg, #fff7ed 0%, #ffedd5 100%)',
      borderColor: '#fed7aa',
      textColor: '#c2410c',
    };
  }

  if (cat.includes('pan') || cat.includes('croissant') || name.includes('cuernito') || name.includes('bisquet') || name.includes('croissant') || sku.startsWith('PAN')) {
    return {
      emoji: '🥐',
      badgeLabel: 'Panadería',
      bgGradient: 'linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%)',
      borderColor: '#fde68a',
      textColor: '#b45309',
    };
  }

  if (cat.includes('café') || cat.includes('cafe') || cat.includes('matcha') || name.includes('matcha') || name.includes('latte') || name.includes('café') || name.includes('cafe') || sku.startsWith('CAF') || sku.startsWith('MAT')) {
    return {
      emoji: '🍵',
      badgeLabel: 'Café & Té',
      bgGradient: 'linear-gradient(135deg, #f0fdfa 0%, #ccfbf1 100%)',
      borderColor: '#99f6e4',
      textColor: '#0f766e',
    };
  }

  if (cat.includes('jugo') || cat.includes('extracto') || name.includes('jugo') || name.includes('extracto') || name.includes('shot') || sku.startsWith('JUG') || sku.startsWith('EXT') || sku.startsWith('SHO')) {
    return {
      emoji: '🥤',
      badgeLabel: 'Jugo / Extracto',
      bgGradient: 'linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%)',
      borderColor: '#bbf7d0',
      textColor: '#15803d',
    };
  }

  if (cat.includes('agua') || cat.includes('bebida') || name.includes('agua')) {
    return {
      emoji: '💧',
      badgeLabel: 'Bebida',
      bgGradient: 'linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%)',
      borderColor: '#bfdbfe',
      textColor: '#1d4ed8',
    };
  }

  if (cat.includes('postre') || name.includes('pastel') || name.includes('galleta') || name.includes('dulce')) {
    return {
      emoji: '🍰',
      badgeLabel: 'Postre',
      bgGradient: 'linear-gradient(135deg, #fff1f2 0%, #ffe4e6 100%)',
      borderColor: '#fecdd3',
      textColor: '#be123c',
    };
  }

  if (cat.includes('sushi') || cat.includes('rollo') || cat.includes('gratinado') || cat.includes('natural') || name.includes('roll') || name.includes('sushi') || name.includes('tampico') || name.includes('anguila') || name.includes('camarón') || name.includes('camaron')) {
    return {
      emoji: '🍣',
      badgeLabel: 'Sushi Roll',
      bgGradient: 'linear-gradient(135deg, #fff7ed 0%, #fed7aa 100%)',
      borderColor: '#fdba74',
      textColor: '#c2410c',
    };
  }

  if (cat.includes('taco') || name.includes('taco') || name.includes('asada') || name.includes('pastor') || name.includes('gringa')) {
    return {
      emoji: '🌮',
      badgeLabel: 'Taquería',
      bgGradient: 'linear-gradient(135deg, #fefce8 0%, #fef08a 100%)',
      borderColor: '#fde047',
      textColor: '#a16207',
    };
  }

  if (cat.includes('pizza') || name.includes('pizza')) {
    return {
      emoji: '🍕',
      badgeLabel: 'Pizza Artesanal',
      bgGradient: 'linear-gradient(135deg, #fff1f2 0%, #ffe4e6 100%)',
      borderColor: '#fecdd3',
      textColor: '#be123c',
    };
  }

  if (cat.includes('hamburguesa') || cat.includes('burger') || name.includes('burger') || name.includes('hamburguesa')) {
    return {
      emoji: '🍔',
      badgeLabel: 'Hamburguesa',
      bgGradient: 'linear-gradient(135deg, #fff7ed 0%, #fed7aa 100%)',
      borderColor: '#fdba74',
      textColor: '#c2410c',
    };
  }

  if (cat.includes('bebida') || cat.includes('refresco') || name.includes('té') || name.includes('te 1lt') || name.includes('limonada') || name.includes('coca') || name.includes('jamaica')) {
    return {
      emoji: '🥤',
      badgeLabel: 'Bebida',
      bgGradient: 'linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%)',
      borderColor: '#bfdbfe',
      textColor: '#1d4ed8',
    };
  }

  return {
    emoji: '🍽️',
    badgeLabel: 'Especialidad',
    bgGradient: 'linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%)',
    borderColor: '#cbd5e1',
    textColor: '#334155',
  };
}
