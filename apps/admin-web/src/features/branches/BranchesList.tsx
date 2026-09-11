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
  Bike,
  AlertCircle,
  Tag,
  Percent,
} from 'lucide-react';

import '../../premium-catalogs.css';
import './BranchesList.css';

export interface DeliveryTier {
  id: string;
  name: string;
  fee_cents: number;
  is_default_web: boolean;
}

export interface BranchCoupon {
  code: string;
  discount_percentage: number;
  is_active: boolean;
}

const defaultBranchCoupons: BranchCoupon[] = [
  { code: 'MIMENU-GRACIAS10', discount_percentage: 10, is_active: true },
];

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
  delivery_fee_enabled?: boolean;
  delivery_tiers?: DeliveryTier[];
  free_delivery_min_cents?: number | null;
  coupons?: BranchCoupon[];
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

const defaultDeliveryTiers: DeliveryTier[] = [
  { id: 'tier-corta', name: 'Corta', fee_cents: 2000, is_default_web: false },
  { id: 'tier-media', name: 'Media', fee_cents: 3000, is_default_web: false },
  { id: 'tier-lejana', name: 'Lejana', fee_cents: 4000, is_default_web: false },
  { id: 'tier-gratis', name: 'Gratis', fee_cents: 0, is_default_web: true },
];

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
  delivery_fee_enabled: true,
  free_delivery_min_pesos: '',
  delivery_tiers: defaultDeliveryTiers,
  coupons: defaultBranchCoupons,
};

const BranchesList = () => {
  const queryClient = useQueryClient();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingBranch, setEditingBranch] = useState<Branch | null>(null);
  const [formData, setFormData] = useState(emptyForm);
  const [locatingGps, setLocatingGps] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState<string | null>(null);

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
    mutationFn: async (data: typeof formData) => {
      setSaveError(null);
      const payload: any = {
        ...data,
        latitude: typeof data.latitude === 'string'
          ? (data.latitude.trim() ? parseFloat(data.latitude) : null)
          : (data.latitude ?? null),
        longitude: typeof data.longitude === 'string'
          ? (data.longitude.trim() ? parseFloat(data.longitude) : null)
          : (data.longitude ?? null),
        free_delivery_min_cents: data.free_delivery_min_pesos && String(data.free_delivery_min_pesos).trim()
          ? Math.round(parseFloat(String(data.free_delivery_min_pesos)) * 100)
          : null,
        coupons: (data.coupons || [])
          .map((c) => ({
            code: String(c.code || '').trim().toUpperCase(),
            discount_percentage: Math.max(1, Math.min(100, Math.round(Number(c.discount_percentage) || 0))),
            is_active: Boolean(c.is_active),
          }))
          .filter((c) => c.code.length > 0),
      };
      delete payload.free_delivery_min_pesos;
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
      setSaveSuccess('¡Sucursal y costos de envío guardados correctamente!');
      setTimeout(() => {
        setIsModalOpen(false);
        setSaveSuccess(null);
      }, 700);
    },
    onError: (err: any) => {
      const code = err?.detail?.code || err?.code;
      const msg = err?.detail?.message || err?.message;
      if (code === 'public_name_reserved') {
        setSaveError('El código o nombre corto está reservado como enlace público. Elige otro código.');
      } else if (code === 'branch_already_exists') {
        setSaveError('Ya existe otra sucursal registrada con este código.');
      } else {
        setSaveError(msg || 'No fue posible guardar los cambios de la sucursal. Revisa los datos.');
      }
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => fetchApi(`/branches/${id}`, { method: 'DELETE' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['branches'] }),
  });

  const openModal = (branch?: Branch) => {
    setSaveError(null);
    setSaveSuccess(null);
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
        delivery_fee_enabled: branch.delivery_fee_enabled !== false,
        free_delivery_min_pesos: branch.free_delivery_min_cents != null && branch.free_delivery_min_cents > 0
          ? String(branch.free_delivery_min_cents / 100)
          : '',
        delivery_tiers: branch.delivery_tiers && branch.delivery_tiers.length > 0
          ? branch.delivery_tiers
          : defaultDeliveryTiers,
        coupons: branch.coupons && branch.coupons.length > 0
          ? branch.coupons
          : defaultBranchCoupons,
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

          {/* 5. Costos de Envío a Domicilio */}
          <section className="branch-form-section">
            <div className="branch-form-section-header">
              <h3 className="branch-form-section-title">
                <Bike size={18} color="#10b981" />
                Costos de Envío a Domicilio
              </h3>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: 10, margin: '10px 0' }}>
              <input
                type="checkbox"
                id="branch-delivery-enabled"
                checked={formData.delivery_fee_enabled}
                onChange={(e) => setFormData({ ...formData, delivery_fee_enabled: e.target.checked })}
                style={{ width: 18, height: 18, cursor: 'pointer', accentColor: '#10b981' }}
              />
              <label htmlFor="branch-delivery-enabled" style={{ fontSize: '0.88rem', fontWeight: 600, color: '#334155', cursor: 'pointer' }}>
                Habilitar cobro de envío a domicilio
              </label>
            </div>

            {formData.delivery_fee_enabled && (
              <>
                <div style={{ margin: '12px 0' }}>
                  <label className="branch-field-label">Envío GRATIS a partir de compras mayores a ($ MXN)</label>
                  <Input
                    type="number"
                    value={formData.free_delivery_min_pesos}
                    onChange={(e: any) => setFormData({ ...formData, free_delivery_min_pesos: e.target.value })}
                    placeholder="Ej. 300 (opcional)"
                  />
                  <span className="branch-input-helper">
                    Si el subtotal del cliente supera este monto, el sistema aplicará automáticamente $0 de envío.
                  </span>
                </div>

                <div style={{ marginTop: 14 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                    <label className="branch-field-label" style={{ margin: 0 }}>Tarifas por distancia / zona</label>
                    <button
                      type="button"
                      onClick={() => {
                        const newId = `tier-${Date.now()}`;
                        setFormData({
                          ...formData,
                          delivery_tiers: [
                            ...formData.delivery_tiers,
                            { id: newId, name: 'Nueva Zona', fee_cents: 2500, is_default_web: false },
                          ],
                        });
                      }}
                      style={{
                        padding: '4px 10px',
                        backgroundColor: '#ecfdf5',
                        border: '1px solid #a7f3d0',
                        borderRadius: 6,
                        color: '#047857',
                        fontSize: '0.78rem',
                        fontWeight: 700,
                        cursor: 'pointer',
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: 4,
                      }}
                    >
                      <Plus size={13} /> Agregar tarifa
                    </button>
                  </div>
                  <span className="branch-input-helper" style={{ marginBottom: 8, display: 'block' }}>
                    Marca con el radio cuál es la tarifa por defecto para el Menú Web Móvil (puedes marcar Gratis si no deseas cobrar envío en la app móvil).
                  </span>

                  <div style={{ display: 'grid', gap: 8 }}>
                    {formData.delivery_tiers.map((tier, idx) => (
                      <div
                        key={tier.id || idx}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 8,
                          padding: '8px 10px',
                          backgroundColor: tier.is_default_web ? '#f0fdf4' : '#f8fafc',
                          border: `1px solid ${tier.is_default_web ? '#86efac' : '#e2e8f0'}`,
                          borderRadius: 8,
                        }}
                      >
                        <label style={{ display: 'flex', alignItems: 'center', gap: 4, cursor: 'pointer', margin: 0 }}>
                          <input
                            type="radio"
                            name="default_web_tier_branch"
                            checked={tier.is_default_web}
                            onChange={() => {
                              setFormData({
                                ...formData,
                                delivery_tiers: formData.delivery_tiers.map((t, i) => ({
                                  ...t,
                                  is_default_web: i === idx,
                                })),
                              });
                            }}
                            title="Predeterminado Web"
                            style={{ width: 16, height: 16, cursor: 'pointer', accentColor: '#10b981' }}
                          />
                          <span style={{ fontSize: '0.72rem', fontWeight: 600, color: tier.is_default_web ? '#059669' : '#64748b', whiteSpace: 'nowrap' }}>
                            {tier.is_default_web ? 'Predeterminado Web' : 'Web'}
                          </span>
                        </label>
                        <input
                          type="text"
                          value={tier.name}
                          onChange={(e) => {
                            const updated = [...formData.delivery_tiers];
                            updated[idx] = { ...updated[idx], name: e.target.value };
                            setFormData({ ...formData, delivery_tiers: updated });
                          }}
                          placeholder="Nombre (ej. Corta, Gratis)"
                          style={{
                            flex: 1,
                            minWidth: 80,
                            padding: '6px 8px',
                            fontSize: '0.85rem',
                            borderRadius: 6,
                            border: '1px solid #cbd5e1',
                            outline: 'none',
                          }}
                        />
                        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                          <span style={{ fontSize: '0.85rem', color: '#64748b' }}>$</span>
                          <input
                            type="number"
                            min="0"
                            step="1"
                            value={tier.fee_cents / 100}
                            onChange={(e) => {
                              const updated = [...formData.delivery_tiers];
                              const val = parseFloat(e.target.value) || 0;
                              updated[idx] = { ...updated[idx], fee_cents: Math.max(0, Math.round(val * 100)) };
                              setFormData({ ...formData, delivery_tiers: updated });
                            }}
                            style={{
                              width: 65,
                              padding: '6px 8px',
                              fontSize: '0.85rem',
                              borderRadius: 6,
                              border: '1px solid #cbd5e1',
                              outline: 'none',
                            }}
                          />
                        </div>
                        {formData.delivery_tiers.length > 1 && (
                          <button
                            type="button"
                            onClick={() => {
                              const updated = formData.delivery_tiers.filter((_, i) => i !== idx);
                              if (tier.is_default_web && updated.length > 0) {
                                updated[0].is_default_web = true;
                              }
                              setFormData({ ...formData, delivery_tiers: updated });
                            }}
                            style={{
                              background: 'none',
                              border: 'none',
                              color: '#94a3b8',
                              cursor: 'pointer',
                              padding: 4,
                            }}
                            title="Eliminar tarifa"
                          >
                            <Trash2 size={16} />
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}
          </section>

          {/* 6. Cupones de Descuento */}
          <section className="branch-form-section">
            <div className="branch-form-section-header">
              <h3 className="branch-form-section-title">
                <Tag size={18} color="#10b981" />
                Cupones de Descuento
              </h3>
              <button
                type="button"
                onClick={() => {
                  setFormData({
                    ...formData,
                    coupons: [
                      ...formData.coupons,
                      { code: '', discount_percentage: 10, is_active: true },
                    ],
                  });
                }}
                style={{
                  padding: '4px 10px',
                  backgroundColor: '#ecfdf5',
                  border: '1px solid #a7f3d0',
                  borderRadius: 6,
                  color: '#047857',
                  fontSize: '0.78rem',
                  fontWeight: 700,
                  cursor: 'pointer',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 4,
                }}
              >
                <Plus size={13} /> Agregar cupón
              </button>
            </div>
            <span className="branch-input-helper" style={{ marginBottom: 12, display: 'block' }}>
              Configura los códigos promocionales y porcentaje de descuento que tus clientes pueden aplicar al ordenar desde el Menú Web Móvil.
            </span>

            {formData.coupons.length === 0 ? (
              <div style={{ padding: '16px', textAlign: 'center', backgroundColor: '#f8fafc', borderRadius: 8, border: '1px dashed #cbd5e1', color: '#64748b', fontSize: '0.85rem' }}>
                No hay cupones configurados para esta sucursal. Haz clic en "Agregar cupón" para crear uno.
              </div>
            ) : (
              <div style={{ display: 'grid', gap: 10 }}>
                {formData.coupons.map((coupon, idx) => (
                  <div
                    key={idx}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 10,
                      padding: '10px 12px',
                      backgroundColor: coupon.is_active ? '#ffffff' : '#f8fafc',
                      border: `1px solid ${coupon.is_active ? '#cbd5e1' : '#e2e8f0'}`,
                      borderRadius: 8,
                      opacity: coupon.is_active ? 1 : 0.7,
                    }}
                  >
                    <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', margin: 0 }} title="Activar/Desactivar cupón">
                      <input
                        type="checkbox"
                        checked={coupon.is_active}
                        onChange={(e) => {
                          const updated = [...formData.coupons];
                          updated[idx] = { ...updated[idx], is_active: e.target.checked };
                          setFormData({ ...formData, coupons: updated });
                        }}
                        style={{ width: 16, height: 16, cursor: 'pointer', accentColor: '#10b981' }}
                      />
                      <span style={{ fontSize: '0.75rem', fontWeight: 600, color: coupon.is_active ? '#059669' : '#94a3b8', whiteSpace: 'nowrap' }}>
                        {coupon.is_active ? 'Activo' : 'Inactivo'}
                      </span>
                    </label>

                    <div style={{ flex: 1, minWidth: 140 }}>
                      <input
                        type="text"
                        value={coupon.code}
                        onChange={(e) => {
                          const updated = [...formData.coupons];
                          updated[idx] = { ...updated[idx], code: e.target.value.toUpperCase() };
                          setFormData({ ...formData, coupons: updated });
                        }}
                        placeholder="CÓDIGO (ej. MIMENU-GRACIAS10)"
                        style={{
                          width: '100%',
                          boxSizing: 'border-box',
                          padding: '6px 10px',
                          fontSize: '0.85rem',
                          fontWeight: 700,
                          borderRadius: 6,
                          border: '1px solid #cbd5e1',
                          outline: 'none',
                          textTransform: 'uppercase',
                        }}
                      />
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                      <input
                        type="number"
                        min="1"
                        max="100"
                        step="1"
                        value={coupon.discount_percentage}
                        onChange={(e) => {
                          const updated = [...formData.coupons];
                          const val = parseInt(e.target.value, 10) || 0;
                          updated[idx] = { ...updated[idx], discount_percentage: Math.max(1, Math.min(100, val)) };
                          setFormData({ ...formData, coupons: updated });
                        }}
                        style={{
                          width: 55,
                          padding: '6px 8px',
                          fontSize: '0.85rem',
                          fontWeight: 600,
                          borderRadius: 6,
                          border: '1px solid #cbd5e1',
                          outline: 'none',
                          textAlign: 'center',
                        }}
                      />
                      <span style={{ fontSize: '0.85rem', fontWeight: 700, color: '#475569' }}>% OFF</span>
                    </div>

                    <button
                      type="button"
                      onClick={() => {
                        const updated = formData.coupons.filter((_, i) => i !== idx);
                        setFormData({ ...formData, coupons: updated });
                      }}
                      style={{
                        background: 'none',
                        border: 'none',
                        color: '#94a3b8',
                        cursor: 'pointer',
                        padding: 4,
                      }}
                      title="Eliminar cupón"
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* Alertas de Error y Éxito */}
          {saveError && (
            <div
              style={{
                margin: '12px 0 4px',
                padding: '10px 14px',
                borderRadius: 8,
                backgroundColor: '#fef2f2',
                border: '1px solid #fca5a5',
                color: '#b91c1c',
                fontSize: '0.85rem',
                fontWeight: 600,
                display: 'flex',
                alignItems: 'center',
                gap: 8,
              }}
            >
              <AlertCircle size={16} style={{ flexShrink: 0 }} />
              <span>{saveError}</span>
            </div>
          )}

          {saveSuccess && (
            <div
              style={{
                margin: '12px 0 4px',
                padding: '10px 14px',
                borderRadius: 8,
                backgroundColor: '#f0fdf4',
                border: '1px solid #86efac',
                color: '#15803d',
                fontSize: '0.85rem',
                fontWeight: 600,
                display: 'flex',
                alignItems: 'center',
                gap: 8,
              }}
            >
              <CheckCircle2 size={16} style={{ flexShrink: 0 }} />
              <span>{saveSuccess}</span>
            </div>
          )}

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
