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
  Sparkles,
  Globe,
  Bike,
  Plus,
  Trash2,
  ArrowUp,
} from 'lucide-react';

interface OrgProfile {
  id: string;
  name: string;
  plan: string;
  subscription_status: string;
  trial_ends_at?: string | null;
  trial_days_remaining?: number;
  trial_extra_days?: number;
}

interface MobileBranchSettingsTabProps {
  branchId: string;
  branchName?: string;
  onSwitchToDesktop?: () => void;
  onOpenOnboarding?: () => void;
  onboardingPending?: boolean;
}

export interface DeliveryTier {
  id: string;
  name: string;
  fee_cents: number;
  is_default_web: boolean;
}

interface Branch {
  id: string;
  name: string;
  code: string;
  status: string;
  phone?: string;
  google_review_url?: string;
  whatsapp_ordering_enabled?: boolean;
  delivery_fee_enabled?: boolean;
  delivery_tiers?: DeliveryTier[];
  free_delivery_min_cents?: number | null;
}

interface LinksResponse {
  name: string;
  canonical_slug: string;
  preferred_slug?: string;
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
  onOpenOnboarding,
  onboardingPending,
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

  const { data: orgProfile } = useQuery<OrgProfile>({
    queryKey: ['org-profile'],
    queryFn: () => fetchApi<OrgProfile>('/organization/profile'),
  });

  // Local form states
  const [branchPhone, setBranchPhone] = useState('');
  const [whatsappEnabled, setWhatsappEnabled] = useState(false);
  const [googleReviewUrl, setGoogleReviewUrl] = useState('');
  const [isOpenForOrders, setIsOpenForOrders] = useState(true);
  const [deliveryFeeEnabled, setDeliveryFeeEnabled] = useState(true);
  const [freeDeliveryMinPesos, setFreeDeliveryMinPesos] = useState('');
  const [deliveryTiers, setDeliveryTiers] = useState<DeliveryTier[]>([]);

  // Alias / Public link customization state
  const [aliasInput, setAliasInput] = useState('');
  const [aliasError, setAliasError] = useState<string | null>(null);
  const [aliasSuccess, setAliasSuccess] = useState<string | null>(null);
  const [isSavingAlias, setIsSavingAlias] = useState(false);

  useEffect(() => {
    if (currentBranch) {
      setBranchPhone(currentBranch.phone || '');
      setWhatsappEnabled(Boolean(currentBranch.whatsapp_ordering_enabled));
      setGoogleReviewUrl(currentBranch.google_review_url || '');
      setIsOpenForOrders(currentBranch.status !== 'inactive');
      setDeliveryFeeEnabled(currentBranch.delivery_fee_enabled !== false);
      setFreeDeliveryMinPesos(
        currentBranch.free_delivery_min_cents != null && currentBranch.free_delivery_min_cents > 0
          ? String(currentBranch.free_delivery_min_cents / 100)
          : ''
      );
      setDeliveryTiers(
        currentBranch.delivery_tiers && currentBranch.delivery_tiers.length > 0
          ? currentBranch.delivery_tiers
          : [
              { id: 'tier-corta', name: 'Corta ($20)', fee_cents: 2000, is_default_web: false },
              { id: 'tier-media', name: 'Media ($30)', fee_cents: 3000, is_default_web: false },
              { id: 'tier-lejana', name: 'Lejana ($40)', fee_cents: 4000, is_default_web: false },
              { id: 'tier-gratis', name: 'Gratis ($0)', fee_cents: 0, is_default_web: true },
            ]
      );
    }
  }, [currentBranch]);

  useEffect(() => {
    if (linksData) {
      setAliasInput(linksData.preferred_slug || linksData.canonical_slug || '');
    }
  }, [linksData]);

  const handleSaveAlias = async (e: React.FormEvent) => {
    e.preventDefault();
    setAliasError(null);
    setAliasSuccess(null);

    const cleanAlias = aliasInput
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9-]/g, '-')
      .replace(/-+/g, '-')
      .replace(/^-|-$/g, '');

    if (!cleanAlias || cleanAlias.length < 3) {
      setAliasError('El nombre debe tener al menos 3 caracteres.');
      return;
    }
    if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(cleanAlias)) {
      setAliasError('Usa letras minúsculas, números y guiones.');
      return;
    }

    setIsSavingAlias(true);
    try {
      await fetchApi('/saas/links/alias', {
        method: 'PUT',
        body: JSON.stringify({ alias: cleanAlias }),
      });
      setAliasSuccess('Enlace actualizado. Los enlaces anteriores se conservan.');
      setAliasInput(cleanAlias);
      await queryClient.invalidateQueries({ queryKey: ['saas-links'] });
      setTimeout(() => setAliasSuccess(null), 4000);
    } catch (err: any) {
      const code = err?.detail?.code || err?.code;
      const msg = err?.detail?.message || err?.message;
      if (code === 'alias_unavailable' || err?.status === 409) {
        setAliasError(`El nombre "${cleanAlias}" no está disponible. Ya está ocupado.`);
      } else if (code === 'alias_reserved') {
        setAliasError(`El nombre "${cleanAlias}" está reservado. Elige otro.`);
      } else if (code === 'alias_invalid') {
        setAliasError(`El nombre "${cleanAlias}" no puede usarse como subdominio. Elige otro.`);
      } else {
        setAliasError(msg || 'No se pudo guardar el nombre del enlace. Inténtalo de nuevo.');
      }
    } finally {
      setIsSavingAlias(false);
    }
  };

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
      delivery_fee_enabled: deliveryFeeEnabled,
      delivery_tiers: deliveryTiers,
      free_delivery_min_cents: freeDeliveryMinPesos.trim() ? Math.round(parseFloat(freeDeliveryMinPesos) * 100) : null,
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
        {/* Trial Days Remaining Banner */}
        {(orgProfile?.plan === 'trial' || orgProfile?.subscription_status === 'trialing') && (
          <section
            style={{
              background: (orgProfile.trial_extra_days ?? 0) > 0 || orgProfile.trial_days_remaining === 0
                ? 'linear-gradient(135deg, #0284c7 0%, #0369a1 100%)'
                : 'linear-gradient(135deg, #0284c7 0%, #0ea5e9 100%)',
              borderRadius: 16,
              padding: '16px 18px',
              color: '#ffffff',
              marginBottom: 16,
              boxShadow: '0 4px 12px rgba(2, 132, 199, 0.25)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 12,
            }}
          >
            <div>
              <div
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 4,
                  background: 'rgba(255, 255, 255, 0.2)',
                  padding: '2px 8px',
                  borderRadius: 9999,
                  fontSize: '0.65rem',
                  fontWeight: 800,
                  textTransform: 'uppercase',
                  marginBottom: 4,
                }}
              >
                <span>Periodo de Prueba</span>
                {((orgProfile.trial_extra_days ?? 0) > 0 || orgProfile.trial_days_remaining === 0) && (
                  <ArrowUp size={11} strokeWidth={3} />
                )}
              </div>
              <h3 style={{ margin: '0 0 2px', fontSize: '1rem', fontWeight: 800, color: '#ffffff', display: 'flex', alignItems: 'center', gap: '6px' }}>
                {(orgProfile.trial_extra_days ?? 0) > 0 ? (
                  <>
                    <span>+{orgProfile.trial_extra_days} {orgProfile.trial_extra_days === 1 ? 'día adicional' : 'días adicionales'}</span>
                    <ArrowUp size={16} strokeWidth={3} />
                  </>
                ) : orgProfile.trial_days_remaining === 0 ? (
                  <>
                    <span>0 días restantes</span>
                    <ArrowUp size={16} strokeWidth={3} />
                  </>
                ) : (
                  <span>
                    {orgProfile.trial_days_remaining} {orgProfile.trial_days_remaining === 1 ? 'día restante' : 'días restantes'}
                  </span>
                )}
              </h3>
              <p style={{ margin: 0, fontSize: '0.75rem', color: '#e0f2fe' }}>
                {(orgProfile.trial_extra_days ?? 0) > 0
                  ? 'Tu prueba concluyó; tus operaciones continúan activas mientras gestionas tu activación.'
                  : 'Cuentas con acceso completo a todas las funciones de tu sucursal.'}
              </p>
            </div>
            <div
              style={{
                backgroundColor: 'rgba(255, 255, 255, 0.2)',
                borderRadius: 12,
                padding: '8px 12px',
                textAlign: 'center',
                whiteSpace: 'nowrap',
              }}
            >
              <div style={{ fontSize: '0.65rem', fontWeight: 700, color: '#e0f2fe', textTransform: 'uppercase' }}>
                Estado
              </div>
              <div style={{ fontSize: '0.85rem', fontWeight: 800 }}>
                {(orgProfile.trial_extra_days ?? 0) > 0 ? 'En Gracia' : 'Activo'}
              </div>
            </div>
          </section>
        )}

        {/* Onboarding Quickstart Card */}
        {onOpenOnboarding && (
          <section
            style={{
              background: onboardingPending
                ? 'linear-gradient(135deg, #064e3b 0%, #047857 100%)'
                : 'linear-gradient(135deg, #1e293b 0%, #334155 100%)',
              borderRadius: 16,
              padding: '16px 18px',
              color: '#ffffff',
              marginBottom: 16,
              boxShadow: '0 4px 12px rgba(0, 0, 0, 0.1)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 12,
            }}
          >
            <div>
              <div
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 4,
                  background: 'rgba(255, 255, 255, 0.2)',
                  padding: '2px 8px',
                  borderRadius: 9999,
                  fontSize: '0.65rem',
                  fontWeight: 800,
                  textTransform: 'uppercase',
                  marginBottom: 4,
                }}
              >
                <Sparkles size={12} /> {onboardingPending ? 'Configuración Inicial' : 'Asistente'}
              </div>
              <h3 style={{ margin: '0 0 2px', fontSize: '0.95rem', fontWeight: 800, color: '#ffffff' }}>
                Asistente de Menú y QR
              </h3>
              <p style={{ margin: 0, fontSize: '0.75rem', color: '#d1fae5' }}>
                {onboardingPending
                  ? 'Configura tu menú con IA y genera tu QR listo para imprimir.'
                  : 'Vuelve a abrir el asistente para recargar menú o revisar tu QR.'}
              </p>
            </div>
            <button
              type="button"
              onClick={onOpenOnboarding}
              style={{
                backgroundColor: '#ffffff',
                color: '#065f46',
                border: 'none',
                borderRadius: 10,
                padding: '8px 14px',
                fontSize: '0.8rem',
                fontWeight: 800,
                cursor: 'pointer',
                whiteSpace: 'nowrap',
                boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
              }}
            >
              Abrir
            </button>
          </section>
        )}

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

            {/* Card: Nombre de tu enlace público */}
            <div
              style={{
                backgroundColor: '#ffffff',
                borderRadius: 16,
                padding: 16,
                border: '1px solid #e2e8f0',
                boxShadow: '0 2px 4px rgba(0,0,0,0.03)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                <Globe size={20} color="#059669" />
                <h3 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 800, color: '#0f172a' }}>
                  Nombre de tu enlace público
                </h3>
              </div>
              <p style={{ margin: '0 0 12px', fontSize: '0.8rem', color: '#64748b', lineHeight: 1.4 }}>
                Usa letras minúsculas, números y guiones. Tus enlaces anteriores seguirán funcionando.
              </p>

              <form onSubmit={handleSaveAlias}>
                <label
                  htmlFor="mobile-restaurant-alias"
                  style={{
                    display: 'block',
                    fontSize: '0.825rem',
                    fontWeight: 700,
                    color: '#334155',
                    marginBottom: 6,
                  }}
                >
                  Nombre personalizado
                </label>

                <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
                  <input
                    id="mobile-restaurant-alias"
                    type="text"
                    value={aliasInput}
                    onChange={(e) => {
                      setAliasInput(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ''));
                      setAliasError(null);
                    }}
                    placeholder="hamburgueria"
                    style={{
                      flex: 1,
                      minWidth: 0,
                      padding: '10px 12px',
                      fontSize: '0.95rem',
                      borderRadius: 10,
                      border: aliasError ? '2px solid #ef4444' : '1px solid #cbd5e1',
                      outline: 'none',
                      boxSizing: 'border-box',
                      backgroundColor: '#ffffff',
                    }}
                  />
                  <button
                    type="submit"
                    disabled={isSavingAlias || !aliasInput.trim()}
                    style={{
                      padding: '10px 16px',
                      backgroundColor: '#047857',
                      color: '#ffffff',
                      border: 'none',
                      borderRadius: 10,
                      fontWeight: 700,
                      fontSize: '0.875rem',
                      cursor: isSavingAlias || !aliasInput.trim() ? 'not-allowed' : 'pointer',
                      opacity: isSavingAlias || !aliasInput.trim() ? 0.65 : 1,
                      whiteSpace: 'nowrap',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 6,
                    }}
                  >
                    {isSavingAlias ? 'Guardando...' : 'Guardar nombre'}
                  </button>
                </div>

                {/* Error message when not available or invalid */}
                {aliasError && (
                  <div
                    role="alert"
                    style={{
                      backgroundColor: '#fef2f2',
                      border: '1px solid #fecaca',
                      borderRadius: 8,
                      padding: '8px 12px',
                      color: '#dc2626',
                      fontSize: '0.8rem',
                      fontWeight: 600,
                      marginBottom: 8,
                      display: 'flex',
                      alignItems: 'center',
                      gap: 6,
                    }}
                  >
                    <AlertCircle size={15} style={{ flexShrink: 0 }} />
                    <span>{aliasError}</span>
                  </div>
                )}

                {/* Success feedback */}
                {aliasSuccess && (
                  <div
                    role="status"
                    style={{
                      backgroundColor: '#f0fdf4',
                      border: '1px solid #bbf7d0',
                      borderRadius: 8,
                      padding: '8px 12px',
                      color: '#16a34a',
                      fontSize: '0.8rem',
                      fontWeight: 600,
                      marginBottom: 8,
                      display: 'flex',
                      alignItems: 'center',
                      gap: 6,
                    }}
                  >
                    <CheckCircle2 size={15} style={{ flexShrink: 0 }} />
                    <span>{aliasSuccess}</span>
                  </div>
                )}

                {/* Permanent link reference */}
                {linksData?.canonical_menu_url && (
                  <p style={{ margin: '6px 0 0', fontSize: '0.75rem', color: '#64748b' }}>
                    Enlace permanente:{' '}
                    <a
                      href={linksData.canonical_menu_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ color: '#047857', textDecoration: 'underline', wordBreak: 'break-all' }}
                    >
                      {linksData.canonical_menu_url}
                    </a>
                  </p>
                )}
              </form>
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

              {/* Card: Costos de Envío a Domicilio */}
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
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                  <Bike size={20} color="#059669" />
                  <h3 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 800, color: '#0f172a' }}>
                    Costos de Envío a Domicilio
                  </h3>
                </div>

                {/* Toggle Delivery Fee */}
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '10px 0',
                    borderBottom: '1px solid #f1f5f9',
                  }}
                >
                  <div>
                    <div style={{ fontSize: '0.9rem', fontWeight: 700, color: '#0f172a' }}>
                      Cobrar costo de envío
                    </div>
                    <div style={{ fontSize: '0.775rem', color: '#64748b' }}>
                      {deliveryFeeEnabled ? 'Tarifas activas para POS y Menú Digital' : 'Envío siempre sin costo adicional'}
                    </div>
                  </div>
                  <input
                    type="checkbox"
                    checked={deliveryFeeEnabled}
                    onChange={(e) => setDeliveryFeeEnabled(e.target.checked)}
                    style={{ width: 22, height: 22, cursor: 'pointer', accentColor: '#059669' }}
                  />
                </div>

                {deliveryFeeEnabled && (
                  <>
                    {/* Free Delivery threshold */}
                    <div style={{ padding: '14px 0', borderBottom: '1px solid #f1f5f9' }}>
                      <label
                        style={{
                          display: 'block',
                          fontSize: '0.85rem',
                          fontWeight: 700,
                          color: '#334155',
                          marginBottom: 4,
                        }}
                      >
                        Envío GRATIS en compras a partir de ($ MXN)
                      </label>
                      <input
                        type="number"
                        min="0"
                        step="1"
                        placeholder="Ej. 300 (opcional, deja vacío si no aplica)"
                        value={freeDeliveryMinPesos}
                        onChange={(e) => setFreeDeliveryMinPesos(e.target.value)}
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
                      <span style={{ display: 'block', marginTop: 4, fontSize: '0.75rem', color: '#64748b' }}>
                        Si el subtotal del cliente alcanza este monto, el sistema aplicará automáticamente envío gratis ($0).
                      </span>
                    </div>

                    {/* Tiers List */}
                    <div style={{ paddingTop: 14 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                        <label
                          style={{
                            fontSize: '0.85rem',
                            fontWeight: 700,
                            color: '#334155',
                          }}
                        >
                          Tarifas por distancia / zona
                        </label>
                        <button
                          type="button"
                          onClick={() => {
                            const newId = `tier-${Date.now()}`;
                            setDeliveryTiers([
                              ...deliveryTiers,
                              { id: newId, name: 'Nueva Zona', fee_cents: 2500, is_default_web: false },
                            ]);
                          }}
                          style={{
                            padding: '4px 10px',
                            backgroundColor: '#ecfdf5',
                            border: '1px solid #a7f3d0',
                            borderRadius: 8,
                            color: '#047857',
                            fontSize: '0.78rem',
                            fontWeight: 700,
                            cursor: 'pointer',
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: 4,
                          }}
                        >
                          <Plus size={14} /> Agregar tarifa
                        </button>
                      </div>
                      <p style={{ margin: '0 0 10px', fontSize: '0.75rem', color: '#64748b' }}>
                        Selecciona con el radio cuál es la tarifa <strong>por defecto para el Menú Web Móvil</strong> (puedes marcar Gratis si no deseas cobrar envío por la web).
                      </p>

                      <div style={{ display: 'grid', gap: 10 }}>
                        {deliveryTiers.map((tier, idx) => (
                          <div
                            key={tier.id || idx}
                            style={{
                              display: 'flex',
                              flexDirection: 'column',
                              gap: 10,
                              padding: '12px',
                              backgroundColor: tier.is_default_web ? '#f0fdf4' : '#f8fafc',
                              border: `1px solid ${tier.is_default_web ? '#86efac' : '#e2e8f0'}`,
                              borderRadius: 12,
                              boxSizing: 'border-box',
                              width: '100%',
                            }}
                          >
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                              <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', margin: 0 }}>
                                <input
                                  type="radio"
                                  name="default_web_tier"
                                  checked={tier.is_default_web}
                                  onChange={() => {
                                    setDeliveryTiers(
                                      deliveryTiers.map((t, i) => ({
                                        ...t,
                                        is_default_web: i === idx,
                                      }))
                                    );
                                  }}
                                  title="Predeterminado Web"
                                  style={{ width: 18, height: 18, cursor: 'pointer', accentColor: '#16a34a' }}
                                />
                                <span style={{ fontSize: '0.78rem', fontWeight: 600, color: tier.is_default_web ? '#059669' : '#64748b' }}>
                                  {tier.is_default_web ? 'Tarifa por defecto en Menú Web' : 'Predeterminado Web'}
                                </span>
                              </label>

                              {deliveryTiers.length > 1 && (
                                <button
                                  type="button"
                                  onClick={() => {
                                    const updated = deliveryTiers.filter((_, i) => i !== idx);
                                    if (tier.is_default_web && updated.length > 0) {
                                      updated[0].is_default_web = true;
                                    }
                                    setDeliveryTiers(updated);
                                  }}
                                  style={{
                                    background: 'none',
                                    border: 'none',
                                    color: '#ef4444',
                                    cursor: 'pointer',
                                    padding: '4px 6px',
                                    display: 'inline-flex',
                                    alignItems: 'center',
                                    gap: 4,
                                    fontSize: '0.75rem',
                                  }}
                                  title="Eliminar tarifa"
                                >
                                  <Trash2 size={16} />
                                </button>
                              )}
                            </div>

                            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                              <input
                                type="text"
                                value={tier.name}
                                onChange={(e) => {
                                  const updated = [...deliveryTiers];
                                  updated[idx] = { ...updated[idx], name: e.target.value };
                                  setDeliveryTiers(updated);
                                }}
                                placeholder="Nombre (ej. Corta, Gratis)"
                                style={{
                                  flex: 1,
                                  minWidth: 0,
                                  boxSizing: 'border-box',
                                  padding: '8px 10px',
                                  fontSize: '0.85rem',
                                  borderRadius: 8,
                                  border: '1px solid #cbd5e1',
                                  outline: 'none',
                                  background: '#ffffff',
                                }}
                              />

                              <div style={{ display: 'flex', alignItems: 'center', gap: 4, flexShrink: 0 }}>
                                <span style={{ fontSize: '0.85rem', color: '#64748b', fontWeight: 600 }}>$</span>
                                <input
                                  type="number"
                                  min="0"
                                  step="1"
                                  value={tier.fee_cents / 100}
                                  onChange={(e) => {
                                    const updated = [...deliveryTiers];
                                    const val = parseFloat(e.target.value) || 0;
                                    updated[idx] = { ...updated[idx], fee_cents: Math.max(0, Math.round(val * 100)) };
                                    setDeliveryTiers(updated);
                                  }}
                                  style={{
                                    width: 70,
                                    boxSizing: 'border-box',
                                    padding: '8px 10px',
                                    fontSize: '0.85rem',
                                    borderRadius: 8,
                                    border: '1px solid #cbd5e1',
                                    outline: 'none',
                                    background: '#ffffff',
                                  }}
                                />
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </>
                )}
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
