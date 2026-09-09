import React, { useEffect, useState } from 'react';
import { fetchApi, ApiError } from '@restaurantos/api-client';
import {
  X,
  Phone,
  MessageCircle,
  Clock,
  MapPin,
  Utensils,
  CheckCircle,
  AlertCircle,
  Bike,
  ShoppingBag,
  Tag,
  ChefHat,
  DollarSign
} from 'lucide-react';

interface OrderLineItem {
  id: string;
  product_name: string;
  quantity: number;
  unit_price_cents: number;
  line_total_cents: number;
  station?: string;
  selected_modifiers?: Array<{
    name: string;
    price_cents?: number;
    [key: string]: any;
  }>;
  line_notes?: string;
}

interface OrderDetail {
  id: string;
  folio: string;
  status: string;
  service_type?: string;
  order_type?: string;
  channel?: string;
  table_number?: string;
  total_cents: number;
  currency: string;
  created_at: string;
  owner_name?: string;
  customer_label?: string;
  customer_phone?: string;
  delivery_address?: string;
  delivery_notes?: string;
  order_notes?: string;
  cash_amount?: string;
  payment_method_intent?: string;
  customer_snapshot?: {
    name?: string;
    phone?: string;
    [key: string]: any;
  };
  delivery_address_snapshot?: {
    street?: string;
    neighborhood?: string;
    notes?: string;
    phone?: string;
    [key: string]: any;
  };
  payment_status?: string;
  payment_method?: string;
  is_public_intent?: boolean;
  public_reference?: string;
  lines?: OrderLineItem[];
}

interface MobileOrderDetailModalProps {
  orderId: string | null;
  isOpen: boolean;
  onClose: () => void;
  onOrderUpdated?: () => void;
  branchName?: string;
}

export const MobileOrderDetailModal: React.FC<MobileOrderDetailModalProps> = ({
  orderId,
  isOpen,
  onClose,
  onOrderUpdated,
  branchName,
}) => {
  const [detail, setDetail] = useState<OrderDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen || !orderId) {
      setDetail(null);
      setError(null);
      return;
    }

    let active = true;
    const fetchDetail = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await fetchApi<OrderDetail>(`/orders/${encodeURIComponent(orderId)}`);
        if (active) {
          setDetail(data);
        }
      } catch (err) {
        if (active) {
          setError(err instanceof ApiError ? err.message : 'No se pudo cargar el detalle del pedido.');
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };

    void fetchDetail();
    return () => {
      active = false;
    };
  }, [isOpen, orderId]);

  if (!isOpen) return null;

  const handleAcceptOrder = async () => {
    if (!orderId) return;
    setActionLoading(true);
    try {
      await fetchApi(`/orders/${encodeURIComponent(orderId)}/accept`, {
        method: 'POST',
      });
      if (onOrderUpdated) onOrderUpdated();
      onClose();
    } catch (err: any) {
      const msg =
        typeof err?.message === 'string'
          ? err.message
          : typeof err === 'string'
            ? err
            : 'Error al aceptar el pedido.';
      setError(msg);
    } finally {
      setActionLoading(false);
    }
  };

  const handleFulfillTransition = async (command: string = 'deliver') => {
    if (!orderId) return;
    setActionLoading(true);
    try {
      const idempotencyKey = `mobile-fulfill-${orderId}-${command}-${Date.now()}`;
      await fetchApi(`/orders/${encodeURIComponent(orderId)}/fulfillment/${encodeURIComponent(command)}`, {
        method: 'POST',
        headers: {
          'Idempotency-Key': idempotencyKey,
        },
      });
      if (onOrderUpdated) onOrderUpdated();
      onClose();
    } catch (err: any) {
      const msg =
        typeof err?.message === 'string'
          ? err.message
          : typeof err === 'string'
            ? err
            : 'Error al actualizar el estado de la comanda.';
      setError(msg);
    } finally {
      setActionLoading(false);
    }
  };

  const customerName =
    detail?.customer_snapshot?.name ||
    detail?.owner_name ||
    detail?.customer_label ||
    'Cliente';

  const rawPhone =
    detail?.customer_phone ||
    detail?.customer_snapshot?.phone ||
    detail?.delivery_address_snapshot?.phone ||
    '';

  const cleanPhone = rawPhone.replace(/\D/g, '');
  const formattedPhone =
    cleanPhone.length === 10
      ? `52${cleanPhone}`
      : cleanPhone;

  const orderFolio = detail?.folio || orderId?.slice(-6).toUpperCase() || '';
  const orderTotal = detail ? (detail.total_cents / 100).toFixed(2) : '0.00';

  const isDineIn =
    detail?.service_type?.toLowerCase() === 'dine-in' ||
    detail?.order_type?.toLowerCase() === 'dine-in' ||
    detail?.service_type?.toLowerCase() === 'local';

  const isDelivery =
    detail?.service_type?.toLowerCase() === 'delivery' ||
    detail?.order_type?.toLowerCase() === 'delivery';

  const tableNumber =
    detail?.table_number ||
    (detail as any)?.table ||
    (detail?.customer_snapshot as any)?.table_number ||
    '';

  const orderNotes =
    detail?.order_notes ||
    (detail as any)?.notes ||
    (detail?.customer_snapshot as any)?.order_notes ||
    detail?.delivery_notes ||
    detail?.delivery_address_snapshot?.notes ||
    '';

  const cashAmount =
    detail?.cash_amount ||
    (detail as any)?.cash_amount ||
    (detail?.customer_snapshot as any)?.cash_amount ||
    '';

  const paymentMethodRaw =
    detail?.payment_method_intent ||
    detail?.payment_method ||
    (detail?.customer_snapshot as any)?.payment_method ||
    '';

  const paymentMethodLabel =
    paymentMethodRaw === 'cash'
      ? 'Efectivo'
      : paymentMethodRaw === 'card'
        ? 'Tarjeta'
        : paymentMethodRaw === 'transfer'
          ? 'Transferencia'
          : paymentMethodRaw;

  const fullAddress =
    detail?.delivery_address ||
    detail?.delivery_address_snapshot?.street ||
    '';

  const addressNotes =
    detail?.delivery_notes ||
    detail?.delivery_address_snapshot?.notes ||
    '';

  const isUnaccepted = Boolean(
    detail?.is_public_intent ||
    ['PENDING', 'PENDING_REVIEW', 'DRAFT'].includes(detail?.status?.toUpperCase() || '')
  );

  const isReadyOrInPrep = Boolean(
    ['ACCEPTED', 'READY', 'IN_PRODUCTION', 'IN_PREPARATION', 'SENT_TO_PRODUCTION', 'IN_DELIVERY'].includes(
      detail?.status?.toUpperCase() || ''
    )
  );

  const isCompleted = Boolean(
    ['DELIVERED', 'CLOSED', 'CANCELLED', 'REJECTED'].includes(detail?.status?.toUpperCase() || '')
  );

  // WhatsApp prefilled message
  const waStatusText = isCompleted
    ? 'ha sido entregado con éxito. ¡Buen provecho!'
    : isReadyOrInPrep
      ? 'ya está listo para recoger / en camino.'
      : 'ha sido recibido y está por prepararse.';

  const waMessage = encodeURIComponent(
    `¡Hola ${customerName}! Te escribimos de *${branchName || 'nuestro restaurante'}* para avisarte que tu pedido *#${orderFolio}* ${waStatusText} Total: $${orderTotal} MXN. ¡Muchas gracias!`
  );

  const waUrl = formattedPhone ? `https://wa.me/${formattedPhone}?text=${waMessage}` : '';

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.65)',
        backdropFilter: 'blur(3px)',
        zIndex: 9999,
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'flex-end',
        animation: 'fadeIn 0.2s ease-out',
      }}
      onClick={onClose}
    >
      <div
        style={{
          backgroundColor: '#ffffff',
          borderTopLeftRadius: 20,
          borderTopRightRadius: 20,
          maxHeight: '90vh',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          boxShadow: '0 -10px 25px rgba(0,0,0,0.2)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          style={{
            padding: '16px 20px',
            borderBottom: '1px solid #e2e8f0',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            backgroundColor: '#f8fafc',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span
              style={{
                fontSize: '1.25rem',
                fontWeight: 800,
                color: '#0f172a',
                letterSpacing: '-0.02em',
              }}
            >
              #{orderFolio}
            </span>
            <span
              style={{
                fontSize: '0.75rem',
                fontWeight: 700,
                textTransform: 'uppercase',
                padding: '4px 8px',
                borderRadius: 6,
                backgroundColor:
                  isCompleted
                    ? '#f1f5f9'
                    : isReadyOrInPrep
                      ? '#dcfce7'
                      : '#e0f2fe',
                color:
                  isCompleted
                    ? '#475569'
                    : isReadyOrInPrep
                      ? '#166534'
                      : '#0369a1',
              }}
            >
              {isCompleted
                ? 'Entregado'
                : isReadyOrInPrep
                  ? 'Listo para Entrega'
                  : 'Por Aceptar'}
            </span>
          </div>
          <button
            onClick={onClose}
            style={{
              border: 'none',
              background: '#e2e8f0',
              borderRadius: '50%',
              width: 34,
              height: 34,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: 'pointer',
              color: '#475569',
            }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Scrollable Content */}
        <div style={{ padding: '16px 20px', overflowY: 'auto', flex: 1 }}>
          {loading && (
            <div style={{ textAlign: 'center', padding: '40px 0', color: '#64748b' }}>
              <Clock className="animate-spin" size={28} style={{ margin: '0 auto 8px' }} />
              <p style={{ margin: 0, fontSize: '0.9rem' }}>Cargando detalles de la comanda...</p>
            </div>
          )}

          {error && (
            <div
              style={{
                backgroundColor: '#fef2f2',
                color: '#991b1b',
                padding: '12px 14px',
                borderRadius: 8,
                marginBottom: 14,
                fontSize: '0.875rem',
                display: 'flex',
                alignItems: 'center',
                gap: 8,
              }}
            >
              <AlertCircle size={18} />
              <span>{typeof error === 'string' ? error : JSON.stringify(error)}</span>
            </div>
          )}

          {!loading && detail && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              {/* Customer & Direct Contact Card */}
              <div
                style={{
                  backgroundColor: '#f8fafc',
                  border: '1px solid #e2e8f0',
                  borderRadius: 12,
                  padding: 14,
                }}
              >
                <div style={{ fontSize: '0.8rem', color: '#64748b', fontWeight: 600, marginBottom: 4 }}>
                  CLIENTE Y CONTACTO
                </div>
                <div style={{ fontSize: '1.05rem', fontWeight: 700, color: '#1e293b' }}>
                  {customerName}
                </div>
                {rawPhone ? (
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                      marginTop: 10,
                      flexWrap: 'wrap',
                    }}
                  >
                    <a
                      href={waUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: 6,
                        backgroundColor: '#25D366',
                        color: '#ffffff',
                        padding: '8px 14px',
                        borderRadius: 8,
                        fontWeight: 600,
                        fontSize: '0.875rem',
                        textDecoration: 'none',
                      }}
                    >
                      <MessageCircle size={16} />
                      WhatsApp
                    </a>
                    <a
                      href={`tel:${cleanPhone}`}
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: 6,
                        backgroundColor: '#ffffff',
                        border: '1px solid #cbd5e1',
                        color: '#334155',
                        padding: '8px 14px',
                        borderRadius: 8,
                        fontWeight: 600,
                        fontSize: '0.875rem',
                        textDecoration: 'none',
                      }}
                    >
                      <Phone size={16} />
                      {rawPhone}
                    </a>
                  </div>
                ) : (
                  <div style={{ fontSize: '0.85rem', color: '#94a3b8', marginTop: 4 }}>
                    Sin teléfono registrado
                  </div>
                )}
              </div>

              {/* Service Modality Card */}
              <div
                style={{
                  backgroundColor: '#f8fafc',
                  border: '1px solid #e2e8f0',
                  borderRadius: 12,
                  padding: 14,
                }}
              >
                <div style={{ fontSize: '0.8rem', color: '#64748b', fontWeight: 600, marginBottom: 4 }}>
                  MODALIDAD DE ENTREGA
                </div>
                {isDineIn ? (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#0f172a', fontWeight: 600 }}>
                    <Utensils size={18} color="#0284c7" />
                    <span>Para Comer Aquí {tableNumber ? `— Mesa: ${tableNumber}` : '(En barra)'}</span>
                  </div>
                ) : isDelivery ? (
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#0f172a', fontWeight: 600 }}>
                      <Bike size={18} color="#059669" />
                      <span>Envío a Domicilio</span>
                    </div>
                    {fullAddress && (
                      <div
                        style={{
                          marginTop: 6,
                          fontSize: '0.875rem',
                          color: '#334155',
                          display: 'flex',
                          alignItems: 'flex-start',
                          gap: 6,
                        }}
                      >
                        <MapPin size={16} style={{ flexShrink: 0, marginTop: 2 }} color="#64748b" />
                        <div>
                          <div>{fullAddress}</div>
                          {addressNotes && (
                            <div style={{ fontSize: '0.8rem', color: '#64748b', fontStyle: 'italic', marginTop: 2 }}>
                              Ref: {addressNotes}
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#0f172a', fontWeight: 600 }}>
                    <ShoppingBag size={18} color="#d97706" />
                    <span>Para Llevar / Recoger en Barra</span>
                  </div>
                )}
              </div>

              {/* Customer Notes & Special Instructions Card */}
              {Boolean(orderNotes) && (
                <div
                  style={{
                    backgroundColor: '#fffbeb',
                    border: '1px solid #fde68a',
                    borderRadius: 12,
                    padding: 14,
                  }}
                >
                  <div style={{ fontSize: '0.8rem', color: '#b45309', fontWeight: 700, marginBottom: 4, display: 'flex', alignItems: 'center', gap: 6 }}>
                    📝 INSTRUCCIONES / COMENTARIOS DEL CLIENTE
                  </div>
                  <div style={{ fontSize: '0.95rem', fontWeight: 600, color: '#78350f', whiteSpace: 'pre-wrap' }}>
                    {orderNotes}
                  </div>
                </div>
              )}

              {/* Order Lines & Modifiers */}
              <div
                style={{
                  backgroundColor: '#ffffff',
                  border: '1px solid #e2e8f0',
                  borderRadius: 12,
                  padding: 14,
                }}
              >
                <div style={{ fontSize: '0.8rem', color: '#64748b', fontWeight: 600, marginBottom: 10 }}>
                  PRODUCTOS Y COMANDA
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  {detail.lines && detail.lines.length > 0 ? (
                    detail.lines.map((line) => (
                      <div
                        key={line.id}
                        style={{
                          paddingBottom: 10,
                          borderBottom: '1px dashed #e2e8f0',
                        }}
                      >
                        <div
                          style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'baseline',
                            fontWeight: 700,
                            fontSize: '0.95rem',
                            color: '#0f172a',
                          }}
                        >
                          <span>
                            <span style={{ color: '#0284c7', marginRight: 6 }}>{line.quantity}x</span>
                            {line.product_name}
                          </span>
                          <span style={{ color: '#334155', fontSize: '0.9rem' }}>
                            ${((line.line_total_cents || 0) / 100).toFixed(2)}
                          </span>
                        </div>

                        {/* Modifiers / Extras */}
                        {line.selected_modifiers && line.selected_modifiers.length > 0 && (
                          <div style={{ marginTop: 4, paddingLeft: 16 }}>
                            {line.selected_modifiers.map((mod, idx) => (
                              <div
                                key={idx}
                                style={{
                                  fontSize: '0.8125rem',
                                  color: '#475569',
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: 4,
                                }}
                              >
                                <span style={{ color: '#059669', fontWeight: 600 }}>+</span>
                                <span>{mod.name}</span>
                                {mod.price_cents ? (
                                  <span style={{ color: '#64748b', fontSize: '0.75rem' }}>
                                    (+${(mod.price_cents / 100).toFixed(2)})
                                  </span>
                                ) : null}
                              </div>
                            ))}
                          </div>
                        )}

                        {/* Product notes */}
                        {line.line_notes && (
                          <div
                            style={{
                              marginTop: 4,
                              paddingLeft: 16,
                              fontSize: '0.825rem',
                              color: '#b45309',
                              fontWeight: 600,
                              fontStyle: 'italic',
                              display: 'flex',
                              alignItems: 'center',
                              gap: 4,
                            }}
                          >
                            <span>📝 Nota:</span> <span>{line.line_notes}</span>
                          </div>
                        )}
                      </div>
                    ))
                  ) : (
                    <div style={{ fontSize: '0.85rem', color: '#94a3b8' }}>
                      Sin partidas registradas.
                    </div>
                  )}
                </div>

                {/* Total & Payment */}
                <div
                  style={{
                    marginTop: 12,
                    paddingTop: 10,
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                  }}
                >
                  <div>
                    <div style={{ fontSize: '0.75rem', color: '#64748b', textTransform: 'uppercase', fontWeight: 600 }}>
                      TOTAL DEL PEDIDO
                    </div>
                    <div style={{ fontSize: '0.8rem', color: '#059669', fontWeight: 600 }}>
                      {detail.payment_status === 'CONFIRMED' ? 'Pagado' : 'Cobro pendiente'}
                      {paymentMethodLabel ? ` • ${paymentMethodLabel}` : ''}
                      {cashAmount ? ` (Paga con: $${cashAmount})` : ''}
                    </div>
                  </div>
                  <div style={{ fontSize: '1.4rem', fontWeight: 800, color: '#0f172a' }}>
                    ${orderTotal} <span style={{ fontSize: '0.85rem', fontWeight: 500, color: '#64748b' }}>MXN</span>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Operational Footer Actions */}
        <div
          style={{
            padding: '14px 20px',
            borderTop: '1px solid #e2e8f0',
            backgroundColor: '#ffffff',
            display: 'flex',
            flexDirection: 'column',
            gap: 10,
          }}
        >
          {isUnaccepted && (
            <button
              onClick={handleAcceptOrder}
              disabled={actionLoading}
              style={{
                width: '100%',
                backgroundColor: '#10b981',
                color: '#ffffff',
                border: 'none',
                borderRadius: 10,
                padding: '12px',
                fontWeight: 700,
                fontSize: '1rem',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 8,
                cursor: 'pointer',
              }}
            >
              <CheckCircle size={18} />
              {actionLoading ? 'Aceptando...' : 'Aceptar Pedido'}
            </button>
          )}

          {isReadyOrInPrep && (
            <button
              onClick={() => handleFulfillTransition('deliver')}
              disabled={actionLoading}
              style={{
                width: '100%',
                backgroundColor: '#0f172a',
                color: '#ffffff',
                border: 'none',
                borderRadius: 10,
                padding: '12px',
                fontWeight: 700,
                fontSize: '1rem',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 8,
                cursor: 'pointer',
              }}
            >
              <CheckCircle size={18} />
              {actionLoading ? 'Finalizando...' : 'Finalizar / Entregado'}
            </button>
          )}

          {isCompleted && (
            <div
              style={{
                width: '100%',
                backgroundColor: '#f1f5f9',
                color: '#166534',
                borderRadius: 10,
                padding: '12px',
                fontWeight: 700,
                fontSize: '0.95rem',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 8,
              }}
            >
              <CheckCircle size={18} color="#16a34a" />
              Pedido Entregado y Finalizado
            </div>
          )}

          <button
            onClick={onClose}
            style={{
              width: '100%',
              backgroundColor: '#f1f5f9',
              color: '#475569',
              border: 'none',
              borderRadius: 10,
              padding: '10px',
              fontWeight: 600,
              fontSize: '0.9rem',
              cursor: 'pointer',
            }}
          >
            Cerrar
          </button>
        </div>
      </div>
    </div>
  );
};
