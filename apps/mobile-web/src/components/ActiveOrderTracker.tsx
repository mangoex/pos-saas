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
import { fetchPublicOrderTracking, formatMoney, saveTrackedOrder, getTrackedOrders, clearTrackedOrder } from '../api';

interface ActiveOrderTrackerProps {
  initialOrder: TrackedActiveOrder | null;
  initialOrders?: TrackedActiveOrder[];
  onClearOrder?: (publicReference?: string) => void;
  whatsappPhone?: string;
  restaurantName?: string;
  branchId?: string;
}

export const ActiveOrderTracker: React.FC<ActiveOrderTrackerProps> = ({
  initialOrder,
  initialOrders,
  onClearOrder,
  whatsappPhone,
  restaurantName,
  branchId,
}) => {
  const [ordersList, setOrdersList] = useState<TrackedActiveOrder[]>(() => {
    if (initialOrders && initialOrders.length > 0) return initialOrders;
    const fromStorage = getTrackedOrders(branchId);
    if (fromStorage.length > 0) return fromStorage;
    return initialOrder ? [initialOrder] : [];
  });
  const [selectedReference, setSelectedReference] = useState<string | null>(
    () => ordersList[0]?.public_reference || initialOrder?.public_reference || null
  );
  const [isExpanded, setIsExpanded] = useState(false);
  const [isOrderPickerOpen, setIsOrderPickerOpen] = useState(false);
  const previousStatus = useRef<string | null>(null);

  // Sync with prop updates
  useEffect(() => {
    if (initialOrders && initialOrders.length > 0) {
      setOrdersList(initialOrders);
      if (!selectedReference || !initialOrders.some((o) => o.public_reference === selectedReference)) {
        setSelectedReference(initialOrders[0].public_reference);
      }
    } else if (initialOrder) {
      setOrdersList((prev) => {
        const idx = prev.findIndex((o) => o.public_reference === initialOrder.public_reference);
        if (idx >= 0) {
          const next = [...prev];
          next[idx] = { ...next[idx], ...initialOrder };
          return next;
        }
        return [initialOrder, ...prev];
      });
      if (!selectedReference) {
        setSelectedReference(initialOrder.public_reference);
      }
    }
  }, [initialOrder, initialOrders, selectedReference]);

  const order = ordersList.find((o) => o.public_reference === selectedReference) || ordersList[0] || null;

  // Polling every 3.5 seconds for live state transition updates across active orders
  useEffect(() => {
    if (ordersList.length === 0) return;

    const poll = async () => {
      let anyChanged = false;
      const updatedList = await Promise.all(
        ordersList.map(async (curr) => {
          const st = (curr.operational_status || curr.status || '').toUpperCase();
          if (['DELIVERED', 'CLOSED', 'CANCELLED', 'REJECTED'].includes(st)) {
            return curr;
          }
          const refreshed = await fetchPublicOrderTracking(curr.public_reference);
          if (refreshed) {
            const merged: TrackedActiveOrder = {
              ...curr,
              status: refreshed.status,
              operational_status: refreshed.operational_status,
              folio: refreshed.folio || curr.folio,
            };
            saveTrackedOrder(merged);

            // Haptic vibration feedback if selected order becomes READY
            const newStatus = (refreshed.operational_status || refreshed.status || '').toUpperCase();
            if (curr.public_reference === order?.public_reference && newStatus === 'READY' && previousStatus.current !== 'READY') {
              if (typeof navigator !== 'undefined' && 'vibrate' in navigator) {
                try {
                  navigator.vibrate([150, 60, 150]);
                } catch {
                  // Ignore unsupported
                }
              }
            }
            if (curr.public_reference === order?.public_reference) {
              previousStatus.current = newStatus;
            }
            anyChanged = true;
            return merged;
          }
          return curr;
        })
      );

      if (anyChanged) {
        setOrdersList(updatedList);
      }
    };

    poll();
    const interval = window.setInterval(poll, 3500);

    return () => window.clearInterval(interval);
  }, [ordersList.map((o) => o.public_reference).join(','), order?.public_reference]);

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
  } else if (rawStatus === 'ACCEPTED' || ['IN_PRODUCTION', 'IN_PREPARATION', 'SENT_TO_PRODUCTION', 'CONFIRMED'].includes(rawStatus)) {
    activeStep = 2;
    statusTitle = 'En Preparación 🍳';
    statusSubtitle = '¡Comanda aceptada! Nuestros chefs están cocinando tu orden';
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
    const remaining = ordersList.filter((o) => o.public_reference !== order.public_reference);
    setOrdersList(remaining);
    if (remaining.length > 0) {
      setSelectedReference(remaining[0].public_reference);
    } else {
      setSelectedReference(null);
    }
    if (onClearOrder) onClearOrder(order.public_reference);
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
                {ordersList.length > 1 ? (
                  <div style={{ position: 'relative' }}>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        setIsOrderPickerOpen(!isOrderPickerOpen);
                      }}
                      style={{
                        backgroundColor: '#ffffff',
                        color: '#0f172a',
                        fontSize: '0.75rem',
                        fontWeight: 700,
                        padding: '2px 8px',
                        borderRadius: 6,
                        border: '1.5px solid #cbd5e1',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 4,
                        cursor: 'pointer',
                        boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
                      }}
                      title="Seleccionar comanda activa"
                      aria-label="Ver lista de pedidos activos"
                    >
                      <span>{displayFolio}</span>
                      <span style={{ fontSize: '0.68rem', color: '#ff5722', fontWeight: 800 }}>
                        ({ordersList.length})
                      </span>
                      <ChevronDown size={13} color="#64748b" />
                    </button>

                    {isOrderPickerOpen && (
                      <div
                        onClick={(e) => e.stopPropagation()}
                        style={{
                          position: 'absolute',
                          top: '100%',
                          left: 0,
                          marginTop: 6,
                          backgroundColor: '#ffffff',
                          borderRadius: 12,
                          boxShadow: '0 10px 25px -5px rgba(0,0,0,0.15)',
                          border: '1px solid #cbd5e1',
                          padding: 6,
                          zIndex: 100,
                          minWidth: 200,
                          display: 'flex',
                          flexDirection: 'column',
                          gap: 4,
                        }}
                      >
                        <div style={{ padding: '4px 8px', fontSize: '0.7rem', fontWeight: 700, color: '#64748b', textTransform: 'uppercase' }}>
                          Tus comandas activas:
                        </div>
                        {ordersList.map((ord) => {
                          const isSel = ord.public_reference === order.public_reference;
                          const ordFolio = ord.folio ? `#${ord.folio}` : `#${ord.public_reference}`;
                          const ordSt = (ord.operational_status || ord.status || '').toUpperCase();
                          const stLabel = ordSt === 'READY' ? 'Listo 🎉' : ['ACCEPTED', 'IN_PRODUCTION'].includes(ordSt) ? 'Preparando 🍳' : 'Recibido';
                          return (
                            <button
                              key={ord.public_reference}
                              type="button"
                              onClick={() => {
                                setSelectedReference(ord.public_reference);
                                setIsOrderPickerOpen(false);
                              }}
                              style={{
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'space-between',
                                padding: '6px 8px',
                                borderRadius: 6,
                                border: 'none',
                                backgroundColor: isSel ? '#f1f5f9' : 'transparent',
                                cursor: 'pointer',
                                textAlign: 'left',
                                width: '100%',
                              }}
                            >
                              <div>
                                <div style={{ fontSize: '0.78rem', fontWeight: isSel ? 800 : 600, color: isSel ? '#0f172a' : '#334155' }}>
                                  {ordFolio}
                                </div>
                                <div style={{ fontSize: '0.68rem', color: '#64748b' }}>
                                  {stLabel}
                                </div>
                              </div>
                              {isSel && <CheckCircle2 size={14} color="#16a34a" />}
                            </button>
                          );
                        })}
                      </div>
                    )}
                  </div>
                ) : (
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
                )}
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
              {/* Background Connecting Track (strictly from Step 1 center to Step 3 center) */}
              <div
                style={{
                  position: 'absolute',
                  top: '16px',
                  left: '35px',
                  right: '35px',
                  height: 3,
                  backgroundColor: '#e2e8f0',
                  zIndex: 1,
                  overflow: 'hidden',
                }}
              >
                {/* Active Fill Line bounded strictly within the track */}
                <div
                  style={{
                    height: '100%',
                    width: activeStep <= 1 ? '0%' : activeStep === 2 ? '50%' : '100%',
                    backgroundColor: activeStep >= 3 ? '#16a34a' : '#2563eb',
                    transition: 'width 0.4s ease',
                  }}
                />
              </div>

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
