import React, { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchApi, ApiError } from '@restaurantos/api-client';
import {
  Store,
  Share2,
  Copy,
  ExternalLink,
  MessageSquare,
  Star,
  Monitor,
  CheckCircle2,
  AlertCircle,
  Phone,
  Power,
} from 'lucide-react';

interface MobileBranchSettingsTabProps {
  branchId: string;
  branchName?: string;
  onSwitchToDesktop?: () => void;
}

interface Branch {
  id: string;
  name: string;
  code: string;
  status: string;
  phone?: string;
  google_review_url?: string;
  whatsapp_ordering_enabled?: boolean;
}

interface LinksResponse {
  name: string;
  canonical_slug: string;
  canonical_menu_url: string;
  links: {
    menu: string;
    admin: string;
    pos: string;
    kds: string;
  };
}

export const MobileBranchSettingsTab: React.FC<MobileBranchSettingsTabProps> = ({
  branchId,
  branchName: _branchName,
  onSwitchToDesktop,
}) => {
  const queryClient = useQueryClient();
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3500);
  };

  // Queries
  const { data: branches = [], isLoading: branchesLoading } = useQuery<Branch[]>({
    queryKey: ['branches'],
    queryFn: () => fetchApi('/branches'),
  });

  const currentBranch = branches.find((b) => b.id === branchId) || branches[0];

  const { data: linksData } = useQuery<LinksResponse>({
    queryKey: ['saas-links'],
    queryFn: () => fetchApi('/saas/links'),
  });

  // Local form states
  const [branchPhone, setBranchPhone] = useState('');
  const [whatsappEnabled, setWhatsappEnabled] = useState(false);
  const [googleReviewUrl, setGoogleReviewUrl] = useState('');
  const [isOpenForOrders, setIsOpenForOrders] = useState(true);

  useEffect(() => {
    if (currentBranch) {
      setBranchPhone(currentBranch.phone || '');
      setWhatsappEnabled(Boolean(currentBranch.whatsapp_ordering_enabled));
      setGoogleReviewUrl(currentBranch.google_review_url || '');
      setIsOpenForOrders(currentBranch.status !== 'inactive');
    }
  }, [currentBranch]);

  // Update Branch Mutation
  const updateBranchMutation = useMutation({
    mutationFn: async (payload: Partial<Branch>) => {
      if (!currentBranch) return;
      return fetchApi(`/branches/${currentBranch.id}`, {
        method: 'PUT',
        body: JSON.stringify(payload),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['branches'] });
      showToast('Configuración guardada correctamente');
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.message : 'Error al guardar la sucursal');
    },
  });

  const handleSaveSettings = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    updateBranchMutation.mutate({
      name: currentBranch?.name,
      phone: branchPhone.trim(),
      whatsapp_ordering_enabled: whatsappEnabled,
      google_review_url: googleReviewUrl.trim(),
      status: isOpenForOrders ? 'active' : 'inactive',
    });
  };

  const copyToClipboard = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      showToast('¡Enlace copiado al portapapeles!');
    } catch {
      showToast('No se pudo copiar automáticamente.');
    }
  };

  const menuUrl = linksData?.links?.menu || linksData?.canonical_menu_url || window.location.origin;

  const shareViaWhatsApp = () => {
    const text = encodeURIComponent(
      `¡Hola! Te comparto el menú digital de ${currentBranch?.name || 'nuestro restaurante'} para hacer tus pedidos: ${menuUrl}`
    );
    window.open(`https://wa.me/?text=${text}`, '_blank');
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
              backgroundColor: '#8b5cf6',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Store size={20} color="#ffffff" />
          </div>
          <div>
            <div style={{ fontSize: '1rem', fontWeight: 800, lineHeight: 1.1 }}>
              Sucursal y Enlaces
            </div>
            <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
              {currentBranch?.name || 'Mi Sucursal'}
            </div>
          </div>
        </div>
      </header>

      <main style={{ padding: '16px 14px', maxWidth: 640, margin: '0 auto' }}>
        {/* Toast */}
        {toastMessage && (
          <div
            style={{
              backgroundColor: '#dcfce7',
              border: '1px solid #bbf7d0',
              borderRadius: 12,
              padding: '10px 14px',
              color: '#15803d',
              fontSize: '0.875rem',
              fontWeight: 600,
              marginBottom: 14,
              display: 'flex',
              alignItems: 'center',
              gap: 8,
            }}
          >
            <CheckCircle2 size={18} />
            <span>{toastMessage}</span>
          </div>
        )}

        {error && (
          <div
            style={{
              backgroundColor: '#fee2e2',
              border: '1px solid #fecaca',
              borderRadius: 12,
              padding: '10px 14px',
              color: '#b91c1c',
              fontSize: '0.875rem',
              fontWeight: 600,
              marginBottom: 14,
              display: 'flex',
              alignItems: 'center',
              gap: 8,
            }}
          >
            <AlertCircle size={18} />
            <span>{error}</span>
          </div>
        )}

        {branchesLoading ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#64748b' }}>Cargando sucursal...</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {/* Card: Menú Digital Compartible */}
            <div
              style={{
                backgroundColor: '#ffffff',
                borderRadius: 16,
                padding: 16,
                border: '1px solid #e2e8f0',
                boxShadow: '0 2px 4px rgba(0,0,0,0.03)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <Share2 size={20} color="#2563eb" />
                <h3 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 800, color: '#0f172a' }}>
                  Tu Menú Digital para Clientes
                </h3>
              </div>
              <p style={{ margin: '0 0 12px', fontSize: '0.825rem', color: '#64748b' }}>
                Comparte esta liga en tus redes sociales o imprímela en tus mesas para que los clientes pidan desde su celular.
              </p>

              <div
                style={{
                  backgroundColor: '#f8fafc',
                  border: '1px solid #cbd5e1',
                  borderRadius: 10,
                  padding: '10px 12px',
                  marginBottom: 12,
                  wordBreak: 'break-all',
                  fontSize: '0.85rem',
                  fontWeight: 600,
                  color: '#1d4ed8',
                }}
              >
                {menuUrl}
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                <button
                  type="button"
                  onClick={() => void copyToClipboard(menuUrl)}
                  style={{
                    padding: '10px',
                    backgroundColor: '#eff6ff',
                    border: '1px solid #bfdbfe',
                    borderRadius: 10,
                    color: '#1d4ed8',
                    fontWeight: 700,
                    fontSize: '0.85rem',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: 6,
                    cursor: 'pointer',
                  }}
                >
                  <Copy size={16} /> Copiar Enlace
                </button>

                <button
                  type="button"
                  onClick={shareViaWhatsApp}
                  style={{
                    padding: '10px',
                    backgroundColor: '#dcfce7',
                    border: '1px solid #bbf7d0',
                    borderRadius: 10,
                    color: '#15803d',
                    fontWeight: 700,
                    fontSize: '0.85rem',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: 6,
                    cursor: 'pointer',
                  }}
                >
                  <MessageSquare size={16} /> WhatsApp
                </button>
              </div>

              <div style={{ marginTop: 8 }}>
                <a
                  href={menuUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: 6,
                    padding: '8px',
                    color: '#64748b',
                    fontSize: '0.8rem',
                    fontWeight: 600,
                    textDecoration: 'none',
                  }}
                >
                  <ExternalLink size={14} /> Abrir menú en una pestaña nueva
                </a>
              </div>
            </div>

            {/* Form Settings */}
            <form onSubmit={handleSaveSettings}>
              {/* Card: Operating State & WhatsApp */}
              <div
                style={{
                  backgroundColor: '#ffffff',
                  borderRadius: 16,
                  padding: 16,
                  border: '1px solid #e2e8f0',
                  boxShadow: '0 2px 4px rgba(0,0,0,0.03)',
                  marginBottom: 14,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                  <Power size={20} color="#16a34a" />
                  <h3 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 800, color: '#0f172a' }}>
                    Estado Operativo
                  </h3>
                </div>

                {/* Open/Close Toggle */}
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '12px 0',
                    borderBottom: '1px solid #f1f5f9',
                  }}
                >
                  <div>
                    <div style={{ fontSize: '0.9rem', fontWeight: 700, color: '#0f172a' }}>
                      Recepción de Pedidos
                    </div>
                    <div style={{ fontSize: '0.775rem', color: '#64748b' }}>
                      {isOpenForOrders ? 'Sucursal abierta para vender' : 'Sucursal pausada (Cerrada)'}
                    </div>
                  </div>
                  <input
                    type="checkbox"
                    checked={isOpenForOrders}
                    onChange={(e) => setIsOpenForOrders(e.target.checked)}
                    style={{ width: 22, height: 22, cursor: 'pointer', accentColor: '#16a34a' }}
                  />
                </div>

                {/* WhatsApp Ordering Toggle */}
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '12px 0',
                    borderBottom: '1px solid #f1f5f9',
                  }}
                >
                  <div>
                    <div style={{ fontSize: '0.9rem', fontWeight: 700, color: '#0f172a' }}>
                      Pedidos por WhatsApp
                    </div>
                    <div style={{ fontSize: '0.775rem', color: '#64748b' }}>
                      Enviar pedidos de clientes directo a tu WhatsApp
                    </div>
                  </div>
                  <input
                    type="checkbox"
                    checked={whatsappEnabled}
                    onChange={(e) => setWhatsappEnabled(e.target.checked)}
                    style={{ width: 22, height: 22, cursor: 'pointer', accentColor: '#2563eb' }}
                  />
                </div>

                {/* Phone number */}
                <div style={{ paddingTop: 12 }}>
                  <label
                    style={{
                      display: 'block',
                      fontSize: '0.85rem',
                      fontWeight: 700,
                      color: '#334155',
                      marginBottom: 4,
                    }}
                  >
                    Teléfono de la sucursal
                  </label>
                  <div style={{ position: 'relative' }}>
                    <Phone
                      size={16}
                      style={{
                        position: 'absolute',
                        left: 12,
                        top: '50%',
                        transform: 'translateY(-50%)',
                        color: '#94a3b8',
                      }}
                    />
                    <input
                      type="tel"
                      placeholder="6671234567"
                      value={branchPhone}
                      onChange={(e) => setBranchPhone(e.target.value)}
                      style={{
                        width: '100%',
                        boxSizing: 'border-box',
                        padding: '10px 12px 10px 36px',
                        fontSize: '0.95rem',
                        borderRadius: 10,
                        border: '1px solid #cbd5e1',
                        outline: 'none',
                      }}
                    />
                  </div>
                </div>
              </div>

              {/* Card: Google Reviews */}
              <div
                style={{
                  backgroundColor: '#ffffff',
                  borderRadius: 16,
                  padding: 16,
                  border: '1px solid #e2e8f0',
                  boxShadow: '0 2px 4px rgba(0,0,0,0.03)',
                  marginBottom: 18,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                  <Star size={20} color="#f59e0b" />
                  <h3 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 800, color: '#0f172a' }}>
                    Reseñas de Google Maps
                  </h3>
                </div>
                <p style={{ margin: '0 0 10px', fontSize: '0.8rem', color: '#64748b' }}>
                  Los clientes que califiquen con 4 o 5 estrellas serán invitados a dejar su opinión en Google.
                </p>

                <input
                  type="url"
                  placeholder="https://g.page/r/tu-negocio/review"
                  value={googleReviewUrl}
                  onChange={(e) => setGoogleReviewUrl(e.target.value)}
                  style={{
                    width: '100%',
                    boxSizing: 'border-box',
                    padding: '10px 12px',
                    fontSize: '0.9rem',
                    borderRadius: 10,
                    border: '1px solid #cbd5e1',
                    outline: 'none',
                  }}
                />
              </div>

              <button
                type="submit"
                disabled={updateBranchMutation.isPending}
                style={{
                  width: '100%',
                  padding: '14px',
                  backgroundColor: '#0f172a',
                  color: '#ffffff',
                  border: 'none',
                  borderRadius: 12,
                  fontSize: '1rem',
                  fontWeight: 800,
                  cursor: 'pointer',
                  marginBottom: 16,
                  boxShadow: '0 4px 6px -1px rgba(15, 23, 42, 0.2)',
                }}
              >
                {updateBranchMutation.isPending ? 'Guardando...' : 'Guardar Configuración'}
              </button>
            </form>

            {/* Switch to desktop mode */}
            <div
              style={{
                backgroundColor: '#ffffff',
                borderRadius: 14,
                padding: 16,
                border: '1px solid #e2e8f0',
                textAlign: 'center',
              }}
            >
              <Monitor size={24} color="#64748b" style={{ margin: '0 auto 6px' }} />
              <div style={{ fontSize: '0.9rem', fontWeight: 700, color: '#0f172a', marginBottom: 2 }}>
                ¿Necesitas funciones avanzadas?
              </div>
              <p style={{ fontSize: '0.775rem', color: '#64748b', margin: '0 0 12px' }}>
                Facturación electrónica CFDI 4.0, compras por XML, auditoría y reportes detallados en versión PC.
              </p>
              <button
                type="button"
                onClick={() => {
                  try {
                    localStorage.setItem('restaurantos_force_desktop', 'true');
                  } catch {
                    // ignore
                  }
                  if (onSwitchToDesktop) {
                    onSwitchToDesktop();
                  } else {
                    window.location.reload();
                  }
                }}
                style={{
                  padding: '10px 16px',
                  backgroundColor: '#f1f5f9',
                  border: '1px solid #cbd5e1',
                  borderRadius: 10,
                  fontSize: '0.85rem',
                  fontWeight: 700,
                  color: '#334155',
                  cursor: 'pointer',
                }}
              >
                Ver Versión Completa de Escritorio
              </button>
            </div>
          </div>
        )}
      </main>
    </div>
  );
};
