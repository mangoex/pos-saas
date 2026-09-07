import React, { useState } from 'react';
import { Copy, Check, Download, ExternalLink, QrCode } from 'lucide-react';
import { Card, Button } from '@restaurantos/ui';

interface QRCodeCardProps {
  restaurantName: string;
  restaurantSlug: string;
  whatsappPhone?: string;
  fullUrl?: string;
}

export const QRCodeCard: React.FC<QRCodeCardProps> = ({
  restaurantName,
  restaurantSlug,
  whatsappPhone,
  fullUrl,
}) => {
  const [copied, setCopied] = useState(false);

  const baseUrl = window.location.origin;
  const menuPath = `/menu/${restaurantSlug}/`;
  const resolvedUrl = fullUrl || `${baseUrl}${menuPath}`;
  const qrImageUrl = `https://api.qrserver.com/v1/create-qr-code/?size=320x320&data=${encodeURIComponent(resolvedUrl)}&margin=10`;

  const handleCopy = () => {
    navigator.clipboard.writeText(resolvedUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    const a = document.createElement('a');
    a.href = qrImageUrl;
    a.download = `menu-qr-${restaurantSlug}.png`;
    a.target = '_blank';
    a.click();
  };

  const handleOpenPreview = () => {
    window.open(resolvedUrl, '_blank', 'noopener,noreferrer');
  };

  return (
    <Card style={{ padding: 24, borderRadius: 16, border: '1px solid #e2e8f0', background: '#fff' }}>
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center' }}>
        <div style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 6,
          background: 'rgba(16, 185, 129, 0.12)',
          color: '#10b981',
          padding: '4px 12px',
          borderRadius: 9999,
          fontSize: '0.75rem',
          fontWeight: 700,
          textTransform: 'uppercase',
          marginBottom: 12,
        }}>
          <QrCode size={14} /> Menú Digital QR
        </div>

        <h3 style={{ margin: '0 0 6px', fontSize: '1.25rem', fontWeight: 800, color: '#0f172a' }}>
          {restaurantName}
        </h3>
        <p style={{ margin: '0 0 16px', color: '#64748b', fontSize: '0.875rem' }}>
          Imprime este código para mesas, mostrador o empaques.
        </p>

        {/* QR Code Container */}
        <div style={{
          background: '#f8fafc',
          padding: 16,
          borderRadius: 16,
          border: '1px solid #e2e8f0',
          boxShadow: '0 4px 12px rgba(0,0,0,0.04)',
          marginBottom: 16,
          position: 'relative',
        }}>
          <img
            src={qrImageUrl}
            alt={`QR Menú ${restaurantName}`}
            style={{ width: 200, height: 200, display: 'block', borderRadius: 8 }}
          />
        </div>

        {/* URL Link Box */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          background: '#f1f5f9',
          padding: '8px 12px',
          borderRadius: 8,
          width: '100%',
          maxWidth: 380,
          marginBottom: 16,
          fontSize: '0.85rem',
          color: '#334155',
        }}>
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1, fontWeight: 500 }}>
            {resolvedUrl}
          </span>
          <button
            type="button"
            onClick={handleCopy}
            title="Copiar enlace"
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              color: copied ? '#10b981' : '#64748b',
              display: 'flex',
              alignItems: 'center',
              padding: 4,
            }}
          >
            {copied ? <Check size={16} /> : <Copy size={16} />}
          </button>
        </div>

        {/* Action Buttons */}
        <div style={{ display: 'flex', gap: 10, width: '100%', maxWidth: 380 }}>
          <Button
            type="button"
            variant="secondary"
            onClick={handleDownload}
            style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, fontSize: '0.875rem' }}
          >
            <Download size={16} /> Descargar QR
          </Button>

          <Button
            type="button"
            variant="primary"
            onClick={handleOpenPreview}
            style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, fontSize: '0.875rem' }}
          >
            <ExternalLink size={16} /> Probar Menú
          </Button>
        </div>

        {whatsappPhone && (
          <p style={{ margin: '14px 0 0', fontSize: '0.8rem', color: '#64748b' }}>
            📱 Pedidos directos a WhatsApp: <strong>{whatsappPhone}</strong>
          </p>
        )}
      </div>
    </Card>
  );
};

export default QRCodeCard;
