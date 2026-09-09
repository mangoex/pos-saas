import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Button, Badge, Modal, Input } from '@restaurantos/ui';
import { fetchApi } from '@restaurantos/api-client';
import {
  Plus,
  Store,
  Edit,
  Trash2,
  MapPin,
  Navigation,
  Phone,
  Star,
  ExternalLink,
  Compass,
  Building2,
  CheckCircle2,
  MessageSquare,
} from 'lucide-react';

import '../../premium-catalogs.css';
import './BranchesList.css';

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
  whatsapp_ordering_enabled?: boolean;
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
  whatsapp_ordering_enabled: false,
};

const BranchesList = () => {
  const queryClient = useQueryClient();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingBranch, setEditingBranch] = useState<Branch | null>(null);
  const [formData, setFormData] = useState(emptyForm);
  const [locatingGps, setLocatingGps] = useState(false);

  const { data: branches, isLoading, error } = useQuery<Branch[]>({
    queryKey: ['branches'],
    queryFn: () => fetchApi('/branches'),
  });

  const { data: businessUnits = [] } = useQuery<BusinessUnit[]>({
    queryKey: ['business-units'],
    queryFn: () => fetchApi('/business-units'),
  });

  // Si hay más de 1 unidad de negocio y estamos creando, es relevante mostrarla
  const showBusinessUnitSelector = businessUnits.length > 1 && !editingBranch;
  // En la tabla, solo mostrar la columna si existen múltiples unidades
  const showBusinessUnitColumn = businessUnits.length > 1;

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
        whatsapp_ordering_enabled: Boolean(branch.whatsapp_ordering_enabled),
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

  const handleDetectGps = () => {
    if (!navigator.geolocation) {
      alert('Tu navegador no soporta geolocalización.');
      return;
    }
    setLocatingGps(true);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setLocatingGps(false);
        setFormData((prev) => ({
          ...prev,
          latitude: position.coords.latitude.toFixed(7),
          longitude: position.coords.longitude.toFixed(7),
        }));
      },
      (err) => {
        setLocatingGps(false);
        alert(`No se pudo obtener la ubicación GPS: ${err.message}`);
      },
      { enableHighAccuracy: true, timeout: 10000 }
    );
  };

  const formatBranchAddress = (b: Branch) => {
    const parts = [];
    if (b.street) {
      parts.push(`${b.street} ${b.exterior_number || ''}`.trim());
    }
    if (b.neighborhood) {
      parts.push(`Col. ${b.neighborhood}`);
    }
    if (b.city) {
      parts.push(b.city);
    }
    return parts.length > 0 ? parts.join(', ') : 'Sin domicilio registrado';
  };

  return (
    <div className="branches-page-container">
      {/* Encabezado Principal */}
      <header className="branches-header">
        <div className="branches-header-left">
          <div className="branches-eyebrow">
            <Store size={13} />
            <span>Puntos de Venta & Sucursales</span>
          </div>
          <h1 className="branches-title">Mi Restaurante y Sucursales</h1>
          <p className="branches-subtitle">
            Administra los datos operativos de tu restaurante, domicilio físico, coordenadas GPS y canales de pedido.
          </p>
        </div>

        <button className="branches-add-btn" onClick={() => openModal()}>
          <Plus size={18} />
          <span>Nueva Sucursal</span>
        </button>
      </header>

      {/* Tabla de Sucursales */}
      <div className="branches-card">
        {isLoading ? (
          <div style={{ padding: 48, textAlign: 'center', color: '#64748b' }}>Cargando sucursales...</div>
        ) : error ? (
          <div style={{ padding: 48, textAlign: 'center', color: '#dc2626' }}>Error al cargar sucursales.</div>
        ) : !branches || branches.length === 0 ? (
          <div className="premium-empty-state" style={{ padding: '60px 24px', textAlign: 'center' }}>
            <Store size={56} style={{ color: '#94a3b8', margin: '0 auto 16px', display: 'block' }} />
            <h3 style={{ margin: '0 0 8px', fontSize: '1.2rem', fontWeight: 700, color: '#0f172a' }}>No hay sucursales registradas</h3>
            <p style={{ color: '#64748b', margin: 0, fontSize: '0.9rem' }}>Agrega tu restaurante o primera sucursal para comenzar a operar.</p>
          </div>
        ) : (
          <div className="branches-table-wrap">
            <table className="branches-modern-table">
              <thead>
                <tr>
                  <th>Restaurante / Sucursal</th>
                  <th>Estatus</th>
                  <th>Código / Slug Móvil</th>
                  <th>Domicilio & Referencias</th>
                  <th>Ubicación GPS</th>
                  {showBusinessUnitColumn && <th>Unidad de negocio</th>}
                  <th style={{ textAlign: 'right' }}>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {branches.map((branch) => (
                  <tr key={branch.id}>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                        <div className="branches-store-icon">
                          <Store size={20} />
                        </div>
                        <div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <strong style={{ fontSize: '0.95rem', color: '#0f172a' }}>{branch.name}</strong>
                            {branch.google_review_url && (
                              <a
                                href={branch.google_review_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                title={`Google Reviews: ${branch.google_review_url}`}
                                style={{
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                  gap: 3,
                                  background: '#fef9c3',
                                  color: '#854d0e',
                                  padding: '2px 7px',
                                  borderRadius: 6,
                                  fontSize: '0.7rem',
                                  fontWeight: 750,
                                  textDecoration: 'none',
                                }}
                              >
                                <Star size={11} fill="#eab308" color="#eab308" /> Reseñas
                              </a>
                            )}
                          </div>
                          {branch.phone && (
                            <div style={{ fontSize: '0.78rem', color: '#64748b', display: 'flex', alignItems: 'center', gap: 8, marginTop: 4 }}>
                              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                                <Phone size={12} color="#94a3b8" /> {branch.phone}
                              </span>
                              {branch.whatsapp_ordering_enabled ? (
                                <span style={{ fontSize: '0.7rem', fontWeight: 750, color: '#059669', background: '#ecfdf5', border: '1px solid #d1fae5', padding: '1px 6px', borderRadius: 4 }}>
                                  WhatsApp ✓
                                </span>
                              ) : (
                                <span style={{ fontSize: '0.7rem', color: '#64748b', background: '#f1f5f9', padding: '1px 6px', borderRadius: 4 }}>
                                  Solo POS
                                </span>
                              )}
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
                    <td>
                      <span className="branches-slug-badge">
                        {branch.code}
                      </span>
                    </td>
                    <td>
                      <div style={{ fontSize: '0.86rem', maxWidth: 280 }}>
                        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 6 }}>
                          <MapPin size={15} style={{ color: '#10b981', flexShrink: 0, marginTop: 2 }} />
                          <span style={{ color: '#334155' }}>{formatBranchAddress(branch)}</span>
                        </div>
                        {branch.cross_streets && (
                          <div style={{ fontSize: '0.74rem', color: '#64748b', marginTop: 3, paddingLeft: 21 }}>
                            Entre: {branch.cross_streets}
                          </div>
                        )}
                      </div>
                    </td>
                    <td>
                      {branch.latitude && branch.longitude ? (
                        <div className="branches-gps-pill">
                          <Navigation size={12} />
                          <span>{Number(branch.latitude).toFixed(4)}, {Number(branch.longitude).toFixed(4)}</span>
                        </div>
                      ) : (
                        <span style={{ fontSize: '0.78rem', color: '#94a3b8' }}>Sin GPS</span>
                      )}
                    </td>
                    {showBusinessUnitColumn && <td>{branch.business_unit_name}</td>}
                    <td style={{ textAlign: 'right' }}>
                      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                        <button
                          className="branches-action-icon-btn edit"
                          onClick={() => openModal(branch)}
                          title="Editar sucursal"
                        >
                          <Edit size={16} />
                        </button>
                        <button
                          className="branches-action-icon-btn delete"
                          onClick={() => {
                            if (window.confirm(`¿Estás seguro de desactivar la sucursal "${branch.name}"?`)) {
                              deleteMutation.mutate(branch.id);
                            }
                          }}
                          title="Desactivar sucursal"
                        >
                          <Trash2 size={16} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Modal Modernizado de Sucursal */}
      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title={editingBranch ? `Restaurante: ${editingBranch.name}` : 'Nuevo Restaurante / Sucursal'}
      >
        <div className="branch-form-modal">
          {/* 1. Datos de Identidad y Contacto */}
          <section className="branch-form-section">
            <div className="branch-form-section-header">
              <h3 className="branch-form-section-title">
                <Store size={18} color="#10b981" />
                Datos del Restaurante
              </h3>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
              <div>
                <label className="branch-field-label">Nombre del restaurante o sucursal *</label>
                <Input
                  value={formData.name}
                  onChange={(e: any) => setFormData({ ...formData, name: e.target.value })}
                  placeholder="Ej. Tacos el Güero / Matriz Centro"
                />
              </div>
              <div>
                <label className="branch-field-label">Código / Slug móvil (ej. PILOTO) *</label>
                <Input
                  value={formData.code}
                  onChange={(e: any) => setFormData({ ...formData, code: e.target.value })}
                  placeholder="Ej. ELGUERO o PILOTO"
                />
                <span className="branch-input-helper">
                  Identificador para tu Menú Web Móvil y QR (<code>?slug={formData.code || 'CODIGO'}</code>)
                </span>
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: showBusinessUnitSelector ? '1fr 1fr' : '1fr', gap: 14 }}>
              {showBusinessUnitSelector && (
                <div>
                  <label htmlFor="business-unit" className="branch-field-label">Unidad de negocio</label>
                  <select
                    id="business-unit"
                    value={formData.business_unit_id}
                    onChange={(event) => setFormData({ ...formData, business_unit_id: event.target.value })}
                    style={{
                      width: '100%',
                      padding: 10,
                      borderRadius: 10,
                      border: '1px solid #cbd5e1',
                      backgroundColor: '#ffffff',
                      fontSize: '0.88rem',
                    }}
                  >
                    <option value="">Selecciona una unidad</option>
                    {businessUnits.map((unit) => (
                      <option key={unit.id} value={unit.id}>{unit.name} · {unit.legal_entity_name}</option>
                    ))}
                  </select>
                </div>
              )}

              <div>
                <label className="branch-field-label">Teléfono de contacto / WhatsApp</label>
                <Input
                  value={formData.phone}
                  onChange={(e: any) => setFormData({ ...formData, phone: e.target.value })}
                  placeholder="Ej. 6671234567 o 526671234567"
                />
                <span className="branch-input-helper">Número a 10 dígitos (o con código de país) para recibir pedidos.</span>
              </div>
            </div>

            {/* Tarjeta de Pedidos por WhatsApp */}
            <div
              className={`branch-whatsapp-card ${formData.whatsapp_ordering_enabled ? 'active' : ''}`}
              onClick={() => setFormData({ ...formData, whatsapp_ordering_enabled: !formData.whatsapp_ordering_enabled })}
            >
              <input
                type="checkbox"
                checked={Boolean(formData.whatsapp_ordering_enabled)}
                onChange={(e) => setFormData({ ...formData, whatsapp_ordering_enabled: e.target.checked })}
                onClick={(e) => e.stopPropagation()}
              />
              <div style={{ flex: 1 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <MessageSquare size={15} color={formData.whatsapp_ordering_enabled ? '#059669' : '#64748b'} />
                  <strong style={{ fontSize: '0.88rem', color: formData.whatsapp_ordering_enabled ? '#065f46' : '#1e293b' }}>
                    Recibir pedidos por WhatsApp en esta sucursal
                  </strong>
                </div>
                <p style={{ margin: '4px 0 0', fontSize: '0.78rem', color: '#64748b', lineHeight: 1.4 }}>
                  {formData.whatsapp_ordering_enabled
                    ? '✓ Activo: Los clientes en celular podrán enviar el pedido detallado por WhatsApp a tu teléfono de contacto además de guardarse en el sistema POS.'
                    : '✕ Desactivado: Los pedidos se registrarán únicamente en el sistema POS. NO se abrirá WhatsApp ni se mostrará el botón de envío.'}
                </p>
              </div>
            </div>
          </section>

          {/* 2. Domicilio Físico */}
          <section className="branch-form-section">
            <div className="branch-form-section-header">
              <h3 className="branch-form-section-title">
                <MapPin size={18} color="#10b981" />
                Domicilio Físico
              </h3>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr', gap: 14 }}>
              <div>
                <label className="branch-field-label">Calle</label>
                <Input
                  value={formData.street}
                  onChange={(e: any) => setFormData({ ...formData, street: e.target.value })}
                  placeholder="Ej. Av. Álvaro Obregón"
                />
              </div>
              <div>
                <label className="branch-field-label">No. Exterior</label>
                <Input
                  value={formData.exterior_number}
                  onChange={(e: any) => setFormData({ ...formData, exterior_number: e.target.value })}
                  placeholder="Ej. 450"
                />
              </div>
              <div>
                <label className="branch-field-label">No. Interior / Local</label>
                <Input
                  value={formData.interior_number}
                  onChange={(e: any) => setFormData({ ...formData, interior_number: e.target.value })}
                  placeholder="Ej. Local 3B"
                />
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 14 }}>
              <div>
                <label className="branch-field-label">Colonia</label>
                <Input
                  value={formData.neighborhood}
                  onChange={(e: any) => setFormData({ ...formData, neighborhood: e.target.value })}
                  placeholder="Ej. Centro"
                />
              </div>
              <div>
                <label className="branch-field-label">Código Postal</label>
                <Input
                  value={formData.postal_code}
                  onChange={(e: any) => setFormData({ ...formData, postal_code: e.target.value })}
                  placeholder="Ej. 80000"
                />
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
              <div>
                <label className="branch-field-label">Ciudad</label>
                <Input
                  value={formData.city}
                  onChange={(e: any) => setFormData({ ...formData, city: e.target.value })}
                  placeholder="Ej. Culiacán"
                />
              </div>
              <div>
                <label className="branch-field-label">Estado</label>
                <Input
                  value={formData.state}
                  onChange={(e: any) => setFormData({ ...formData, state: e.target.value })}
                  placeholder="Ej. Sinaloa"
                />
              </div>
            </div>

            <div>
              <label className="branch-field-label">Entre calles / Referencias de ubicación</label>
              <Input
                value={formData.cross_streets}
                onChange={(e: any) => setFormData({ ...formData, cross_streets: e.target.value })}
                placeholder="Ej. Entre Ruperto Paliza y Domingo Rubí, frente a catedral"
              />
            </div>
          </section>

          {/* 3. Geolocalización GPS */}
          <section className="branch-form-section">
            <div className="branch-form-section-header">
              <h3 className="branch-form-section-title">
                <Navigation size={18} color="#10b981" />
                Geolocalización GPS
              </h3>
              <button type="button" className="branch-gps-btn" onClick={handleDetectGps} disabled={locatingGps}>
                <Compass size={14} />
                <span>{locatingGps ? 'Detectando...' : 'Obtener mi ubicación actual'}</span>
              </button>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
              <div>
                <label className="branch-field-label">Latitud GPS (Lat)</label>
                <Input
                  value={formData.latitude}
                  onChange={(e: any) => setFormData({ ...formData, latitude: e.target.value })}
                  placeholder="Ej. 24.8083000"
                />
              </div>
              <div>
                <label className="branch-field-label">Longitud GPS (Lng)</label>
                <Input
                  value={formData.longitude}
                  onChange={(e: any) => setFormData({ ...formData, longitude: e.target.value })}
                  placeholder="Ej. -107.3941000"
                />
              </div>
            </div>
            <span className="branch-input-helper">
              Permite la asignación automática de repartidores y cálculo de distancias para servicio a domicilio.
            </span>
          </section>

          {/* 4. Reseñas y Reputación */}
          <section className="branch-form-section">
            <div className="branch-form-section-header">
              <h3 className="branch-form-section-title">
                <Star size={18} color="#eab308" fill="#eab308" />
                Reputación & Reseñas de Google Maps
              </h3>
            </div>

            <div>
              <label className="branch-field-label">
                Enlace para Solicitar Opiniones en Google (Google Reviews URL)
              </label>
              <Input
                value={formData.google_review_url}
                onChange={(e: any) => setFormData({ ...formData, google_review_url: e.target.value })}
                placeholder="Ej. https://g.page/r/AbCdEfGhIjK/review"
              />
              <p className="branch-input-helper" style={{ margin: '6px 0 0' }}>
                Los comensales que califiquen con 4 o 5 estrellas al confirmar su pedido serán invitados a compartir su reseña pública en este enlace.
              </p>
            </div>
          </section>

          {/* Footer de Acciones */}
          <div className="branch-modal-footer">
            <Button variant="secondary" onClick={() => setIsModalOpen(false)}>
              Cancelar
            </Button>
            <Button
              variant="primary"
              onClick={() => saveMutation.mutate(formData)}
              disabled={saveMutation.isPending || !formData.name.trim() || !formData.code.trim()}
            >
              {saveMutation.isPending ? 'Guardando...' : 'Guardar Cambios'}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default BranchesList;
