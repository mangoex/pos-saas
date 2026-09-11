import React, { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Button, Badge, Modal } from '@restaurantos/ui';
import { fetchApi, ApiError } from '@restaurantos/api-client';
import {
  Check,
  X,
  Clock,
  CheckCircle2,
  XCircle,
  Search,
  Image as ImageIcon,
  Sparkles,
  ExternalLink,
  MessageSquare,
  AlertCircle,
  ThumbsUp,
  RotateCcw,
} from 'lucide-react';
import '../../premium-catalogs.css';

interface CommunityPhotoItem {
  id: string;
  product_id: string;
  product_name: string;
  branch_id: string;
  branch_name?: string;
  customer_name: string;
  order_folio?: string;
  photo_url: string;
  caption?: string;
  status: 'pending' | 'approved' | 'rejected';
  created_at: string;
}

export const CommunityPhotosModeration: React.FC = () => {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<'pending' | 'approved' | 'rejected' | 'all'>('pending');
  const [searchQuery, setSearchQuery] = useState('');
  const [previewPhoto, setPreviewPhoto] = useState<CommunityPhotoItem | null>(null);
  const [actionSuccessMessage, setActionSuccessMessage] = useState<string | null>(null);
  const [actionErrorMessage, setActionErrorMessage] = useState<string | null>(null);

  // Fetch photos
  const { data: photos = [], isLoading, refetch } = useQuery<CommunityPhotoItem[]>({
    queryKey: ['admin-community-photos'],
    queryFn: async () => {
      const res = await fetchApi<CommunityPhotoItem[]>('/admin/community-photos?limit=100');
      return Array.isArray(res) ? res : [];
    },
    staleTime: 1000 * 30, // 30s
  });

  // Moderate status mutation
  const moderateMutation = useMutation({
    mutationFn: async ({ photoId, status }: { photoId: string; status: 'approved' | 'rejected' | 'pending' }) => {
      return fetchApi(`/admin/community-photos/${photoId}/status`, {
        method: 'PATCH',
        body: JSON.stringify({ status }),
      });
    },
    onSuccess: (_, { status }) => {
      queryClient.invalidateQueries({ queryKey: ['admin-community-photos'] });
      setActionErrorMessage(null);
      const msg = status === 'approved'
        ? '✅ Foto aprobada. Ya es visible para los clientes en el menú digital.'
        : status === 'rejected'
        ? '🚫 Foto rechazada y ocultada del menú.'
        : 'Foto reestablecida a estado pendiente.';
      setActionSuccessMessage(msg);
      setTimeout(() => setActionSuccessMessage(null), 4000);
    },
    onError: (err) => {
      setActionSuccessMessage(null);
      setActionErrorMessage(err instanceof ApiError ? err.message : 'Error al actualizar el estado de la foto.');
      setTimeout(() => setActionErrorMessage(null), 5000);
    },
  });

  // Counts by status
  const counts = useMemo(() => {
    let pending = 0;
    let approved = 0;
    let rejected = 0;
    for (const p of photos) {
      if (p.status === 'pending') pending++;
      else if (p.status === 'approved') approved++;
      else if (p.status === 'rejected') rejected++;
    }
    return { pending, approved, rejected, all: photos.length };
  }, [photos]);

  // Filtered list
  const filteredPhotos = useMemo(() => {
    return photos.filter((item) => {
      if (activeTab !== 'all' && item.status !== activeTab) {
        return false;
      }
      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase();
        const matchesDish = item.product_name?.toLowerCase().includes(query);
        const matchesCustomer = item.customer_name?.toLowerCase().includes(query);
        const matchesFolio = item.order_folio?.toLowerCase().includes(query);
        const matchesCaption = item.caption?.toLowerCase().includes(query);
        if (!matchesDish && !matchesCustomer && !matchesFolio && !matchesCaption) {
          return false;
        }
      }
      return true;
    });
  }, [photos, activeTab, searchQuery]);

  const formatDate = (dateString: string) => {
    try {
      const d = new Date(dateString);
      return d.toLocaleDateString('es-MX', {
        day: '2-digit',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return dateString;
    }
  };

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto', padding: '24px 20px 80px' }}>
      {/* Header Banner */}
      <div
        style={{
          background: 'linear-gradient(135deg, #1e293b 0%, #0f172a 100%)',
          borderRadius: 20,
          padding: '28px 24px',
          color: '#fff',
          marginBottom: 24,
          boxShadow: '0 10px 25px -5px rgba(15, 23, 42, 0.2)',
          position: 'relative',
          overflow: 'hidden',
        }}
      >
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6, background: 'rgba(245, 158, 11, 0.2)', border: '1px solid rgba(245, 158, 11, 0.4)', padding: '4px 12px', borderRadius: 9999, fontSize: 12, fontWeight: 700, color: '#f59e0b', marginBottom: 12 }}>
          <Sparkles size={14} />
          <span>Fidelización & Social Proof (UGC)</span>
        </div>
        <h1 style={{ fontSize: 26, fontWeight: 800, margin: '0 0 8px', letterSpacing: '-0.02em' }}>
          📸 Moderación de Fotos de la Comunidad
        </h1>
        <p style={{ fontSize: 14, color: '#94a3b8', margin: 0, maxWidth: 700, lineHeight: 1.5 }}>
          Fotos auténticas subidas por comensales con órdenes verificadas a cambio de un cupón de agradecimiento.
          <strong> Moderación preventiva:</strong> Ninguna foto se muestra públicamente en el menú digital hasta que la apruebes aquí.
        </p>
      </div>

      {/* Action Notification Alert */}
      {actionSuccessMessage && (
        <div style={{ padding: '12px 18px', background: '#ecfdf5', border: '1px solid #6ee7b7', color: '#065f46', borderRadius: 12, marginBottom: 16, fontWeight: 600, fontSize: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
          <CheckCircle2 size={18} color="#059669" />
          <span>{actionSuccessMessage}</span>
        </div>
      )}
      {actionErrorMessage && (
        <div style={{ padding: '12px 18px', background: '#fef2f2', border: '1px solid #fca5a5', color: '#991b1b', borderRadius: 12, marginBottom: 16, fontWeight: 600, fontSize: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
          <AlertCircle size={18} color="#dc2626" />
          <span>{actionErrorMessage}</span>
        </div>
      )}

      {/* Control Bar: Tabs & Search */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        {/* Status Tabs */}
        <div style={{ display: 'flex', gap: 8, background: '#f1f5f9', padding: 4, borderRadius: 12 }}>
          <button
            type="button"
            onClick={() => setActiveTab('pending')}
            style={{
              padding: '8px 16px',
              borderRadius: 8,
              border: 'none',
              background: activeTab === 'pending' ? '#fff' : 'transparent',
              color: activeTab === 'pending' ? '#0f172a' : '#64748b',
              fontWeight: 700,
              fontSize: 13,
              cursor: 'pointer',
              boxShadow: activeTab === 'pending' ? '0 2px 4px rgba(0,0,0,0.06)' : 'none',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}
          >
            <Clock size={14} color="#d97706" />
            <span>Pendientes</span>
            {counts.pending > 0 && (
              <span style={{ background: '#f59e0b', color: '#fff', fontSize: 11, padding: '1px 6px', borderRadius: 9999 }}>
                {counts.pending}
              </span>
            )}
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('approved')}
            style={{
              padding: '8px 16px',
              borderRadius: 8,
              border: 'none',
              background: activeTab === 'approved' ? '#fff' : 'transparent',
              color: activeTab === 'approved' ? '#0f172a' : '#64748b',
              fontWeight: 700,
              fontSize: 13,
              cursor: 'pointer',
              boxShadow: activeTab === 'approved' ? '0 2px 4px rgba(0,0,0,0.06)' : 'none',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}
          >
            <CheckCircle2 size={14} color="#16a34a" />
            <span>Aprobadas ({counts.approved})</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('rejected')}
            style={{
              padding: '8px 16px',
              borderRadius: 8,
              border: 'none',
              background: activeTab === 'rejected' ? '#fff' : 'transparent',
              color: activeTab === 'rejected' ? '#0f172a' : '#64748b',
              fontWeight: 700,
              fontSize: 13,
              cursor: 'pointer',
              boxShadow: activeTab === 'rejected' ? '0 2px 4px rgba(0,0,0,0.06)' : 'none',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}
          >
            <XCircle size={14} color="#dc2626" />
            <span>Rechazadas ({counts.rejected})</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('all')}
            style={{
              padding: '8px 16px',
              borderRadius: 8,
              border: 'none',
              background: activeTab === 'all' ? '#fff' : 'transparent',
              color: activeTab === 'all' ? '#0f172a' : '#64748b',
              fontWeight: 700,
              fontSize: 13,
              cursor: 'pointer',
              boxShadow: activeTab === 'all' ? '0 2px 4px rgba(0,0,0,0.06)' : 'none',
            }}
          >
            Todas ({counts.all})
          </button>
        </div>

        {/* Search input */}
        <div style={{ position: 'relative', width: 280 }}>
          <Search size={16} color="#94a3b8" style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)' }} />
          <input
            type="text"
            placeholder="Buscar por platillo, cliente o folio..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{
              width: '100%',
              padding: '9px 12px 9px 36px',
              borderRadius: 10,
              border: '1px solid #cbd5e1',
              fontSize: 13,
              outline: 'none',
              boxSizing: 'border-box',
            }}
          />
        </div>
      </div>

      {/* Main Content Grid */}
      {isLoading ? (
        <div style={{ textAlign: 'center', padding: '60px 20px', color: '#64748b' }}>
          <div className="loading-spinner" style={{ margin: '0 auto 12px' }} />
          <p style={{ fontWeight: 600 }}>Cargando fotos de la comunidad…</p>
        </div>
      ) : filteredPhotos.length === 0 ? (
        <div
          style={{
            textAlign: 'center',
            padding: '60px 20px',
            background: '#fff',
            borderRadius: 16,
            border: '1px dashed #cbd5e1',
            color: '#64748b',
          }}
        >
          <ImageIcon size={48} color="#cbd5e1" style={{ margin: '0 auto 12px' }} />
          <h3 style={{ fontSize: 16, fontWeight: 700, color: '#334155', margin: '0 0 6px' }}>
            {activeTab === 'pending'
              ? '¡Todo limpio! No hay fotos pendientes de moderación'
              : 'No se encontraron fotos con los filtros actuales'}
          </h3>
          <p style={{ fontSize: 13, color: '#94a3b8', margin: 0 }}>
            {activeTab === 'pending'
              ? 'Cuando los clientes suban fotos desde el ticket o confirmación de pedido, aparecerán aquí para tu aprobación.'
              : 'Prueba cambiando de pestaña o limpiando el término de búsqueda.'}
          </p>
        </div>
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
            gap: 20,
          }}
        >
          {filteredPhotos.map((photo) => {
            const isPending = photo.status === 'pending';
            const isApproved = photo.status === 'approved';
            const isRejected = photo.status === 'rejected';

            return (
              <div
                key={photo.id}
                style={{
                  background: '#fff',
                  borderRadius: 16,
                  border: isPending ? '2px solid #f59e0b' : '1px solid #e2e8f0',
                  boxShadow: isPending ? '0 4px 16px rgba(245, 158, 11, 0.12)' : '0 2px 8px rgba(0,0,0,0.04)',
                  overflow: 'hidden',
                  display: 'flex',
                  flexDirection: 'column',
                  transition: 'transform 0.15s ease',
                }}
              >
                {/* Photo Image preview */}
                <div
                  style={{
                    height: 200,
                    width: '100%',
                    position: 'relative',
                    cursor: 'pointer',
                    background: '#f8fafc',
                  }}
                  onClick={() => setPreviewPhoto(photo)}
                >
                  <img
                    src={photo.photo_url}
                    alt={photo.product_name}
                    style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                  />
                  {/* Status badge pill */}
                  <div
                    style={{
                      position: 'absolute',
                      top: 10,
                      right: 10,
                      padding: '4px 10px',
                      borderRadius: 9999,
                      fontSize: 11,
                      fontWeight: 700,
                      color: '#fff',
                      background: isApproved ? '#16a34a' : isRejected ? '#dc2626' : '#d97706',
                      boxShadow: '0 2px 6px rgba(0,0,0,0.2)',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 4,
                    }}
                  >
                    {isApproved && <CheckCircle2 size={12} />}
                    {isRejected && <XCircle size={12} />}
                    {isPending && <Clock size={12} />}
                    <span>{isApproved ? 'Aprobada' : isRejected ? 'Rechazada' : 'Por Revisar'}</span>
                  </div>

                  {/* Branch tag if available */}
                  {photo.branch_name && (
                    <div
                      style={{
                        position: 'absolute',
                        bottom: 8,
                        left: 8,
                        background: 'rgba(15, 23, 42, 0.75)',
                        backdropFilter: 'blur(4px)',
                        color: '#fff',
                        padding: '2px 8px',
                        borderRadius: 6,
                        fontSize: 11,
                        fontWeight: 600,
                      }}
                    >
                      {photo.branch_name}
                    </div>
                  )}
                </div>

                {/* Card Body */}
                <div style={{ padding: 16, display: 'flex', flexDirection: 'column', flex: 1 }}>
                  <div style={{ marginBottom: 8 }}>
                    <span style={{ fontSize: 11, fontWeight: 700, color: '#f59e0b', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                      Platillo
                    </span>
                    <h3 style={{ fontSize: 16, fontWeight: 700, margin: '2px 0 0', color: '#0f172a' }}>
                      {photo.product_name}
                    </h3>
                  </div>

                  {/* Customer and Order meta */}
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10, fontSize: 12, color: '#64748b' }}>
                    <span style={{ fontWeight: 600, color: '#334155' }}>
                      👤 {photo.customer_name || 'Comensal mimenu'}
                    </span>
                    {photo.order_folio && (
                      <span style={{ background: '#f1f5f9', padding: '2px 6px', borderRadius: 4, fontWeight: 600 }}>
                        Orden #{photo.order_folio}
                      </span>
                    )}
                  </div>

                  {/* Caption quote if present */}
                  {photo.caption && (
                    <div
                      style={{
                        background: '#f8fafc',
                        borderLeft: '3px solid #cbd5e1',
                        padding: '6px 10px',
                        borderRadius: '0 8px 8px 0',
                        fontSize: 12,
                        color: '#475569',
                        fontStyle: 'italic',
                        marginBottom: 12,
                        lineHeight: 1.4,
                      }}
                    >
                      "{photo.caption}"
                    </div>
                  )}

                  <div style={{ marginTop: 'auto', paddingTop: 8, borderTop: '1px solid #f1f5f9', display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: 11, color: '#94a3b8' }}>
                    <span>{formatDate(photo.created_at)}</span>
                  </div>

                  {/* Actions buttons */}
                  <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                    {!isApproved && (
                      <button
                        type="button"
                        onClick={() => moderateMutation.mutate({ photoId: photo.id, status: 'approved' })}
                        disabled={moderateMutation.isPending}
                        style={{
                          flex: 1,
                          padding: '8px 12px',
                          background: '#16a34a',
                          color: '#fff',
                          border: 'none',
                          borderRadius: 8,
                          fontSize: 12,
                          fontWeight: 700,
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          gap: 6,
                          boxShadow: '0 2px 4px rgba(22, 163, 74, 0.2)',
                        }}
                      >
                        <Check size={14} />
                        <span>Aprobar</span>
                      </button>
                    )}

                    {!isRejected && (
                      <button
                        type="button"
                        onClick={() => moderateMutation.mutate({ photoId: photo.id, status: 'rejected' })}
                        disabled={moderateMutation.isPending}
                        style={{
                          flex: 1,
                          padding: '8px 12px',
                          background: '#fff',
                          color: '#dc2626',
                          border: '1px solid #fca5a5',
                          borderRadius: 8,
                          fontSize: 12,
                          fontWeight: 700,
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          gap: 6,
                        }}
                      >
                        <X size={14} />
                        <span>Rechazar</span>
                      </button>
                    )}

                    {(isApproved || isRejected) && (
                      <button
                        type="button"
                        title="Reestablecer a pendiente"
                        onClick={() => moderateMutation.mutate({ photoId: photo.id, status: 'pending' })}
                        disabled={moderateMutation.isPending}
                        style={{
                          padding: '8px',
                          background: '#f1f5f9',
                          color: '#64748b',
                          border: 'none',
                          borderRadius: 8,
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                        }}
                      >
                        <RotateCcw size={14} />
                      </button>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Full Photo Modal Preview */}
      {previewPhoto && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(15, 23, 42, 0.85)',
            backdropFilter: 'blur(6px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 9999,
            padding: 20,
          }}
          onClick={() => setPreviewPhoto(null)}
        >
          <div
            style={{
              background: '#fff',
              borderRadius: 20,
              maxWidth: 580,
              width: '100%',
              overflow: 'hidden',
              boxShadow: '0 25px 50px -12px rgba(0,0,0,0.5)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ position: 'relative', maxHeight: '60vh', background: '#000', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <img
                src={previewPhoto.photo_url}
                alt={previewPhoto.product_name}
                style={{ maxWidth: '100%', maxHeight: '60vh', objectFit: 'contain' }}
              />
              <button
                type="button"
                onClick={() => setPreviewPhoto(null)}
                style={{
                  position: 'absolute',
                  top: 12,
                  right: 12,
                  background: 'rgba(0,0,0,0.6)',
                  border: 'none',
                  color: '#fff',
                  width: 32,
                  height: 32,
                  borderRadius: 9999,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <X size={18} />
              </button>
            </div>
            <div style={{ padding: 20 }}>
              <h2 style={{ fontSize: 18, fontWeight: 800, margin: '0 0 6px', color: '#0f172a' }}>
                {previewPhoto.product_name}
              </h2>
              <div style={{ display: 'flex', gap: 12, fontSize: 13, color: '#64748b', marginBottom: 12 }}>
                <span>Subida por: <strong>{previewPhoto.customer_name}</strong></span>
                {previewPhoto.order_folio && <span>Folio #{previewPhoto.order_folio}</span>}
              </div>
              {previewPhoto.caption && (
                <p style={{ background: '#f8fafc', padding: '10px 14px', borderRadius: 8, fontStyle: 'italic', margin: '0 0 16px', color: '#334155', fontSize: 13 }}>
                  "{previewPhoto.caption}"
                </p>
              )}
              <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
                {previewPhoto.status !== 'approved' && (
                  <Button
                    variant="primary"
                    onClick={() => {
                      moderateMutation.mutate({ photoId: previewPhoto.id, status: 'approved' });
                      setPreviewPhoto(null);
                    }}
                  >
                    Aprobar para el Menú
                  </Button>
                )}
                {previewPhoto.status !== 'rejected' && (
                  <Button
                    variant="danger"
                    onClick={() => {
                      moderateMutation.mutate({ photoId: previewPhoto.id, status: 'rejected' });
                      setPreviewPhoto(null);
                    }}
                  >
                    Rechazar Foto
                  </Button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default CommunityPhotosModeration;
