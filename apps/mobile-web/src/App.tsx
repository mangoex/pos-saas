import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { Product, Category, CartItem, CustomerOrderInfo, OrderType, CreatedOrderResult, BranchInfo, SelectedModifier, StorefrontOrganization, TrendingDish } from './types';
import { fetchMobileMenu, submitMobileOrder, fetchStorefront, fetchStorefrontContext, saveCustomerProfile, fetchTrendingDishes } from './api';
import { HeroHeader } from './components/HeroHeader';
import { CategoryCircles } from './components/CategoryCircles';
import { SizeSelectorFilter } from './components/SizeSelectorFilter';
import { ProductCard } from './components/ProductCard';
import { ProductModal } from './components/ProductModal';
import { CartDrawer } from './components/CartDrawer';
import { OrderSuccessModal } from './components/OrderSuccessModal';
import { FavoritesView } from './components/FavoritesView';
import { TrendingFeed } from './components/TrendingFeed';
import { BottomNav, NavTab } from './components/BottomNav';
import { FloatingCartBar } from './components/FloatingCartBar';
import { BranchSelectorModal } from './components/BranchSelectorModal';
import { VoiceOrderModal } from './components/VoiceOrderModal';
import { detectProductSize } from './imageMap';
import { replaceCartLine, validateCartDraft } from './utils/cartPersonalization';
import { hasPendingMobileOrder, readPendingMobileOrder, mobileOrderTimestamp, hasMobileOrderCompletedSince } from './pendingMobileOrder';

const EXCLUDED_CATEGORY_KEYWORDS = [
  'servicio a domicilio',
  'domicilio',
  'envio',
  'envío',
  'delivery',
  'extra',
  'extras',
  'adicional',
  'adicionales',
  'modificador',
  'modificadores',
];
const API_BASE_URL = '/api/v1';

export const App: React.FC = () => {
  const [products, setProducts] = useState<Product[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeCategoryId, setActiveCategoryId] = useState<string>('all');
  const [activeSize, setActiveSize] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [orderType, setOrderType] = useState<OrderType>('takeaway');
  const feedContainerRef = useRef<HTMLDivElement>(null);

  // Branch & GPS Geolocation state
  const [branches, setBranches] = useState<BranchInfo[]>([]);
  const [selectedBranch, setSelectedBranch] = useState<BranchInfo | null>(null);
  const [isBranchModalOpen, setIsBranchModalOpen] = useState(false);
  const [isLoadingLocation, setIsLoadingLocation] = useState(false);
  const [customerCoords, setCustomerCoords] = useState<{ lat: number; lng: number } | null>(null);
  const [returnToCartAfterBranch, setReturnToCartAfterBranch] = useState(false);
  const [organization, setOrganization] = useState<StorefrontOrganization | null>(null);
  const [isResolvingStorefront, setIsResolvingStorefront] = useState(true);
  const [storefrontError, setStorefrontError] = useState<string | null>(null);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [catalogRetry, setCatalogRetry] = useState(0);
  const [catalogHasActiveShift, setCatalogHasActiveShift] = useState<boolean | undefined>(undefined);
  const [storageReadyKey, setStorageReadyKey] = useState<string | null>(null);
  const [, refreshPendingOrder] = useState(0);
  const cartStartedAt = useRef(mobileOrderTimestamp());

  // Visual Theme (Light vs Warm Dark)
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', 'orange');
  }, []);

  const [likedProductIds, setLikedProductIds] = useState<Set<string>>(new Set());

  const [cart, setCart] = useState<CartItem[]>([]);

  // Modals & Navigation state
  const [currentTab, setCurrentTab] = useState<NavTab>('explore');
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);
  const [editingLine, setEditingLine] = useState<{ cartId: string; namespace: string } | null>(null);
  const consumedDeepLink = useRef<string | null>(null);
  const [isCartOpen, setIsCartOpen] = useState(false);
  const [isVoiceModalOpen, setIsVoiceModalOpen] = useState(false);
  const [isSubmittingOrder, setIsSubmittingOrder] = useState(false);
  const submittingOrderRef = useRef(false);
  const [createdOrderResult, setCreatedOrderResult] = useState<CreatedOrderResult | null>(null);
  const [orderSubmitError, setOrderSubmitError] = useState<string | null>(null);

  // Trending Dishes state
  const [trendingDishes, setTrendingDishes] = useState<TrendingDish[]>([]);
  const [isLoadingTrending, setIsLoadingTrending] = useState(false);

  // Restaurant Context (SaaS Multi-tenant)
  const storefrontIdentifier = useMemo(() => {
    try {
      const urlParams = new URLSearchParams(window.location.search);
      const pathSegments = window.location.pathname.split('/').filter(Boolean);
      let slug = urlParams.get('restaurant') || urlParams.get('r') || urlParams.get('org');
      if (!slug && ['r', 'restaurant', 'org', 'menu', 'order', 'mobile'].includes(pathSegments[0]) && pathSegments[1]) {
        slug = pathSegments[1];
      }
      if (slug) {
        return slug;
      }
      return null;
    } catch {
      return null;
    }
  }, []);

  const resolveStorefront = useCallback(async () => {
    setIsResolvingStorefront(true);
    setStorefrontError(null);
    try {
      const storefront = storefrontIdentifier
        ? await fetchStorefront(storefrontIdentifier)
        : await fetchStorefrontContext();
      setOrganization(storefront.organization);
      setBranches(storefront.branches);
      let savedId: string | null = null;
      try { savedId = localStorage.getItem(`restaurantos_storefront:${storefront.organization.id}:selected_branch`); } catch { /* Storage may be unavailable. */ }
      const selected = storefront.branches.find((branch) => branch.id === storefront.selected_branch_id)
        ?? storefront.branches.find((branch) => branch.id === savedId) ?? storefront.branches[0] ?? null;
      setSelectedBranch(selected);
      if (!selected) setStorefrontError('Este restaurante no tiene una sucursal disponible para pedidos.');
    } catch {
      setOrganization(null);
      setBranches([]);
      setSelectedBranch(null);
      setStorefrontError('No pudimos encontrar este restaurante. Verifica el enlace e inténtalo de nuevo.');
    } finally {
      setIsResolvingStorefront(false);
    }
  }, [storefrontIdentifier]);

  // Geolocation detector
  const detectLocationAndFetchBranches = useCallback(() => {
    setIsLoadingLocation(true);

    if ('geolocation' in navigator) {
      navigator.geolocation.getCurrentPosition(
        async (pos) => {
          const lat = pos.coords.latitude;
          const lng = pos.coords.longitude;
          setCustomerCoords({ lat, lng });
          setIsLoadingLocation(false);
        },
        async (err) => {
          console.warn('High accuracy geolocation failed or denied, retrying fallback...', err);
          navigator.geolocation.getCurrentPosition(
            async (fallbackPos) => {
              const lat = fallbackPos.coords.latitude;
              const lng = fallbackPos.coords.longitude;
              setCustomerCoords({ lat, lng });
              setIsLoadingLocation(false);
            },
            async (fallbackErr) => {
              console.warn('Geolocation unavailable, loading default branches:', fallbackErr);
              setIsLoadingLocation(false);
            },
            { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 }
          );
        },
        { enableHighAccuracy: true, timeout: 5000, maximumAge: 60000 }
      );
    } else {
      setIsLoadingLocation(false);
    }
  }, []);

  // Load branches on mount; the catalog follows the selected branch key exactly.
  useEffect(() => {
    void resolveStorefront();
  }, [resolveStorefront]);

  useEffect(() => {
    let isMounted = true;
    setLoading(true);
    setCatalogError(null);
    setProducts([]);
    setCategories([]);
    setCatalogHasActiveShift(undefined);
    if (!selectedBranch?.public_key) {
      setProducts([]);
      setCategories([]);
      setLoading(false);
      return () => { isMounted = false; };
    }
    fetchMobileMenu(selectedBranch.public_key).then(({ products: prods, categories: cats, has_active_shift }) => {
      if (isMounted) {
        setProducts(prods);
        setCategories(cats);
        setCatalogHasActiveShift(has_active_shift);
        setLoading(false);
      }
    }).catch(() => {
      if (isMounted) {
        setLoading(false);
        setCatalogError('No pudimos cargar el catálogo. Inténtalo de nuevo.');
      }
    });
    return () => {
      isMounted = false;
    };
  }, [selectedBranch?.public_key, catalogRetry]);



  // Fetch trending dishes whenever branch changes
  useEffect(() => {
    if (!selectedBranch?.public_key) {
      setTrendingDishes([]);
      return;
    }
    let isMounted = true;
    setIsLoadingTrending(true);
    fetchTrendingDishes(selectedBranch.public_key)
      .then((dishes) => {
        if (isMounted) {
          setTrendingDishes(dishes);
        }
      })
      .catch((err) => {
        console.warn('Failed to load trending dishes:', err);
        if (isMounted) {
          setTrendingDishes([]);
        }
      })
      .finally(() => {
        if (isMounted) {
          setIsLoadingTrending(false);
        }
      });
    return () => {
      isMounted = false;
    };
  }, [selectedBranch?.public_key]);

  // Deep Link handler: ?dish=<productId> or ?p=<productId> or ?product=<productId>
  useEffect(() => {
    if (products.length === 0 || editingLine || isCartOpen) return;
    try {
      const urlParams = new URLSearchParams(window.location.search);
      const dishId = urlParams.get('dish') || urlParams.get('p') || urlParams.get('product');
      const linkContext = `${organization?.id}:${selectedBranch?.id}:${dishId}`;
      if (dishId && consumedDeepLink.current !== linkContext) {
        const target = products.find((p) => p.id === dishId);
        if (target) {
          consumedDeepLink.current = linkContext;
          setSelectedProduct(target);
        }
      }
    } catch {
      // ignore
    }
  }, [products]);

  const handleSelectBranch = (branch: BranchInfo) => {
    if (submittingOrderRef.current) return;
    if (!branches.some((candidate) => candidate.id === branch.id)) return;
    setSelectedBranch(branch);
    if (organization) {
      try { localStorage.setItem(`restaurantos_storefront:${organization.id}:selected_branch`, branch.id); } catch { /* Selection still works without storage. */ }
    }
    if (returnToCartAfterBranch) {
      setReturnToCartAfterBranch(false);
      setIsCartOpen(true);
    }
  };

  const storageNamespace = organization && selectedBranch
    ? `restaurantos_storefront:${organization.id}:${selectedBranch.id}` : null;
  const pendingOrder = hasPendingMobileOrder(selectedBranch?.public_key || selectedBranch?.id);
  const pendingState = readPendingMobileOrder(selectedBranch?.public_key || selectedBranch?.id);
  const hasStaleCart = () => Boolean(cart.length && selectedBranch
    && hasMobileOrderCompletedSince(selectedBranch.public_key || selectedBranch.id, cartStartedAt.current));
  const staleCart = hasStaleCart();
  const cartMutationsBlocked = () => submittingOrderRef.current
    || hasPendingMobileOrder(selectedBranch?.public_key || selectedBranch?.id) || hasStaleCart();
  const editingBlockedReason = isSubmittingOrder ? 'Estamos confirmando tu pedido.'
    : pendingState.kind === 'legacy' ? 'Hay un envío anterior sin información suficiente para reintentarlo. Contacta a la sucursal para confirmar si lo recibió antes de hacer otro pedido.'
    : pendingState.kind === 'unavailable' ? 'No podemos acceder al almacenamiento de este navegador para confirmar pedidos de forma segura.'
    : pendingOrder ? 'Hay un envío pendiente de confirmar. Reintenta el envío original antes de cambiar tu pedido.'
    : staleCart ? 'Se confirmó un pedido en otra pestaña. Conservamos este carrito para que lo revises; no lo enviaremos otra vez.' : undefined;
  const catalogReady = !loading && !catalogError && Boolean(selectedBranch?.public_key) && storageReadyKey === storageNamespace;
  const liveCartContext = useRef({ namespace: storageNamespace, cart, products, blocked: Boolean(editingBlockedReason), catalogReady, editingLine });
  liveCartContext.current = { namespace: storageNamespace, cart, products, blocked: Boolean(editingBlockedReason), catalogReady, editingLine };
  const editingItem = editingLine?.namespace === storageNamespace
    ? cart.find(item => item.cart_id === editingLine.cartId) : undefined;
  const editingProduct = editingItem ? products.find(product => product.id === editingItem.product.id) : undefined;

  useEffect(() => {
    const refresh = () => {
      refreshPendingOrder(version => version + 1);
    };
    window.addEventListener('storage', refresh);
    return () => window.removeEventListener('storage', refresh);
  }, [storageNamespace, selectedBranch?.public_key, selectedBranch?.id]);

  useEffect(() => {
    setEditingLine(null);
    setSelectedProduct(null);
    setOrderSubmitError(null);
  }, [storageNamespace]);

  useEffect(() => {
    if (editingLine && !editingItem) setEditingLine(null);
  }, [editingLine, editingItem]);

  useEffect(() => {
    setStorageReadyKey(null);
    cartStartedAt.current = mobileOrderTimestamp();
    if (!storageNamespace) { setLikedProductIds(new Set()); setCart([]); return; }
    try {
      const favorites = localStorage.getItem(`${storageNamespace}:favorites`);
      const savedCart = localStorage.getItem(`${storageNamespace}:cart`);
      const savedEpoch = localStorage.getItem(`${storageNamespace}:cart_started_at`);
      cartStartedAt.current = savedEpoch && Number.isFinite(Number(savedEpoch)) ? Number(savedEpoch) : savedCart ? 0 : mobileOrderTimestamp();
      setLikedProductIds(favorites ? new Set(JSON.parse(favorites)) : new Set());
      setCart(savedCart ? JSON.parse(savedCart) : []);
    } catch { setLikedProductIds(new Set()); setCart([]); }
    setStorageReadyKey(storageNamespace);
  }, [storageNamespace]);

  useEffect(() => {
    if (!organization) return;
    const palette = selectedBranch?.color_palette || 'orange';
    document.documentElement.setAttribute('data-theme', organization.mobile_theme === 'dark' ? 'dark' : palette);
    document.title = `${organization.name} | Menú Digital`;
    let manifest = document.querySelector<HTMLLinkElement>('link[rel="manifest"]');
    if (!manifest) {
      manifest = document.createElement('link');
      manifest.rel = 'manifest';
      document.head.appendChild(manifest);
    }
    manifest.href = storefrontIdentifier
      ? `${API_BASE_URL}/public/storefronts/${encodeURIComponent(organization.public_slug)}/manifest.webmanifest`
      : `${API_BASE_URL}/public/storefront-context/manifest.webmanifest`;
  }, [organization, storefrontIdentifier]);

  useEffect(() => {
    if (storageNamespace && storageReadyKey === storageNamespace) localStorage.setItem(`${storageNamespace}:favorites`, JSON.stringify(Array.from(likedProductIds)));
  }, [likedProductIds, storageNamespace, storageReadyKey]);

  useEffect(() => {
    if (storageNamespace && storageReadyKey === storageNamespace) {
      localStorage.setItem(`${storageNamespace}:cart_started_at`, String(cartStartedAt.current));
      localStorage.setItem(`${storageNamespace}:cart`, JSON.stringify(cart));
    }
  }, [cart, storageNamespace, storageReadyKey]);

  // Reset size filter when category changes
  useEffect(() => {
    setActiveSize('all');
  }, [activeCategoryId]);

  // Toggle Heart / Like
  const handleToggleLike = (productId: string) => {
    setLikedProductIds((prev) => {
      const next = new Set(prev);
      if (next.has(productId)) {
        next.delete(productId);
      } else {
        next.add(productId);
      }
      return next;
    });
  };

  // Add to Cart
  const handleAddToCart = (product: Product, quantity: number, notes?: string, modifiers: SelectedModifier[] = []) => {
    if (liveCartContext.current.blocked || cartMutationsBlocked()) return;
    const basePriceCents = (product.is_promo && product.promo_price_cents && product.promo_price_cents < product.price_cents)
      ? product.promo_price_cents
      : product.price_cents;
    setCart((prev) => {
      if (prev.length === 0) cartStartedAt.current = mobileOrderTimestamp();
      const existingIndex = prev.findIndex(
        (item) => item.product.id === product.id
          && item.notes === (notes || '')
          && JSON.stringify(item.modifiers ?? []) === JSON.stringify(modifiers)
      );
      if (existingIndex > -1) {
        const updated = [...prev];
        const current = updated[existingIndex];
        const newQty = current.quantity + quantity;
        updated[existingIndex] = {
          ...current,
          quantity: newQty,
          line_total_cents: newQty * (basePriceCents + modifiers.reduce((sum, modifier) => sum + modifier.price_delta_cents, 0)),
        };
        return updated;
      } else {
        const newItem: CartItem = {
          cart_id: `${product.id}-${Date.now()}`,
          product,
          quantity,
          notes: notes || '',
          modifiers,
          line_total_cents: quantity * (basePriceCents + modifiers.reduce((sum, modifier) => sum + modifier.price_delta_cents, 0)),
        };
        return [...prev, newItem];
      }
    });
  };

  // Required catalog choices cannot be silently bypassed from the quick-add affordance.
  const handleQuickAddToCart = (product: Product) => {
    if (liveCartContext.current.blocked || cartMutationsBlocked()) return;
    if ((product.modifier_groups ?? []).some((group) => group.minimum_selections > 0)) {
      setSelectedProduct(product);
      return;
    }
    handleAddToCart(product, 1);
  };

  const handleUpdateCartQuantity = (cartId: string, delta: number) => {
    if (liveCartContext.current.blocked || cartMutationsBlocked()) return;
    setCart((prev) => {
      return prev
        .map((item) => {
          if (item.cart_id === cartId) {
            const newQty = item.quantity + delta;
            if (newQty <= 0) return null;
            const basePriceCents = (item.product.is_promo && item.product.promo_price_cents && item.product.promo_price_cents < item.product.price_cents)
              ? item.product.promo_price_cents
              : item.product.price_cents;
            return {
              ...item,
              quantity: newQty,
              line_total_cents: newQty * (basePriceCents + (item.modifiers ?? []).reduce((sum, modifier) => sum + modifier.price_delta_cents, 0)),
            };
          }
          return item;
        })
        .filter((item): item is CartItem => item !== null);
    });
  };

  const handleRemoveCartItem = (cartId: string) => {
    if (liveCartContext.current.blocked || cartMutationsBlocked()) return;
    setCart((prev) => prev.filter((item) => item.cart_id !== cartId));
  };

  const handleEditCartItem = (cartId: string) => {
    if (!catalogReady || !storageNamespace || liveCartContext.current.blocked || cartMutationsBlocked()) return;
    if (!cart.some(item => item.cart_id === cartId)) return;
    setSelectedProduct(null);
    setEditingLine({ cartId, namespace: storageNamespace });
  };

  const handleSaveCartItem = (quantity: number, notes: string, modifiers: SelectedModifier[]) => {
    const current = liveCartContext.current;
    if (!editingLine || editingLine !== current.editingLine || editingLine.namespace !== current.namespace || current.blocked || !current.catalogReady || cartMutationsBlocked()) return;
    const item = current.cart.find(line => line.cart_id === editingLine.cartId);
    const product = current.products.find(candidate => candidate.id === item?.product.id);
    if (!item || !product || validateCartDraft(product, quantity, modifiers)) return;
    setCart(previous => {
      if (liveCartContext.current.namespace !== editingLine.namespace || liveCartContext.current.blocked) return previous;
      return replaceCartLine(previous, editingLine.cartId, product, quantity, notes, modifiers);
    });
    setEditingLine(null);
  };

  // Submit Order (Hybrid: System + WhatsApp with Branch & GPS)
  const handleSubmitOrder = async (info: CustomerOrderInfo) => {
    if (submittingOrderRef.current || editingLine) return;
    submittingOrderRef.current = true;
    liveCartContext.current.blocked = true;
    const submittedNamespace = storageNamespace;
    setIsSubmittingOrder(true);
    setOrderSubmitError(null);
    try {
      const result = await submitMobileOrder(
        info,
        cart,
        selectedBranch?.id,
        selectedBranch?.name,
        customerCoords || undefined,
        selectedBranch?.public_key || selectedBranch?.id,
        selectedBranch?.phone,
        Boolean(selectedBranch?.whatsapp_ordering_enabled) === true,
        cartStartedAt.current,
      );
      if (liveCartContext.current.namespace !== submittedNamespace) return;
      saveCustomerProfile({
        name: result.customer_info.name,
        phone: result.customer_info.phone,
        street: result.customer_info.address_street,
        number: result.customer_info.address_number,
        neighborhood: result.customer_info.address_neighborhood,
        address_notes: result.customer_info.address_notes,
      });
      setCreatedOrderResult(result);
      // A replay may belong to another tab's snapshot. Never discard divergent local work.
      setCart(previous => JSON.stringify(previous) === JSON.stringify(result.items) ? [] : previous);
      setIsCartOpen(false);
    } catch (err: any) {
      if (liveCartContext.current.namespace !== submittedNamespace) return;
      setOrderSubmitError(err?.message || 'No fue posible confirmar el pedido. Conservamos tu carrito para que puedas reintentar.');
    } finally {
      submittingOrderRef.current = false;
      setIsSubmittingOrder(false);
    }
  };

  // Filter visible categories: exclude empty categories and operational items (delivery fee, extras)
  // Filter visible categories: exclude empty categories and operational items (delivery fee, extras)
  const visibleCategories = useMemo(() => {
    const list = categories.filter((cat) => {
      const isAll = cat.id === 'all';
      if (isAll) return products.length > 0;

      const nameLower = (cat.name || '').toLowerCase().trim();
      const isExcluded = EXCLUDED_CATEGORY_KEYWORDS.some((kw) => nameLower === kw || nameLower.includes(kw));
      if (isExcluded) return false;

      const count = products.filter((p) => p.category_name === cat.name || p.category_id === cat.id).length;
      return count > 0;
    });

    const hasPromos = products.some((p) => p.is_promo);
    if (hasPromos) {
      const allIndex = list.findIndex((c) => c.id === 'all');
      const promoCategory: Category = { id: 'promotions', name: '🔥 Promociones' };
      if (allIndex >= 0) {
        list.splice(allIndex + 1, 0, promoCategory);
      } else {
        list.unshift(promoCategory);
      }
    }

    return list;
  }, [categories, products]);

  // Ensure activeCategoryId stays valid among visible categories
  useEffect(() => {
    if (activeCategoryId !== 'all' && visibleCategories.length > 0) {
      const exists = visibleCategories.some((c) => c.id === activeCategoryId);
      if (!exists) {
        setActiveCategoryId('all');
      }
    }
  }, [visibleCategories, activeCategoryId]);

  // Extract available sizes in current category
  const availableSizes = useMemo(() => {
    const sizeSet = new Set<string>();
    products.forEach((p) => {
      if (activeCategoryId === 'promotions') {
        if (!p.is_promo) return;
      } else if (activeCategoryId !== 'all' && activeCategoryId !== '') {
        const selectedCat = visibleCategories.find((c) => c.id === activeCategoryId);
        if (selectedCat && p.category_name !== selectedCat.name) {
          return;
        }
      }
      const s = detectProductSize(p.name);
      if (s) sizeSet.add(s);
    });
    const order = ['CH', 'MED', 'GDE', '500ml', '1L'];
    return Array.from(sizeSet).sort((a, b) => {
      const idxA = order.indexOf(a);
      const idxB = order.indexOf(b);
      if (idxA !== -1 && idxB !== -1) return idxA - idxB;
      if (idxA !== -1) return -1;
      if (idxB !== -1) return 1;
      return a.localeCompare(b);
    });
  }, [products, visibleCategories, activeCategoryId]);

  const productsCountByCategory = useMemo(() => {
    const map: Record<string, number> = {};
    visibleCategories.forEach((cat) => {
      if (cat.id === 'promotions') {
        map[cat.id] = products.filter((p) => p.is_promo).length;
      } else if (cat.id === 'all') {
        map[cat.id] = products.length;
      } else {
        map[cat.id] = products.filter((p) => p.category_name === cat.name || p.category_id === cat.id).length;
      }
    });
    return map;
  }, [visibleCategories, products]);

  // Handle clicking on category card -> smooth scroll down/up to feed
  const handleCategoryCardClick = useCallback((_categoryId: string) => {
    if (feedContainerRef.current) {
      feedContainerRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, []);

  // Filtered Products
  const filteredProducts = useMemo(() => {
    return products.filter((p) => {
      // Category filter
      if (activeCategoryId === 'promotions') {
        if (!p.is_promo) return false;
      } else if (activeCategoryId !== 'all' && activeCategoryId !== '') {
        const selectedCat = visibleCategories.find((c) => c.id === activeCategoryId);
        if (selectedCat && p.category_name !== selectedCat.name) {
          return false;
        }
      }
      // Size filter
      if (activeSize !== 'all') {
        const s = detectProductSize(p.name);
        if (s !== activeSize) return false;
      }
      // Search filter
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchesName = p.name.toLowerCase().includes(q);
        const matchesDesc = (p.description || '').toLowerCase().includes(q);
        const matchesCat = (p.category_name || '').toLowerCase().includes(q);
        if (!matchesName && !matchesDesc && !matchesCat) return false;
      }
      return true;
    });
  }, [products, visibleCategories, activeCategoryId, activeSize, searchQuery]);

  const favoriteProducts = useMemo(() => {
    return products.filter((p) => likedProductIds.has(p.id));
  }, [products, likedProductIds]);

  const totalCartCount = cart.reduce((sum, item) => sum + item.quantity, 0);
  const totalCartCents = cart.reduce((sum, item) => sum + item.line_total_cents, 0);
  const currentCategory = visibleCategories.find((c) => c.id === activeCategoryId);
  const isBranchClosed = selectedBranch?.has_active_shift === false || catalogHasActiveShift === false;
  const hasActiveShift = !isBranchClosed;

  if (isResolvingStorefront || storefrontError) {
    return (
      <main className="mobile-app-shell feed-empty-state" role={storefrontError ? 'alert' : 'status'}>
        <p className="empty-title">{isResolvingStorefront ? 'Abriendo menú…' : storefrontError}</p>
        {storefrontError && <button type="button" className="btn-reset-filters" onClick={() => void resolveStorefront()}>Reintentar</button>}
      </main>
    );
  }

  return (
    <div className="mobile-app-shell">
      {catalogError && <div className="feed-empty-state" role="alert">
        <p>{catalogError}</p>
        <button type="button" onClick={() => setCatalogRetry(attempt => attempt + 1)}>Reintentar catálogo</button>
      </div>}
      {currentTab === 'explore' && (
        <HeroHeader
          categories={visibleCategories}
          activeCategoryId={activeCategoryId}
          onSelectCategory={setActiveCategoryId}
          onCategoryCardClick={handleCategoryCardClick}
          productsCountByCategory={productsCountByCategory}
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          selectedBranch={selectedBranch}
          onOpenBranchSelector={() => setIsBranchModalOpen(true)}
          onRefreshLocation={() => detectLocationAndFetchBranches()}
          isLoadingLocation={isLoadingLocation}
        />
      )}

      {currentTab === 'explore' && (
        <main className="mobile-main-content">
          {/* Circular Category Quick Scroll Bar (as in reference design) */}
          <CategoryCircles
            categories={visibleCategories}
            activeCategoryId={activeCategoryId}
            onSelectCategory={setActiveCategoryId}
            productsCountByCategory={productsCountByCategory}
          />

          {/* Size Filter Bar */}
          <SizeSelectorFilter
            availableSizes={availableSizes}
            activeSize={activeSize}
            onSelectSize={setActiveSize}
          />

          {/* Feed Content */}
          <div ref={feedContainerRef} className="feed-container" id="menu-feed">
            <div className="section-title-bar">
              <div className="section-title-wrapper">
                <span className="section-eyebrow">Selección de la casa</span>
                <h2>
                  {searchQuery ? `Resultados para "${searchQuery}"` : (
                    activeCategoryId === 'all'
                      ? (isBranchClosed ? 'Menú (Cerrado por el momento)' : 'Todo el Menú')
                      : (currentCategory?.name || 'Menú')
                  )}
                </h2>
              </div>
              <span className="section-count-badge">{filteredProducts.length}</span>
            </div>

            {loading ? (
              <div className="feed-loading-state">
                <div className="loading-spinner" />
                <p>Cargando menú fresco…</p>
              </div>
            ) : filteredProducts.length === 0 ? (
              <div className="feed-empty-state">
                <p className="empty-title">No encontramos productos con estos filtros.</p>
                <button
                  type="button"
                  className="btn-reset-filters"
                  onClick={() => { setSearchQuery(''); setActiveCategoryId('all'); setActiveSize('all'); }}
                >
                  Ver todo el menú
                </button>
              </div>
            ) : (
              <div className="product-items-grid">
                {filteredProducts.map((product) => (
                  <ProductCard
                    key={product.id}
                    product={product}
                    isLiked={likedProductIds.has(product.id)}
                    onToggleLike={handleToggleLike}
                    onOpenDetail={setSelectedProduct}
                    onQuickAdd={handleQuickAddToCart}
                  />
                ))}
              </div>
            )}
          </div>
        </main>
      )}

      {currentTab === 'favorites' && (
        <main className="mobile-main-content">
          <FavoritesView
            favoriteProducts={favoriteProducts}
            likedProductIds={likedProductIds}
            onToggleLike={handleToggleLike}
            onOpenDetail={setSelectedProduct}
            onQuickAdd={handleQuickAddToCart}
            onExploreMenu={() => setCurrentTab('explore')}
          />
        </main>
      )}

      {currentTab === 'trending' && (
        <main className="mobile-main-content">
          <TrendingFeed
            dishes={trendingDishes}
            isLoading={isLoadingTrending}
            likedProductIds={likedProductIds}
            onToggleLike={handleToggleLike}
            onOpenDetail={setSelectedProduct}
            onQuickAdd={handleQuickAddToCart}
            onExploreMenu={() => setCurrentTab('explore')}
            publicKey={selectedBranch?.public_key}
            restaurantName={organization?.name || selectedBranch?.name}
          />
        </main>
      )}

      {/* Floating Cart Bar on Feed when cart has items */}
      {!isCartOpen && (
        <FloatingCartBar
          totalCount={totalCartCount}
          totalCents={totalCartCents}
          onOpenCart={() => setIsCartOpen(true)}
        />
      )}

      {/* Product Detail Modal */}
      {selectedProduct && (
        <ProductModal
          key={`add:${selectedProduct.id}`}
          product={selectedProduct}
          isLiked={likedProductIds.has(selectedProduct.id)}
          onToggleLike={handleToggleLike}
          onClose={() => setSelectedProduct(null)}
          onAddToCart={handleAddToCart}
          blockedReason={editingBlockedReason}
          publicKey={selectedBranch?.public_key}
          restaurantName={organization?.name || selectedBranch?.name}
        />
      )}

      {editingItem && (
        <ProductModal
          key={`edit:${editingLine?.namespace}:${editingItem.cart_id}`}
          product={editingProduct || { ...editingItem.product, is_available: false }}
          initialItem={editingItem}
          onSave={handleSaveCartItem}
          blockedReason={editingBlockedReason || (!catalogReady ? 'Espera a que cargue el catálogo para guardar.' : !editingProduct ? 'Este producto ya no está disponible.' : undefined)}
          isLiked={likedProductIds.has(editingItem.product.id)}
          onToggleLike={handleToggleLike}
          onClose={() => setEditingLine(null)}
          onAddToCart={handleAddToCart}
          publicKey={selectedBranch?.public_key}
          restaurantName={organization?.name || selectedBranch?.name}
        />
      )}

      {/* Cart & Checkout Sheet */}
      {isCartOpen && (
        <CartDrawer
          onEditItem={handleEditCartItem}
          catalogReady={catalogReady}
          onRetryCatalog={() => setCatalogRetry(attempt => attempt + 1)}
          editingItem={Boolean(editingItem || selectedProduct)}
          editingBlockedReason={editingBlockedReason}
          onRetryPendingOrder={pendingState.kind === 'record' ? () => void handleSubmitOrder(pendingState.attempt.customerInfo) : undefined}
          onStartNewOrder={staleCart && pendingState.kind === 'none' ? () => {
            if (submittingOrderRef.current || hasPendingMobileOrder(selectedBranch?.public_key || selectedBranch?.id)) return;
            cartStartedAt.current = mobileOrderTimestamp();
            setEditingLine(null);
            setCart([]);
            setOrderSubmitError(null);
          } : undefined}
          items={pendingState.kind === 'record' ? pendingState.attempt.items : cart}
          allProducts={products}
          orderType={orderType}
          selectedBranch={selectedBranch}
          hasActiveShift={hasActiveShift}
          onOpenBranchSelector={() => {
            setReturnToCartAfterBranch(true);
            setIsCartOpen(false);
            setIsBranchModalOpen(true);
          }}
          onClose={() => setIsCartOpen(false)}
          onUpdateQuantity={handleUpdateCartQuantity}
          onRemoveItem={handleRemoveCartItem}
          onQuickAddProduct={handleQuickAddToCart}
          onSubmitOrder={handleSubmitOrder}
          isSubmitting={isSubmittingOrder}
          submitError={orderSubmitError}
        />
      )}

      {/* Branch Selector Modal */}
      <BranchSelectorModal
        isOpen={isBranchModalOpen}
        onClose={() => setIsBranchModalOpen(false)}
        branches={branches}
        selectedBranchId={selectedBranch?.id || null}
        onSelectBranch={handleSelectBranch}
        onRefreshLocation={() => detectLocationAndFetchBranches()}
        isLoadingLocation={isLoadingLocation}
      />

      {/* Order Success & WhatsApp Modal */}
      {createdOrderResult && (
        <OrderSuccessModal
          orderResult={createdOrderResult}
          branch={selectedBranch}
          onClose={() => setCreatedOrderResult(null)}
          onNewOrder={() => setCreatedOrderResult(null)}
        />
      )}

      {/* Bottom Navigation */}
      <BottomNav
        currentTab={currentTab}
        onSelectTab={(tab) => {
          if (tab === 'cart') {
            setIsCartOpen(true);
          } else {
            setCurrentTab(tab);
          }
        }}
        cartCount={totalCartCount}
        favoritesCount={likedProductIds.size}
        onOpenVoiceModal={() => setIsVoiceModalOpen(true)}
      />

      {/* Voice / AI Order Modal */}
      <VoiceOrderModal
        isOpen={isVoiceModalOpen}
        onClose={() => setIsVoiceModalOpen(false)}
        publicKey={selectedBranch?.public_key || null}
        products={products}
        onAddCartItems={(items) => {
          if (liveCartContext.current.blocked || cartMutationsBlocked()) return;
          if (cart.length === 0) cartStartedAt.current = mobileOrderTimestamp();
          setCart((prev) => [...prev, ...items]);
          setIsCartOpen(true);
        }}
      />
    </div>
  );
};

export default App;
