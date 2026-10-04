export interface PantoneSwatch {
  id: string;
  name: string;
  hex: string;
  column: number;
  row: number;
  category: string;
  categoryLabel: string;
  recommendedFor: string;
  contrast: '#ffffff' | '#0f172a';
}

export const PANTONE_CATEGORIES = [
  { id: 'todos', label: 'Todos (64)', icon: '🎨' },
  { id: 'calidos', label: 'Cálidos & Fuego', icon: '🔥', description: 'Taquerías, Hamburguesas, Pizzerías, Snacks' },
  { id: 'tintos', label: 'Tinto & Rosas', icon: '🍷', description: 'Vinos, Carnes, Postres, Gelato, Repostería' },
  { id: 'azules', label: 'Azules & Océano', icon: '🌊', description: 'Mariscos, Pescados, Clásicos, Coctelería' },
  { id: 'turquesa', label: 'Turquesa & Cian', icon: '💎', description: 'Bebidas, Cocktails, Poke, Bowls, Helados' },
  { id: 'verdes', label: 'Verdes & Fresco', icon: '🌿', description: 'Ensaladas, Saludable, Bowls, Vegetariano' },
  { id: 'lima', label: 'Lima & Olivo', icon: '🍋', description: 'Cocina de autor, Brunch, Fresco, Cervecería' },
  { id: 'tierra', label: 'Café & Tierra', icon: '☕', description: 'Cafeterías, Dark Kitchens, Asados, Ahumados' },
  { id: 'neutros', label: 'Neutros & Ocre', icon: '✨', description: 'Cafés de especialidad, Panaderías, Deli' },
] as const;

export const PANTONE_SWATCHES: PantoneSwatch[] = [
  // Col 0: Neutros & Ocre
  { id: 'p-0-0', name: 'Blanco Hueso', hex: '#eaeaea', column: 0, row: 0, category: 'neutros', categoryLabel: '✨ Neutros & Ocre', recommendedFor: 'Cafés de especialidad, Panaderías, Deli', contrast: '#0f172a' },
  { id: 'p-0-1', name: 'Lino Suave', hex: '#e8ebe8', column: 0, row: 1, category: 'neutros', categoryLabel: '✨ Neutros & Ocre', recommendedFor: 'Cafés de especialidad, Panaderías, Deli', contrast: '#0f172a' },
  { id: 'p-0-2', name: 'Crema Vainilla', hex: '#eee3c7', column: 0, row: 2, category: 'neutros', categoryLabel: '✨ Neutros & Ocre', recommendedFor: 'Cafés de especialidad, Panaderías, Deli', contrast: '#0f172a' },
  { id: 'p-0-3', name: 'Trigo Dorado', hex: '#ebddba', column: 0, row: 3, category: 'neutros', categoryLabel: '✨ Neutros & Ocre', recommendedFor: 'Cafés de especialidad, Panaderías, Deli', contrast: '#0f172a' },
  { id: 'p-0-4', name: 'Arena Desierto', hex: '#dacfa6', column: 0, row: 4, category: 'neutros', categoryLabel: '✨ Neutros & Ocre', recommendedFor: 'Cafés de especialidad, Panaderías, Deli', contrast: '#0f172a' },
  { id: 'p-0-5', name: 'Ocre Claro', hex: '#cac6ac', column: 0, row: 5, category: 'neutros', categoryLabel: '✨ Neutros & Ocre', recommendedFor: 'Cafés de especialidad, Panaderías, Deli', contrast: '#0f172a' },
  { id: 'p-0-6', name: 'Mostaza Ocre', hex: '#b29832', column: 0, row: 6, category: 'neutros', categoryLabel: '✨ Neutros & Ocre', recommendedFor: 'Cafés de especialidad, Panaderías, Deli', contrast: '#0f172a' },
  { id: 'p-0-7', name: 'Caramelo Tostado', hex: '#a36026', column: 0, row: 7, category: 'neutros', categoryLabel: '✨ Neutros & Ocre', recommendedFor: 'Cafés de especialidad, Panaderías, Deli', contrast: '#ffffff' },

  // Col 1: Cálidos & Fuego
  { id: 'p-1-0', name: 'Vainilla Suave', hex: '#f4e6b0', column: 1, row: 0, category: 'calidos', categoryLabel: '🔥 Cálidos & Fuego', recommendedFor: 'Taquerías, Hamburguesas, Pizzerías, Snacks', contrast: '#0f172a' },
  { id: 'p-1-1', name: 'Amarillo Sol', hex: '#f3d964', column: 1, row: 1, category: 'calidos', categoryLabel: '🔥 Cálidos & Fuego', recommendedFor: 'Taquerías, Hamburguesas, Pizzerías, Snacks', contrast: '#0f172a' },
  { id: 'p-1-2', name: 'Ámbar Brillante', hex: '#eb9b3d', column: 1, row: 2, category: 'calidos', categoryLabel: '🔥 Cálidos & Fuego', recommendedFor: 'Taquerías, Hamburguesas, Pizzerías, Snacks', contrast: '#0f172a' },
  { id: 'p-1-3', name: 'Mandarina Cálida', hex: '#de8643', column: 1, row: 3, category: 'calidos', categoryLabel: '🔥 Cálidos & Fuego', recommendedFor: 'Taquerías, Hamburguesas, Pizzerías, Snacks', contrast: '#0f172a' },
  { id: 'orange', name: 'Naranja', hex: '#ea580c', column: 1, row: 4, category: 'calidos', categoryLabel: '🔥 Cálidos & Fuego', recommendedFor: 'Taquerías, Hamburguesas, Pizzerías, Snacks', contrast: '#ffffff' },
  { id: 'p-1-5', name: 'Naranja Intenso', hex: '#e55933', column: 1, row: 5, category: 'calidos', categoryLabel: '🔥 Cálidos & Fuego', recommendedFor: 'Taquerías, Hamburguesas, Pizzerías, Snacks', contrast: '#ffffff' },
  { id: 'p-1-6', name: 'Rojo Carmín', hex: '#e33749', column: 1, row: 6, category: 'calidos', categoryLabel: '🔥 Cálidos & Fuego', recommendedFor: 'Taquerías, Hamburguesas, Pizzerías, Snacks', contrast: '#ffffff' },
  { id: 'p-1-7', name: 'Rojo Fuego', hex: '#b82d4d', column: 1, row: 7, category: 'calidos', categoryLabel: '🔥 Cálidos & Fuego', recommendedFor: 'Taquerías, Hamburguesas, Pizzerías, Snacks', contrast: '#ffffff' },

  // Col 2: Tinto & Rosas
  { id: 'p-2-0', name: 'Rosa Pastel', hex: '#f1dade', column: 2, row: 0, category: 'tintos', categoryLabel: '🍷 Tinto & Rosas', recommendedFor: 'Vinos, Carnes, Postres, Gelato, Repostería', contrast: '#0f172a' },
  { id: 'p-2-1', name: 'Rosa Frambuesa', hex: '#e56c91', column: 2, row: 1, category: 'tintos', categoryLabel: '🍷 Tinto & Rosas', recommendedFor: 'Vinos, Carnes, Postres, Gelato, Repostería', contrast: '#ffffff' },
  { id: 'p-2-2', name: 'Fucsia Neón', hex: '#d84393', column: 2, row: 2, category: 'tintos', categoryLabel: '🍷 Tinto & Rosas', recommendedFor: 'Vinos, Carnes, Postres, Gelato, Repostería', contrast: '#ffffff' },
  { id: 'p-2-3', name: 'Magenta Profundo', hex: '#b1426d', column: 2, row: 3, category: 'tintos', categoryLabel: '🍷 Tinto & Rosas', recommendedFor: 'Vinos, Carnes, Postres, Gelato, Repostería', contrast: '#ffffff' },
  { id: 'p-2-4', name: 'Mora Silvestre', hex: '#a1328a', column: 2, row: 4, category: 'tintos', categoryLabel: '🍷 Tinto & Rosas', recommendedFor: 'Vinos, Carnes, Postres, Gelato, Repostería', contrast: '#ffffff' },
  { id: 'p-2-5', name: 'Púrpura Ciruela', hex: '#933b92', column: 2, row: 5, category: 'tintos', categoryLabel: '🍷 Tinto & Rosas', recommendedFor: 'Vinos, Carnes, Postres, Gelato, Repostería', contrast: '#ffffff' },
  { id: 'tinto', name: 'Tinto', hex: '#881337', column: 2, row: 6, category: 'tintos', categoryLabel: '🍷 Tinto & Rosas', recommendedFor: 'Vinos, Carnes, Postres, Gelato, Repostería', contrast: '#ffffff' },
  { id: 'p-2-7', name: 'Vino Borgoña', hex: '#492784', column: 2, row: 7, category: 'tintos', categoryLabel: '🍷 Tinto & Rosas', recommendedFor: 'Vinos, Carnes, Postres, Gelato, Repostería', contrast: '#ffffff' },

  // Col 3: Azules & Océano
  { id: 'p-3-0', name: 'Gris Azulado', hex: '#d1d3e6', column: 3, row: 0, category: 'azules', categoryLabel: '🌊 Azules & Océano', recommendedFor: 'Mariscos, Pescados, Clásicos, Coctelería', contrast: '#0f172a' },
  { id: 'p-3-1', name: 'Lavanda Azul', hex: '#afbbd6', column: 3, row: 1, category: 'azules', categoryLabel: '🌊 Azules & Océano', recommendedFor: 'Mariscos, Pescados, Clásicos, Coctelería', contrast: '#0f172a' },
  { id: 'p-3-2', name: 'Azul Acero', hex: '#7091c5', column: 3, row: 2, category: 'azules', categoryLabel: '🌊 Azules & Océano', recommendedFor: 'Mariscos, Pescados, Clásicos, Coctelería', contrast: '#0f172a' },
  { id: 'p-3-3', name: 'Azul Océano', hex: '#2b6ab2', column: 3, row: 3, category: 'azules', categoryLabel: '🌊 Azules & Océano', recommendedFor: 'Mariscos, Pescados, Clásicos, Coctelería', contrast: '#ffffff' },
  { id: 'blue', name: 'Azul', hex: '#2563eb', column: 3, row: 4, category: 'azules', categoryLabel: '🌊 Azules & Océano', recommendedFor: 'Mariscos, Pescados, Clásicos, Coctelería', contrast: '#ffffff' },
  { id: 'p-3-5', name: 'Cobalto Intenso', hex: '#104b8b', column: 3, row: 5, category: 'azules', categoryLabel: '🌊 Azules & Océano', recommendedFor: 'Mariscos, Pescados, Clásicos, Coctelería', contrast: '#ffffff' },
  { id: 'p-3-6', name: 'Azul Marino', hex: '#0e385d', column: 3, row: 6, category: 'azules', categoryLabel: '🌊 Azules & Océano', recommendedFor: 'Mariscos, Pescados, Clásicos, Coctelería', contrast: '#ffffff' },
  { id: 'p-3-7', name: 'Azul Noche', hex: '#1b4152', column: 3, row: 7, category: 'azules', categoryLabel: '🌊 Azules & Océano', recommendedFor: 'Mariscos, Pescados, Clásicos, Coctelería', contrast: '#ffffff' },

  // Col 4: Turquesa & Cian
  { id: 'p-4-0', name: 'Hielo Glaciar', hex: '#c0e0ec', column: 4, row: 0, category: 'turquesa', categoryLabel: '💎 Turquesa & Cian', recommendedFor: 'Bebidas, Cocktails, Poke, Bowls, Helados', contrast: '#0f172a' },
  { id: 'p-4-1', name: 'Celeste Cielo', hex: '#92d2e1', column: 4, row: 1, category: 'turquesa', categoryLabel: '💎 Turquesa & Cian', recommendedFor: 'Bebidas, Cocktails, Poke, Bowls, Helados', contrast: '#0f172a' },
  { id: 'p-4-2', name: 'Cian Brillante', hex: '#48afc0', column: 4, row: 2, category: 'turquesa', categoryLabel: '💎 Turquesa & Cian', recommendedFor: 'Bebidas, Cocktails, Poke, Bowls, Helados', contrast: '#0f172a' },
  { id: 'p-4-3', name: 'Turquesa Mar', hex: '#46a7a9', column: 4, row: 3, category: 'turquesa', categoryLabel: '💎 Turquesa & Cian', recommendedFor: 'Bebidas, Cocktails, Poke, Bowls, Helados', contrast: '#0f172a' },
  { id: 'p-4-4', name: 'Verde Agua', hex: '#47a69d', column: 4, row: 4, category: 'turquesa', categoryLabel: '💎 Turquesa & Cian', recommendedFor: 'Bebidas, Cocktails, Poke, Bowls, Helados', contrast: '#0f172a' },
  { id: 'p-4-5', name: 'Azul Petróleo', hex: '#2d6e63', column: 4, row: 5, category: 'turquesa', categoryLabel: '💎 Turquesa & Cian', recommendedFor: 'Bebidas, Cocktails, Poke, Bowls, Helados', contrast: '#ffffff' },
  { id: 'p-4-6', name: 'Verde Petróleo Oscuro', hex: '#11352f', column: 4, row: 6, category: 'turquesa', categoryLabel: '💎 Turquesa & Cian', recommendedFor: 'Bebidas, Cocktails, Poke, Bowls, Helados', contrast: '#ffffff' },
  { id: 'p-4-7', name: 'Abismo Marino', hex: '#0c292a', column: 4, row: 7, category: 'turquesa', categoryLabel: '💎 Turquesa & Cian', recommendedFor: 'Bebidas, Cocktails, Poke, Bowls, Helados', contrast: '#ffffff' },

  // Col 5: Verdes & Fresco
  { id: 'p-5-0', name: 'Menta Muy Clara', hex: '#cce2e4', column: 5, row: 0, category: 'verdes', categoryLabel: '🌿 Verdes & Fresco', recommendedFor: 'Ensaladas, Saludable, Bowls, Vegetariano', contrast: '#0f172a' },
  { id: 'p-5-1', name: 'Menta Fresca', hex: '#abd8da', column: 5, row: 1, category: 'verdes', categoryLabel: '🌿 Verdes & Fresco', recommendedFor: 'Ensaladas, Saludable, Bowls, Vegetariano', contrast: '#0f172a' },
  { id: 'p-5-2', name: 'Verde Jade', hex: '#4db091', column: 5, row: 2, category: 'verdes', categoryLabel: '🌿 Verdes & Fresco', recommendedFor: 'Ensaladas, Saludable, Bowls, Vegetariano', contrast: '#0f172a' },
  { id: 'p-5-3', name: 'Esmeralda Suave', hex: '#4aa87f', column: 5, row: 3, category: 'verdes', categoryLabel: '🌿 Verdes & Fresco', recommendedFor: 'Ensaladas, Saludable, Bowls, Vegetariano', contrast: '#0f172a' },
  { id: 'green', name: 'Verde', hex: '#059669', column: 5, row: 4, category: 'verdes', categoryLabel: '🌿 Verdes & Fresco', recommendedFor: 'Ensaladas, Saludable, Bowls, Vegetariano', contrast: '#ffffff' },
  { id: 'p-5-5', name: 'Verde Pasto', hex: '#4aa55b', column: 5, row: 5, category: 'verdes', categoryLabel: '🌿 Verdes & Fresco', recommendedFor: 'Ensaladas, Saludable, Bowls, Vegetariano', contrast: '#0f172a' },
  { id: 'p-5-6', name: 'Verde Bosque', hex: '#529138', column: 5, row: 6, category: 'verdes', categoryLabel: '🌿 Verdes & Fresco', recommendedFor: 'Ensaladas, Saludable, Bowls, Vegetariano', contrast: '#ffffff' },
  { id: 'p-5-7', name: 'Verde Pino', hex: '#485a16', column: 5, row: 7, category: 'verdes', categoryLabel: '🌿 Verdes & Fresco', recommendedFor: 'Ensaladas, Saludable, Bowls, Vegetariano', contrast: '#ffffff' },

  // Col 6: Lima & Olivo
  { id: 'p-6-0', name: 'Lima Pálido', hex: '#dfe8d5', column: 6, row: 0, category: 'lima', categoryLabel: '🍋 Lima & Olivo', recommendedFor: 'Cocina de autor, Brunch, Fresco, Cervecería', contrast: '#0f172a' },
  { id: 'p-6-1', name: 'Verde Manzana Claro', hex: '#c2dbb2', column: 6, row: 1, category: 'lima', categoryLabel: '🍋 Lima & Olivo', recommendedFor: 'Cocina de autor, Brunch, Fresco, Cervecería', contrast: '#0f172a' },
  { id: 'p-6-2', name: 'Verde Lima', hex: '#cdda71', column: 6, row: 2, category: 'lima', categoryLabel: '🍋 Lima & Olivo', recommendedFor: 'Cocina de autor, Brunch, Fresco, Cervecería', contrast: '#0f172a' },
  { id: 'p-6-3', name: 'Chartreuse', hex: '#c4d553', column: 6, row: 3, category: 'lima', categoryLabel: '🍋 Lima & Olivo', recommendedFor: 'Cocina de autor, Brunch, Fresco, Cervecería', contrast: '#0f172a' },
  { id: 'p-6-4', name: 'Verde Pistache', hex: '#b1bb39', column: 6, row: 4, category: 'lima', categoryLabel: '🍋 Lima & Olivo', recommendedFor: 'Cocina de autor, Brunch, Fresco, Cervecería', contrast: '#0f172a' },
  { id: 'p-6-5', name: 'Olivo Dorado', hex: '#b5af37', column: 6, row: 5, category: 'lima', categoryLabel: '🍋 Lima & Olivo', recommendedFor: 'Cocina de autor, Brunch, Fresco, Cervecería', contrast: '#0f172a' },
  { id: 'p-6-6', name: 'Olivo Oscuro', hex: '#594b14', column: 6, row: 6, category: 'lima', categoryLabel: '🍋 Lima & Olivo', recommendedFor: 'Cocina de autor, Brunch, Fresco, Cervecería', contrast: '#ffffff' },
  { id: 'p-6-7', name: 'Olivo Profundo', hex: '#4f3c10', column: 6, row: 7, category: 'lima', categoryLabel: '🍋 Lima & Olivo', recommendedFor: 'Cocina de autor, Brunch, Fresco, Cervecería', contrast: '#ffffff' },

  // Col 7: Café & Tierra
  { id: 'p-7-0', name: 'Almendra', hex: '#e1e1c9', column: 7, row: 0, category: 'tierra', categoryLabel: '☕ Café & Tierra', recommendedFor: 'Cafeterías, Dark Kitchens, Asados, Ahumados', contrast: '#0f172a' },
  { id: 'p-7-1', name: 'Caqui Suave', hex: '#d8d5ac', column: 7, row: 1, category: 'tierra', categoryLabel: '☕ Café & Tierra', recommendedFor: 'Cafeterías, Dark Kitchens, Asados, Ahumados', contrast: '#0f172a' },
  { id: 'p-7-2', name: 'Dorado Antiguo', hex: '#b3a962', column: 7, row: 2, category: 'tierra', categoryLabel: '☕ Café & Tierra', recommendedFor: 'Cafeterías, Dark Kitchens, Asados, Ahumados', contrast: '#0f172a' },
  { id: 'p-7-3', name: 'Bronce Tierra', hex: '#aea178', column: 7, row: 3, category: 'tierra', categoryLabel: '☕ Café & Tierra', recommendedFor: 'Cafeterías, Dark Kitchens, Asados, Ahumados', contrast: '#0f172a' },
  { id: 'p-7-4', name: 'Café Canela', hex: '#97824b', column: 7, row: 4, category: 'tierra', categoryLabel: '☕ Café & Tierra', recommendedFor: 'Cafeterías, Dark Kitchens, Asados, Ahumados', contrast: '#ffffff' },
  { id: 'p-7-5', name: 'Café Moca', hex: '#907866', column: 7, row: 5, category: 'tierra', categoryLabel: '☕ Café & Tierra', recommendedFor: 'Cafeterías, Dark Kitchens, Asados, Ahumados', contrast: '#ffffff' },
  { id: 'p-7-6', name: 'Chocolate Amargo', hex: '#693914', column: 7, row: 6, category: 'tierra', categoryLabel: '☕ Café & Tierra', recommendedFor: 'Cafeterías, Dark Kitchens, Asados, Ahumados', contrast: '#ffffff' },
  { id: 'p-7-7', name: 'Café Espresso', hex: '#3d1e16', column: 7, row: 7, category: 'tierra', categoryLabel: '☕ Café & Tierra', recommendedFor: 'Cafeterías, Dark Kitchens, Asados, Ahumados', contrast: '#ffffff' },
];

const SWATCH_MAP = new Map(PANTONE_SWATCHES.map((s) => [s.id, s]));

export function findPantoneSwatch(idOrHex?: string | null): PantoneSwatch | undefined {
  if (!idOrHex) return undefined;
  const normalized = idOrHex.trim().toLowerCase();
  const byId = SWATCH_MAP.get(normalized);
  if (byId) return byId;
  return PANTONE_SWATCHES.find((s) => s.hex.toLowerCase() === normalized);
}

export function resolvePantoneSwatch(val?: string | null): PantoneSwatch {
  const match = findPantoneSwatch(val);
  if (match) return match;

  const raw = (val || '').trim();
  if (/^#?([0-9a-f]{3}|[0-9a-f]{6})$/i.test(raw)) {
    let hex = raw.startsWith('#') ? raw : '#' + raw;
    if (hex.length === 4) {
      hex = '#' + hex.slice(1).split('').map((c) => c + c).join('');
    }
    hex = hex.toLowerCase();

    const existing = PANTONE_SWATCHES.find((s) => s.hex.toLowerCase() === hex);
    if (existing) return existing;

    const num = parseInt(hex.slice(1), 16);
    const r = (num >> 16) & 255;
    const g = (num >> 8) & 255;
    const b = num & 255;
    const relLuminance = 0.2126 * (r / 255) + 0.7152 * (g / 255) + 0.0722 * (b / 255);
    const contrast: '#ffffff' | '#0f172a' = relLuminance > 0.55 ? '#0f172a' : '#ffffff';

    return {
      id: hex,
      name: 'Color Personalizado',
      hex,
      column: -1,
      row: -1,
      category: 'personalizado',
      categoryLabel: '🎯 Personalizado',
      recommendedFor: 'Tono exacto personalizado para tu marca',
      contrast,
    };
  }

  return findPantoneSwatch('orange') || PANTONE_SWATCHES[12];
}
