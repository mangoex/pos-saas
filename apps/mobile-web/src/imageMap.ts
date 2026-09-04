/**
 * Realistic Product Image Mapper (Bundled Static Assets)
 * Maps real Kiwi catalog items to high-resolution realistic culinary photography.
 */

import jugoVerdeImg from './assets/products/jugo_verde.jpg';
import smoothieRosaImg from './assets/products/smoothie_rosa.jpg';
import macchaPinkuImg from './assets/products/maccha_pinku.jpg';
import ensaladaFrutosImg from './assets/products/ensalada_frutos.jpg';
import sandoKyotoImg from './assets/products/sando_kyoto.jpg';
import cuernitoJamonImg from './assets/products/cuernito_jamon.jpg';
import extractoRojoImg from './assets/products/extracto_rojo.jpg';
import todosMenuHeroImg from './assets/products/todos_menu_hero.jpg';
import frutasFrescasImg from './assets/products/frutas_frescas.jpg';
import combosDeluxeImg from './assets/products/combos_deluxe.jpg';
import aguasFrescasImg from './assets/products/aguas_frescas.jpg';
import focacciaArtesanalImg from './assets/products/focaccia_artesanal.jpg';
import omeletteGourmetImg from './assets/products/omelette_gourmet.jpg';
import quesadillasDoradasImg from './assets/products/quesadillas_doradas.jpg';
import sushiRollsImg from './assets/products/sushi_rolls.jpg';
import gratinadosSushiImg from './assets/products/gratinados_sushi.jpg';
import naturalSushiImg from './assets/products/natural_sushi.jpg';
import bebidasBarImg from './assets/products/bebidas_bar.jpg';
import tacosMexicanosImg from './assets/products/tacos_mexicanos.jpg';
import gourmetBurgersImg from './assets/products/gourmet_burgers.jpg';
import artisanPizzaImg from './assets/products/artisan_pizza.jpg';

const SKU_IMAGE_MAP: Record<string, string> = {
  // Direct SKU matches
  'JUG-VER': jugoVerdeImg,
  'EXT-VER': jugoVerdeImg,
  'EXT-ROJ': extractoRojoImg,
  'JUG-ANT': extractoRojoImg,
  'SHO-JEN': jugoVerdeImg,
  'SMO-ROS': smoothieRosaImg,
  'SMO-FRE': smoothieRosaImg,
  'SMO-CAC': smoothieRosaImg,
  'SMO-PRO': smoothieRosaImg,
  'MAT-PIN': macchaPinkuImg,
  'MAT-SHI': macchaPinkuImg,
  'CAF-LAT': macchaPinkuImg,
  'CAF-LAT-FRE': macchaPinkuImg,
  'CAF-SOL': macchaPinkuImg,
  'ENS-FRU': ensaladaFrutosImg,
  'ENS-MAN': ensaladaFrutosImg,
  'ENS-CHE': ensaladaFrutosImg,
  'SAN-KYO-BBQ': sandoKyotoImg,
  'EMP-POL': sandoKyotoImg,
  'PAN-CUE': cuernitoJamonImg,
  'PAN-BAG': cuernitoJamonImg,
  'PAN-BIS': cuernitoJamonImg,
  'PAN-FOC': focacciaArtesanalImg,
  'COM-LIG': combosDeluxeImg,
  'COM-PRE': combosDeluxeImg,
  'FRU-AVE': frutasFrescasImg,
  'FRU-PLA': frutasFrescasImg,
  'OME-ESP': omeletteGourmetImg,
  'OME-JAM': omeletteGourmetImg,
  'QUE-NAT': quesadillasDoradasImg,
  'QUE-JAM': quesadillasDoradasImg,
};

export function getProductImage(product: { sku?: string; name?: string; category_name?: string; image_url?: string }): string {
  if (product.image_url && product.image_url.trim() !== '') {
    return product.image_url;
  }
  if (product.sku && SKU_IMAGE_MAP[product.sku]) {
    return SKU_IMAGE_MAP[product.sku];
  }

  const nameLower = (product.name || '').toLowerCase();
  const catLower = (product.category_name || '').toLowerCase();

  if (nameLower.includes('gratinado') || catLower.includes('gratinado') || catLower.includes('horneado')) {
    return gratinadosSushiImg;
  }
  if (nameLower.includes('natural') && (catLower.includes('sushi') || catLower.includes('rollo') || nameLower.includes('roll'))) {
    return naturalSushiImg;
  }
  if (nameLower.includes('sushi') || nameLower.includes('roll') || nameLower.includes('maki') || catLower.includes('sushi') || catLower.includes('rollo')) {
    return sushiRollsImg;
  }
  if (nameLower.includes('coca') || nameLower.includes('pepsi') || nameLower.includes('refresco') || nameLower.includes('cerveza') || nameLower.includes('drink') || catLower.includes('bebida') || catLower.includes('refresco') || catLower.includes('bar')) {
    return bebidasBarImg;
  }
  if (nameLower.includes('taco') || catLower.includes('taco') || nameLower.includes('pastor') || nameLower.includes('asada')) {
    return tacosMexicanosImg;
  }
  if (nameLower.includes('burger') || nameLower.includes('hamburguesa') || catLower.includes('burger') || catLower.includes('hamburguesa') || nameLower.includes('boneless') || nameLower.includes('alita')) {
    return gourmetBurgersImg;
  }
  if (nameLower.includes('pizza') || catLower.includes('pizza') || nameLower.includes('pasta') || catLower.includes('pasta')) {
    return artisanPizzaImg;
  }
  if (nameLower.includes('fruta') || nameLower.includes('avena') || nameLower.includes('cereal') || catLower.includes('fruta')) {
    return frutasFrescasImg;
  }
  if (nameLower.includes('combo') || nameLower.includes('paquete') || catLower.includes('combo')) {
    return combosDeluxeImg;
  }
  if (nameLower.includes('focaccia') || catLower.includes('focaccia')) {
    return focacciaArtesanalImg;
  }
  if (nameLower.includes('omelette') || nameLower.includes('omelet') || nameLower.includes('huevo') || catLower.includes('omelette')) {
    return omeletteGourmetImg;
  }
  if (nameLower.includes('quesadilla') || catLower.includes('quesadilla')) {
    return quesadillasDoradasImg;
  }
  if (nameLower.includes('agua') || (catLower.includes('agua') && !catLower.includes('aguacate'))) {
    return aguasFrescasImg;
  }
  if (nameLower.includes('verde') || nameLower.includes('apio') || nameLower.includes('nopal')) {
    return jugoVerdeImg;
  }
  if (nameLower.includes('rojo') || nameLower.includes('betabel') || nameLower.includes('anemia')) {
    return extractoRojoImg;
  }
  if (nameLower.includes('smoothie') || nameLower.includes('rosa') || nameLower.includes('fresa')) {
    return smoothieRosaImg;
  }
  if (nameLower.includes('matcha') || nameLower.includes('maccha') || nameLower.includes('latte') || nameLower.includes('café') || nameLower.includes('cafe')) {
    return macchaPinkuImg;
  }
  if (nameLower.includes('ensalada') || nameLower.includes('frutos') || nameLower.includes('salad') || catLower.includes('ensalada')) {
    return ensaladaFrutosImg;
  }
  if (nameLower.includes('sando') || nameLower.includes('sandwich') || nameLower.includes('emparedado') || nameLower.includes('pollo') || catLower.includes('sando') || catLower.includes('emparedado')) {
    return sandoKyotoImg;
  }
  if (nameLower.includes('cuernito') || nameLower.includes('pan') || nameLower.includes('baguette') || nameLower.includes('bisquet') || catLower.includes('pan')) {
    return cuernitoJamonImg;
  }
  if (catLower.includes('jugo') || catLower.includes('extracto')) {
    return jugoVerdeImg;
  }
  if (catLower.includes('smoothie')) {
    return smoothieRosaImg;
  }
  if (catLower.includes('café') || catLower.includes('matcha')) {
    return macchaPinkuImg;
  }

  return todosMenuHeroImg;
}

export function getCategoryCover(categoryName: string): string {
  const cat = (categoryName || '').toLowerCase().trim();
  if (cat === 'todos' || cat === 'all' || cat === 'menú' || cat === 'todo el menú' || cat === '') {
    return todosMenuHeroImg;
  }
  if (cat.includes('gratinado') || cat.includes('horneado')) {
    return gratinadosSushiImg;
  }
  if (cat.includes('natural') || cat.includes('fresco') || cat.includes('frio') || cat.includes('frío')) {
    return naturalSushiImg;
  }
  if (cat.includes('sushi') || cat.includes('rollo') || cat.includes('roll') || cat.includes('maki') || cat.includes('nigiri') || cat.includes('sashimi') || cat.includes('tampico')) {
    return sushiRollsImg;
  }
  if (cat.includes('bebida') || cat.includes('refresco') || cat.includes('cerveza') || cat.includes('trago') || cat.includes('bar') || cat.includes('cocktail') || cat.includes('coctel') || cat.includes('drink')) {
    return bebidasBarImg;
  }
  if (cat.includes('taco') || cat.includes('asada') || cat.includes('pastor') || cat.includes('gringa')) {
    return tacosMexicanosImg;
  }
  if (cat.includes('burger') || cat.includes('hamburguesa') || cat.includes('alita') || cat.includes('boneless')) {
    return gourmetBurgersImg;
  }
  if (cat.includes('pizza') || cat.includes('pasta')) {
    return artisanPizzaImg;
  }
  if (cat.includes('fruta') || cat.includes('cereal') || cat.includes('avena')) {
    return frutasFrescasImg;
  }
  if (cat.includes('combo') || cat.includes('paquete')) {
    return combosDeluxeImg;
  }
  if (cat.includes('focaccia')) {
    return focacciaArtesanalImg;
  }
  if (cat.includes('omelette') || cat.includes('omelet') || cat.includes('huevo') || cat.includes('desayuno')) {
    return omeletteGourmetImg;
  }
  if (cat.includes('quesadilla')) {
    return quesadillasDoradasImg;
  }
  if (cat.includes('agua') || cat.includes('infusión') || cat.includes('infusion')) {
    return aguasFrescasImg;
  }
  if (cat.includes('ensalada')) {
    return ensaladaFrutosImg;
  }
  if (cat.includes('sando') || cat.includes('sandwich') || cat.includes('emparedado') || cat.includes('baguette')) {
    return sandoKyotoImg;
  }
  if (cat.includes('smoothie') || cat.includes('licuado') || cat.includes('bowl')) {
    return smoothieRosaImg;
  }
  if (cat.includes('café') || cat.includes('cafe') || cat.includes('matcha') || cat.includes('latte')) {
    return macchaPinkuImg;
  }
  if (cat.includes('pan') || cat.includes('croissant') || cat.includes('cuernito') || cat.includes('repostería')) {
    return cuernitoJamonImg;
  }
  if (cat.includes('jugo') || cat.includes('extracto') || cat.includes('shot')) {
    return jugoVerdeImg;
  }
  return todosMenuHeroImg;
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

export function getProductNutritionMeta(productName: string): { calories: string; prep_time: string; tag: string } {
  const name = productName.toLowerCase();
  if (name.includes('jugo') || name.includes('extracto') || name.includes('shot')) {
    return { calories: '120 kcal', prep_time: '5-8 min', tag: 'Cold Pressed' };
  }
  if (name.includes('smoothie')) {
    return { calories: '260 kcal', prep_time: '6-10 min', tag: 'Energizante' };
  }
  if (name.includes('matcha') || name.includes('latte') || name.includes('café')) {
    return { calories: '140 kcal', prep_time: '4-7 min', tag: 'Especialidad' };
  }
  if (name.includes('ensalada')) {
    return { calories: '320 kcal', prep_time: '10-15 min', tag: 'Gourmet' };
  }
  if (name.includes('sando') || name.includes('emparedado')) {
    return { calories: '480 kcal', prep_time: '12-15 min', tag: 'Chef Choice' };
  }
  if (name.includes('cuernito') || name.includes('pan')) {
    return { calories: '290 kcal', prep_time: '3-5 min', tag: 'Artesanal' };
  }
  if (name.includes('fruta') || name.includes('avena') || name.includes('cereal')) {
    return { calories: '190 kcal', prep_time: '4-6 min', tag: 'Natural' };
  }
  if (name.includes('focaccia')) {
    return { calories: '340 kcal', prep_time: '8-12 min', tag: 'Horneado' };
  }
  if (name.includes('omelette') || name.includes('huevo')) {
    return { calories: '360 kcal', prep_time: '10-14 min', tag: 'Desayuno' };
  }
  if (name.includes('quesadilla')) {
    return { calories: '420 kcal', prep_time: '8-10 min', tag: 'Clásico' };
  }
  if (name.includes('agua')) {
    return { calories: '90 kcal', prep_time: '2-4 min', tag: 'Refrescante' };
  }
  return { calories: '180 kcal', prep_time: '5-10 min', tag: 'Fresco' };
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
