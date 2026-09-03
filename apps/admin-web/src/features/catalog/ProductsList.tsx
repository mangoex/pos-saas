import React, { useMemo, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { Button, Badge, Modal, Input } from '@restaurantos/ui';
import { ApiError, fetchApi } from '@restaurantos/api-client';
import { Plus, Package, Edit, Trash2, SlidersHorizontal, Search, Sparkles, UploadCloud, FileText, Check } from 'lucide-react';
import { ModifierManager } from './ModifierManager';
import { resolveBranchId } from '../../lib/branchContext';

import '../../premium-catalogs.css';

interface Product {
  id: string;
  name: string;
  sku: string;
  category_name: string;
  price_cents: number | null;
  delivery_price_cents?: number | null;
  station: string;
  status?: string;
  image_url?: string;
  catalog_scope?: 'organization' | 'branch';
  source_branch_id?: string | null;
}

const emptyForm = {
  name: '',
  sku: '',
  category_name: '',
  station: 'kitchen',
  status: 'active',
  price_cents: 0,
  delivery_price_cents: null as number | null,
  image_url: '',
};

const ProductsList = () => {
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [search, setSearch] = useState(searchParams.get('search') || '');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingProduct, setEditingProduct] = useState<Product | null>(null);
  const [modifierProduct, setModifierProduct] = useState<Product | null>(null);
  const [formData, setFormData] = useState(emptyForm);
  const [isTemplateModalOpen, setIsTemplateModalOpen] = useState(false);
  const [modalTab, setModalTab] = useState<'templates' | 'ai_upload'>('templates');
  const [selectedTemplate, setSelectedTemplate] = useState('taqueria');
  const [selectedFile, setSelectedFile] = useState<{ file: File; base64: string; previewUrl?: string } | null>(null);
  const [parsedCategories, setParsedCategories] = useState<Array<{ name: string; products: Array<{ name: string; price: number; description: string; station: string }> }>>([]);
  const [templateError, setTemplateError] = useState('');

  const templateMutation = useMutation({
    mutationFn: (templateType: string) => {
      const branchId = resolveBranchId();
      return fetchApi('/catalog/seed-starter-template', {
        method: 'POST',
        body: JSON.stringify({ template_type: templateType, branch_id: branchId }),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['products'] });
      queryClient.invalidateQueries({ queryKey: ['categories'] });
      setIsTemplateModalOpen(false);
      setTemplateError('');
    },
    onError: (err) => {
      setTemplateError(err instanceof ApiError ? err.message : 'Error al cargar la plantilla de menú.');
    },
  });

  const parseMutation = useMutation({
    mutationFn: async (fileData: { base64: string; mime_type: string; filename: string }) => {
      return fetchApi('/catalog/parse-menu-file', {
        method: 'POST',
        body: JSON.stringify({
          file_base64: fileData.base64,
          mime_type: fileData.mime_type,
          filename: fileData.filename,
        }),
      });
    },
    onSuccess: (data: any) => {
      setParsedCategories(data.categories || []);
      setTemplateError('');
    },
    onError: (err) => {
      setTemplateError(err instanceof ApiError ? err.message : 'Error al procesar el archivo con IA.');
    },
  });

  const importMutation = useMutation({
    mutationFn: async (categories: any) => {
      const branchId = resolveBranchId();
      return fetchApi('/catalog/import-custom-catalog', {
        method: 'POST',
        body: JSON.stringify({
          categories,
          branch_id: branchId,
        }),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['products'] });
      queryClient.invalidateQueries({ queryKey: ['categories'] });
      setIsTemplateModalOpen(false);
      setParsedCategories([]);
      setSelectedFile(null);
      setTemplateError('');
    },
    onError: (err) => {
      setTemplateError(err instanceof ApiError ? err.message : 'Error al importar los productos al catálogo.');
    },
  });

  const { data: products, isLoading, error } = useQuery<Product[]>({
    queryKey: ['products'],
    queryFn: () => fetchApi('/catalog/products'),
  });

  const filteredProducts = useMemo(() => {
    const term = search.trim().toLocaleLowerCase('es-MX');
    if (!term) return products || [];
    return (products || []).filter((product) => (
      product.name.toLocaleLowerCase('es-MX').includes(term)
      || product.sku.toLocaleLowerCase('es-MX').includes(term)
    ));
  }, [products, search]);

  const updateSearch = (value: string) => {
    setSearch(value);
    setSearchParams(value ? { search: value } : {}, { replace: true });
  };

  const saveMutation = useMutation({
    mutationFn: (data: typeof formData) => {
      if (editingProduct) {
        return fetchApi(`/catalog/products/${editingProduct.id}`, {
          method: 'PUT',
          body: JSON.stringify(data),
        });
      }
      return fetchApi('/catalog/products', {
        method: 'POST',
        body: JSON.stringify(data),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['products'] });
      setIsModalOpen(false);
    }
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => fetchApi(`/catalog/products/${id}`, { method: 'DELETE' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['products'] })
  });

  const openModal = (product?: Product) => {
    if (product) {
      setEditingProduct(product);
      setFormData({ 
        name: product.name, 
        sku: product.sku, 
        category_name: product.category_name || '', 
        station: product.station || 'kitchen', 
        status: product.status || 'active',
        price_cents: product.price_cents || 0,
        delivery_price_cents: product.delivery_price_cents ?? null,
        image_url: product.image_url || ''
      });
    } else {
      setEditingProduct(null);
      setFormData(emptyForm);
    }
    setIsModalOpen(true);
  };

  const applyMargin = (percentage: number) => {
    if (!formData.price_cents) return;
    const calculated = Math.round(formData.price_cents * (1 + percentage / 100));
    setFormData((prev) => ({ ...prev, delivery_price_cents: calculated }));
  };

  return (
    <>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 32 }}>
        <div>
          <h1 className="premium-header-title">Productos y catálogo</h1>
          <p className="premium-header-subtitle">Ajusta categorías, precios, estaciones y activa los productos de tu catálogo.</p>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <button
            type="button"
            onClick={() => setIsTemplateModalOpen(true)}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 8,
              padding: '10px 16px',
              borderRadius: 10,
              border: '1px solid #cbd5e1',
              background: '#fff',
              color: '#0f172a',
              cursor: 'pointer',
              fontWeight: 600,
              fontSize: '0.875rem',
            }}
          >
            <Sparkles size={17} color="#10b981" />
            Cargar plantilla de menú
          </button>
          <button className="premium-add-btn" onClick={() => openModal()}>
            <Plus size={18} />
            Nuevo producto
          </button>
        </div>
      </div>

      <div style={{ position: 'relative', width: 360, maxWidth: '100%', marginBottom: 18 }}>
        <Search size={17} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: '#94a3b8' }} />
        <input
          value={search}
          onChange={(event) => updateSearch(event.target.value)}
          placeholder="Buscar producto por nombre o SKU"
          aria-label="Buscar producto por nombre o SKU"
          style={{ width: '100%', boxSizing: 'border-box', padding: '10px 12px 10px 38px', border: '1px solid #cbd5e1', borderRadius: 10, background: '#fff' }}
        />
      </div>

      <div className="premium-card">
        {isLoading ? (
          <div style={{ padding: 40, textAlign: 'center', color: 'var(--color-text-muted)' }}>Cargando catálogo...</div>
        ) : error ? (
          <div style={{ padding: 40, textAlign: 'center', color: 'var(--color-red)' }}>
            {error instanceof ApiError ? error.message : 'Error al cargar los productos.'}
          </div>
        ) : !products || products.length === 0 ? (
          <div className="premium-empty-state">
            <Package size={64} className="premium-empty-icon" />
            <h3 style={{ marginBottom: 8, fontSize: '1.25rem', fontWeight: 600 }}>No hay productos registrados</h3>
            <p style={{ color: 'var(--color-text-muted)' }}>Comienza agregando tu primer producto al menú o carga una plantilla.</p>
            <div style={{ display: 'flex', gap: 12, justifyContent: 'center', marginTop: 16 }}>
              <button
                type="button"
                onClick={() => setIsTemplateModalOpen(true)}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '10px 18px',
                  borderRadius: 8,
                  border: 'none',
                  background: '#10b981',
                  color: '#fff',
                  cursor: 'pointer',
                  fontWeight: 600,
                  fontSize: '0.875rem',
                }}
              >
                <Sparkles size={16} /> Cargar menú prediseñado
              </button>
            </div>
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table className="premium-table">
              <thead>
                <tr>
                  <th>Producto</th>
                  <th>SKU</th>
                  <th>Categoría</th>
                  <th>Estación</th>
                  <th style={{ textAlign: 'right' }}>Precio Salón</th>
                  <th style={{ textAlign: 'right' }}>Precio Delivery Apps</th>
                  <th style={{ textAlign: 'right' }}>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {filteredProducts.map((product) => (
                  <tr key={product.id}>
                    <td style={{ fontWeight: 500 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                        <div style={{ padding: 8, background: 'rgba(59, 130, 246, 0.1)', color: '#3b82f6', borderRadius: 8 }}>
                          <Package size={18} />
                        </div>
                        {product.name}
                        {product.status === 'inactive' && <Badge variant="default">Inactivo</Badge>}
                        {product.status === 'needs_review' && <Badge variant="warning">Requiere revisión</Badge>}
                        {product.catalog_scope === 'branch' && <Badge variant="info">De sucursal</Badge>}
                        {product.price_cents == null && <Badge variant="warning">Sin precio</Badge>}
                      </div>
                    </td>
                    <td style={{ color: 'var(--color-text-muted)' }}>{product.sku}</td>
                    <td><Badge variant="info">{product.category_name}</Badge></td>
                    <td>{product.station}</td>
                    <td style={{ textAlign: 'right', fontWeight: 600 }}>{product.price_cents == null ? 'No vendible' : `$${(product.price_cents / 100).toFixed(2)}`}</td>
                    <td style={{ textAlign: 'right', fontWeight: 600, color: product.delivery_price_cents ? '#0284c7' : '#64748b' }}>
                      {product.delivery_price_cents != null
                        ? `$${(product.delivery_price_cents / 100).toFixed(2)}`
                        : (product.price_cents ? `$${(product.price_cents / 100).toFixed(2)} (igual)` : '-')}
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                        <button className="premium-action-btn edit" title="Modificadores" onClick={() => setModifierProduct(product)}><SlidersHorizontal size={18} /></button>
                        <button className="premium-action-btn edit" onClick={() => openModal(product)}><Edit size={18} /></button>
                        <button className="premium-action-btn delete" onClick={() => deleteMutation.mutate(product.id)}><Trash2 size={18} /></button>
                      </div>
                    </td>
                  </tr>
                ))}
                {filteredProducts.length === 0 && (
                  <tr><td colSpan={7} style={{ padding: 32, textAlign: 'center', color: 'var(--color-text-muted)' }}>No hay productos que coincidan con la búsqueda.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <Modal isOpen={isModalOpen} onClose={() => setIsModalOpen(false)} title={editingProduct ? "Ajustar producto" : "Nuevo producto"}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500, fontSize: '0.875rem' }}>Nombre</label>
            <Input value={formData.name} onChange={(e: any) => setFormData({...formData, name: e.target.value})} />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500, fontSize: '0.875rem' }}>SKU</label>
            <Input value={formData.sku} onChange={(e: any) => setFormData({...formData, sku: e.target.value})} />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500, fontSize: '0.875rem' }}>Categoría</label>
            <Input value={formData.category_name} onChange={(e: any) => setFormData({...formData, category_name: e.target.value})} />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500, fontSize: '0.875rem' }}>Estación operativa</label>
            <select value={formData.station} onChange={(event) => setFormData({ ...formData, station: event.target.value })} style={{ width: '100%', padding: 10, borderRadius: 8, border: '1px solid #d1d5db' }}>
              <option value="unassigned">Sin asignar</option>
              <option value="kitchen">Cocina</option>
              <option value="drinks">Bebidas</option>
              <option value="packing">Empaque</option>
            </select>
          </div>
          {editingProduct && (
            <div>
              <label style={{ display: 'block', marginBottom: 4, fontWeight: 500, fontSize: '0.875rem' }}>Estado</label>
              <select value={formData.status} onChange={(event) => setFormData({ ...formData, status: event.target.value })} style={{ width: '100%', padding: 10, borderRadius: 8, border: '1px solid #d1d5db' }}>
                <option value="needs_review">Requiere revisión</option>
                <option value="active">Activo</option>
                <option value="inactive">Inactivo</option>
              </select>
              {formData.status === 'active' && formData.station === 'unassigned' && <p style={{ color: '#b45309', fontSize: 13 }}>Asigna una estación antes de activar.</p>}
            </div>
          )}
          <div>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500, fontSize: '0.875rem' }}>Precio Salón / Mostrador ($ MXN)</label>
            <Input
              type="number"
              step="0.50"
              value={formData.price_cents ? (formData.price_cents / 100).toString() : ''}
              onChange={(e: any) => {
                const val = parseFloat(e.target.value);
                setFormData({ ...formData, price_cents: isNaN(val) ? 0 : Math.round(val * 100) });
              }}
              placeholder="Ej. 120.00"
            />
          </div>
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
              <label style={{ fontWeight: 500, fontSize: '0.875rem' }}>Precio Apps Delivery (Uber / DiDi / Rappi)</label>
              <div style={{ display: 'flex', gap: 4 }}>
                <span style={{ fontSize: '0.75rem', color: '#64748b', marginRight: 4 }}>Margen:</span>
                <button
                  type="button"
                  onClick={() => applyMargin(20)}
                  style={{ fontSize: '0.75rem', padding: '2px 6px', borderRadius: 4, background: '#e0f2fe', color: '#0369a1', border: 'none', cursor: 'pointer' }}
                >
                  +20%
                </button>
                <button
                  type="button"
                  onClick={() => applyMargin(25)}
                  style={{ fontSize: '0.75rem', padding: '2px 6px', borderRadius: 4, background: '#e0f2fe', color: '#0369a1', border: 'none', cursor: 'pointer' }}
                >
                  +25%
                </button>
                <button
                  type="button"
                  onClick={() => applyMargin(30)}
                  style={{ fontSize: '0.75rem', padding: '2px 6px', borderRadius: 4, background: '#e0f2fe', color: '#0369a1', border: 'none', cursor: 'pointer' }}
                >
                  +30%
                </button>
              </div>
            </div>
            <Input
              type="number"
              step="0.50"
              value={formData.delivery_price_cents ? (formData.delivery_price_cents / 100).toString() : ''}
              onChange={(e: any) => {
                const val = parseFloat(e.target.value);
                setFormData({ ...formData, delivery_price_cents: isNaN(val) ? null : Math.round(val * 100) });
              }}
              placeholder="Opcional (si se omite, se usa precio de salón)"
            />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500, fontSize: '0.875rem' }}>URL de imagen</label>
            <Input value={formData.image_url} onChange={(e: any) => setFormData({...formData, image_url: e.target.value})} placeholder="https://example.com/image.png" />
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12, marginTop: 16 }}>
            <Button variant="secondary" onClick={() => setIsModalOpen(false)}>Cancelar</Button>
            <Button variant="primary" onClick={() => saveMutation.mutate(formData)} disabled={saveMutation.isPending || (formData.status === 'active' && formData.station === 'unassigned')}>
              {saveMutation.isPending ? 'Guardando...' : 'Guardar'}
            </Button>
          </div>
        </div>
      </Modal>

      {modifierProduct && <ModifierManager isOpen productId={modifierProduct.id} productName={modifierProduct.name} onClose={() => setModifierProduct(null)} />}

      <Modal isOpen={isTemplateModalOpen} onClose={() => { setIsTemplateModalOpen(false); setParsedCategories([]); setSelectedFile(null); }} title="Crear o Cargar Menú">
        <div style={{ display: 'grid', gap: 16, maxHeight: '85vh', overflowY: 'auto' }}>
          {/* Tabs */}
          <div style={{ display: 'flex', borderBottom: '1px solid #e2e8f0', gap: 8 }}>
            <button
              type="button"
              onClick={() => setModalTab('templates')}
              style={{
                padding: '8px 16px',
                border: 'none',
                background: 'transparent',
                fontWeight: 600,
                fontSize: '0.875rem',
                cursor: 'pointer',
                color: modalTab === 'templates' ? '#10b981' : '#64748b',
                borderBottom: modalTab === 'templates' ? '2px solid #10b981' : '2px solid transparent',
              }}
            >
              📋 Plantillas Rápidas
            </button>
            <button
              type="button"
              onClick={() => setModalTab('ai_upload')}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                padding: '8px 16px',
                border: 'none',
                background: 'transparent',
                fontWeight: 600,
                fontSize: '0.875rem',
                cursor: 'pointer',
                color: modalTab === 'ai_upload' ? '#10b981' : '#64748b',
                borderBottom: modalTab === 'ai_upload' ? '2px solid #10b981' : '2px solid transparent',
              }}
            >
              <Sparkles size={16} /> Subir Menú (PDF / Imagen)
            </button>
          </div>

          {templateError && (
            <div style={{ padding: 12, borderRadius: 8, background: '#fee2e2', color: '#dc2626', fontSize: '0.875rem' }}>
              {templateError}
            </div>
          )}

          {modalTab === 'templates' ? (
            <>
              <p style={{ margin: 0, color: '#64748b', fontSize: '0.875rem' }}>
                Selecciona un giro comercial para precargar categorías, productos listos para la venta, precios base y configuración de estación.
              </p>

              <div style={{ display: 'grid', gap: 10 }}>
                {[
                  { id: 'taqueria', title: '🌮 Taquería Mexicana', desc: 'Tacos al Pastor, Asada, Gringas y Aguas Frescas' },
                  { id: 'cafeteria', title: '☕ Cafetería y Repostería', desc: 'Americano, Capuchino, Latte, Croissants y Pasteles' },
                  { id: 'hamburgueseria', title: '🍔 Hamburguesería & Snacks', desc: 'Burgers clásicas, dobles, Papas a la Francesa y Bebidas' },
                  { id: 'pizzeria', title: '🍕 Pizzería Artesanal', desc: 'Pizzas medianas de Pepperoni, Hawaiana y Refrescos' },
                  { id: 'general', title: '🍽️ Menú Restaurante General', desc: 'Platillos especiales, combos del día y bebidas de la casa' },
                ].map((tmpl) => (
                  <button
                    key={tmpl.id}
                    type="button"
                    onClick={() => setSelectedTemplate(tmpl.id)}
                    style={{
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: 'flex-start',
                      gap: 4,
                      padding: '12px 16px',
                      borderRadius: 10,
                      border: selectedTemplate === tmpl.id ? '2px solid #10b981' : '1px solid #e2e8f0',
                      background: selectedTemplate === tmpl.id ? '#ecfdf5' : '#fff',
                      cursor: 'pointer',
                      textAlign: 'left',
                    }}
                  >
                    <strong style={{ fontSize: '0.95rem', color: '#0f172a' }}>{tmpl.title}</strong>
                    <span style={{ fontSize: '0.8125rem', color: '#64748b' }}>{tmpl.desc}</span>
                  </button>
                ))}
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12, marginTop: 8 }}>
                <Button variant="secondary" onClick={() => setIsTemplateModalOpen(false)}>
                  Cancelar
                </Button>
                <Button
                  variant="primary"
                  onClick={() => templateMutation.mutate(selectedTemplate)}
                  disabled={templateMutation.isPending}
                >
                  {templateMutation.isPending ? 'Cargando plantilla...' : 'Cargar este menú'}
                </Button>
              </div>
            </>
          ) : (
            /* Tab: Subir Menú PDF / Imagen */
            <>
              {parsedCategories.length === 0 ? (
                <div style={{ display: 'grid', gap: 16 }}>
                  <p style={{ margin: 0, color: '#64748b', fontSize: '0.875rem' }}>
                    Sube una fotografía, imagen digital o archivo PDF de tu carta o menú. Nuestra IA analizará los platillos, bebidas y precios para importarlos a tu sistema.
                  </p>

                  <label
                    style={{
                      border: '2px dashed #cbd5e1',
                      borderRadius: 12,
                      padding: 28,
                      textAlign: 'center',
                      background: selectedFile ? '#f0fdf4' : '#f8fafc',
                      cursor: 'pointer',
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: 'center',
                      gap: 10,
                    }}
                  >
                    <input
                      type="file"
                      accept=".pdf,image/png,image/jpeg,image/jpg,image/webp"
                      style={{ display: 'none' }}
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (!file) return;
                        const reader = new FileReader();
                        reader.onload = (event) => {
                          const base64 = event.target?.result as string;
                          const previewUrl = file.type.startsWith('image/') ? URL.createObjectURL(file) : undefined;
                          setSelectedFile({ file, base64, previewUrl });
                          setTemplateError('');
                        };
                        reader.readAsDataURL(file);
                      }}
                    />
                    <div style={{ padding: 12, borderRadius: 12, background: '#ecfdf5', color: '#10b981' }}>
                      <UploadCloud size={32} />
                    </div>
                    {selectedFile ? (
                      <div>
                        <strong style={{ color: '#0f172a', display: 'block' }}>{selectedFile.file.name}</strong>
                        <span style={{ fontSize: '0.8125rem', color: '#64748b' }}>
                          {(selectedFile.file.size / 1024).toFixed(1)} KB · Clic para cambiar archivo
                        </span>
                        {selectedFile.previewUrl && (
                          <div style={{ marginTop: 12, maxHeight: 180, overflow: 'hidden', borderRadius: 8 }}>
                            <img src={selectedFile.previewUrl} alt="Preview" style={{ maxHeight: 180, objectFit: 'contain' }} />
                          </div>
                        )}
                      </div>
                    ) : (
                      <div>
                        <strong style={{ color: '#0f172a', display: 'block' }}>Selecciona o arrastra tu menú</strong>
                        <span style={{ fontSize: '0.8125rem', color: '#64748b' }}>Soporta PDF, JPG, PNG o WebP (hasta 10MB)</span>
                      </div>
                    )}
                  </label>

                  <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12, marginTop: 8 }}>
                    <Button variant="secondary" onClick={() => setIsTemplateModalOpen(false)}>
                      Cancelar
                    </Button>
                    <Button
                      variant="primary"
                      disabled={!selectedFile || parseMutation.isPending}
                      onClick={() => {
                        if (!selectedFile) return;
                        parseMutation.mutate({
                          base64: selectedFile.base64,
                          mime_type: selectedFile.file.type,
                          filename: selectedFile.file.name,
                        });
                      }}
                    >
                      {parseMutation.isPending ? 'Analizando con IA...' : '✨ Analizar menú con IA'}
                    </Button>
                  </div>
                </div>
              ) : (
                /* Parsed Review Mode */
                <div style={{ display: 'grid', gap: 14 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <h4 style={{ margin: 0, fontSize: '1rem', color: '#0f172a' }}>Revisión del menú detectado</h4>
                      <p style={{ margin: '2px 0 0', color: '#64748b', fontSize: '0.8125rem' }}>
                        Verifica y ajusta los nombres y precios antes de importar a tu menú.
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => { setParsedCategories([]); setSelectedFile(null); }}
                      style={{ fontSize: '0.8125rem', color: '#64748b', background: 'transparent', border: 'none', cursor: 'pointer', textDecoration: 'underline' }}
                    >
                      Volver a escanear
                    </button>
                  </div>

                  <div style={{ display: 'grid', gap: 12, maxHeight: '380px', overflowY: 'auto' }}>
                    {parsedCategories.map((cat, catIdx) => (
                      <div key={catIdx} style={{ border: '1px solid #e2e8f0', borderRadius: 8, padding: 12, background: '#fff' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                          <input
                            type="text"
                            value={cat.name}
                            onChange={(e) => {
                              const newCats = [...parsedCategories];
                              newCats[catIdx].name = e.target.value;
                              setParsedCategories(newCats);
                            }}
                            style={{ fontWeight: 700, fontSize: '0.95rem', border: 'none', borderBottom: '1px dashed #cbd5e1', outline: 'none', padding: '2px 4px', width: '220px' }}
                          />
                          <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>{cat.products.length} productos</span>
                        </div>
                        <div style={{ display: 'grid', gap: 6 }}>
                          {cat.products.map((prod, prodIdx) => (
                            <div key={prodIdx} style={{ display: 'flex', alignItems: 'center', gap: 8, background: '#f8fafc', padding: '6px 10px', borderRadius: 6 }}>
                              <input
                                type="text"
                                value={prod.name}
                                onChange={(e) => {
                                  const newCats = [...parsedCategories];
                                  newCats[catIdx].products[prodIdx].name = e.target.value;
                                  setParsedCategories(newCats);
                                }}
                                style={{ flex: 1, border: '1px solid #cbd5e1', borderRadius: 4, padding: '4px 8px', fontSize: '0.85rem' }}
                              />
                              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                                <span style={{ fontSize: '0.85rem', color: '#64748b' }}>$</span>
                                <input
                                  type="number"
                                  step="0.50"
                                  value={prod.price}
                                  onChange={(e) => {
                                    const newCats = [...parsedCategories];
                                    newCats[catIdx].products[prodIdx].price = parseFloat(e.target.value) || 0;
                                    setParsedCategories(newCats);
                                  }}
                                  style={{ width: 80, border: '1px solid #cbd5e1', borderRadius: 4, padding: '4px 8px', fontSize: '0.85rem', textAlign: 'right' }}
                                />
                              </div>
                              <span style={{ fontSize: '0.75rem', padding: '2px 6px', borderRadius: 4, background: prod.station === 'barra' ? '#e0f2fe' : '#fef3c7', color: prod.station === 'barra' ? '#0369a1' : '#b45309' }}>
                                {prod.station === 'barra' ? 'Barra' : 'Cocina'}
                              </span>
                              <button
                                type="button"
                                onClick={() => {
                                  const newCats = [...parsedCategories];
                                  newCats[catIdx].products.splice(prodIdx, 1);
                                  if (newCats[catIdx].products.length === 0) {
                                    newCats.splice(catIdx, 1);
                                  }
                                  setParsedCategories(newCats);
                                }}
                                style={{ border: 'none', background: 'transparent', color: '#ef4444', cursor: 'pointer', padding: 2 }}
                              >
                                <Trash2 size={15} />
                              </button>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>

                  <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12, marginTop: 8 }}>
                    <Button variant="secondary" onClick={() => setIsTemplateModalOpen(false)}>
                      Cancelar
                    </Button>
                    <Button
                      variant="primary"
                      disabled={parsedCategories.length === 0 || importMutation.isPending}
                      onClick={() => importMutation.mutate(parsedCategories)}
                    >
                      {importMutation.isPending ? 'Guardando en el menú...' : 'Guardar en el menú'}
                    </Button>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </Modal>
    </>
  );
};
export default ProductsList;
