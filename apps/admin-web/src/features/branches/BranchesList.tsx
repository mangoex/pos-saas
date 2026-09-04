import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Button, Badge, Modal, Input } from '@restaurantos/ui';
import { fetchApi } from '@restaurantos/api-client';
import { Plus, Store, Edit, Trash2, MapPin, Navigation, Phone, Star } from 'lucide-react';

import '../../premium-catalogs.css';

interface Branch {
  id: string;
  name: string;
  code: string;
  status: string;
  street?: string;
  exterior_number?: string;
  interior_number?: string;
  neighborhood?: string;
  postal_code?: string;
  city?: string;
  state?: string;
  cross_streets?: string;
  latitude?: number | null;
  longitude?: number | null;
  phone?: string;
  google_review_url?: string;
  organization_id: string;
  business_unit_id: string;
  business_unit_name: string;
  legal_entity_name: string;
}

interface BusinessUnit {
  id: string;
  name: string;
  code: string;
  unit_type: 'restaurant' | 'other';
  legal_entity_name: string;
}

const emptyForm = {
  name: '',
  code: '',
  business_unit_id: '',
  street: '',
  exterior_number: '',
  interior_number: '',
  neighborhood: '',
  postal_code: '',
  city: 'Culiacán',
  state: 'Sinaloa',
  cross_streets: '',
  latitude: '',
  longitude: '',
  phone: '',
  google_review_url: '',
};

const BranchesList = () => {
  const queryClient = useQueryClient();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingBranch, setEditingBranch] = useState<Branch | null>(null);
  const [formData, setFormData] = useState(emptyForm);

  const { data: branches, isLoading, error } = useQuery<Branch[]>({
    queryKey: ['branches'],
    queryFn: () => fetchApi('/branches'),
  });

  const { data: businessUnits = [] } = useQuery<BusinessUnit[]>({
    queryKey: ['business-units'],
    queryFn: () => fetchApi('/business-units'),
  });

  const saveMutation = useMutation({
    mutationFn: (data: typeof formData) => {
      const payload: any = {
        ...data,
        latitude: data.latitude.trim() ? parseFloat(data.latitude) : null,
        longitude: data.longitude.trim() ? parseFloat(data.longitude) : null,
      };
      if (editingBranch) {
        return fetchApi(`/branches/${editingBranch.id}`, {
          method: 'PUT',
          body: JSON.stringify(payload),
        });
      }
      return fetchApi('/branches', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['branches'] });
      setIsModalOpen(false);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => fetchApi(`/branches/${id}`, { method: 'DELETE' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['branches'] }),
  });

  const openModal = (branch?: Branch) => {
    if (branch) {
      setEditingBranch(branch);
      setFormData({
        name: branch.name || '',
        code: branch.code || '',
        business_unit_id: branch.business_unit_id || '',
        street: branch.street || '',
        exterior_number: branch.exterior_number || '',
        interior_number: branch.interior_number || '',
        neighborhood: branch.neighborhood || '',
        postal_code: branch.postal_code || '',
        city: branch.city || 'Culiacán',
        state: branch.state || 'Sinaloa',
        cross_streets: branch.cross_streets || '',
        latitude: branch.latitude !== null && branch.latitude !== undefined ? String(branch.latitude) : '',
        longitude: branch.longitude !== null && branch.longitude !== undefined ? String(branch.longitude) : '',
        phone: branch.phone || '',
        google_review_url: branch.google_review_url || '',
      });
    } else {
      setEditingBranch(null);
      setFormData({
        ...emptyForm,
        business_unit_id: businessUnits[0]?.id || '',
      });
    }
    setIsModalOpen(true);
  };

  const formatBranchAddress = (b: Branch) => {
    const parts = [];
    if (b.street) {
      parts.push(`${b.street} ${b.exterior_number || ''}`.trim());
    }
    if (b.neighborhood) {
      parts.push(`Col. ${b.neighborhood}`);
    }
    return parts.length > 0 ? parts.join(', ') : 'Sin domicilio registrado';
  };

  return (
    <>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 32 }}>
        <div>
          <h1 className="premium-header-title">Mi Restaurante y Sucursales</h1>
          <p className="premium-header-subtitle">Administra los datos de tu restaurante, domicilio, coordenadas GPS y enlace de tu Menú Web Móvil.</p>
        </div>
        <button className="premium-add-btn" onClick={() => openModal()}>
          <Plus size={18} />
          Nuevo Restaurante / Sucursal
        </button>
      </div>

      <div className="premium-card">
        {isLoading ? (
          <div style={{ padding: 40, textAlign: 'center', color: 'var(--color-text-muted)' }}>Cargando sucursales...</div>
        ) : error ? (
          <div style={{ padding: 40, textAlign: 'center', color: 'var(--color-red)' }}>Error al cargar sucursales.</div>
        ) : !branches || branches.length === 0 ? (
          <div className="premium-empty-state">
            <Store size={64} className="premium-empty-icon" />
            <h3 style={{ marginBottom: 8, fontSize: '1.25rem', fontWeight: 600 }}>No hay sucursales registradas</h3>
            <p style={{ color: 'var(--color-text-muted)' }}>Agrega la primera sucursal para operar.</p>
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table className="premium-table">
              <thead>
                <tr>
                  <th>Nombre</th>
                  <th>Estatus</th>
                  <th>Código</th>
                  <th>Domicilio & Entre Calles</th>
                  <th>GPS (Lat, Lng)</th>
                  <th>Unidad de negocio</th>
                  <th style={{ textAlign: 'right' }}>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {branches.map((branch) => (
                  <tr key={branch.id}>
                    <td style={{ fontWeight: 500 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                        <div style={{ padding: 8, background: 'rgba(59, 130, 246, 0.1)', color: '#3b82f6', borderRadius: 8 }}>
                          <Store size={18} />
                        </div>
                        <div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                            <span>{branch.name}</span>
                            {branch.google_review_url && (
                              <span title={`Google Reviews: ${branch.google_review_url}`} style={{ display: 'inline-flex', alignItems: 'center', gap: 2, background: '#fef9c3', color: '#854d0e', padding: '2px 6px', borderRadius: 4, fontSize: '0.6875rem', fontWeight: 700 }}>
                                <Star size={10} fill="#eab308" color="#eab308" /> Reseñas
                              </span>
                            )}
                          </div>
                          {branch.phone && (
                            <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', display: 'flex', alignItems: 'center', gap: 4, marginTop: 2 }}>
                              <Phone size={12} /> {branch.phone}
                            </div>
                          )}
                        </div>
                      </div>
                    </td>
                    <td>
                      <Badge variant={branch.status === 'active' ? 'success' : 'default'}>
                        {branch.status === 'active' ? 'Activa' : 'Inactiva'}
                      </Badge>
                    </td>
                    <td style={{ color: 'var(--color-text-muted)', fontWeight: 600 }}>{branch.code}</td>
                    <td>
                      <div style={{ fontSize: '0.875rem' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                          <MapPin size={14} style={{ color: '#3b82f6', flexShrink: 0 }} />
                          <span>{formatBranchAddress(branch)}</span>
                        </div>
                        {branch.cross_streets && (
                          <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', marginTop: 2, paddingLeft: 18 }}>
                            Entre: {branch.cross_streets}
                          </div>
                        )}
                      </div>
                    </td>
                    <td>
                      {branch.latitude && branch.longitude ? (
                        <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: '0.8125rem', fontFamily: 'monospace', color: '#059669', background: '#ecfdf5', padding: '4px 8px', borderRadius: 6, width: 'fit-content' }}>
                          <Navigation size={12} />
                          <span>{Number(branch.latitude).toFixed(5)}, {Number(branch.longitude).toFixed(5)}</span>
                        </div>
                      ) : (
                        <span style={{ fontSize: '0.8125rem', color: 'var(--color-text-muted)' }}>Sin GPS</span>
                      )}
                    </td>
                    <td>{branch.business_unit_name}</td>
                    <td style={{ textAlign: 'right' }}>
                      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                        <button className="premium-action-btn edit" onClick={() => openModal(branch)} title="Editar"><Edit size={18} /></button>
                        <button className="premium-action-btn delete" onClick={() => deleteMutation.mutate(branch.id)} title="Desactivar"><Trash2 size={18} /></button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <Modal isOpen={isModalOpen} onClose={() => setIsModalOpen(false)} title={editingBranch ? `Restaurante: ${editingBranch.name}` : 'Nuevo Restaurante'}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16, maxHeight: '75vh', overflowY: 'auto', paddingRight: 4 }}>
          <div style={{ borderBottom: '1px solid var(--color-border)', paddingBottom: 12 }}>
            <h4 style={{ margin: '0 0 12px 0', fontSize: '0.9rem', color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Datos del Restaurante</h4>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <div>
                <label style={{ display: 'block', marginBottom: 4, fontWeight: 500, fontSize: '0.875rem' }}>Nombre del restaurante o sucursal *</label>
                <Input value={formData.name} onChange={(e: any) => setFormData({...formData, name: e.target.value})} placeholder="Ej. Mi Taquería / Sucursal Centro" />
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: 4, fontWeight: 500, fontSize: '0.875rem' }}>Código / Slug móvil (ej. PILOTO) *</label>
                <Input value={formData.code} onChange={(e: any) => setFormData({...formData, code: e.target.value})} placeholder="Ej. PILOTO o MITAQUERIA" />
                <span style={{ display: 'block', fontSize: '0.75rem', color: 'var(--color-text-muted)', marginTop: 4 }}>
                  Identificador para tu Menú Web Móvil y QR (<code>?slug={formData.code || 'CODIGO'}</code>)
                </span>
              </div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 12 }}>
              <div>
                <label htmlFor="business-unit" style={{ display: 'block', marginBottom: 4, fontWeight: 500, fontSize: '0.875rem' }}>Unidad de negocio</label>
                <select
                  id="business-unit"
                  value={formData.business_unit_id}
                  onChange={(event) => setFormData({...formData, business_unit_id: event.target.value})}
                  disabled={Boolean(editingBranch)}
                  style={{ width: '100%', padding: 10, borderRadius: 8, border: '1px solid var(--color-border)', backgroundColor: 'var(--color-surface)' }}
                >
                  <option value="">Selecciona una unidad</option>
                  {businessUnits.map((unit) => (
                    <option key={unit.id} value={unit.id}>{unit.name} · {unit.legal_entity_name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: 4, fontWeight: 500, fontSize: '0.875rem' }}>Teléfono de contacto</label>
                <Input value={formData.phone} onChange={(e: any) => setFormData({...formData, phone: e.target.value})} placeholder="Ej. 6671234567" />
              </div>
            </div>
          </div>

          <div style={{ borderBottom: '1px solid var(--color-border)', paddingBottom: 12 }}>
            <h4 style={{ margin: '0 0 12px 0', fontSize: '0.9rem', color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Domicilio Físico</h4>
            <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr', gap: 12 }}>
              <div>
                <label style={{ display: 'block', marginBottom: 4, fontWeight: 500, fontSize: '0.875rem' }}>Calle</label>
                <Input value={formData.street} onChange={(e: any) => setFormData({...formData, street: e.target.value})} placeholder="Ej. Av. Álvaro Obregón" />
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: 4, fontWeight: 500, fontSize: '0.875rem' }}>No. Exterior</label>
                <Input value={formData.exterior_number} onChange={(e: any) => setFormData({...formData, exterior_number: e.target.value})} placeholder="Ej. 450" />
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: 4, fontWeight: 500, fontSize: '0.875rem' }}>No. Interior / Local</label>
                <Input value={formData.interior_number} onChange={(e: any) => setFormData({...formData, interior_number: e.target.value})} placeholder="Ej. Local 3B" />
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 12, marginTop: 12 }}>
              <div>
                <label style={{ display: 'block', marginBottom: 4, fontWeight: 500, fontSize: '0.875rem' }}>Colonia</label>
                <Input value={formData.neighborhood} onChange={(e: any) => setFormData({...formData, neighborhood: e.target.value})} placeholder="Ej. Centro" />
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: 4, fontWeight: 500, fontSize: '0.875rem' }}>Código Postal</label>
                <Input value={formData.postal_code} onChange={(e: any) => setFormData({...formData, postal_code: e.target.value})} placeholder="Ej. 80000" />
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 12 }}>
              <div>
                <label style={{ display: 'block', marginBottom: 4, fontWeight: 500, fontSize: '0.875rem' }}>Ciudad</label>
                <Input value={formData.city} onChange={(e: any) => setFormData({...formData, city: e.target.value})} placeholder="Ej. Culiacán" />
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: 4, fontWeight: 500, fontSize: '0.875rem' }}>Estado</label>
                <Input value={formData.state} onChange={(e: any) => setFormData({...formData, state: e.target.value})} placeholder="Ej. Sinaloa" />
              </div>
            </div>

            <div style={{ marginTop: 12 }}>
              <label style={{ display: 'block', marginBottom: 4, fontWeight: 500, fontSize: '0.875rem' }}>Entre calles / Referencias de ubicación</label>
              <Input value={formData.cross_streets} onChange={(e: any) => setFormData({...formData, cross_streets: e.target.value})} placeholder="Ej. Entre Ruperto Paliza y Domingo Rubí, frente a catedral" />
            </div>
          </div>

          <div>
            <h4 style={{ margin: '0 0 12px 0', fontSize: '0.9rem', color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Geolocalización GPS (Para asignación automática)</h4>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <div>
                <label style={{ display: 'block', marginBottom: 4, fontWeight: 500, fontSize: '0.875rem' }}>Latitud GPS (Lat)</label>
                <Input value={formData.latitude} onChange={(e: any) => setFormData({...formData, latitude: e.target.value})} placeholder="Ej. 24.8083000" />
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: 4, fontWeight: 500, fontSize: '0.875rem' }}>Longitud GPS (Lng)</label>
                <Input value={formData.longitude} onChange={(e: any) => setFormData({...formData, longitude: e.target.value})} placeholder="Ej. -107.3941000" />
              </div>
            </div>
          </div>

          <div style={{ borderTop: '1px solid var(--color-border)', paddingTop: 12 }}>
            <h4 style={{ margin: '0 0 12px 0', fontSize: '0.9rem', color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', display: 'flex', alignItems: 'center', gap: 6 }}>
              <Star size={16} style={{ color: '#eab308' }} /> Reputación & Reseñas de Google Maps
            </h4>
            <div>
              <label style={{ display: 'block', marginBottom: 4, fontWeight: 500, fontSize: '0.875rem' }}>
                Enlace para Solicitar Opiniones en Google (Google Reviews URL)
              </label>
              <Input
                value={formData.google_review_url}
                onChange={(e: any) => setFormData({...formData, google_review_url: e.target.value})}
                placeholder="Ej. https://g.page/r/AbCdEfGhIjK/review"
              />
              <p style={{ margin: '6px 0 0', fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
                Los comensales que califiquen con 4 o 5 estrellas al confirmar su pedido serán invitados a compartir su reseña pública en este enlace.
              </p>
            </div>
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12, marginTop: 16 }}>
            <Button variant="secondary" onClick={() => setIsModalOpen(false)}>Cancelar</Button>
            <Button variant="primary" onClick={() => saveMutation.mutate(formData)} disabled={saveMutation.isPending}>
              {saveMutation.isPending ? 'Guardando...' : 'Guardar'}
            </Button>
          </div>
        </div>
      </Modal>
    </>
  );
};
export default BranchesList;
