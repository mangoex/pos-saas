import React, { useState, useEffect, useRef } from 'react';
import {
  Clock,
  ChefHat,
  CheckCircle2,
  Bike,
  ShoppingBag,
  ChevronDown,
  ChevronUp,
  X,
  ExternalLink,
  Sparkles,
  AlertCircle
} from 'lucide-react';
import { TrackedActiveOrder } from '../types';
import { fetchPublicOrderTracking, formatMoney, saveTrackedOrder, clearTrackedOrder } from '../api';

interface ActiveOrderTrackerProps {
  initialOrder: TrackedActiveOrder | null;
  onClearOrder?: () => void;
  whatsappPhone?: string;
  restaurantName?: string;
}

export const ActiveOrderTracker: React.FC<ActiveOrderTrackerProps> = ({
  initialOrder,
  onClearOrder,
  whatsappPhone,
  restaurantName,
}) => {
  const [order, setOrder] = useState<TrackedActiveOrder | null>(initialOrder);
  const [isExpanded, setIsExpanded] = useState(false);
  const previousStatus = useRef<string | null>(null);

  // Sync with prop
  useEffect(() => {
    if (initialOrder) {
      setOrder(initialOrder);
    }
  }, [initialOrder]);

  // Polling every 6 seconds for live state transition updates
  useEffect(() => {
    if (!order?.public_reference) return;

    const currentStatus = (order.operational_status || order.status || '').toUpperCase();
    if (['DELIVERED', 'CLOSED', 'CANCELLED', 'REJECTED'].includes(currentStatus)) {
      return; // Stop polling on terminal states
    }

    const interval = window.setInterval(async () => {
      const refreshed = await fetchPublicOrderTracking(order.public_reference);
      if (refreshed) {
        setOrder((prev) => {
          if (!prev) return refreshed;
          const merged: TrackedActiveOrder = {
            ...prev,
            status: refreshed.status,
            operational_status: refreshed.operational_status,
            folio: refreshed.folio || prev.folio,
          };
          saveTrackedOrder(merged);

          // Haptic vibration feedback when state becomes READY
          const newStatus = (refreshed.operational_status || refreshed.status || '').toUpperCase();
          if (newStatus === 'READY' && previousStatus.current !== 'READY') {
            if (typeof navigator !== 'undefined' && 'vibrate' in navigator) {
              try {
                navigator.vibrate([150, 60, 150]);
              } catch {
                // Ignore unsupported
              }
            }
          }
          previousStatus.current = newStatus;

          return merged;
        });
      }
    }, 6000);

    return () => window.clearInterval(interval);
  }, [order?.public_reference]);

  if (!order) return null;

  const rawStatus = (order.operational_status || order.status || '').toUpperCase();
  const isTerminal = ['DELIVERED', 'CLOSED', 'CANCELLED', 'REJECTED'].includes(rawStatus);

  // Derive active stage (1: Recibido/Aceptado, 2: Preparando, 3: Listo/Entregado)
  let activeStep = 1;
  let statusTitle = 'Pedido Recibido';
  let statusSubtitle = 'Esperando confirmación del restaurante';
  let themeColor = '#f59e0b'; // Amber
  let themeBg = '#fffbeb';
  let themeBorder = '#fde68a';

  if (rawStatus === 'PENDING_REVIEW' || rawStatus === 'PENDING' || rawStatus === 'DRAFT') {
    activeStep = 1;
    statusTitle = 'Pedido Enviado';
    statusSubtitle = 'El restaurante está confirmando tu pedido';
    themeColor = '#ea580c';
    themeBg = '#fff7ed';
    themeBorder = '#ffedd5';
  } else if (rawStatus === 'ACCEPTED') {
    activeStep = 1;
    statusTitle = 'Pedido Aceptado';
    statusSubtitle = '¡Comanda confirmada! En cola de cocina';
    themeColor = '#0284c7';
    themeBg = '#f0f9ff';
    themeBorder = '#e0f2fe';
  } else if (['IN_PRODUCTION', 'IN_PREPARATION', 'SENT_TO_PRODUCTION'].includes(rawStatus)) {
    activeStep = 2;
    statusTitle = 'En Preparación 🍳';
    statusSubtitle = 'Nuestros chefs están cocinando tu orden';
    themeColor = '#2563eb';
    themeBg = '#eff6ff';
    themeBorder = '#dbeafe';
  } else if (rawStatus === 'READY') {
    activeStep = 3;
    statusTitle = '¡Tu pedido está Listo! 🎉';
    statusSubtitle = order.service_type === 'delivery'
      ? 'Empaquetado y listo para salir a tu domicilio'
      : 'Listo para recoger en barra o llevar a tu mesa';
    themeColor = '#16a34a';
    themeBg = '#f0fdf4';
    themeBorder = '#bbf7d0';
  } else if (rawStatus === 'IN_DELIVERY') {
    activeStep = 3;
    statusTitle = 'En Camino 🛵';
    statusSubtitle = 'El repartidor va rumbo a tu ubicación';
    themeColor = '#16a34a';
    themeBg = '#f0fdf4';
    themeBorder = '#bbf7d0';
  } else if (rawStatus === 'DELIVERED' || rawStatus === 'CLOSED') {
    activeStep = 3;
    statusTitle = '¡Pedido Entregado! ✨';
    statusSubtitle = '¡Esperamos que lo disfrutes! Buen provecho';
    themeColor = '#059669';
    themeBg = '#ecfdf5';
    themeBorder = '#a7f3d0';
  } else if (rawStatus === 'REJECTED' || rawStatus === 'CANCELLED') {
    statusTitle = rawStatus === 'REJECTED' ? 'Pedido No Aceptado' : 'Pedido Cancelado';
    statusSubtitle = 'Comunícate con el restaurante si tienes dudas';
    themeColor = '#dc2626';
    themeBg = '#fef2f2';
    themeBorder = '#fecaca';
  }

  const displayFolio = order.folio ? `#${order.folio}` : `#${order.public_reference}`;

  const handleDismiss = () => {
    clearTrackedOrder(order.public_reference);
    setOrder(null);
    if (onClearOrder) onClearOrder();
  };

  return (
    <>
      {/* Floating or Top Pinned Tracking Card */}
      <aside
        aria-label="Seguimiento de comanda activa"
        style={{
          margin: '12px 14px',
          backgroundColor: '#ffffff',
          borderRadius: 18,
          border: `1.5px solid ${themeBorder}`,
          boxShadow: '0 4px 16px rgba(0,0,0,0.06)',
          overflow: 'hidden',
          transition: 'all 0.3s ease',
        }}
      >
        {/* Card Header */}
        <div
          onClick={() => setIsExpanded(!isExpanded)}
          style={{
            padding: '12px 16px',
            backgroundColor: themeBg,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            cursor: 'pointer',
            borderBottom: isExpanded ? `1px solid ${themeBorder}` : 'none',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            {/* Live Indicator Dot */}
            <div
              style={{
                width: 10,
                height: 10,
                borderRadius: '50%',
                backgroundColor: themeColor,
                boxShadow: `0 0 0 3px ${themeBorder}`,
              }}
            />
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ fontWeight: 800, fontSize: '0.95rem', color: '#0f172a' }}>
                  {statusTitle}
                </span>
                <span
                  style={{
                    backgroundColor: '#ffffff',
                    color: '#475569',
                    fontSize: '0.75rem',
                    fontWeight: 700,
                    padding: '2px 6px',
                    borderRadius: 6,
                    border: '1px solid #e2e8f0',
                  }}
                >
                  {displayFolio}
                </span>
              </div>
              <p style={{ margin: '2px 0 0', fontSize: '0.78rem', color: '#64748b' }}>
                {statusSubtitle}
              </p>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            {isTerminal && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  handleDismiss();
                }}
                style={{
                  background: 'none',
                  border: 'none',
                  color: '#94a3b8',
                  padding: 4,
                  cursor: 'pointer',
                  borderRadius: '50%',
                }}
                title="Cerrar seguimiento"
              >
                <X size={16} />
              </button>
            )}
            <button
              type="button"
              style={{
                background: 'none',
                border: 'none',
                color: '#64748b',
                padding: 4,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
              }}
            >
              {isExpanded ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
            </button>
          </div>
        </div>

        {/* Stepper Horizontal Progress Bar (Inspired by User Reference 2) */}
        {!['REJECTED', 'CANCELLED'].includes(rawStatus) && (
          <div style={{ padding: '14px 16px 16px' }}>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                position: 'relative',
              }}
            >
              {/* Background Connecting Line */}
              <div
                style={{
                  position: 'absolute',
                  top: '16px',
                  left: '20px',
                  right: '20px',
                  height: 3,
                  backgroundColor: '#e2e8f0',
                  zIndex: 1,
                }}
              />
              {/* Active Fill Line */}
              <div
                style={{
                  position: 'absolute',
                  top: '16px',
                  left: '20px',
                  width: activeStep === 1 ? '15%' : activeStep === 2 ? '50%' : '100%',
                  height: 3,
                  backgroundColor: activeStep === 3 ? '#16a34a' : '#2563eb',
                  transition: 'width 0.5s ease',
                  zIndex: 2,
                }}
              />

              {/* Step 1: Aceptado */}
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: 6,
                  zIndex: 3,
                  minWidth: 70,
                }}
              >
                <div
                  style={{
                    width: 32,
                    height: 32,
                    borderRadius: '50%',
                    backgroundColor: activeStep >= 1 ? (activeStep > 1 ? '#16a34a' : '#2563eb') : '#e2e8f0',
                    color: '#ffffff',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    boxShadow: activeStep === 1 ? '0 0 0 4px #dbeafe' : 'none',
                    transition: 'all 0.3s ease',
                  }}
                >
                  {activeStep > 1 ? <CheckCircle2 size={16} /> : <Clock size={16} />}
                </div>
                <span
                  style={{
                    fontSize: '0.72rem',
                    fontWeight: activeStep >= 1 ? 700 : 500,
                    color: activeStep >= 1 ? '#1e293b' : '#94a3b8',
                  }}
                >
                  Aceptado
                </span>
              </div>

              {/* Step 2: Preparando */}
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: 6,
                  zIndex: 3,
                  minWidth: 70,
                }}
              >
                <div
                  style={{
                    width: 32,
                    height: 32,
                    borderRadius: '50%',
                    backgroundColor: activeStep >= 2 ? (activeStep > 2 ? '#16a34a' : '#2563eb') : '#f1f5f9',
                    color: activeStep >= 2 ? '#ffffff' : '#94a3b8',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    boxShadow: activeStep === 2 ? '0 0 0 4px #dbeafe' : 'none',
                    transition: 'all 0.3s ease',
                  }}
                >
                  {activeStep > 2 ? <CheckCircle2 size={16} /> : <ChefHat size={16} />}
                </div>
                <span
                  style={{
                    fontSize: '0.72rem',
                    fontWeight: activeStep >= 2 ? 700 : 500,
                    color: activeStep >= 2 ? '#1e293b' : '#94a3b8',
                  }}
                >
                  Preparando
                </span>
              </div>

              {/* Step 3: Listo / Entregado */}
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: 6,
                  zIndex: 3,
                  minWidth: 70,
                }}
              >
                <div
                  style={{
                    width: 32,
                    height: 32,
                    borderRadius: '50%',
                    backgroundColor: activeStep >= 3 ? '#16a34a' : '#f1f5f9',
                    color: activeStep >= 3 ? '#ffffff' : '#94a3b8',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    boxShadow: activeStep === 3 ? '0 0 0 4px #bbf7d0' : 'none',
                    transition: 'all 0.3s ease',
                  }}
                >
                  {rawStatus === 'IN_DELIVERY' ? <Bike size={16} /> : <ShoppingBag size={16} />}
                </div>
                <span
                  style={{
                    fontSize: '0.72rem',
                    fontWeight: activeStep >= 3 ? 700 : 500,
                    color: activeStep >= 3 ? '#16a34a' : '#94a3b8',
                  }}
                >
                  {rawStatus === 'IN_DELIVERY' ? 'En camino' : 'Listo'}
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Detailed Timeline View (Expandable Drawer / Modal - Inspired by User Reference 3) */}
        {isExpanded && (
          <div
            style={{
              padding: '16px',
              borderTop: '1px solid #f1f5f9',
              backgroundColor: '#fafafa',
              display: 'flex',
              flexDirection: 'column',
              gap: 14,
            }}
          >
            {/* Items Summary if available */}
            {order.items_summary && order.items_summary.length > 0 && (
              <div>
                <div style={{ fontSize: '0.8rem', fontWeight: 700, color: '#475569', marginBottom: 6 }}>
                  Artículos del pedido:
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  {order.items_summary.map((it, idx) => (
                    <div
                      key={idx}
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        fontSize: '0.85rem',
                        color: '#334155',
                      }}
                    >
                      <span>
                        {it.quantity}x {it.name}
                      </span>
                      <span style={{ fontWeight: 600 }}>{formatMoney(it.line_total_cents)}</span>
                    </div>
                  ))}
                </div>
                <div
                  style={{
                    marginTop: 8,
                    paddingTop: 8,
                    borderTop: '1px dashed #cbd5e1',
                    display: 'flex',
                    justifyContent: 'space-between',
                    fontWeight: 800,
                    fontSize: '0.9rem',
                    color: '#0f172a',
                  }}
                >
                  <span>Total</span>
                  <span>{formatMoney(order.total_cents)}</span>
                </div>
              </div>
            )}

            {/* WhatsApp or Contact Action */}
            {Boolean(whatsappPhone || order.whatsapp_url) && (
              <a
                href={
                  order.whatsapp_url ||
                  `https://wa.me/${whatsappPhone}?text=${encodeURIComponent(
                    `Hola, tengo una consulta sobre mi pedido ${displayFolio}`
                  )}`
                }
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 8,
                  backgroundColor: '#25D366',
                  color: '#ffffff',
                  textDecoration: 'none',
                  padding: '10px 14px',
                  borderRadius: 10,
                  fontSize: '0.85rem',
                  fontWeight: 700,
                }}
              >
                <span>Consultar por WhatsApp</span>
                <ExternalLink size={14} />
              </a>
            )}

            {/* Close tracker if delivered */}
            {isTerminal && (
              <button
                type="button"
                onClick={handleDismiss}
                style={{
                  backgroundColor: '#f1f5f9',
                  color: '#475569',
                  border: 'none',
                  padding: '8px 12px',
                  borderRadius: 8,
                  fontSize: '0.825rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                Ocultar seguimiento
              </button>
            )}
          </div>
        )}
      </aside>
    </>
  );
};
