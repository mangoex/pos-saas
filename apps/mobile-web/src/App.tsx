import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { Product, Category, CartItem, CustomerOrderInfo, OrderType, CreatedOrderResult, BranchInfo, SelectedModifier } from './types';
import { fetchMobileMenu, submitMobileOrder, fetchPublicBranches } from './api';
import { HeroHeader } from './components/HeroHeader';
import { CategoryCircles } from './components/CategoryCircles';
import { SizeSelectorFilter } from './components/SizeSelectorFilter';
import { ProductCard } from './components/ProductCard';
import { ProductModal } from './components/ProductModal';
import { CartDrawer } from './components/CartDrawer';
import { OrderSuccessModal } from './components/OrderSuccessModal';
import { FavoritesView } from './components/FavoritesView';
import { BottomNav, NavTab } from './components/BottomNav';
import { FloatingCartBar } from './components/FloatingCartBar';
import { BranchSelectorModal } from './components/BranchSelectorModal';
import { detectProductSize } from './imageMap';

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

  // Visual Theme (Light vs Warm Dark)
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    try {
      const urlParams = new URLSearchParams(window.location.search);
      const fromUrl = urlParams.get('theme');
      if (fromUrl === 'dark' || fromUrl === 'light') return fromUrl;
      return (localStorage.getItem('restaurantos_mobile_theme') as 'light' | 'dark') || 'light';
    } catch {
      return 'light';
    }
  });

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  // Favorites state with localStorage
  const [likedProductIds, setLikedProductIds] = useState<Set<string>>(() => {
    try {
      const saved = localStorage.getItem('restaurantos_liked_products') || localStorage.getItem('kiwi_liked_products');
      return saved ? new Set(JSON.parse(saved)) : new Set();
    } catch {
      return new Set();
    }
  });

  // Cart state with localStorage
  const [cart, setCart] = useState<CartItem[]>(() => {
    try {
      const saved = localStorage.getItem('restaurantos_mobile_cart') || localStorage.getItem('kiwi_mobile_cart');
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });

  // Modals & Navigation state
  const [currentTab, setCurrentTab] = useState<NavTab>('explore');
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);
  const [isCartOpen, setIsCartOpen] = useState(false);
  const [isSubmittingOrder, setIsSubmittingOrder] = useState(false);
  const [createdOrderResult, setCreatedOrderResult] = useState<CreatedOrderResult | null>(null);
  const [orderSubmitError, setOrderSubmitError] = useState<string | null>(null);

  // Geolocation detector
  const detectLocationAndFetchBranches = useCallback((forceNearest = false) => {
    setIsLoadingLocation(true);

    const applyBranchSelection = (branchList: BranchInfo[], isGps: boolean) => {
      setBranches(branchList);
      setIsLoadingLocation(false);
      if (branchList.length > 0) {
        if (forceNearest && isGps) {
          // When user explicitly clicks GPS button, choose the nearest branch
          setSelectedBranch(branchList[0]);
          localStorage.setItem('restaurantos_selected_branch_id', branchList[0].id);
        } else {
          const savedId = localStorage.getItem('restaurantos_selected_branch_id') || localStorage.getItem('kiwi_selected_branch_id');
          const match = branchList.find((b) => b.id === savedId);
          setSelectedBranch(match || branchList[0]);
        }
      }
    };

    if ('geolocation' in navigator) {
      navigator.geolocation.getCurrentPosition(
        async (pos) => {
          const lat = pos.coords.latitude;
          const lng = pos.coords.longitude;
          setCustomerCoords({ lat, lng });
          const branchList = await fetchPublicBranches(lat, lng);
          applyBranchSelection(branchList, true);
        },
        async (err) => {
          console.warn('High accuracy geolocation failed or denied, retrying fallback...', err);
          navigator.geolocation.getCurrentPosition(
            async (fallbackPos) => {
              const lat = fallbackPos.coords.latitude;
              const lng = fallbackPos.coords.longitude;
              setCustomerCoords({ lat, lng });
              const branchList = await fetchPublicBranches(lat, lng);
              applyBranchSelection(branchList, true);
            },
            async (fallbackErr) => {
              console.warn('Geolocation unavailable, loading default branches:', fallbackErr);
              const branchList = await fetchPublicBranches();
              applyBranchSelection(branchList, false);
            },
            { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 }
          );
        },
        { enableHighAccuracy: true, timeout: 5000, maximumAge: 60000 }
      );
    } else {
      fetchPublicBranches().then((branchList) => {
        applyBranchSelection(branchList, false);
      });
    }
  }, []);

  // Load branches on mount; the catalog follows the selected branch key exactly.
  useEffect(() => {
    detectLocationAndFetchBranches(false);
  }, [detectLocationAndFetchBranches]);

  useEffect(() => {
    let isMounted = true;
    setLoading(true);
    fetchMobileMenu(selectedBranch?.public_key).then(({ products: prods, categories: cats }) => {
      if (isMounted) {
        setProducts(prods);
        setCategories(cats);
        setLoading(false);
      }
    });
    return () => {
      isMounted = false;
    };
  }, [selectedBranch?.public_key]);

  const handleSelectBranch = (branch: BranchInfo) => {
    setSelectedBranch(branch);
    localStorage.setItem('restaurantos_selected_branch_id', branch.id);
    if (returnToCartAfterBranch) {
      setReturnToCartAfterBranch(false);
      setIsCartOpen(true);
    }
  };

  // Save favorites & cart to localStorage
  useEffect(() => {
    localStorage.setItem('restaurantos_liked_products', JSON.stringify(Array.from(likedProductIds)));
  }, [likedProductIds]);

  useEffect(() => {
    localStorage.setItem('restaurantos_mobile_cart', JSON.stringify(cart));
  }, [cart]);

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
    setCart((prev) => {
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
          line_total_cents: newQty * (product.price_cents + modifiers.reduce((sum, modifier) => sum + modifier.price_delta_cents, 0)),
        };
        return updated;
      } else {
        const newItem: CartItem = {
          cart_id: `${product.id}-${Date.now()}`,
          product,
          quantity,
          notes: notes || '',
          modifiers,
          line_total_cents: quantity * (product.price_cents + modifiers.reduce((sum, modifier) => sum + modifier.price_delta_cents, 0)),
        };
        return [...prev, newItem];
      }
    });
  };

  // Required catalog choices cannot be silently bypassed from the quick-add affordance.
  const handleQuickAddToCart = (product: Product) => {
    if ((product.modifier_groups ?? []).some((group) => group.minimum_selections > 0)) {
      setSelectedProduct(product);
      return;
    }
    handleAddToCart(product, 1);
  };

  const handleUpdateCartQuantity = (cartId: string, delta: number) => {
    setCart((prev) => {
      return prev
        .map((item) => {
          if (item.cart_id === cartId) {
            const newQty = item.quantity + delta;
            if (newQty <= 0) return null;
            return {
              ...item,
              quantity: newQty,
              line_total_cents: newQty * (item.product.price_cents + (item.modifiers ?? []).reduce((sum, modifier) => sum + modifier.price_delta_cents, 0)),
            };
          }
          return item;
        })
        .filter((item): item is CartItem => item !== null);
    });
  };

  const handleRemoveCartItem = (cartId: string) => {
    setCart((prev) => prev.filter((item) => item.cart_id !== cartId));
  };

  // Submit Order (Hybrid: System + WhatsApp with Branch & GPS)
  const handleSubmitOrder = async (info: CustomerOrderInfo) => {
    setIsSubmittingOrder(true);
    setOrderSubmitError(null);
    try {
      const result = await submitMobileOrder(
        info,
        cart,
        selectedBranch?.id,
        selectedBranch?.name,
        customerCoords || undefined,
        selectedBranch?.public_key,
      );
      setCreatedOrderResult(result);
      setCart([]);
      setIsCartOpen(false);
    } catch {
      setOrderSubmitError('No fue posible confirmar el pedido. Conservamos tu carrito para que puedas reintentar.');
    } finally {
      setIsSubmittingOrder(false);
    }
  };

  // Filter visible categories: exclude empty categories and operational items (delivery fee, extras)
  const visibleCategories = useMemo(() => {
    return categories.filter((cat) => {
      const isAll = cat.id === 'all' || cat.name === 'Todos';
      if (isAll) return products.length > 0;

      const nameLower = (cat.name || '').toLowerCase().trim();
      const isExcluded = EXCLUDED_CATEGORY_KEYWORDS.some((kw) => nameLower === kw || nameLower.includes(kw));
      if (isExcluded) return false;

      const count = products.filter((p) => p.category_name === cat.name || p.category_id === cat.id).length;
      return count > 0;
    });
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
      if (activeCategoryId !== 'all' && activeCategoryId !== '') {
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
      if (cat.id === 'all') {
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
      if (activeCategoryId !== 'all' && activeCategoryId !== '') {
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

  return (
    <div className="mobile-app-shell">
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
          onRefreshLocation={() => detectLocationAndFetchBranches(true)}
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
                      ? 'Todo el Menú'
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
          product={selectedProduct}
          isLiked={likedProductIds.has(selectedProduct.id)}
          onToggleLike={handleToggleLike}
          onClose={() => setSelectedProduct(null)}
          onAddToCart={handleAddToCart}
        />
      )}

      {/* Cart & Checkout Sheet */}
      {isCartOpen && (
        <CartDrawer
          items={cart}
          allProducts={products}
          orderType={orderType}
          selectedBranch={selectedBranch}
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
        onRefreshLocation={() => detectLocationAndFetchBranches(true)}
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
      />
    </div>
  );
};

export default App;
