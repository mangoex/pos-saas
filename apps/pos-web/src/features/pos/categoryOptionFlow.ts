export interface CategoryOptionValue {
  id: string;
  code: string;
  name: string;
  display_order: number;
}

export interface CategorySelectionGroup {
  id: string;
  code: string;
  name: string;
  values: CategoryOptionValue[];
}

export interface CategoryOptionProduct {
  id: string;
  category_id?: string;
  name: string;
  selection?: { group_id: string; value_id: string } | null;
}

export interface ProductCategoryReference {
  category_id?: string;
  category?: string;
}

export type CatalogMenuGroupId = 'all' | 'food' | 'drinks' | 'other' | 'favorites';

export const CATALOG_MENU_GROUPS: ReadonlyArray<{ id: CatalogMenuGroupId; label: string }> = [
  { id: 'all', label: 'TODO' },
  { id: 'food', label: 'ALIMENTOS' },
  { id: 'drinks', label: 'BEBIDAS' },
  { id: 'other', label: 'OTROS' },
  { id: 'favorites', label: 'FAVORITOS' },
];

export interface CatalogMenuProduct extends ProductCategoryReference {
  id: string;
  station?: string;
}

export function categoriesWithAvailableProducts<
  TCategory extends { id: string; name: string },
>(categories: readonly TCategory[], products: readonly ProductCategoryReference[]): TCategory[] {
  if (products.length === 0) return [];
  const categoryIds = new Set(products.map((product) => product.category_id).filter(Boolean));
  const categoryNames = new Set(products.map((product) => product.category).filter(Boolean));
  return categories.filter((category) =>
    category.id === ''
    || category.name === 'Todas'
    || categoryIds.has(category.id)
    || categoryNames.has(category.name),
  );
}

export function productsForCatalogMenuGroup<TProduct extends CatalogMenuProduct>(
  products: readonly TProduct[], groupId: CatalogMenuGroupId, favoriteProductIds: readonly string[],
): TProduct[] {
  const norm = (v?: string) => (v || '').trim().toLowerCase();
  if (groupId === 'all') return [...products];
  if (groupId === 'food') {
    return products.filter((product) => {
      const s = norm(product.station);
      const c = norm(product.category);
      return s === 'kitchen' || s === 'cocina' || s === 'comida' || s === 'alimentos'
        || c.includes('alimento') || c.includes('comida');
    });
  }
  if (groupId === 'drinks') {
    return products.filter((product) => {
      const s = norm(product.station);
      const c = norm(product.category);
      return s === 'drinks' || s === 'barra' || s === 'bebida' || s === 'bebidas'
        || c.includes('bebida') || c.includes('refresco') || c.includes('cerveza') || c.includes('trago') || c.includes('bar');
    });
  }
  if (groupId === 'other') {
    return products.filter((product) => {
      const s = norm(product.station);
      const c = norm(product.category);
      const isFood = s === 'kitchen' || s === 'cocina' || s === 'comida' || s === 'alimentos'
        || c.includes('alimento') || c.includes('comida');
      const isDrink = s === 'drinks' || s === 'barra' || s === 'bebida' || s === 'bebidas'
        || c.includes('bebida') || c.includes('refresco') || c.includes('cerveza') || c.includes('trago') || c.includes('bar');
      return !isFood && !isDrink;
    });
  }
  const favorites = new Set(favoriteProductIds);
  return products.filter((product) => favorites.has(product.id));
}

export function categoriesForCatalogMenuGroup<
  TCategory extends { id: string; name: string },
  TProduct extends CatalogMenuProduct,
>(
  categories: readonly TCategory[], products: readonly TProduct[], groupId: CatalogMenuGroupId,
  favoriteProductIds: readonly string[],
): TCategory[] {
  if (groupId === 'favorites') return [];
  const groupedProducts = productsForCatalogMenuGroup(products, groupId, favoriteProductIds);
  const withProducts = categoriesWithAvailableProducts(categories, groupedProducts).filter(
    (category) => category.id !== '' && category.name !== 'Todas',
  );
  if (withProducts.length > 0) return withProducts;

  // Fallback: If no products exist yet for this group, allow defined categories
  // matching the group to display so the user sees their catalog structure.
  if (groupId === 'all') {
    return categories.filter((c) => c.id !== '' && c.name !== 'Todas');
  }
  if (groupId === 'drinks') {
    return categories.filter((c) => {
      const name = c.name.toLowerCase();
      return c.id !== '' && c.name !== 'Todas' && (
        name.includes('bebida') || name.includes('cerveza') || name.includes('refresco') || name.includes('bar') || name.includes('trago')
      );
    });
  }
  if (groupId === 'food') {
    return categories.filter((c) => {
      const name = c.name.toLowerCase();
      const isDrink = name.includes('bebida') || name.includes('cerveza') || name.includes('refresco') || name.includes('bar') || name.includes('trago');
      return c.id !== '' && c.name !== 'Todas' && !isDrink;
    });
  }
  return withProducts;
}

export interface CategoryOptionState {
  categoryId: string;
  valueId: string;
}

export interface CatalogNavigationState<TCart> extends CategoryOptionState {
  cart: TCart;
  search: string;
  transient: {
    modifierProductId: string | null;
    groups: string[];
    selections: Record<string, string[]>;
    error: string;
  };
}

export type CatalogProjectionState = 'ready' | 'error' | 'selection-empty';

/** Keeps projection recovery independent from cart and product selection. */
export function catalogProjectionState(
  hasCatalogError: boolean,
  group: CategorySelectionGroup | null | undefined,
): CatalogProjectionState {
  if (hasCatalogError) return 'error';
  if (group && availableOptionValues(group).length === 0) return 'selection-empty';
  return 'ready';
}

export function availableOptionValues(group: CategorySelectionGroup): CategoryOptionValue[] {
  return [...group.values].sort((left, right) =>
    left.display_order - right.display_order || left.name.localeCompare(right.name) || left.id.localeCompare(right.id),
  );
}

export function resolveCategoryOptionState(
  category: { selection_group?: CategorySelectionGroup | null }, valueId: string,
): 'products' | 'selection-required' {
  if (!category.selection_group) return 'products';
  return availableOptionValues(category.selection_group).some((value) => value.id === valueId)
    ? 'products'
    : 'selection-required';
}

export function filterProductsForCategoryOption<T extends CategoryOptionProduct>(
  products: readonly T[], categoryId: string, valueId: string, search: string,
): T[] {
  const normalizedSearch = search.trim().toLocaleLowerCase('es-MX');
  return products.filter((product) =>
    (!categoryId || product.category_id === categoryId)
    && (!valueId || product.selection?.value_id === valueId)
    && (!normalizedSearch || product.name.toLocaleLowerCase('es-MX').includes(normalizedSearch)),
  );
}

export function transitionCategoryOption(
  current: CategoryOptionState, categoryId: string, valueId: string,
): CategoryOptionState {
  if (current.categoryId !== categoryId) return { categoryId, valueId: '' };
  return { categoryId, valueId };
}

/** Navigation clears only uncommitted personalization; cart and search are preserved verbatim. */
export function transitionCatalogNavigation<TCart>(
  current: CatalogNavigationState<TCart>, categoryId: string, valueId: string,
): CatalogNavigationState<TCart> {
  const selection = transitionCategoryOption(current, categoryId, valueId);
  return {
    ...current,
    ...selection,
    transient: { modifierProductId: null, groups: [], selections: {}, error: '' },
  };
}
