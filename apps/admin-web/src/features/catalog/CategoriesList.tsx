import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Button, Badge, Modal, Input } from '@restaurantos/ui';
import { fetchApi } from '@restaurantos/api-client';
import { Plus, Tags, Edit } from 'lucide-react';

import '../../premium-catalogs.css';

interface Category {
  id: string;
  name: string;
  display_order: number;
  status: string;
}

const CategoriesList = () => {
  const queryClient = useQueryClient();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingCategory, setEditingCategory] = useState<Category | null>(null);
  const [formData, setFormData] = useState({ name: '', display_order: 0, status: 'active' });
  const [formError, setFormError] = useState<string | null>(null);

  const { data: categories, isLoading, error } = useQuery<Category[]>({
    queryKey: ['categories'],
    queryFn: () => fetchApi('/categories'),
  });

  const saveMutation = useMutation({
    mutationFn: (data: typeof formData) => {
      if (editingCategory) {
        return fetchApi(`/categories/${editingCategory.id}`, {
          method: 'PUT',
          body: JSON.stringify({ name: data.name, display_order: data.display_order, status: data.status }),
        });
      }
      return fetchApi('/categories', {
        method: 'POST',
        body: JSON.stringify({ name: data.name, display_order: data.display_order }),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['categories'] });
      setFormError(null);
      setIsModalOpen(false);
    },
    onError: (err: any) => {
      setFormError(err?.message || err?.detail?.message || 'No fue posible guardar la categoría.');
    }
  });

  const openModal = (category?: Category) => {
    setFormError(null);
    if (category) {
      setEditingCategory(category);
      setFormData({ name: category.name, display_order: category.display_order, status: category.status });
    } else {
      setEditingCategory(null);
      setFormData({ name: '', display_order: categories ? categories.length : 0, status: 'active' });
    }
    setIsModalOpen(true);
  };

  return (
    <>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 32 }}>
        <div>
          <h1 className="premium-header-title">Categorías</h1>
          <p className="premium-header-subtitle">Organiza tus productos en categorías para el punto de venta.</p>
        </div>
        <button className="premium-add-btn" onClick={() => openModal()}>
          <Plus size={18} />
          Nueva Categoría
        </button>
      </div>

      <div className="premium-card">
        {isLoading ? (
          <div style={{ padding: 40, textAlign: 'center', color: 'var(--color-text-muted)' }}>Cargando categorías...</div>
        ) : error ? (
          <div style={{ padding: 40, textAlign: 'center', color: 'var(--color-red)' }}>Error al cargar categorías.</div>
        ) : !categories || categories.length === 0 ? (
          <div className="premium-empty-state">
            <Tags size={64} className="premium-empty-icon" />
            <h3 style={{ marginBottom: 8, fontSize: '1.25rem', fontWeight: 600 }}>No hay categorías</h3>
            <p style={{ color: 'var(--color-text-muted)' }}>Crea categorías (ej. Bebidas, Postres) para agrupar productos.</p>
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table className="premium-table">
              <thead>
                <tr>
                  <th>Orden</th>
                  <th>Nombre</th>
                  <th>Estatus</th>
                  <th style={{ textAlign: 'right' }}>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {categories.map((category) => (
                  <tr key={category.id}>
                    <td style={{ color: 'var(--color-text-muted)', fontWeight: 600 }}>{category.display_order}</td>
                    <td style={{ fontWeight: 500 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                        <div style={{ padding: 8, background: 'rgba(59, 130, 246, 0.1)', color: '#3b82f6', borderRadius: 8 }}>
                          <Tags size={18} />
                        </div>
                        {category.name}
                      </div>
                    </td>
                    <td>
                      <Badge variant={category.status === 'active' ? 'success' : 'default'}>
                        {category.status === 'active' ? 'Activo' : 'Inactivo'}
                      </Badge>
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                        <button className="premium-action-btn edit" onClick={() => openModal(category)}><Edit size={18} /></button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <Modal isOpen={isModalOpen} onClose={() => setIsModalOpen(false)} title={editingCategory ? "Editar Categoría" : "Nueva Categoría"}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {formError && (
            <div role="alert" style={{ padding: '10px 14px', borderRadius: 8, background: '#fee2e2', color: '#b91c1c', fontSize: '0.875rem' }}>
              {formError}
            </div>
          )}
          <div>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500, fontSize: '0.875rem' }}>Nombre</label>
            <Input value={formData.name} onChange={(e: any) => setFormData({...formData, name: e.target.value})} />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500, fontSize: '0.875rem' }}>Orden de Aparición</label>
            <Input 
              type="number" 
              value={formData.display_order} 
              onChange={(e: any) => setFormData({...formData, display_order: parseInt(e.target.value) || 0})} 
            />
          </div>
          {editingCategory && (
            <div>
              <label style={{ display: 'block', marginBottom: 4, fontWeight: 500, fontSize: '0.875rem' }}>Estatus</label>
              <select 
                value={formData.status} 
                onChange={e => setFormData({...formData, status: e.target.value})}
                style={{ width: '100%', padding: '10px 12px', borderRadius: 8, border: '1px solid var(--color-border)', backgroundColor: 'var(--color-bg)', outline: 'none' }}
              >
                <option value="active">Activo</option>
                <option value="inactive">Inactivo</option>
              </select>
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12, marginTop: 16 }}>
            <Button variant="secondary" onClick={() => setIsModalOpen(false)}>Cancelar</Button>
            <Button variant="primary" onClick={() => saveMutation.mutate(formData)} disabled={saveMutation.isPending || !formData.name}>
              {saveMutation.isPending ? 'Guardando...' : 'Guardar'}
            </Button>
          </div>
        </div>
      </Modal>
    </>
  );
};
export default CategoriesList;
