import React, { useEffect, useRef, useState } from 'react';
import { fetchApi, ApiError, formatOrderModifier } from '@restaurantos/api-client';
import { runMobileOrderCommand, pendingMobileOrderCommand, type MobileCommandAction } from './mobileOrderRecovery';
import {
  X,
  Phone,
  MessageCircle,
  Clock,
  MapPin,
  Utensils,
  CheckCircle,
  XCircle,
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
  selected_modifiers?: unknown[];
  line_notes?: string;
}

interface OrderDetail {
  id: string;
  organization_id: string;
  branch_id: string;
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
  onOrderAccepted?: () => void;
  onOrderRejected?: () => void;
  branchName?: string;
}

export const MobileOrderDetailModal: React.FC<MobileOrderDetailModalProps> = ({
  orderId,
  isOpen,
  onClose,
  onOrderUpdated,
  onOrderAccepted,
  onOrderRejected,
  branchName,
}) => {
  const [detail, setDetail] = useState<OrderDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [paymentMethod, setPaymentMethod] = useState<'cash' | 'card' | 'transfer'>('cash');
  const [hasPendingRecovery, setHasPendingRecovery] = useState(false);
  const activeOrder = useRef(orderId);
  const viewEpoch = useRef(0);
  activeOrder.current = isOpen ? orderId : null;
  const currentToken = () => {
    try { return localStorage.getItem('auth_token') || sessionStorage.getItem('auth_token'); }
    catch { return null; }
  };


  useEffect(() => {
    viewEpoch.current += 1;
    setActionLoading(false);
    setDetail(null);
    if (!isOpen || !orderId) {
      setError(null);
      setNotice(null);
      return;
    }

    let active = true;
    const session = currentToken();
    setHasPendingRecovery(false);
    setLoading(true);
    setError(null);
    setNotice(null);

    fetchApi<OrderDetail>(`/orders/${encodeURIComponent(orderId)}`)
      .then(async (data: OrderDetail) => {
        if (!active || currentToken() !== session) return;
        const profile = await fetchApi<{ user: { id: string } }>(
          `/auth/session?branch_id=${encodeURIComponent(data.branch_id)}`,
        );
        if (!active || currentToken() !== session) return;
        const pending = pendingMobileOrderCommand({ organizationId: data.organization_id,
          branchId: data.branch_id, actorId: profile.user.id, orderId: data.id }, localStorage);
        setHasPendingRecovery(Boolean(pending));
        setDetail(data);
        if (pending && ['cash', 'card', 'transfer'].includes(pending.method)) {
          setPaymentMethod(pending.method as 'cash' | 'card' | 'transfer');
        } else if (data.payment_method_intent) {
          setPaymentMethod(
            data.payment_method_intent === 'card'
              ? 'card'
              : data.payment_method_intent === 'transfer'
                ? 'transfer'
                : 'cash'
          );
        }
      })
      .catch((err: any) => {
        if (!active) return;
        setError(err instanceof ApiError ? err.message : 'No se pudo cargar el detalle del pedido.');
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
      viewEpoch.current += 1;
    };
  }, [isOpen, orderId]);

  if (!isOpen) return null;

  const handleAcceptOrder = async () => {
    if (!orderId) return;
    setActionLoading(true);
    setError(null);
    try {
      await fetchApi(`/orders/${encodeURIComponent(orderId)}/accept`, {
        method: 'POST',
      });
      if (onOrderAccepted) {
        onOrderAccepted();
      } else if (onOrderUpdated) {
        onOrderUpdated();
      }
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

  const handleRejectOrder = async () => {
    if (!orderId) return;
    const confirmReject = window.confirm('¿Estás seguro de que deseas rechazar este pedido? Se moverá al historial como rechazado.');
    if (!confirmReject) return;
    setActionLoading(true);
    setError(null);
    try {
      await fetchApi(`/orders/${encodeURIComponent(orderId)}/reject`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: 'Rechazado desde detalle móvil' }),
      });
      if (onOrderRejected) {
        onOrderRejected();
      } else if (onOrderUpdated) {
        onOrderUpdated();
      }
      onClose();
    } catch (err: any) {
      const msg =
        typeof err?.message === 'string'
          ? err.message
          : typeof err === 'string'
            ? err
            : 'Error al rechazar el pedido.';
      setError(msg);
    } finally {
      setActionLoading(false);
    }
  };

  const executeFinancialCommand = async (action: MobileCommandAction, recover = false) => {
    if (!orderId || !detail || actionLoading) return;
    const requestedOrder = orderId;
    const requestedEpoch = viewEpoch.current;
    const currentView = () => activeOrder.current === requestedOrder && viewEpoch.current === requestedEpoch;
    setActionLoading(true);
    setError(null);
    setNotice(null);
    try {
      const session = currentToken();
      if (!session) throw new Error('La sesión no está disponible. Inicia sesión nuevamente.');
      const profile = await fetchApi<{ user: { id: string } }>(
        `/auth/session?branch_id=${encodeURIComponent(detail.branch_id)}`,
      );
      if (currentToken() !== session || !currentView()) {
        throw new Error('La sesión o el pedido cambió. Abre nuevamente el pedido.');
      }
      const scope = { organizationId: detail.organization_id, branchId: detail.branch_id,
        actorId: profile.user.id, orderId: detail.id };
      const pending = pendingMobileOrderCommand(scope, localStorage);
      setHasPendingRecovery(Boolean(pending));
      if (recover && !pending) {
        const refreshed = await fetchApi<OrderDetail>(`/orders/${encodeURIComponent(detail.id)}`);
        if (currentView() && currentToken() === session) {
          setDetail(refreshed);
          setNotice('No hay un intento guardado. Se actualizó el estado sin iniciar un cobro.');
        }
        return;
      }
      const selectedAction = recover && pending ? pending.action : action;
      const result = await runMobileOrderCommand({ scope, action: selectedAction,
        method: recover && pending ? pending.method : paymentMethod,
        registerId: recover && pending ? pending.registerId : localStorage.getItem('pos_register_id') || 'CAJA-01',
        session,
      }, {
        storage: localStorage, api: fetchApi, currentSession: currentToken,
        newKey: () => crypto.randomUUID(),
        lock: navigator.locks ? async (name, operation) => await navigator.locks.request(name, operation) : undefined,
      });
      if (!currentView() || currentToken() !== session) return;
      setDetail((previous) => previous ? { ...previous, ...result.order,
        payment_method: result.payment?.method || previous.payment_method } : null);
      setHasPendingRecovery(false);
      setNotice(result.payment ? 'Cobro confirmado; recibo recuperado.' : 'Estado del pedido actualizado.');
      if (onOrderUpdated) onOrderUpdated();
      if (selectedAction !== 'pay') onClose();
    } catch (err: unknown) {
      if (!currentView()) return;
      let message = err instanceof Error ? err.message : 'No se pudo completar la operación.';
      if (message.includes('cash_shift_not_open') || message.includes('OPEN cash shift is required')) {
        message = 'La caja está cerrada. Abre el turno y recupera el intento pendiente.';
      }
      setError(`${message} Si el envío quedó pendiente, usa Recuperar operación pendiente.`);
      // A failed response may have committed. Recovery reads durable local and server state.
      setHasPendingRecovery(true);
    } finally {
      if (currentView()) setActionLoading(false);
    }
  };

  const handleDeliverAndPay = () => executeFinancialCommand('pay_and_deliver');
  const handleConfirmPaymentOnly = () => executeFinancialCommand('pay');

  const handleMarkOrderReadyInModal = async () => {
    if (!detail?.id || actionLoading) return;
    setActionLoading(true);
    setError(null);
    try {
      const updated = await fetchApi<OrderDetail>(`/orders/${encodeURIComponent(detail.id)}/ready`, {
        method: 'POST',
      });
      setDetail(updated);
      setNotice('Comanda marcada como LISTA.');
      if (onOrderUpdated) onOrderUpdated();
    } catch (err: any) {
      setError(err instanceof ApiError ? err.message : 'Error al marcar comanda como lista.');
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

  const isCompleted = Boolean(
    ['DELIVERED', 'CLOSED', 'CANCELLED', 'REJECTED', 'EXPIRED'].includes(detail?.status?.toUpperCase() || '')
  );

  const isUnaccepted = Boolean(
    !isCompleted &&
    ((detail?.is_public_intent && detail?.status?.toUpperCase() !== 'ACCEPTED') ||
    ['PENDING', 'PENDING_REVIEW', 'DRAFT'].includes(detail?.status?.toUpperCase() || ''))
  );

  const isOrderReadyStatus = detail?.status?.toUpperCase() === 'READY';

  const isReadyOrInPrep = Boolean(
    !isUnaccepted &&
    !isCompleted &&
    ['ACCEPTED', 'READY', 'IN_PRODUCTION', 'IN_PREPARATION', 'SENT_TO_PRODUCTION', 'IN_DELIVERY'].includes(
      detail?.status?.toUpperCase() || ''
    )
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
                    ? ['REJECTED', 'CANCELLED', 'EXPIRED'].includes(detail?.status?.toUpperCase() || '')
                      ? '#fef2f2'
                      : detail?.payment_status === 'CONFIRMED'
                        ? '#dcfce7'
                        : '#fef3c7'
                    : isReadyOrInPrep
                      ? '#dcfce7'
                      : '#e0f2fe',
                color:
                  isCompleted
                    ? ['REJECTED', 'CANCELLED', 'EXPIRED'].includes(detail?.status?.toUpperCase() || '')
                      ? '#dc2626'
                      : detail?.payment_status === 'CONFIRMED'
                        ? '#166534'
                        : '#b45309'
                    : isReadyOrInPrep
                      ? '#166534'
                      : '#0369a1',
              }}
            >
              {isCompleted
                ? detail?.status?.toUpperCase() === 'EXPIRED'
                  ? 'Expirado'
                  : detail?.status?.toUpperCase() === 'REJECTED'
                  ? 'Rechazado'
                  : detail?.status?.toUpperCase() === 'CANCELLED'
                    ? 'Cancelado'
                    : detail?.payment_status === 'CONFIRMED'
                      ? 'Entregado y Pagado'
                      : 'Entregado (Por Cobrar)'
                : isReadyOrInPrep
                  ? detail?.payment_status === 'CONFIRMED'
                    ? 'Listo (Pagado)'
                    : 'Listo para Entrega'
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

          {hasPendingRecovery && (
            <div role="status" style={{ padding: 12, background: '#fff7ed', borderRadius: 8 }}>
              <p>Hay una operación por verificar. Recupera el intento antes de iniciar otro cobro.</p>
              <button type="button" disabled={actionLoading}
                style={{ width: '100%', minHeight: 44, marginTop: 8, borderRadius: 8,
                  border: '1px solid #9a3412', background: '#9a3412', color: '#fff',
                  fontWeight: 700, padding: '10px 12px', cursor: actionLoading ? 'wait' : 'pointer' }}
                onClick={() => void executeFinancialCommand('pay', true)}>
                {actionLoading ? 'Recuperando…' : 'Recuperar operación pendiente'}
              </button>
            </div>
          )}
          {notice && (
            <div
              style={{
                backgroundColor: '#f0fdf4',
                color: '#166534',
                padding: '12px 14px',
                borderRadius: 8,
                marginBottom: 14,
                fontSize: '0.875rem',
                fontWeight: 600,
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                border: '1px solid #bbf7d0',
              }}
            >
              <CheckCircle size={18} color="#16a34a" />
              <span>{notice}</span>
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
                            {line.selected_modifiers.map((mod, idx) => {
                              const presentation = formatOrderModifier(mod);
                              return <div
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
                                <span>{presentation.label}</span>
                                {presentation.priceLabel ? (
                                  <span style={{ color: '#64748b', fontSize: '0.75rem' }}>
                                    ({presentation.priceLabel})
                                  </span>
                                ) : null}
                              </div>;
                            })}
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
            <div style={{ display: 'flex', gap: 10, width: '100%' }}>
              <button
                onClick={handleRejectOrder}
                disabled={actionLoading}
                style={{
                  flex: 1,
                  backgroundColor: '#fef2f2',
                  color: '#dc2626',
                  border: '1.5px solid #fecaca',
                  borderRadius: 10,
                  padding: '12px',
                  fontWeight: 700,
                  fontSize: '0.95rem',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 8,
                  cursor: 'pointer',
                }}
              >
                <XCircle size={18} />
                {actionLoading ? 'Procesando...' : 'Rechazar'}
              </button>
              <button
                onClick={handleAcceptOrder}
                disabled={actionLoading}
                style={{
                  flex: 2,
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
            </div>
          )}

          {/* Payment Method Selector if not yet confirmed */}
          {detail && detail.status?.toUpperCase() !== 'EXPIRED' &&
            detail.payment_status !== 'CONFIRMED' && !isUnaccepted && (
            <div
              style={{
                backgroundColor: '#f8fafc',
                border: '1px solid #e2e8f0',
                borderRadius: 10,
                padding: '8px 10px',
                display: 'flex',
                flexDirection: 'column',
                gap: 6,
              }}
            >
              <div
                style={{
                  fontSize: '0.75rem',
                  fontWeight: 700,
                  color: '#475569',
                  textTransform: 'uppercase',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <span>Método de Cobro al Entregar</span>
                {cashAmount ? (
                  <span style={{ color: '#059669', fontSize: '0.72rem', fontWeight: 600 }}>
                    Paga con: ${cashAmount}
                  </span>
                ) : null}
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6 }}>
                {[
                  { id: 'cash' as const, label: 'Efectivo', icon: '💵' },
                  { id: 'card' as const, label: 'Tarjeta', icon: '💳' },
                  { id: 'transfer' as const, label: 'Transfer.', icon: '📲' },
                ].map((m) => {
                  const isSelected = paymentMethod === m.id;
                  return (
                    <button
                      key={m.id}
                      type="button"
                      onClick={() => setPaymentMethod(m.id)}
                      disabled={actionLoading || hasPendingRecovery}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: 6,
                        padding: '8px 4px',
                        borderRadius: 8,
                        border: isSelected ? '2px solid #059669' : '1px solid #cbd5e1',
                        backgroundColor: isSelected ? '#ecfdf5' : '#ffffff',
                        color: isSelected ? '#065f46' : '#64748b',
                        fontWeight: isSelected ? 700 : 600,
                        fontSize: '0.8rem',
                        cursor: 'pointer',
                        transition: 'all 0.15s ease',
                      }}
                    >
                      <span>{m.icon}</span>
                      <span>{m.label}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {isReadyOrInPrep && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, width: '100%' }}>
              {!isOrderReadyStatus && (
                <button
                  type="button"
                  onClick={handleMarkOrderReadyInModal}
                  disabled={actionLoading || loading}
                  style={{
                    width: '100%',
                    backgroundColor: '#0284c7',
                    color: '#ffffff',
                    border: 'none',
                    borderRadius: 10,
                    padding: '12px',
                    fontWeight: 700,
                    fontSize: '0.95rem',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: 8,
                    cursor: 'pointer',
                  }}
                >
                  <ChefHat size={18} />
                  {actionLoading ? 'Actualizando comanda...' : 'Marcar Pedido como Listo'}
                </button>
              )}
              <button
                onClick={handleDeliverAndPay}
                disabled={actionLoading || hasPendingRecovery || loading}
                style={{
                  width: '100%',
                  backgroundColor: detail?.payment_status === 'CONFIRMED' ? '#0f172a' : '#059669',
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
                {actionLoading
                  ? 'Procesando entrega y cobro...'
                  : detail?.payment_status === 'CONFIRMED'
                    ? 'Listo para Entregar'
                    : `Entregar y Confirmar Pago ($${orderTotal} MXN)`}
              </button>
            </div>
          )}

          {isCompleted && (
            ['REJECTED', 'EXPIRED'].includes(detail?.status?.toUpperCase() || '') ? (
              <div
                style={{
                  width: '100%',
                  backgroundColor: '#fef2f2',
                  border: '1px solid #fecaca',
                  color: '#991b1b',
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
                <XCircle size={18} color="#dc2626" />
                {detail?.status?.toUpperCase() === 'EXPIRED'
                  ? 'Pedido Expirado'
                  : 'Pedido Rechazado (No cobrado ni preparado)'}
              </div>
            ) : detail?.status?.toUpperCase() === 'CANCELLED' ? (
              <div
                style={{
                  width: '100%',
                  backgroundColor: '#fef2f2',
                  border: '1px solid #fecaca',
                  color: '#991b1b',
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
                <XCircle size={18} color="#dc2626" />
                Pedido Cancelado
              </div>
            ) : detail?.payment_status === 'CONFIRMED' ? (
              <div
                style={{
                  width: '100%',
                  backgroundColor: '#f0fdf4',
                  border: '1px solid #bbf7d0',
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
                Pedido Entregado y Pagado
              </div>
            ) : (
              <>
                <div
                  style={{
                    backgroundColor: '#fffbeb',
                    border: '1px solid #fde68a',
                    color: '#92400e',
                    borderRadius: 10,
                    padding: '8px 12px',
                    fontSize: '0.825rem',
                    fontWeight: 600,
                    textAlign: 'center',
                  }}
                >
                  ⚠️ Pedido entregado sin cobro confirmado
                </div>
                <button
                  onClick={handleConfirmPaymentOnly}
                  disabled={actionLoading || hasPendingRecovery || loading}
                  style={{
                    width: '100%',
                    backgroundColor: '#059669',
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
                  <DollarSign size={18} />
                  {actionLoading
                    ? 'Confirmando pago...'
                    : `Confirmar Pago Recibido ($${orderTotal} MXN)`}
                </button>
              </>
            )
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
