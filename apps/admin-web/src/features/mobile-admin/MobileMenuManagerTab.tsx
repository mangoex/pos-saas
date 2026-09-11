import React, { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchApi, ApiError } from '@restaurantos/api-client';
import {
  Utensils,
  Plus,
  Search,
  CheckCircle2,
  AlertCircle,
  Camera,
  Image as ImageIcon,
  Tag,
  Edit2,
  X,
  Sparkles,
  ToggleLeft,
  ToggleRight,
} from 'lucide-react';

interface MobileMenuManagerTabProps {
  branchId: string;
  branchName?: string;
}

interface Product {
  id: string;
  name: string;
  sku: string;
  category_name: string;
  price_cents: number | null;
  station: string;
  status?: string;
  image_url?: string;
}

interface Category {
  id: string;
  name: string;
  display_order: number;
  status: string;
  image_url?: string | null;
}

interface MenuHome {
  name: string;
  image_url: string | null;
}

const MENU_COVER_PRESET_IMAGES = [
  { label: 'Tacos & Parrilla', url: 'https://images.unsplash.com/photo-1551504734-5ee1c4a1479b?auto=format&fit=crop&w=800&q=80', emoji: '🌮' },
  { label: 'Hamburguesas & Grill', url: 'https://images.unsplash.com/photo-1568901346375-23c9450c58cd?auto=format&fit=crop&w=800&q=80', emoji: '🍔' },
  { label: 'Sushi & Oriental', url: 'https://images.unsplash.com/photo-1579871494447-9811cf80d66c?auto=format&fit=crop&w=800&q=80', emoji: '🍣' },
  { label: 'Pizzería Artesanal', url: 'https://images.unsplash.com/photo-1513104890138-7c749659a591?auto=format&fit=crop&w=800&q=80', emoji: '🍕' },
  { label: 'Cortes & Asados', url: 'https://images.unsplash.com/photo-1544025162-d76694265947?auto=format&fit=crop&w=800&q=80', emoji: '🥩' },
  { label: 'Cafetería & Brunch', url: 'https://images.unsplash.com/photo-1509042239860-f550ce710b93?auto=format&fit=crop&w=800&q=80', emoji: '☕' },
  { label: 'Bebidas & Bar', url: 'https://images.unsplash.com/photo-1514933651103-005eec06c04b?auto=format&fit=crop&w=800&q=80', emoji: '🍺' },
  { label: 'Postres & Dulces', url: 'https://images.unsplash.com/photo-1587314168485-3236d6710814?auto=format&fit=crop&w=800&q=80', emoji: '🍰' },
];

const FOOD_PRESET_IMAGES = [
  { label: 'Tacos', url: 'https://images.unsplash.com/photo-1551504734-5ee1c4a1479b?auto=format&fit=crop&w=400&q=80', emoji: '🌮' },
  { label: 'Hamburguesa', url: 'https://images.unsplash.com/photo-1568901346375-23c9450c58cd?auto=format&fit=crop&w=400&q=80', emoji: '🍔' },
  { label: 'Sushi / Rollo', url: 'https://images.unsplash.com/photo-1579871494447-9811cf80d66c?auto=format&fit=crop&w=400&q=80', emoji: '🍣' },
  { label: 'Pizza', url: 'https://images.unsplash.com/photo-1513104890138-7c749659a591?auto=format&fit=crop&w=400&q=80', emoji: '🍕' },
  { label: 'Corte / Carne', url: 'https://images.unsplash.com/photo-1544025162-d76694265947?auto=format&fit=crop&w=400&q=80', emoji: '🥩' },
  { label: 'Ensalada', url: 'https://images.unsplash.com/photo-1512621776951-a57141f2eefd?auto=format&fit=crop&w=400&q=80', emoji: '🥗' },
  { label: 'Café / Bebida Caliente', url: 'https://images.unsplash.com/photo-1509042239860-f550ce710b93?auto=format&fit=crop&w=400&q=80', emoji: '☕' },
  { label: 'Bebida Fría / Jugo', url: 'https://images.unsplash.com/photo-1513558161293-cdaf765ed2fd?auto=format&fit=crop&w=400&q=80', emoji: '🥤' },
  { label: 'Cerveza / Cóctel', url: 'https://images.unsplash.com/photo-1514933651103-005eec06c04b?auto=format&fit=crop&w=400&q=80', emoji: '🍺' },
  { label: 'Postre', url: 'https://images.unsplash.com/photo-1587314168485-3236d6710814?auto=format&fit=crop&w=400&q=80', emoji: '🍰' },
];

function getEmojiFallback(name: string, category: string): string {
  const text = `${category} ${name}`.toLowerCase();
  if (text.includes('taco') || text.includes('asada') || text.includes('pastor')) return '🌮';
  if (text.includes('burger') || text.includes('hamburguesa')) return '🍔';
  if (text.includes('sushi') || text.includes('rollo') || text.includes('roll')) return '🍣';
  if (text.includes('pizza')) return '🍕';
  if (text.includes('carne') || text.includes('corte') || text.includes('alitas')) return '🥩';
  if (text.includes('ensalada') || text.includes('aguacate') || text.includes('bowl')) return '🥗';
  if (text.includes('cafe') || text.includes('café') || text.includes('latte')) return '☕';
  if (text.includes('cerveza') || text.includes('beer') || text.includes('trago')) return '🍺';
  if (text.includes('postre') || text.includes('pastel') || text.includes('helado')) return '🍰';
  if (text.includes('agua') || text.includes('refresco') || text.includes('bebida') || text.includes('jugo')) return '🥤';
  return '🍽️';
}

export const MobileMenuManagerTab: React.FC<MobileMenuManagerTabProps> = ({
  branchId: _branchId,
  branchName,
}) => {
  const queryClient = useQueryClient();
  const [activeSubTab, setActiveSubTab] = useState<'products' | 'categories'>('products');
  const [search, setSearch] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('ALL');

  // Product Modal State
  const [isProductModalOpen, setIsProductModalOpen] = useState(false);
  const [editingProduct, setEditingProduct] = useState<Product | null>(null);
  const [productForm, setProductForm] = useState({
    name: '',
    sku: '',
    category_name: '',
    station: 'kitchen',
    price: '',
    image_url: '',
    status: 'active',
  });
  const [productModalError, setProductModalError] = useState<string | null>(null);

  // Category Modal State
  const [isCategoryModalOpen, setIsCategoryModalOpen] = useState(false);
  const [editingCategory, setEditingCategory] = useState<Category | null>(null);
  const [categoryForm, setCategoryForm] = useState({
    name: '',
    display_order: 0,
    status: 'active',
    image_url: '',
  });
  const [categoryModalError, setCategoryModalError] = useState<string | null>(null);

  // Menu Home ("Todos") Portada Modal State
  const [isMenuHomeModalOpen, setIsMenuHomeModalOpen] = useState(false);
  const [menuHomeForm, setMenuHomeForm] = useState({
    name: 'Todos',
    image_url: '',
  });
  const [menuHomeModalError, setMenuHomeModalError] = useState<string | null>(null);

  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3000);
  };

  // Queries
  const { data: menuHome, isLoading: menuHomeLoading } = useQuery<MenuHome>({
    queryKey: ['menu-home'],
    queryFn: () => fetchApi('/catalog/menu-home'),
  });

  const { data: products = [], isLoading: productsLoading } = useQuery<Product[]>({
    queryKey: ['products'],
    queryFn: () => fetchApi('/catalog/products'),
  });

  const { data: categories = [], isLoading: categoriesLoading } = useQuery<Category[]>({
    queryKey: ['categories'],
    queryFn: () => fetchApi('/categories'),
  });

  const sortedCategories = useMemo(() => {
    return [...categories]
      .filter((c) => c.status !== 'inactive')
      .sort((a, b) => (a.display_order ?? 0) - (b.display_order ?? 0) || a.name.localeCompare(b.name));
  }, [categories]);

  const filteredProducts = useMemo(() => {
    let list = products;
    if (selectedCategory !== 'ALL') {
      list = list.filter((p) => p.category_name?.trim().toLowerCase() === selectedCategory.trim().toLowerCase());
    }
    const q = search.trim().toLowerCase();
    if (q) {
      list = list.filter((p) => p.name.toLowerCase().includes(q) || p.sku.toLowerCase().includes(q));
    }
    return list;
  }, [products, selectedCategory, search]);

  // Mutations
  const toggleAvailabilityMutation = useMutation({
    mutationFn: async (product: Product) => {
      const nextStatus = product.status === 'inactive' ? 'active' : 'inactive';
      return fetchApi(`/catalog/products/${product.id}`, {
        method: 'PUT',
        body: JSON.stringify({
          name: product.name,
          sku: product.sku,
          price_cents: product.price_cents,
          station: product.station,
          status: nextStatus,
          image_url: product.image_url,
        }),
      });
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['products'] });
      const nextStatus = variables.status === 'inactive' ? 'Disponible' : 'Agotado';
      showToast(`${variables.name} marcado como ${nextStatus}`);
    },
    onError: (err) => {
      showToast(err instanceof ApiError ? err.message : 'Error al cambiar disponibilidad');
    },
  });

  const saveProductMutation = useMutation({
    mutationFn: async (form: typeof productForm) => {
      const cents = Math.round((parseFloat(form.price) || 0) * 100);
      const skuVal = form.sku.trim() || `PROD-${Date.now().toString().slice(-6)}`;
      const payload = {
        name: form.name.trim(),
        sku: skuVal,
        category_name: form.category_name.trim(),
        station: form.station,
        price_cents: cents,
        status: form.status,
        image_url: form.image_url.trim() || undefined,
      };

      if (editingProduct) {
        return fetchApi(`/catalog/products/${editingProduct.id}`, {
          method: 'PUT',
          body: JSON.stringify(payload),
        });
      }
      return fetchApi('/catalog/products', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['products'] });
      setIsProductModalOpen(false);
      showToast(editingProduct ? 'Producto actualizado' : 'Producto creado con éxito');
    },
    onError: (err: any) => {
      setProductModalError(err?.message || err?.detail?.message || 'Error al guardar producto');
    },
  });

  const saveCategoryMutation = useMutation({
    mutationFn: async (form: typeof categoryForm) => {
      const payload = {
        name: form.name.trim(),
        display_order: Number(form.display_order) || 0,
        status: form.status,
        image_url: form.image_url.trim() || undefined,
      };

      if (editingCategory) {
        return fetchApi(`/categories/${editingCategory.id}`, {
          method: 'PUT',
          body: JSON.stringify(payload),
        });
      }
      return fetchApi('/categories', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['categories'] });
      setIsCategoryModalOpen(false);
      showToast(editingCategory ? 'Categoría actualizada' : 'Categoría creada con éxito');
    },
    onError: (err: any) => {
      setCategoryModalError(err?.message || err?.detail?.message || 'Error al guardar categoría');
    },
  });

  const saveMenuHomeMutation = useMutation({
    mutationFn: async (form: typeof menuHomeForm) => {
      return fetchApi('/catalog/menu-home', {
        method: 'PUT',
        body: JSON.stringify({
          name: form.name.trim(),
          image_url: form.image_url.trim() || undefined,
        }),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['menu-home'] });
      setIsMenuHomeModalOpen(false);
      showToast('Portada principal actualizada con éxito');
    },
    onError: (err: any) => {
      setMenuHomeModalError(err?.message || err?.detail?.message || 'Error al guardar la portada principal');
    },
  });

  const openMenuHomeModal = () => {
    setMenuHomeModalError(null);
    setMenuHomeForm({
      name: menuHome?.name || 'Todos',
      image_url: menuHome?.image_url || '',
    });
    setIsMenuHomeModalOpen(true);
  };

  // Open Product Modal
  const openProductModal = (product?: Product) => {
    setProductModalError(null);
    if (product) {
      setEditingProduct(product);
      setProductForm({
        name: product.name,
        sku: product.sku,
        category_name: product.category_name || (sortedCategories[0]?.name || ''),
        station: product.station || 'kitchen',
        price: product.price_cents ? (product.price_cents / 100).toFixed(2) : '0.00',
        image_url: product.image_url || '',
        status: product.status || 'active',
      });
    } else {
      setEditingProduct(null);
      setProductForm({
        name: '',
        sku: '',
        category_name: selectedCategory !== 'ALL' ? selectedCategory : (sortedCategories[0]?.name || ''),
        station: 'kitchen',
        price: '',
        image_url: '',
        status: 'active',
      });
    }
    setIsProductModalOpen(true);
  };

  // Open Category Modal
  const openCategoryModal = (cat?: Category) => {
    setCategoryModalError(null);
    if (cat) {
      setEditingCategory(cat);
      setCategoryForm({
        name: cat.name,
        display_order: cat.display_order ?? 0,
        status: cat.status || 'active',
        image_url: cat.image_url || '',
      });
    } else {
      setEditingCategory(null);
      setCategoryForm({
        name: '',
        display_order: categories.length + 1,
        status: 'active',
        image_url: '',
      });
    }
    setIsCategoryModalOpen(true);
  };

  // File to base64 for camera/gallery (product & category & menu-home)
  const handlePhotoUpload = (
    e: React.ChangeEvent<HTMLInputElement>,
    target: 'product' | 'category' | 'menu-home' = 'product'
  ) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (event) => {
      const dataUrl = event.target?.result as string;
      if (dataUrl) {
        // Use an image canvas to resize to friendly size
        const img = new Image();
        img.src = dataUrl;
        img.onload = () => {
          const canvas = document.createElement('canvas');
          const maxDim = target === 'menu-home' ? 900 : 600;
          let width = img.width;
          let height = img.height;
          if (width > height) {
            if (width > maxDim) {
              height = Math.round((height * maxDim) / width);
              width = maxDim;
            }
          } else {
            if (height > maxDim) {
              width = Math.round((width * maxDim) / height);
              height = maxDim;
            }
          }
          canvas.width = width;
          canvas.height = height;
          const ctx = canvas.getContext('2d');
          if (ctx) {
            ctx.drawImage(img, 0, 0, width, height);
            const compressed = canvas.toDataURL('image/jpeg', target === 'menu-home' ? 0.78 : 0.7);
            if (target === 'category') {
              setCategoryForm((prev) => ({ ...prev, image_url: compressed }));
            } else if (target === 'menu-home') {
              setMenuHomeForm((prev) => ({ ...prev, image_url: compressed }));
            } else {
              setProductForm((prev) => ({ ...prev, image_url: compressed }));
            }
          }
        };
      }
    };
    reader.readAsDataURL(file);
    // Reset input value so the same file can be chosen again if needed
    e.target.value = '';
  };

  return (
    <div style={{ minHeight: '100vh', backgroundColor: '#f8fafc', paddingBottom: 84 }}>
      {/* Header */}
      <header
        style={{
          position: 'sticky',
          top: 0,
          zIndex: 40,
          backgroundColor: '#0f172a',
          color: '#ffffff',
          padding: '12px 16px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          borderBottom: '1px solid #1e293b',
          boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div
            style={{
              width: 38,
              height: 38,
              borderRadius: 10,
              backgroundColor: '#f59e0b',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Utensils size={20} color="#ffffff" />
          </div>
          <div>
            <div style={{ fontSize: '1rem', fontWeight: 800, lineHeight: 1.1 }}>
              Menú y Catálogo
            </div>
            <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
              {branchName || 'Sucursal Principal'}
            </div>
          </div>
        </div>

        <button
          onClick={() => (activeSubTab === 'products' ? openProductModal() : openCategoryModal())}
          style={{
            border: 'none',
            background: '#3b82f6',
            color: '#ffffff',
            borderRadius: 8,
            padding: '8px 12px',
            display: 'flex',
            alignItems: 'center',
            gap: 4,
            cursor: 'pointer',
            fontSize: '0.85rem',
            fontWeight: 700,
          }}
        >
          <Plus size={16} />
          {activeSubTab === 'products' ? 'Platillo' : 'Categoría'}
        </button>
      </header>

      {/* Subtabs Pill Switcher */}
      <div style={{ padding: '12px 14px 4px', maxWidth: 640, margin: '0 auto' }}>
        <div
          style={{
            display: 'flex',
            backgroundColor: '#e2e8f0',
            borderRadius: 10,
            padding: 3,
            marginBottom: 10,
          }}
        >
          <button
            type="button"
            onClick={() => setActiveSubTab('products')}
            style={{
              flex: 1,
              padding: '8px 0',
              border: 'none',
              borderRadius: 8,
              backgroundColor: activeSubTab === 'products' ? '#ffffff' : 'transparent',
              color: activeSubTab === 'products' ? '#0f172a' : '#64748b',
              fontWeight: 700,
              fontSize: '0.875rem',
              cursor: 'pointer',
              boxShadow: activeSubTab === 'products' ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
            }}
          >
            Platillos ({products.length})
          </button>
          <button
            type="button"
            onClick={() => setActiveSubTab('categories')}
            style={{
              flex: 1,
              padding: '8px 0',
              border: 'none',
              borderRadius: 8,
              backgroundColor: activeSubTab === 'categories' ? '#ffffff' : 'transparent',
              color: activeSubTab === 'categories' ? '#0f172a' : '#64748b',
              fontWeight: 700,
              fontSize: '0.875rem',
              cursor: 'pointer',
              boxShadow: activeSubTab === 'categories' ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
            }}
          >
            Categorías ({categories.length})
          </button>
        </div>

        {/* Toast */}
        {toastMessage && (
          <div
            style={{
              backgroundColor: '#0f172a',
              color: '#ffffff',
              borderRadius: 10,
              padding: '8px 14px',
              fontSize: '0.85rem',
              fontWeight: 600,
              marginBottom: 10,
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)',
            }}
          >
            <CheckCircle2 size={16} color="#22c55e" />
            <span>{toastMessage}</span>
          </div>
        )}
      </div>

      {/* Products Subtab */}
      {activeSubTab === 'products' && (
        <main style={{ padding: '0 14px', maxWidth: 640, margin: '0 auto' }}>
          {/* Search */}
          <div style={{ position: 'relative', marginBottom: 10 }}>
            <Search
              size={18}
              style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: '#94a3b8' }}
            />
            <input
              type="text"
              placeholder="Buscar platillo o código..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{
                width: '100%',
                boxSizing: 'border-box',
                padding: '10px 12px 10px 38px',
                borderRadius: 10,
                border: '1px solid #cbd5e1',
                fontSize: '0.9rem',
                backgroundColor: '#ffffff',
                outline: 'none',
              }}
            />
          </div>

          {/* Category Pills Horizontal Scroll */}
          <div
            style={{
              display: 'flex',
              gap: 6,
              overflowX: 'auto',
              paddingBottom: 8,
              marginBottom: 10,
              scrollbarWidth: 'none',
            }}
          >
            <button
              onClick={() => setSelectedCategory('ALL')}
              style={{
                padding: '6px 12px',
                borderRadius: 20,
                border: selectedCategory === 'ALL' ? 'none' : '1px solid #cbd5e1',
                backgroundColor: selectedCategory === 'ALL' ? '#0f172a' : '#ffffff',
                color: selectedCategory === 'ALL' ? '#ffffff' : '#475569',
                fontSize: '0.8rem',
                fontWeight: 700,
                whiteSpace: 'nowrap',
                cursor: 'pointer',
              }}
            >
              {menuHome?.name || 'Todos'} ({products.length})
            </button>
            {sortedCategories.map((cat) => {
              const count = products.filter((p) => p.category_name === cat.name).length;
              const isSelected = selectedCategory === cat.name;
              return (
                <button
                  key={cat.id}
                  onClick={() => setSelectedCategory(cat.name)}
                  style={{
                    padding: '6px 12px',
                    borderRadius: 20,
                    border: isSelected ? 'none' : '1px solid #cbd5e1',
                    backgroundColor: isSelected ? '#0f172a' : '#ffffff',
                    color: isSelected ? '#ffffff' : '#475569',
                    fontSize: '0.8rem',
                    fontWeight: 700,
                    whiteSpace: 'nowrap',
                    cursor: 'pointer',
                  }}
                >
                  {cat.name} ({count})
                </button>
              );
            })}
          </div>

          {/* Product Cards List */}
          {productsLoading ? (
            <div style={{ padding: 40, textAlign: 'center', color: '#64748b' }}>Cargando platillos...</div>
          ) : filteredProducts.length === 0 ? (
            <div
              style={{
                textAlign: 'center',
                padding: 40,
                backgroundColor: '#ffffff',
                borderRadius: 14,
                border: '1px dashed #cbd5e1',
              }}
            >
              <Utensils size={36} color="#94a3b8" style={{ margin: '0 auto 8px' }} />
              <div style={{ fontWeight: 700, color: '#334155' }}>No hay platillos encontrados</div>
              <p style={{ fontSize: '0.85rem', color: '#64748b', margin: '4px 0 14px' }}>
                Agrega tu primer producto o ajusta el filtro de búsqueda.
              </p>
              <button
                onClick={() => openProductModal()}
                style={{
                  padding: '8px 16px',
                  backgroundColor: '#3b82f6',
                  color: '#ffffff',
                  border: 'none',
                  borderRadius: 8,
                  fontWeight: 700,
                  fontSize: '0.85rem',
                  cursor: 'pointer',
                }}
              >
                + Crear Platillo
              </button>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {filteredProducts.map((product) => {
                const isAvailable = product.status !== 'inactive';
                const emoji = getEmojiFallback(product.name, product.category_name);
                const priceFormatted = product.price_cents
                  ? (product.price_cents / 100).toFixed(2)
                  : '0.00';

                return (
                  <div
                    key={product.id}
                    style={{
                      backgroundColor: '#ffffff',
                      borderRadius: 14,
                      padding: 12,
                      border: '1px solid #e2e8f0',
                      boxShadow: '0 2px 4px rgba(0,0,0,0.03)',
                      display: 'flex',
                      gap: 12,
                      alignItems: 'center',
                      opacity: isAvailable ? 1 : 0.65,
                    }}
                  >
                    {/* Thumbnail */}
                    <div
                      style={{
                        width: 54,
                        height: 54,
                        borderRadius: 10,
                        backgroundColor: '#f1f5f9',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        overflow: 'hidden',
                        flexShrink: 0,
                      }}
                    >
                      {product.image_url ? (
                        <img
                          src={product.image_url}
                          alt={product.name}
                          style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                          onError={(e) => {
                            (e.target as HTMLElement).style.display = 'none';
                          }}
                        />
                      ) : (
                        <span style={{ fontSize: '1.75rem' }}>{emoji}</span>
                      )}
                    </div>

                    {/* Info */}
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div
                        style={{
                          fontSize: '0.95rem',
                          fontWeight: 800,
                          color: '#0f172a',
                          whiteSpace: 'nowrap',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                        }}
                      >
                        {product.name}
                      </div>
                      <div style={{ fontSize: '0.75rem', color: '#64748b', display: 'flex', gap: 6, marginTop: 2 }}>
                        <span>{product.category_name || 'Sin categoría'}</span>
                        <span>•</span>
                        <span style={{ fontWeight: 600, color: product.station === 'drinks' ? '#0284c7' : '#d97706' }}>
                          {product.station === 'drinks' ? 'Barra' : 'Cocina'}
                        </span>
                      </div>
                      <div style={{ fontSize: '0.95rem', fontWeight: 800, color: '#0f172a', marginTop: 4 }}>
                        ${priceFormatted} <span style={{ fontSize: '0.7rem', color: '#64748b', fontWeight: 500 }}>MXN</span>
                      </div>
                    </div>

                    {/* Actions: Toggle Availability & Edit */}
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 6 }}>
                      <button
                        type="button"
                        onClick={() => toggleAvailabilityMutation.mutate(product)}
                        style={{
                          border: 'none',
                          background: 'none',
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          gap: 4,
                          padding: '4px 6px',
                          borderRadius: 8,
                          backgroundColor: isAvailable ? '#dcfce7' : '#fee2e2',
                          color: isAvailable ? '#15803d' : '#b91c1c',
                          fontSize: '0.75rem',
                          fontWeight: 700,
                        }}
                      >
                        {isAvailable ? <ToggleRight size={16} /> : <ToggleLeft size={16} />}
                        {isAvailable ? 'Disponible' : 'Agotado'}
                      </button>

                      <button
                        type="button"
                        onClick={() => openProductModal(product)}
                        style={{
                          border: 'none',
                          background: '#f1f5f9',
                          color: '#475569',
                          borderRadius: 6,
                          padding: '4px 8px',
                          display: 'flex',
                          alignItems: 'center',
                          gap: 4,
                          fontSize: '0.75rem',
                          fontWeight: 600,
                          cursor: 'pointer',
                        }}
                      >
                        <Edit2 size={12} /> Editar
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </main>
      )}

      {/* Categories Subtab */}
      {activeSubTab === 'categories' && (
        <main style={{ padding: '0 14px', maxWidth: 640, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 14 }}>
          {/* Card de la Portada Principal ("Todos") */}
          <div
            style={{
              backgroundColor: '#ffffff',
              borderRadius: 14,
              padding: '14px',
              border: '2px solid #3b82f6',
              boxShadow: '0 4px 12px rgba(59, 130, 246, 0.08)',
              display: 'flex',
              flexDirection: 'column',
              gap: 12,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 4,
                    padding: '3px 8px',
                    backgroundColor: '#eff6ff',
                    color: '#1d4ed8',
                    borderRadius: 6,
                    fontSize: '0.72rem',
                    fontWeight: 800,
                    letterSpacing: '0.02em',
                    textTransform: 'uppercase',
                  }}
                >
                  <Sparkles size={12} /> Categoría Principal
                </span>
                <span style={{ fontSize: '0.75rem', color: '#64748b' }}>
                  • Portada del Menú
                </span>
              </div>

              <button
                type="button"
                onClick={openMenuHomeModal}
                style={{
                  border: 'none',
                  background: '#eff6ff',
                  color: '#1d4ed8',
                  borderRadius: 8,
                  padding: '6px 12px',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 5,
                  fontSize: '0.8rem',
                  fontWeight: 700,
                  cursor: 'pointer',
                }}
              >
                <Edit2 size={13} /> Editar portada
              </button>
            </div>

            <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
              {/* Cover / Header photo preview thumbnail */}
              <div
                onClick={openMenuHomeModal}
                style={{
                  width: 76,
                  height: 54,
                  borderRadius: 10,
                  backgroundColor: '#f1f5f9',
                  border: '1px solid #e2e8f0',
                  overflow: 'hidden',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                  cursor: 'pointer',
                }}
                title="Toca para cambiar foto de cabecera"
              >
                {menuHome?.image_url ? (
                  <img
                    src={menuHome.image_url}
                    alt={menuHome.name || 'Portada'}
                    style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                  />
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', color: '#94a3b8' }}>
                    <Camera size={18} />
                    <span style={{ fontSize: '0.6rem', fontWeight: 700, marginTop: 2 }}>Sin foto</span>
                  </div>
                )}
              </div>

              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: '1.05rem', fontWeight: 800, color: '#0f172a' }}>
                  {menuHome?.name || 'Todos'}
                </div>
                <div style={{ fontSize: '0.78rem', color: '#64748b', marginTop: 2, lineHeight: 1.35 }}>
                  Muestra todos los platillos ({products.length}) en la cabecera principal del menú web.
                </div>
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 4 }}>
            <h3 style={{ margin: 0, fontSize: '0.92rem', fontWeight: 800, color: '#0f172a' }}>
              Otras Categorías ({sortedCategories.length})
            </h3>
            <button
              onClick={() => openCategoryModal()}
              style={{
                border: 'none',
                background: '#f1f5f9',
                color: '#2563eb',
                borderRadius: 8,
                padding: '5px 10px',
                display: 'inline-flex',
                alignItems: 'center',
                gap: 4,
                fontSize: '0.78rem',
                fontWeight: 700,
                cursor: 'pointer',
              }}
            >
              <Plus size={14} /> Nueva categoría
            </button>
          </div>

          {categoriesLoading ? (
            <div style={{ padding: 30, textAlign: 'center', color: '#64748b' }}>Cargando categorías...</div>
          ) : categories.length === 0 ? (
            <div
              style={{
                textAlign: 'center',
                padding: 30,
                backgroundColor: '#ffffff',
                borderRadius: 14,
                border: '1px dashed #cbd5e1',
              }}
            >
              <Tag size={32} color="#94a3b8" style={{ margin: '0 auto 8px' }} />
              <div style={{ fontWeight: 700, color: '#334155' }}>No hay categorías adicionales</div>
              <p style={{ fontSize: '0.82rem', color: '#64748b', margin: '4px 0 12px' }}>
                Crea categorías para clasificar tus platillos en secciones como Tacos, Bebidas o Postres.
              </p>
              <button
                onClick={() => openCategoryModal()}
                style={{
                  padding: '8px 16px',
                  backgroundColor: '#3b82f6',
                  color: '#ffffff',
                  border: 'none',
                  borderRadius: 8,
                  fontWeight: 700,
                  fontSize: '0.85rem',
                  cursor: 'pointer',
                }}
              >
                + Nueva Categoría
              </button>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {sortedCategories.map((cat) => {
                const count = products.filter((p) => p.category_name === cat.name).length;
                return (
                  <div
                    key={cat.id}
                    style={{
                      backgroundColor: '#ffffff',
                      borderRadius: 12,
                      padding: '12px 14px',
                      border: '1px solid #e2e8f0',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      gap: 10,
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12, minWidth: 0 }}>
                      <div
                        style={{
                          width: 44,
                          height: 44,
                          borderRadius: 8,
                          backgroundColor: '#f1f5f9',
                          overflow: 'hidden',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          flexShrink: 0,
                        }}
                      >
                        {cat.image_url ? (
                          <img
                            src={cat.image_url}
                            alt={cat.name}
                            style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                          />
                        ) : (
                          <Tag size={18} color="#94a3b8" />
                        )}
                      </div>
                      <div style={{ minWidth: 0 }}>
                        <div style={{ fontSize: '0.95rem', fontWeight: 800, color: '#0f172a', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                          {cat.name}
                        </div>
                        <div style={{ fontSize: '0.75rem', color: '#64748b', marginTop: 2 }}>
                          {count} platillos • Orden: {cat.display_order ?? 0}
                        </div>
                      </div>
                    </div>

                    <button
                      onClick={() => openCategoryModal(cat)}
                      style={{
                        border: 'none',
                        background: '#f1f5f9',
                        color: '#475569',
                        borderRadius: 6,
                        padding: '6px 10px',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 4,
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        cursor: 'pointer',
                        flexShrink: 0,
                      }}
                    >
                      <Edit2 size={13} /> Editar
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </main>
      )}

      {/* Quick Product Modal */}
      {isProductModalOpen && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(15, 23, 42, 0.6)',
            zIndex: 60,
            display: 'flex',
            alignItems: 'flex-end',
            justifyContent: 'center',
          }}
        >
          <div
            style={{
              backgroundColor: '#ffffff',
              width: '100%',
              maxWidth: 540,
              borderTopLeftRadius: 20,
              borderTopRightRadius: 20,
              padding: '20px 18px 28px',
              boxShadow: '0 -4px 10px rgba(0, 0, 0, 0.15)',
              maxHeight: '90vh',
              overflowY: 'auto',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
              <h3 style={{ margin: 0, fontSize: '1.2rem', fontWeight: 800, color: '#0f172a' }}>
                {editingProduct ? 'Editar Platillo' : 'Nuevo Platillo'}
              </h3>
              <button
                onClick={() => setIsProductModalOpen(false)}
                style={{ background: 'none', border: 'none', color: '#64748b', cursor: 'pointer', padding: 4 }}
              >
                <X size={20} />
              </button>
            </div>

            {productModalError && (
              <div
                style={{
                  backgroundColor: '#fee2e2',
                  border: '1px solid #fecaca',
                  borderRadius: 10,
                  padding: '8px 12px',
                  color: '#b91c1c',
                  fontSize: '0.85rem',
                  fontWeight: 600,
                  marginBottom: 12,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                }}
              >
                <AlertCircle size={16} />
                <span>{productModalError}</span>
              </div>
            )}

            <form
              onSubmit={(e) => {
                e.preventDefault();
                saveProductMutation.mutate(productForm);
              }}
            >
              {/* Product Name */}
              <div style={{ marginBottom: 12 }}>
                <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, color: '#334155', marginBottom: 4 }}>
                  Nombre del platillo *
                </label>
                <input
                  type="text"
                  required
                  placeholder="Ej. Tacos de Asada"
                  value={productForm.name}
                  onChange={(e) => setProductForm({ ...productForm, name: e.target.value })}
                  style={{
                    width: '100%',
                    boxSizing: 'border-box',
                    padding: '10px 12px',
                    fontSize: '0.95rem',
                    fontWeight: 600,
                    borderRadius: 10,
                    border: '1px solid #cbd5e1',
                    outline: 'none',
                  }}
                />
              </div>

              {/* Price & Category in row */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 12 }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, color: '#334155', marginBottom: 4 }}>
                    Precio ($ MXN) *
                  </label>
                  <input
                    type="number"
                    step="0.50"
                    min="0"
                    required
                    placeholder="0.00"
                    value={productForm.price}
                    onChange={(e) => setProductForm({ ...productForm, price: e.target.value })}
                    style={{
                      width: '100%',
                      boxSizing: 'border-box',
                      padding: '10px 12px',
                      fontSize: '0.95rem',
                      fontWeight: 700,
                      borderRadius: 10,
                      border: '1px solid #cbd5e1',
                      outline: 'none',
                    }}
                  />
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, color: '#334155', marginBottom: 4 }}>
                    Categoría *
                  </label>
                  <select
                    value={productForm.category_name}
                    onChange={(e) => setProductForm({ ...productForm, category_name: e.target.value })}
                    required
                    style={{
                      width: '100%',
                      boxSizing: 'border-box',
                      padding: '10px 12px',
                      fontSize: '0.9rem',
                      fontWeight: 600,
                      borderRadius: 10,
                      border: '1px solid #cbd5e1',
                      outline: 'none',
                      backgroundColor: '#ffffff',
                    }}
                  >
                    {sortedCategories.map((c) => (
                      <option key={c.id} value={c.name}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Station & Status */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 14 }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, color: '#334155', marginBottom: 4 }}>
                    Estación de preparación
                  </label>
                  <select
                    value={productForm.station}
                    onChange={(e) => setProductForm({ ...productForm, station: e.target.value })}
                    style={{
                      width: '100%',
                      boxSizing: 'border-box',
                      padding: '10px 12px',
                      fontSize: '0.9rem',
                      fontWeight: 600,
                      borderRadius: 10,
                      border: '1px solid #cbd5e1',
                      outline: 'none',
                      backgroundColor: '#ffffff',
                    }}
                  >
                    <option value="kitchen">Cocina</option>
                    <option value="drinks">Barra / Bebidas</option>
                    <option value="packing">Empaque</option>
                  </select>
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, color: '#334155', marginBottom: 4 }}>
                    Disponibilidad
                  </label>
                  <select
                    value={productForm.status}
                    onChange={(e) => setProductForm({ ...productForm, status: e.target.value })}
                    style={{
                      width: '100%',
                      boxSizing: 'border-box',
                      padding: '10px 12px',
                      fontSize: '0.9rem',
                      fontWeight: 600,
                      borderRadius: 10,
                      border: '1px solid #cbd5e1',
                      outline: 'none',
                      backgroundColor: '#ffffff',
                    }}
                  >
                    <option value="active">Disponible</option>
                    <option value="inactive">Agotado</option>
                  </select>
                </div>
              </div>

              {/* Photo Options */}
              <div style={{ marginBottom: 16 }}>
                <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, color: '#334155', marginBottom: 6 }}>
                  Fotografía del platillo
                </label>

                {/* Preview if any */}
                {productForm.image_url ? (
                  <div style={{ position: 'relative', marginBottom: 10, borderRadius: 10, overflow: 'hidden' }}>
                    <img
                      src={productForm.image_url}
                      alt="Vista previa"
                      style={{ width: '100%', height: 140, objectFit: 'cover' }}
                    />
                    <button
                      type="button"
                      onClick={() => setProductForm({ ...productForm, image_url: '' })}
                      style={{
                        position: 'absolute',
                        top: 8,
                        right: 8,
                        backgroundColor: 'rgba(0,0,0,0.6)',
                        color: '#ffffff',
                        border: 'none',
                        borderRadius: 6,
                        padding: '4px 8px',
                        fontSize: '0.75rem',
                        fontWeight: 700,
                        cursor: 'pointer',
                      }}
                    >
                      Quitar foto
                    </button>
                  </div>
                ) : null}

                {/* Camera / Gallery upload button */}
                <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
                  <label
                    style={{
                      flex: 1,
                      padding: '10px',
                      backgroundColor: '#eff6ff',
                      border: '1px dashed #3b82f6',
                      borderRadius: 10,
                      color: '#1d4ed8',
                      fontSize: '0.85rem',
                      fontWeight: 700,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: 6,
                      cursor: 'pointer',
                    }}
                  >
                    <Camera size={18} />
                    Tomar foto/Cargar
                    <input
                      type="file"
                      accept="image/*"
                      onChange={(e) => handlePhotoUpload(e, 'product')}
                      style={{ display: 'none' }}
                    />
                  </label>
                </div>

                {/* Preset Suggestions */}
                <div style={{ fontSize: '0.75rem', fontWeight: 700, color: '#64748b', marginBottom: 6, display: 'flex', alignItems: 'center', gap: 4 }}>
                  <Sparkles size={14} color="#f59e0b" /> Presets fotográficos apetitosos:
                </div>
                <div
                  style={{
                    display: 'flex',
                    gap: 6,
                    overflowX: 'auto',
                    paddingBottom: 6,
                    scrollbarWidth: 'none',
                  }}
                >
                  {FOOD_PRESET_IMAGES.map((preset) => (
                    <button
                      key={preset.label}
                      type="button"
                      onClick={() => setProductForm({ ...productForm, image_url: preset.url })}
                      style={{
                        padding: '5px 10px',
                        borderRadius: 8,
                        border: productForm.image_url === preset.url ? '2px solid #3b82f6' : '1px solid #e2e8f0',
                        backgroundColor: '#ffffff',
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        whiteSpace: 'nowrap',
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 4,
                      }}
                    >
                      <span>{preset.emoji}</span>
                      <span>{preset.label}</span>
                    </button>
                  ))}
                </div>
              </div>

              <button
                type="submit"
                disabled={saveProductMutation.isPending}
                style={{
                  width: '100%',
                  padding: '14px',
                  backgroundColor: '#16a34a',
                  color: '#ffffff',
                  border: 'none',
                  borderRadius: 12,
                  fontSize: '1rem',
                  fontWeight: 800,
                  cursor: 'pointer',
                  boxShadow: '0 4px 6px -1px rgba(22, 163, 74, 0.3)',
                }}
              >
                {saveProductMutation.isPending ? 'Guardando...' : editingProduct ? 'Guardar Cambios' : 'Crear Platillo'}
              </button>
            </form>
          </div>
        </div>
      )}

      {/* Quick Category Modal */}
      {isCategoryModalOpen && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(15, 23, 42, 0.6)',
            zIndex: 60,
            display: 'flex',
            alignItems: 'flex-end',
            justifyContent: 'center',
          }}
        >
          <div
            style={{
              backgroundColor: '#ffffff',
              width: '100%',
              maxWidth: 500,
              borderTopLeftRadius: 20,
              borderTopRightRadius: 20,
              padding: '20px 18px 28px',
              boxShadow: '0 -4px 10px rgba(0, 0, 0, 0.15)',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
              <h3 style={{ margin: 0, fontSize: '1.2rem', fontWeight: 800, color: '#0f172a' }}>
                {editingCategory ? 'Editar Categoría' : 'Nueva Categoría'}
              </h3>
              <button
                onClick={() => setIsCategoryModalOpen(false)}
                style={{ background: 'none', border: 'none', color: '#64748b', cursor: 'pointer', padding: 4 }}
              >
                <X size={20} />
              </button>
            </div>

            {categoryModalError && (
              <div
                style={{
                  backgroundColor: '#fee2e2',
                  border: '1px solid #fecaca',
                  borderRadius: 10,
                  padding: '8px 12px',
                  color: '#b91c1c',
                  fontSize: '0.85rem',
                  fontWeight: 600,
                  marginBottom: 12,
                }}
              >
                {categoryModalError}
              </div>
            )}

            <form
              onSubmit={(e) => {
                e.preventDefault();
                saveCategoryMutation.mutate(categoryForm);
              }}
            >
              <div style={{ marginBottom: 12 }}>
                <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, color: '#334155', marginBottom: 4 }}>
                  Nombre de la categoría *
                </label>
                <input
                  type="text"
                  required
                  placeholder="Ej. Tacos, Bebidas, Postres"
                  value={categoryForm.name}
                  onChange={(e) => setCategoryForm({ ...categoryForm, name: e.target.value })}
                  style={{
                    width: '100%',
                    boxSizing: 'border-box',
                    padding: '10px 12px',
                    fontSize: '0.95rem',
                    fontWeight: 600,
                    borderRadius: 10,
                    border: '1px solid #cbd5e1',
                    outline: 'none',
                  }}
                />
              </div>

              <div style={{ marginBottom: 16 }}>
                <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, color: '#334155', marginBottom: 6 }}>
                  Fotografía de portada de la categoría
                </label>

                {/* Preview if any */}
                {categoryForm.image_url ? (
                  <div style={{ position: 'relative', marginBottom: 10, borderRadius: 10, overflow: 'hidden' }}>
                    <img
                      src={categoryForm.image_url}
                      alt="Vista previa categoría"
                      style={{ width: '100%', height: 120, objectFit: 'cover' }}
                    />
                    <button
                      type="button"
                      onClick={() => setCategoryForm({ ...categoryForm, image_url: '' })}
                      style={{
                        position: 'absolute',
                        top: 8,
                        right: 8,
                        backgroundColor: 'rgba(0,0,0,0.6)',
                        color: '#ffffff',
                        border: 'none',
                        borderRadius: 6,
                        padding: '4px 8px',
                        fontSize: '0.75rem',
                        fontWeight: 700,
                        cursor: 'pointer',
                      }}
                    >
                      Quitar foto
                    </button>
                  </div>
                ) : null}

                {/* Camera / Gallery upload button */}
                <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
                  <label
                    style={{
                      flex: 1,
                      padding: '10px',
                      backgroundColor: '#eff6ff',
                      border: '1px dashed #3b82f6',
                      borderRadius: 10,
                      color: '#1d4ed8',
                      fontSize: '0.85rem',
                      fontWeight: 700,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: 6,
                      cursor: 'pointer',
                    }}
                  >
                    <Camera size={18} />
                    Tomar foto/Cargar
                    <input
                      type="file"
                      accept="image/*"
                      onChange={(e) => handlePhotoUpload(e, 'category')}
                      style={{ display: 'none' }}
                    />
                  </label>
                </div>

                {/* Category Preset Suggestions */}
                <div style={{ fontSize: '0.75rem', fontWeight: 700, color: '#64748b', marginBottom: 6, display: 'flex', alignItems: 'center', gap: 4 }}>
                  <Sparkles size={14} color="#f59e0b" /> Portadas apetitosas sugeridas:
                </div>
                <div
                  style={{
                    display: 'flex',
                    gap: 6,
                    overflowX: 'auto',
                    paddingBottom: 6,
                    scrollbarWidth: 'none',
                  }}
                >
                  {FOOD_PRESET_IMAGES.map((preset) => (
                    <button
                      key={preset.label}
                      type="button"
                      onClick={() => setCategoryForm({ ...categoryForm, image_url: preset.url })}
                      style={{
                        padding: '5px 10px',
                        borderRadius: 8,
                        border: categoryForm.image_url === preset.url ? '2px solid #3b82f6' : '1px solid #e2e8f0',
                        backgroundColor: '#ffffff',
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        whiteSpace: 'nowrap',
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 4,
                      }}
                    >
                      <span>{preset.emoji}</span>
                      <span>{preset.label}</span>
                    </button>
                  ))}
                </div>

                {/* Optional URL input fallback */}
                <div style={{ marginTop: 8 }}>
                  <input
                    type="url"
                    placeholder="O pega enlace https://... (opcional)"
                    value={categoryForm.image_url.startsWith('data:') ? '' : categoryForm.image_url}
                    onChange={(e) => setCategoryForm({ ...categoryForm, image_url: e.target.value })}
                    style={{
                      width: '100%',
                      boxSizing: 'border-box',
                      padding: '8px 10px',
                      fontSize: '0.8rem',
                      borderRadius: 8,
                      border: '1px solid #cbd5e1',
                      outline: 'none',
                      color: '#475569',
                    }}
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={saveCategoryMutation.isPending}
                style={{
                  width: '100%',
                  padding: '14px',
                  backgroundColor: '#3b82f6',
                  color: '#ffffff',
                  border: 'none',
                  borderRadius: 12,
                  fontSize: '1rem',
                  fontWeight: 800,
                  cursor: 'pointer',
                }}
              >
                {saveCategoryMutation.isPending ? 'Guardando...' : editingCategory ? 'Guardar Cambios' : 'Crear Categoría'}
              </button>
            </form>
          </div>
        </div>
      )}

      {/* Quick Menu Home Modal ("Todos" Portada & Nombre) */}
      {isMenuHomeModalOpen && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(15, 23, 42, 0.6)',
            zIndex: 60,
            display: 'flex',
            alignItems: 'flex-end',
            justifyContent: 'center',
          }}
        >
          <div
            style={{
              backgroundColor: '#ffffff',
              width: '100%',
              maxWidth: 520,
              borderTopLeftRadius: 20,
              borderTopRightRadius: 20,
              padding: '20px 18px 28px',
              boxShadow: '0 -4px 10px rgba(0, 0, 0, 0.15)',
              maxHeight: '90vh',
              overflowY: 'auto',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div style={{ width: 34, height: 34, borderRadius: 8, backgroundColor: '#eff6ff', color: '#2563eb', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Sparkles size={18} />
                </div>
                <div>
                  <h3 style={{ margin: 0, fontSize: '1.15rem', fontWeight: 800, color: '#0f172a' }}>
                    Portada Principal («{menuHomeForm.name || 'Todos'}»)
                  </h3>
                  <p style={{ margin: 0, fontSize: '0.75rem', color: '#64748b' }}>
                    Cabecera del menú web para todos tus platillos
                  </p>
                </div>
              </div>
              <button
                onClick={() => setIsMenuHomeModalOpen(false)}
                style={{ background: 'none', border: 'none', color: '#64748b', cursor: 'pointer', padding: 4 }}
              >
                <X size={20} />
              </button>
            </div>

            {menuHomeModalError && (
              <div
                style={{
                  backgroundColor: '#fee2e2',
                  border: '1px solid #fecaca',
                  borderRadius: 10,
                  padding: '8px 12px',
                  color: '#b91c1c',
                  fontSize: '0.85rem',
                  fontWeight: 600,
                  marginBottom: 12,
                }}
              >
                {menuHomeModalError}
              </div>
            )}

            <form
              onSubmit={(e) => {
                e.preventDefault();
                saveMenuHomeMutation.mutate(menuHomeForm);
              }}
            >
              {/* Name */}
              <div style={{ marginBottom: 14 }}>
                <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, color: '#334155', marginBottom: 4 }}>
                  Nombre de la pestaña principal *
                </label>
                <input
                  type="text"
                  required
                  maxLength={120}
                  placeholder="Todos"
                  value={menuHomeForm.name}
                  onChange={(e) => setMenuHomeForm({ ...menuHomeForm, name: e.target.value })}
                  style={{
                    width: '100%',
                    boxSizing: 'border-box',
                    padding: '10px 12px',
                    fontSize: '0.95rem',
                    fontWeight: 600,
                    borderRadius: 10,
                    border: '1px solid #cbd5e1',
                    outline: 'none',
                  }}
                />
                <span style={{ fontSize: '0.72rem', color: '#64748b', marginTop: 4, display: 'block' }}>
                  Por defecto es «Todos». Muestra el catálogo general de tu restaurante en el menú web.
                </span>
              </div>

              {/* Cover Photo */}
              <div style={{ marginBottom: 16 }}>
                <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, color: '#334155', marginBottom: 6 }}>
                  Foto de cabecera / Portada
                </label>

                {/* Preview if any */}
                {menuHomeForm.image_url ? (
                  <div style={{ position: 'relative', marginBottom: 10, borderRadius: 12, overflow: 'hidden', border: '1px solid #e2e8f0' }}>
                    <img
                      src={menuHomeForm.image_url}
                      alt="Vista previa portada"
                      style={{ width: '100%', height: 150, objectFit: 'cover' }}
                    />
                    <button
                      type="button"
                      onClick={() => setMenuHomeForm({ ...menuHomeForm, image_url: '' })}
                      style={{
                        position: 'absolute',
                        top: 8,
                        right: 8,
                        backgroundColor: 'rgba(0,0,0,0.65)',
                        color: '#ffffff',
                        border: 'none',
                        borderRadius: 6,
                        padding: '4px 8px',
                        fontSize: '0.75rem',
                        fontWeight: 700,
                        cursor: 'pointer',
                      }}
                    >
                      Quitar foto
                    </button>
                  </div>
                ) : (
                  <div
                    style={{
                      height: 76,
                      borderRadius: 10,
                      backgroundColor: '#f8fafc',
                      border: '1px dashed #cbd5e1',
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: 4,
                      marginBottom: 10,
                      color: '#94a3b8',
                      fontSize: '0.78rem',
                    }}
                  >
                    <ImageIcon size={22} />
                    <span>Sin foto de portada (se mostrará la ilustración predeterminada)</span>
                  </div>
                )}

                {/* Camera / Gallery Upload */}
                <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
                  <label
                    style={{
                      flex: 1,
                      padding: '12px',
                      backgroundColor: '#eff6ff',
                      border: '1px dashed #3b82f6',
                      borderRadius: 10,
                      color: '#1d4ed8',
                      fontSize: '0.85rem',
                      fontWeight: 700,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: 8,
                      cursor: 'pointer',
                    }}
                  >
                    <Camera size={20} />
                    Tomar foto con cámara / Cargar imagen
                    <input
                      type="file"
                      accept="image/*"
                      onChange={(e) => handlePhotoUpload(e, 'menu-home')}
                      style={{ display: 'none' }}
                    />
                  </label>
                </div>

                {/* Preset Suggestions */}
                <div style={{ fontSize: '0.75rem', fontWeight: 700, color: '#64748b', marginBottom: 6, display: 'flex', alignItems: 'center', gap: 4 }}>
                  <Sparkles size={14} color="#f59e0b" /> Portadas sugeridas de alta calidad:
                </div>
                <div
                  style={{
                    display: 'flex',
                    gap: 6,
                    overflowX: 'auto',
                    paddingBottom: 6,
                    scrollbarWidth: 'none',
                  }}
                >
                  {MENU_COVER_PRESET_IMAGES.map((preset) => (
                    <button
                      key={preset.label}
                      type="button"
                      onClick={() => setMenuHomeForm({ ...menuHomeForm, image_url: preset.url })}
                      style={{
                        padding: '5px 10px',
                        borderRadius: 8,
                        border: menuHomeForm.image_url === preset.url ? '2px solid #3b82f6' : '1px solid #e2e8f0',
                        backgroundColor: '#ffffff',
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        whiteSpace: 'nowrap',
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 4,
                      }}
                    >
                      <span>{preset.emoji}</span>
                      <span>{preset.label}</span>
                    </button>
                  ))}
                </div>

                {/* URL Input */}
                <div style={{ marginTop: 8 }}>
                  <input
                    type="url"
                    placeholder="O pega enlace público https://... (opcional)"
                    value={menuHomeForm.image_url.startsWith('data:') ? '' : menuHomeForm.image_url}
                    onChange={(e) => setMenuHomeForm({ ...menuHomeForm, image_url: e.target.value })}
                    style={{
                      width: '100%',
                      boxSizing: 'border-box',
                      padding: '8px 10px',
                      fontSize: '0.8rem',
                      borderRadius: 8,
                      border: '1px solid #cbd5e1',
                      outline: 'none',
                      color: '#475569',
                    }}
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={saveMenuHomeMutation.isPending || !menuHomeForm.name.trim()}
                style={{
                  width: '100%',
                  padding: '14px',
                  backgroundColor: '#2563eb',
                  color: '#ffffff',
                  border: 'none',
                  borderRadius: 12,
                  fontSize: '1rem',
                  fontWeight: 800,
                  cursor: 'pointer',
                  boxShadow: '0 4px 6px -1px rgba(37, 99, 235, 0.25)',
                }}
              >
                {saveMenuHomeMutation.isPending ? 'Guardando...' : 'Guardar Portada Principal'}
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
