import type { CartItem, Product, SelectedModifier } from '../types';

const commercial = (kind: string) => kind === 'modifier' || kind === 'ingredient_extra';

export const hasCustomizationOptions = (product: Product): boolean =>
  (product.modifier_groups ?? []).some(group => group.options.some(option => commercial(option.selection_kind)));

export const hasSelectedCustomization = (modifiers?: SelectedModifier[]): boolean =>
  (modifiers ?? []).some(option => commercial(option.selection_kind));

export function currentModifiers(product: Product, modifiers: SelectedModifier[]): SelectedModifier[] {
  const options = new Map((product.modifier_groups ?? []).flatMap(group => group.options).map(option => [option.id, option]));
  return modifiers.map(modifier => {
    const option = options.get(modifier.option_id);
    return option ? { ...modifier, name: option.name, price_delta_cents: option.price_delta_cents, selection_kind: option.selection_kind } : { ...modifier };
  });
}

export function calculateLineTotal(product: Product, quantity: number, modifiers: SelectedModifier[]): number {
  const base = product.is_promo && product.promo_price_cents && product.promo_price_cents < product.price_cents
    ? product.promo_price_cents : product.price_cents;
  return quantity * (base + currentModifiers(product, modifiers).reduce((sum, option) => sum + option.price_delta_cents, 0));
}

export function validateCartDraft(product: Product, quantity: number, modifiers: SelectedModifier[]): string | null {
  if (product.is_available === false) return 'Este producto ya no está disponible.';
  if (!Number.isSafeInteger(quantity) || quantity < 1 || quantity > 99) return 'La cantidad debe ser un entero entre 1 y 99.';
  const ids = new Set(modifiers.map(option => option.option_id));
  if (ids.size !== modifiers.length) return 'Hay opciones repetidas. Revisa tu selección.';
  const groups = product.modifier_groups ?? [];
  const options = new Set(groups.flatMap(group => group.options).map(option => option.id));
  if (modifiers.some(option => !options.has(option.option_id))) return 'Una opción ya no está disponible. Quítala para continuar.';
  for (const group of groups) {
    const count = group.options.filter(option => ids.has(option.id)).length;
    if (count < group.minimum_selections) return `Selecciona al menos ${group.minimum_selections} en ${group.name}.`;
    if (count > group.maximum_selections) return `Selecciona como máximo ${group.maximum_selections} en ${group.name}.`;
  }
  if (!Number.isSafeInteger(product.price_cents)
    || (product.is_promo && product.promo_price_cents != null && !Number.isSafeInteger(product.promo_price_cents))
    || currentModifiers(product, modifiers).some(option => !Number.isSafeInteger(option.price_delta_cents))) {
    return 'El catálogo contiene un importe inválido. Actualízalo antes de guardar.';
  }
  const total = calculateLineTotal(product, quantity, modifiers);
  if (!Number.isSafeInteger(total) || total < 0) return 'No pudimos calcular el importe. Actualiza el catálogo.';
  return null;
}

export function replaceCartLine(cart: CartItem[], cartId: string, product: Product, quantity: number, notes: string, modifiers: SelectedModifier[]): CartItem[] {
  const index = cart.findIndex(item => item.cart_id === cartId && item.product.id === product.id);
  if (index < 0) return cart;
  const error = validateCartDraft(product, quantity, modifiers);
  if (error) throw new Error(error);
  const next = [...cart];
  next[index] = { ...cart[index], product, quantity, notes, modifiers: currentModifiers(product, modifiers), line_total_cents: calculateLineTotal(product, quantity, modifiers) };
  return next;
}
