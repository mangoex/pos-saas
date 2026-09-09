import React, { useCallback, useEffect, useState } from 'react';
import { fetchApi, ApiError } from '@restaurantos/api-client';
import {
  Clock,
  Utensils,
  ShoppingBag,
  Bike,
  RefreshCw,
  Search,
  CheckCircle2,
  AlertCircle,
  ChevronRight,
  ChefHat
} from 'lucide-react';
import { MobileOrderDetailModal } from './MobileOrderDetailModal';

interface OrderItem {
  id: string;
  folio: string;
  status: string;
  service_type?: string;
  order_type?: string;
  total_cents: number;
  currency?: string;
  created_at: string;
  customer_label?: string;
  customer_snapshot?: { name?: string; phone?: string };
  owner_name?: string;
  payment_status?: string;
  channel?: string;
  is_public_intent?: boolean;
  order_notes?: string;
  table_number?: string;
  cash_amount?: string;
}

interface MobileOrdersMonitorProps {
  branchId: string;
  branchName?: string;
}

type OrderFilter = 'ACTIVE' | 'READY' | 'ALL';

const isToday = (dateStr?: string): boolean => {
  if (!dateStr) return false;
  const orderDate = new Date(dateStr);
  if (isNaN(orderDate.getTime())) return false;
  const today = new Date();
  return (
    orderDate.getFullYear() === today.getFullYear() &&
    orderDate.getMonth() === today.getMonth() &&
    orderDate.getDate() === today.getDate()
  );
};

const getElapsedMinutes = (dateStr: string) => {
  const ts = Date.parse(dateStr);
  if (!Number.isFinite(ts)) return 0;
  return Math.max(0, Math.floor((Date.now() - ts) / 60_000));
};

export const MobileOrdersMonitor: React.FC<MobileOrdersMonitorProps> = ({
  branchId,
  branchName,
}) => {
  const [orders, setOrders] = useState<OrderItem[]>([]);
  const [selectedOrderId, setSelectedOrderId] = useState<string | null>(null);
  const [isDetailOpen, setIsDetailOpen] = useState(false);
  const [filter, setFilter] = useState<OrderFilter>('ACTIVE');
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date>(new Date());
  const [error, setError] = useState<string | null>(null);

  const loadOrders = useCallback(async (isSilent = false) => {
    if (!branchId) return;
    if (!isSilent) setRefreshing(true);
    setError(null);
    try {
      // First try /orders/accounts
      let items: OrderItem[] = [];
      try {
        const res = await fetchApi<{ items: OrderItem[] }>(
          `/orders/accounts?branch_id=${encodeURIComponent(branchId)}&limit=100`
        );
        items = Array.isArray(res?.items) ? res.items : [];
      } catch {
        // Fallback to /orders
        const fallback = await fetchApi<OrderItem[]>(
          `/orders?branch_id=${encodeURIComponent(branchId)}`
        );
        items = Array.isArray(fallback) ? fallback : [];
      }
      // ONLY SHOW ORDERS CREATED TODAY (NO HISTORICAL ORDERS)
      const todayOrders = items.filter((item) => isToday(item.created_at));
      setOrders(todayOrders);
      setLastUpdated(new Date());
    } catch (err) {
      if (!isSilent) {
        setError(err instanceof ApiError ? err.message : 'Error al consultar comandas.');
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [branchId]);

  // Initial load
  useEffect(() => {
    void loadOrders();
  }, [loadOrders]);

  // Polling every 8 seconds for live kitchen updates
  useEffect(() => {
    if (!branchId) return undefined;
    const interval = window.setInterval(() => {
      void loadOrders(true);
    }, 8_000);
    return () => window.clearInterval(interval);
  }, [branchId, loadOrders]);

  const handleSelectOrder = (orderId: string) => {
    setSelectedOrderId(orderId);
    setIsDetailOpen(true);
  };

  const isOrderPending = (order: OrderItem) => {
    const status = (order.status || '').toUpperCase();
    if (['DELIVERED', 'CLOSED', 'CANCELLED', 'REJECTED'].includes(status)) return false;
    return ['PENDING', 'PENDING_REVIEW', 'DRAFT'].includes(status) || (order.is_public_intent && status !== 'ACCEPTED');
  };

  const isOrderReady = (order: OrderItem) => {
    const status = (order.status || '').toUpperCase();
    if (['DELIVERED', 'CLOSED', 'CANCELLED', 'REJECTED'].includes(status)) return false;
    return ['ACCEPTED', 'READY', 'IN_PRODUCTION', 'IN_PREPARATION', 'SENT_TO_PRODUCTION', 'IN_DELIVERY'].includes(status);
  };

  const filteredOrders = orders.filter((order) => {
    const matchesFilter =
      filter === 'ALL'
        ? true
        : filter === 'READY'
          ? isOrderReady(order)
          : isOrderPending(order);

    if (!matchesFilter) return false;

    if (!searchQuery.trim()) return true;

    const q = searchQuery.toLowerCase();
    const folio = (order.folio || '').toLowerCase();
    const cust = (
      order.customer_label ||
      order.customer_snapshot?.name ||
      order.owner_name ||
      ''
    ).toLowerCase();

    return folio.includes(q) || cust.includes(q);
  });

  const activeCount = orders.filter(isOrderPending).length;
  const readyCount = orders.filter(isOrderReady).length;

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        minHeight: '100vh',
        backgroundColor: '#f1f5f9',
        fontFamily: 'system-ui, -apple-system, sans-serif',
      }}
    >
      {/* Top Mobile Bar */}
      <header
        style={{
          position: 'sticky',
          top: 0,
          zIndex: 100,
          backgroundColor: '#0f172a',
          color: '#ffffff',
          padding: '12px 16px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div
            style={{
              backgroundColor: '#0284c7',
              borderRadius: 8,
              padding: 6,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <ChefHat size={20} color="#ffffff" />
          </div>
          <div>
            <div style={{ fontSize: '1rem', fontWeight: 800, lineHeight: 1.1 }}>
              Monitor de Pedidos
            </div>
            <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
              {branchName || 'Sucursal Principal'}
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <button
            onClick={() => void loadOrders()}
            disabled={refreshing}
            aria-label="Refrescar pedidos"
            style={{
              border: 'none',
              background: '#1e293b',
              color: '#ffffff',
              borderRadius: 8,
              padding: '8px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: 'pointer',
            }}
          >
            <RefreshCw size={16} className={refreshing ? 'animate-spin' : ''} />
          </button>
        </div>
      </header>

      {/* Main Container */}
      <main style={{ flex: 1, padding: '12px 14px', maxWidth: 640, margin: '0 auto', width: '100%', boxSizing: 'border-box' }}>
        {/* Search Bar */}
        <div
          style={{
            position: 'relative',
            marginBottom: 12,
          }}
        >
          <Search
            size={18}
            style={{
              position: 'absolute',
              left: 12,
              top: '50%',
              transform: 'translateY(-50%)',
              color: '#94a3b8',
            }}
          />
          <input
            type="text"
            placeholder="Buscar por folio o comensal..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{
              width: '100%',
              padding: '10px 12px 10px 38px',
              borderRadius: 10,
              border: '1px solid #cbd5e1',
              backgroundColor: '#ffffff',
              fontSize: '0.9rem',
              outline: 'none',
              boxSizing: 'border-box',
            }}
          />
        </div>

        {/* Filter Pills */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 14 }}>
          <button
            onClick={() => setFilter('ACTIVE')}
            style={{
              flex: 1,
              padding: '8px 12px',
              borderRadius: 8,
              border: 'none',
              fontWeight: 700,
              fontSize: '0.85rem',
              backgroundColor: filter === 'ACTIVE' ? '#0284c7' : '#e2e8f0',
              color: filter === 'ACTIVE' ? '#ffffff' : '#475569',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 6,
            }}
          >
            Activos
            <span
              style={{
                backgroundColor: filter === 'ACTIVE' ? '#0369a1' : '#cbd5e1',
                borderRadius: 10,
                padding: '2px 6px',
                fontSize: '0.75rem',
              }}
            >
              {activeCount}
            </span>
          </button>

          <button
            onClick={() => setFilter('READY')}
            style={{
              flex: 1,
              padding: '8px 12px',
              borderRadius: 8,
              border: 'none',
              fontWeight: 700,
              fontSize: '0.85rem',
              backgroundColor: filter === 'READY' ? '#10b981' : '#e2e8f0',
              color: filter === 'READY' ? '#ffffff' : '#475569',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 6,
            }}
          >
            Listos
            <span
              style={{
                backgroundColor: filter === 'READY' ? '#059669' : '#cbd5e1',
                borderRadius: 10,
                padding: '2px 6px',
                fontSize: '0.75rem',
              }}
            >
              {readyCount}
            </span>
          </button>

          <button
            onClick={() => setFilter('ALL')}
            style={{
              flex: 1,
              padding: '8px 12px',
              borderRadius: 8,
              border: 'none',
              fontWeight: 700,
              fontSize: '0.85rem',
              backgroundColor: filter === 'ALL' ? '#334155' : '#e2e8f0',
              color: filter === 'ALL' ? '#ffffff' : '#475569',
              cursor: 'pointer',
            }}
          >
            Todos ({orders.length})
          </button>
        </div>

        {/* Error Alert */}
        {error && (
          <div
            style={{
              backgroundColor: '#fef2f2',
              color: '#b91c1c',
              padding: '10px 14px',
              borderRadius: 8,
              fontSize: '0.85rem',
              marginBottom: 12,
              display: 'flex',
              alignItems: 'center',
              gap: 8,
            }}
          >
            <AlertCircle size={16} />
            <span>{error}</span>
          </div>
        )}

        {/* Orders Stream */}
        {loading && orders.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '40px 0', color: '#64748b' }}>
            <Clock size={28} className="animate-spin" style={{ margin: '0 auto 8px' }} />
            <p style={{ margin: 0, fontSize: '0.9rem' }}>Cargando pedidos en cocina...</p>
          </div>
        ) : filteredOrders.length === 0 ? (
          <div
            style={{
              backgroundColor: '#ffffff',
              borderRadius: 12,
              padding: '36px 20px',
              textAlign: 'center',
              border: '1px dashed #cbd5e1',
              color: '#64748b',
            }}
          >
            <CheckCircle2 size={36} color="#10b981" style={{ margin: '0 auto 10px' }} />
            <div style={{ fontWeight: 700, fontSize: '1rem', color: '#1e293b' }}>
              No hay pedidos en esta sección
            </div>
            <p style={{ fontSize: '0.85rem', margin: '6px 0 0', color: '#64748b' }}>
              {filter === 'ACTIVE'
                ? 'No hay pedidos pendientes por aceptar hoy.'
                : filter === 'READY'
                  ? 'No hay pedidos listos o en preparación hoy.'
                  : 'No hay pedidos registrados el día de hoy.'}
            </p>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {filteredOrders.map((order) => {
              const elapsed = getElapsedMinutes(order.created_at);
              const status = (order.status || '').toUpperCase();
              const isReady = isOrderReady(order);
              const isDelivered = ['DELIVERED', 'CLOSED'].includes(status);

              const isDineIn =
                order.service_type?.toLowerCase() === 'dine-in' ||
                order.order_type?.toLowerCase() === 'dine-in' ||
                order.service_type?.toLowerCase() === 'local';

              const isDelivery =
                order.service_type?.toLowerCase() === 'delivery' ||
                order.order_type?.toLowerCase() === 'delivery';

              const customerName =
                order.customer_label ||
                order.customer_snapshot?.name ||
                order.owner_name ||
                'Cliente';

              const formattedTotal = ((order.total_cents || 0) / 100).toFixed(2);

              return (
                <div
                  key={order.id}
                  onClick={() => handleSelectOrder(order.id)}
                  style={{
                    backgroundColor: '#ffffff',
                    borderRadius: 12,
                    padding: '14px 16px',
                    boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
                    border: isReady
                      ? '1.5px solid #86efac'
                      : isDelivered
                        ? '1px solid #e2e8f0'
                        : '1.5px solid #93c5fd',
                    cursor: 'pointer',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 8,
                    transition: 'transform 0.1s ease',
                  }}
                >
                  {/* Card Header: Folio, Service Modality, Elapsed Time */}
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span
                        style={{
                          fontWeight: 800,
                          fontSize: '1.05rem',
                          color: '#0f172a',
                        }}
                      >
                        #{order.folio}
                      </span>
                      {order.is_public_intent && (
                        <span
                          style={{
                            fontSize: '0.6875rem',
                            fontWeight: 700,
                            backgroundColor: '#eff6ff',
                            color: '#1d4ed8',
                            padding: '2px 6px',
                            borderRadius: 4,
                          }}
                        >
                          🌐 WEB
                        </span>
                      )}
                    </div>

                    {/* Elapsed Time Badge */}
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 4,
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        color:
                          elapsed > 25
                            ? '#b91c1c'
                            : elapsed > 12
                              ? '#c2410c'
                              : '#15803d',
                        backgroundColor:
                          elapsed > 25
                            ? '#fef2f2'
                            : elapsed > 12
                              ? '#fff7ed'
                              : '#f0fdf4',
                        padding: '2px 8px',
                        borderRadius: 6,
                      }}
                    >
                      <Clock size={12} />
                      <span>{elapsed < 1 ? 'Ahora' : `Hace ${elapsed}m`}</span>
                    </div>
                  </div>

                  {/* Card Body: Customer & Service Modality */}
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                    }}
                  >
                    <div style={{ fontSize: '0.925rem', fontWeight: 600, color: '#334155' }}>
                      {customerName}
                    </div>

                    <div
                      style={{
                        fontSize: '0.8rem',
                        color: '#64748b',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 4,
                      }}
                    >
                      {isDineIn ? (
                        <>
                          <Utensils size={14} color="#0284c7" />
                          <span>Comer Aquí</span>
                        </>
                      ) : isDelivery ? (
                        <>
                          <Bike size={14} color="#059669" />
                          <span>A Domicilio</span>
                        </>
                      ) : (
                        <>
                          <ShoppingBag size={14} color="#d97706" />
                          <span>Para Llevar</span>
                        </>
                      )}
                    </div>
                  </div>

                  {/* Customer Notes snippet */}
                  {order.order_notes && (
                    <div
                      style={{
                        fontSize: '0.78rem',
                        color: '#92400e',
                        backgroundColor: '#fffbeb',
                        border: '1px solid #fef3c7',
                        padding: '4px 8px',
                        borderRadius: 6,
                        display: 'flex',
                        alignItems: 'center',
                        gap: 4,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      <span>📝</span>
                      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{order.order_notes}</span>
                    </div>
                  )}

                  {/* Card Footer: Total, Status & Arrow */}
                  <div
                    style={{
                      paddingTop: 8,
                      borderTop: '1px dashed #f1f5f9',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                    }}
                  >
                    <div style={{ fontWeight: 800, fontSize: '1.1rem', color: '#0f172a' }}>
                      ${formattedTotal} <span style={{ fontSize: '0.75rem', fontWeight: 500, color: '#64748b' }}>MXN</span>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span
                        style={{
                          fontSize: '0.75rem',
                          fontWeight: 700,
                          textTransform: 'uppercase',
                          padding: '3px 8px',
                          borderRadius: 6,
                          backgroundColor: isDelivered
                            ? '#f1f5f9'
                            : isReady
                              ? '#dcfce7'
                              : '#e0f2fe',
                          color: isDelivered
                            ? '#475569'
                            : isReady
                              ? '#166534'
                              : '#0369a1',
                        }}
                      >
                        {isDelivered ? 'Entregado' : isReady ? 'Listo' : 'Por Aceptar'}
                      </span>
                      <ChevronRight size={16} color="#94a3b8" />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </main>

      {/* Interactive Detail Modal */}
      <MobileOrderDetailModal
        orderId={selectedOrderId}
        isOpen={isDetailOpen}
        onClose={() => setIsDetailOpen(false)}
        onOrderUpdated={() => void loadOrders()}
        onOrderAccepted={() => {
          setFilter('READY');
          void loadOrders();
        }}
        branchName={branchName}
      />
    </div>
  );
};
