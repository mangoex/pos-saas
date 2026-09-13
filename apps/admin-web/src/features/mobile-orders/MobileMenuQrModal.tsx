import React, { useEffect, useState } from 'react';
import { fetchApi } from '@restaurantos/api-client';
import {
  QrCode,
  X,
  Download,
  Share2,
  Copy,
  Check,
  ExternalLink,
  MessageCircle,
  Sparkles,
} from 'lucide-react';

interface MobileMenuQrModalProps {
  isOpen: boolean;
  onClose: () => void;
  branchName?: string;
}

interface LinksResponse {
  name?: string;
  canonical_slug?: string;
  preferred_slug?: string;
  canonical_menu_url?: string;
  links?: {
    menu?: string;
    admin?: string;
    pos?: string;
    kds?: string;
  };
}

export const MobileMenuQrModal: React.FC<MobileMenuQrModalProps> = ({
  isOpen,
  onClose,
  branchName,
}) => {
  const [linksData, setLinksData] = useState<LinksResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) {
      setCopied(false);
      setToastMessage(null);
      return;
    }

    let active = true;
    setLoading(true);

    void fetchApi<LinksResponse>('/saas/links')
      .then((data) => {
        if (active) {
          setLinksData(data);
        }
      })
      .catch(() => {
        // Fallback gracefully if API is unreachable
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [isOpen]);

  if (!isOpen) return null;

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => {
      setToastMessage(null);
    }, 2800);
  };

  const menuUrl =
    linksData?.links?.menu ||
    linksData?.canonical_menu_url ||
    (typeof window !== 'undefined'
      ? `${window.location.origin}/menu/${linksData?.preferred_slug || linksData?.canonical_slug || ''}`
      : '');

  const restaurantName = linksData?.name || branchName || 'Tu Restaurante';
  const slug = linksData?.preferred_slug || linksData?.canonical_slug || 'restaurante';

  const qrImageUrl = menuUrl
    ? `https://api.qrserver.com/v1/create-qr-code/?size=360x360&data=${encodeURIComponent(
        menuUrl
      )}&margin=10`
    : null;

  const qrDownloadUrl = menuUrl
    ? `https://api.qrserver.com/v1/create-qr-code/?size=600x600&data=${encodeURIComponent(
        menuUrl
      )}&margin=12`
    : null;

  const handleCopyLink = async () => {
    if (!menuUrl) return;
    try {
      await navigator.clipboard.writeText(menuUrl);
      setCopied(true);
      showToast('¡Enlace copiado al portapapeles!');
      setTimeout(() => setCopied(false), 2000);
    } catch {
      showToast('No se pudo copiar automáticamente.');
    }
  };

  const handleNativeShare = async () => {
    if (!menuUrl) return;
    if (typeof navigator !== 'undefined' && navigator.share) {
      try {
        await navigator.share({
          title: `Menú Digital - ${restaurantName}`,
          text: `¡Hola! Conoce nuestro menú y realiza tus pedidos aquí:`,
          url: menuUrl,
        });
      } catch (err: any) {
        // User aborted share or share cancelled
        if (err?.name !== 'AbortError') {
          await handleCopyLink();
        }
      }
    } else {
      await handleCopyLink();
    }
  };

  const handleWhatsAppShare = () => {
    if (!menuUrl) return;
    const text = encodeURIComponent(
      `¡Hola! Te comparto el menú digital de ${restaurantName} para ver nuestros platillos y hacer tus pedidos: ${menuUrl}`
    );
    window.open(`https://wa.me/?text=${text}`, '_blank');
  };

  const handleDownload = async () => {
    const targetUrl = qrDownloadUrl || qrImageUrl;
    if (!targetUrl) return;
    setDownloading(true);
    try {
      const response = await fetch(targetUrl);
      const blob = await response.blob();
      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = blobUrl;
      a.download = `menu-qr-${slug}.png`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
      showToast('¡Código QR descargado!');
    } catch {
      // Direct link fallback if blob download encounters CORS
      const a = document.createElement('a');
      a.href = targetUrl;
      a.download = `menu-qr-${slug}.png`;
      a.target = '_blank';
      a.click();
      showToast('Abriendo imagen para guardar...');
    } finally {
      setDownloading(false);
    }
  };

  const handleOpenPreview = () => {
    if (!menuUrl) return;
    window.open(menuUrl, '_blank', 'noopener,noreferrer');
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Código QR del Menú"
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.65)',
        backdropFilter: 'blur(4px)',
        WebkitBackdropFilter: 'blur(4px)',
        zIndex: 9999,
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'flex-end',
        alignItems: 'center',
        animation: 'fadeIn 0.2s ease-out',
      }}
      onClick={onClose}
    >
      <div
        style={{
          backgroundColor: '#ffffff',
          borderTopLeftRadius: 24,
          borderTopRightRadius: 24,
          width: '100%',
          maxWidth: 520,
          maxHeight: '92vh',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          boxShadow: '0 -10px 30px rgba(0,0,0,0.25)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div
          style={{
            padding: '16px 20px',
            borderBottom: '1px solid #f1f5f9',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            backgroundColor: '#ffffff',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div
              style={{
                width: 36,
                height: 36,
                borderRadius: 10,
                backgroundColor: 'rgba(16, 185, 129, 0.12)',
                color: '#10b981',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <QrCode size={20} />
            </div>
            <div>
              <div style={{ fontSize: '1.05rem', fontWeight: 800, color: '#0f172a', lineHeight: 1.2 }}>
                QR del Menú Digital
              </div>
              <div style={{ fontSize: '0.75rem', color: '#64748b' }}>
                {restaurantName}
              </div>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            aria-label="Cerrar modal"
            style={{
              border: 'none',
              background: '#f1f5f9',
              borderRadius: '50%',
              width: 34,
              height: 34,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: 'pointer',
              color: '#64748b',
            }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Scrollable Content */}
        <div
          style={{
            padding: '20px 20px 28px',
            overflowY: 'auto',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            textAlign: 'center',
          }}
        >
          {/* Badge */}
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              background: 'rgba(56, 189, 248, 0.12)',
              color: '#0284c7',
              padding: '4px 12px',
              borderRadius: 9999,
              fontSize: '0.75rem',
              fontWeight: 700,
              textTransform: 'uppercase',
              marginBottom: 14,
            }}
          >
            <Sparkles size={13} />
            Listo para Mesas y Redes
          </div>

          {/* QR Container Card */}
          <div
            style={{
              background: '#ffffff',
              padding: 16,
              borderRadius: 20,
              border: '2px solid #e2e8f0',
              boxShadow: '0 8px 24px rgba(0, 0, 0, 0.06)',
              marginBottom: 14,
              position: 'relative',
            }}
          >
            {loading ? (
              <div
                style={{
                  width: 220,
                  height: 220,
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: '#64748b',
                  fontSize: '0.875rem',
                  gap: 10,
                }}
              >
                <div
                  style={{
                    width: 28,
                    height: 28,
                    border: '3px solid #e2e8f0',
                    borderTopColor: '#0284c7',
                    borderRadius: '50%',
                    animation: 'spin 0.8s linear infinite',
                  }}
                />
                Cargando código QR...
              </div>
            ) : qrImageUrl ? (
              <img
                src={qrImageUrl}
                alt={`QR Menú ${restaurantName}`}
                style={{
                  width: 220,
                  height: 220,
                  display: 'block',
                  borderRadius: 12,
                }}
              />
            ) : (
              <div
                style={{
                  width: 220,
                  height: 220,
                  display: 'grid',
                  placeItems: 'center',
                  color: '#ef4444',
                  fontSize: '0.85rem',
                }}
              >
                No se pudo generar el QR
              </div>
            )}
          </div>

          {/* Description */}
          <p
            style={{
              margin: '0 0 16px',
              fontSize: '0.825rem',
              color: '#64748b',
              maxWidth: 340,
              lineHeight: 1.4,
            }}
          >
            Tus comensales solo apuntan su cámara para abrir la carta digital y enviar pedidos a tu
            monitor.
          </p>

          {/* Public URL Box with Copy */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              background: '#f8fafc',
              border: '1px solid #cbd5e1',
              padding: '8px 12px',
              borderRadius: 12,
              width: '100%',
              maxWidth: 380,
              marginBottom: 20,
              boxSizing: 'border-box',
            }}
          >
            <span
              style={{
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                flex: 1,
                fontSize: '0.825rem',
                fontWeight: 600,
                color: '#1e293b',
                textAlign: 'left',
              }}
            >
              {menuUrl || 'Cargando enlace...'}
            </span>

            <button
              type="button"
              onClick={() => void handleCopyLink()}
              disabled={!menuUrl}
              title="Copiar enlace"
              style={{
                border: 'none',
                background: copied ? '#dcfce7' : '#ffffff',
                color: copied ? '#166534' : '#475569',
                padding: '6px 10px',
                borderRadius: 8,
                fontSize: '0.75rem',
                fontWeight: 700,
                display: 'inline-flex',
                alignItems: 'center',
                gap: 4,
                cursor: 'pointer',
                borderWidth: 1,
                borderStyle: 'solid',
                borderColor: copied ? '#bbf7d0' : '#e2e8f0',
                transition: 'all 0.15s ease',
              }}
            >
              {copied ? (
                <>
                  <Check size={14} /> Copiado
                </>
              ) : (
                <>
                  <Copy size={14} /> Copiar
                </>
              )}
            </button>
          </div>

          {/* Actions Section */}
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: 10,
              width: '100%',
              maxWidth: 380,
            }}
          >
            {/* Primary Share row: Share Sheet + WhatsApp */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              <button
                type="button"
                onClick={() => void handleNativeShare()}
                disabled={!menuUrl}
                style={{
                  padding: '12px 14px',
                  backgroundColor: '#0284c7',
                  color: '#ffffff',
                  border: 'none',
                  borderRadius: 12,
                  fontWeight: 700,
                  fontSize: '0.875rem',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 8,
                  cursor: 'pointer',
                  boxShadow: '0 2px 8px rgba(2, 132, 199, 0.25)',
                }}
              >
                <Share2 size={16} /> Compartir
              </button>

              <button
                type="button"
                onClick={handleWhatsAppShare}
                disabled={!menuUrl}
                style={{
                  padding: '12px 14px',
                  backgroundColor: '#22c55e',
                  color: '#ffffff',
                  border: 'none',
                  borderRadius: 12,
                  fontWeight: 700,
                  fontSize: '0.875rem',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 8,
                  cursor: 'pointer',
                  boxShadow: '0 2px 8px rgba(34, 197, 94, 0.25)',
                }}
              >
                <MessageCircle size={16} /> WhatsApp
              </button>
            </div>

            {/* Secondary row: Download QR + Preview Menu */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              <button
                type="button"
                onClick={() => void handleDownload()}
                disabled={!qrImageUrl || downloading}
                style={{
                  padding: '12px 14px',
                  backgroundColor: '#0f172a',
                  color: '#ffffff',
                  border: 'none',
                  borderRadius: 12,
                  fontWeight: 700,
                  fontSize: '0.875rem',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 8,
                  cursor: 'pointer',
                  opacity: downloading ? 0.7 : 1,
                }}
              >
                <Download size={16} /> {downloading ? 'Descargando...' : 'Descargar QR'}
              </button>

              <button
                type="button"
                onClick={handleOpenPreview}
                disabled={!menuUrl}
                style={{
                  padding: '12px 14px',
                  backgroundColor: '#f1f5f9',
                  color: '#334155',
                  border: '1px solid #cbd5e1',
                  borderRadius: 12,
                  fontWeight: 700,
                  fontSize: '0.875rem',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 8,
                  cursor: 'pointer',
                }}
              >
                <ExternalLink size={16} /> Ver Menú
              </button>
            </div>
          </div>

          {/* Toast feedback */}
          {toastMessage && (
            <div
              style={{
                marginTop: 16,
                backgroundColor: '#0f172a',
                color: '#ffffff',
                padding: '8px 16px',
                borderRadius: 9999,
                fontSize: '0.8rem',
                fontWeight: 600,
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
                animation: 'fadeIn 0.2s ease-out',
              }}
            >
              <Check size={14} color="#10b981" />
              {toastMessage}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
