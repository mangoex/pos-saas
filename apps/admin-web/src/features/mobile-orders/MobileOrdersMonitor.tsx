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
  ChefHat,
  QrCode,
  PlaySquare,
  HelpCircle,
  Menu,
  Store,
  ChevronDown
} from 'lucide-react';
import { MobileOrderDetailModal } from './MobileOrderDetailModal';
import { MobileMenuQrModal } from './MobileMenuQrModal';

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
  onOpenHelpVideos?: () => void;
}

type OrderFilter = 'NEW' | 'PREP' | 'HISTORY';

const isToday = (dateStr?: string): boolean => {
  if (!dateStr) return false;
  const orderDate = new Date(dateStr);
  if (isNaN(orderDate.getTime())) return false;
  const today = new Date();
  return (
    orderDate.getDate() === today.getDate() &&
    orderDate.getMonth() === today.getMonth() &&
    orderDate.getFullYear() === today.getFullYear()
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
  onOpenHelpVideos,
}) => {
  const [orders, setOrders] = useState<OrderItem[]>([]);
  const [selectedOrderId, setSelectedOrderId] = useState<string | null>(null);
  const [isDetailOpen, setIsDetailOpen] = useState(false);
  const [isQrModalOpen, setIsQrModalOpen] = useState(false);
  const [filter, setFilter] = useState<OrderFilter>('NEW');
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
      let items: OrderItem[] = [];
      try {
        const res = await fetchApi<{ items: OrderItem[] }>(
          `/orders/accounts?branch_id=${encodeURIComponent(branchId)}&limit=100`
        );
        items = Array.isArray(res?.items) ? res.items : [];
      } catch {
        const fallback = await fetchApi<OrderItem[]>(
          `/orders?branch_id=${encodeURIComponent(branchId)}`
        );
        items = Array.isArray(fallback) ? fallback : [];
      }
      
      // Sort chronologically (FIFO: oldest arrivals at the top, newest arrivals at the bottom)
      const todayOrders = items
        .filter((item) => isToday(item.created_at))
        .sort((a, b) => {
          const timeA = a.created_at ? new Date(a.created_at).getTime() : 0;
          const timeB = b.created_at ? new Date(b.created_at).getTime() : 0;
          return timeA - timeB;
        });
      
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

  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null);

  const handleAcceptOrder = async (e: React.MouseEvent, orderId: string) => {
    e.stopPropagation();
    if (actionLoadingId) return;
    setActionLoadingId(orderId);
    setError(null);
    try {
      await fetchApi(`/orders/${encodeURIComponent(orderId)}/accept`, {
        method: 'POST',
      });
      setFilter('PREP');
      await loadOrders(true);
      window.dispatchEvent(new Event('restaurantos:orders-changed'));
    } catch (err: any) {
      setError(err instanceof ApiError ? err.message : 'Error al aceptar el pedido.');
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleRejectOrder = async (e: React.MouseEvent, orderId: string) => {
    e.stopPropagation();
    if (actionLoadingId) return;
    const confirmReject = window.confirm('¿Estás seguro de que deseas rechazar este pedido? Se moverá al historial como rechazado.');
    if (!confirmReject) return;
    setActionLoadingId(orderId);
    setError(null);
    try {
      await fetchApi(`/orders/${encodeURIComponent(orderId)}/reject`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: 'Rechazado desde administración móvil' }),
      });
      await loadOrders(true);
      window.dispatchEvent(new Event('restaurantos:orders-changed'));
    } catch (err: any) {
      setError(err instanceof ApiError ? err.message : 'Error al rechazar el pedido.');
    } finally {
      setActionLoadingId(null);
    }
  };

  const isOrderNew = (order: OrderItem): boolean => {
    const status = (order.status || '').toUpperCase();
    if (['DELIVERED', 'CLOSED', 'CANCELLED', 'REJECTED'].includes(status)) return false;
    return ['PENDING', 'PENDING_REVIEW', 'DRAFT'].includes(status) || !!(order.is_public_intent && status !== 'ACCEPTED');
  };

  const isOrderPrep = (order: OrderItem) => {
    const status = (order.status || '').toUpperCase();
    if (['DELIVERED', 'CLOSED', 'CANCELLED', 'REJECTED'].includes(status)) return false;
    return ['ACCEPTED', 'IN_PRODUCTION', 'IN_PREPARATION', 'SENT_TO_PRODUCTION', 'READY', 'IN_DELIVERY'].includes(status);
  };

  const isOrderReady = (order: OrderItem) => {
    const status = (order.status || '').toUpperCase();
    return ['READY', 'IN_DELIVERY'].includes(status);
  };
  
  const isOrderHistory = (order: OrderItem) => {
    const status = (order.status || '').toUpperCase();
    return ['DELIVERED', 'CLOSED', 'CANCELLED', 'REJECTED'].includes(status);
  };

  const filteredOrders = orders.filter((order) => {
    let matchesFilter = false;
    if (filter === 'NEW') matchesFilter = isOrderNew(order);
    else if (filter === 'PREP') matchesFilter = isOrderPrep(order);
    else if (filter === 'HISTORY') matchesFilter = isOrderHistory(order);

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
          backgroundColor: '#ffffff',
          padding: '12px 16px',
          display: 'flex',
          flexDirection: 'column',
          gap: 16,
          boxShadow: '0 2px 4px rgba(0,0,0,0.05)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <button 
            type="button"
            style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer' }}
            onClick={() => {}}
          >
            <Menu size={24} color="#334155" />
          </button>
          
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <div style={{ display: 'flex', alignItems: 'center', fontSize: '1.35rem', fontWeight: 900 }}>
               <span style={{ color: '#ff5722' }}>mi</span><span style={{ color: '#1e293b' }}>menu</span><span style={{ color: '#1e293b' }}>.onl</span>
            </div>
            {onOpenHelpVideos && (
              <button
                type="button"
                onClick={onOpenHelpVideos}
                aria-label="Tutoriales y videos de ayuda"
                title="Videos de ayuda"
                style={{
                  border: '1.5px solid #ff5722',
                  background: '#fff7ed',
                  color: '#ff5722',
                  borderRadius: '50%',
                  width: 26,
                  height: 26,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  cursor: 'pointer',
                  padding: 0,
                  fontWeight: 800,
                  boxShadow: '0 1px 3px rgba(255, 87, 34, 0.2)',
                }}
              >
                <HelpCircle size={17} color="#ff5722" />
              </button>
            )}
          </div>
          
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <button
              type="button"
              onClick={() => setIsQrModalOpen(true)}
              aria-label="Ver y compartir código QR del menú"
              title="Código QR del menú"
              style={{
                border: '1px solid #fed7aa',
                background: '#fff7ed',
                color: '#ea580c',
                borderRadius: 8,
                padding: '5px 8px',
                display: 'flex',
                alignItems: 'center',
                gap: 4,
                cursor: 'pointer',
                fontWeight: 700,
                fontSize: '0.78rem',
              }}
            >
              <QrCode size={16} color="#ea580c" />
              <span>QR</span>
            </button>
            <div style={{ width: 32, height: 32, borderRadius: 16, backgroundColor: '#f1f5f9', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.8rem', fontWeight: 700, color: '#334155' }}>
              MG
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', justifyContent: 'center' }}>
           <button style={{ display: 'flex', alignItems: 'center', gap: 6, backgroundColor: '#f1f5f9', border: 'none', padding: '6px 16px', borderRadius: 20, fontSize: '0.9rem', fontWeight: 600, color: '#334155', cursor: 'pointer' }}>
              <Store size={16} />
              {branchName || 'Sucursal Centro'}
              <ChevronDown size={16} />
           </button>
        </div>
      </header>

      {/* Main Container */}
      <main style={{ flex: 1, padding: '12px 14px 84px', maxWidth: 640, margin: '0 auto', width: '100%', boxSizing: 'border-box' }}>
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

        {/* Filter Tabs */}
        <div style={{ display: 'flex', gap: 24, marginBottom: 16, overflowX: 'auto', paddingBottom: 4, whiteSpace: 'nowrap', borderBottom: '1px solid #e2e8f0' }}>
          <button
            onClick={() => setFilter('NEW')}
            style={{
              background: 'none',
              border: 'none',
              padding: '0 4px 8px',
              fontSize: '1rem',
              fontWeight: 700,
              color: filter === 'NEW' ? '#ff5722' : '#94a3b8',
              borderBottom: filter === 'NEW' ? '3px solid #ff5722' : '3px solid transparent',
              cursor: 'pointer',
            }}
          >
            Pedidos
          </button>
          
          <button
            onClick={() => setFilter('PREP')}
            style={{
              background: 'none',
              border: 'none',
              padding: '0 4px 8px',
              fontSize: '1rem',
              fontWeight: 700,
              color: filter === 'PREP' ? '#ff5722' : '#94a3b8',
              borderBottom: filter === 'PREP' ? '3px solid #ff5722' : '3px solid transparent',
              cursor: 'pointer',
            }}
          >
            Preparación
          </button>

          <button
            onClick={() => setFilter('HISTORY')}
            style={{
              background: 'none',
              border: 'none',
              padding: '0 4px 8px',
              fontSize: '1rem',
              fontWeight: 700,
              color: filter === 'HISTORY' ? '#ff5722' : '#94a3b8',
              borderBottom: filter === 'HISTORY' ? '3px solid #ff5722' : '3px solid transparent',
              cursor: 'pointer',
            }}
          >
            Historial
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
              {filter === 'NEW'
                ? 'No hay pedidos nuevos por aceptar hoy.'
                : filter === 'PREP'
                  ? 'No hay pedidos en preparación.'
                  : 'No hay historial de pedidos el día de hoy.'}
            </p>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {filteredOrders.map((order) => {
              const elapsed = getElapsedMinutes(order.created_at);
              const status = (order.status || '').toUpperCase();
              
              const isReady = isOrderReady(order);
              const isDelivered = isOrderHistory(order);
              const isPrep = isOrderPrep(order);
              const isNew = isOrderNew(order);

              let statusBg = '#f1f5f9';
              let statusColor = '#475569';
              let statusLabel = 'Desconocido';
              
              if (isNew) {
                statusBg = '#fef3c7';
                statusColor = '#d97706';
                statusLabel = 'Nuevo';
              } else if (isPrep) {
                statusBg = '#e0f2fe';
                statusColor = '#2563eb';
                statusLabel = 'En preparación';
              } else if (isReady) {
                statusBg = '#dcfce7';
                statusColor = '#16a34a';
                statusLabel = 'Listo';
              } else if (isDelivered) {
                if (['CANCELLED', 'REJECTED'].includes(status)) {
                  statusBg = '#fef2f2';
                  statusColor = '#dc2626';
                  statusLabel = status === 'REJECTED' ? 'Rechazado' : 'Cancelado';
                } else {
                  statusBg = '#f1f5f9';
                  statusColor = '#475569';
                  statusLabel = 'Entregado';
                }
              }

              const customerName =
                order.customer_label ||
                order.customer_snapshot?.name ||
                order.owner_name ||
                'Cliente';

              const formattedTotal = ((order.total_cents || 0) / 100).toFixed(0);
              const items = (order as any).items || [];

              return (
                <div
                  key={order.id}
                  onClick={() => handleSelectOrder(order.id)}
                  style={{
                    backgroundColor: '#ffffff',
                    borderRadius: 16,
                    padding: '16px',
                    boxShadow: '0 2px 8px rgba(0,0,0,0.04)',
                    border: '1px solid #f1f5f9',
                    cursor: 'pointer',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 12,
                    marginBottom: 12,
                  }}
                >
                  {/* Card Header: Folio, Elapsed Time */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <span style={{ fontWeight: 800, fontSize: '1.1rem', color: '#0f172a' }}>
                      #{order.folio}
                    </span>
                    <span style={{ fontSize: '0.85rem', color: '#64748b' }}>
                      {elapsed < 1 ? 'Ahora' : `Hace ${elapsed} min`}
                    </span>
                  </div>

                  {/* Card Body: Customer & Status Badge */}
                  <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
                    <div style={{ fontSize: '1.1rem', color: '#334155' }}>
                      {customerName}
                      
                      {/* Items Mock/Display */}
                      <div style={{ marginTop: 8, fontSize: '0.9rem', color: '#64748b', display: 'flex', flexDirection: 'column', gap: 4 }}>
                         {items.length > 0 ? items.map((it: any, i: number) => (
                           <div key={i}>{it.quantity || 1} x {it.name || 'Producto'}</div>
                         )) : (
                           <>
                             <div>1 x Consumo</div>
                           </>
                         )}
                      </div>
                    </div>

                    <div style={{ textAlign: 'right' }}>
                      <div
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: 4,
                          fontSize: '0.8rem',
                          fontWeight: 600,
                          backgroundColor: statusBg,
                          color: statusColor,
                          padding: '4px 10px',
                          borderRadius: 20,
                          marginBottom: 16,
                        }}
                      >
                        {isNew && <span style={{ fontSize: '0.9rem' }}>👋</span>}
                        {isReady && <CheckCircle2 size={14} />}
                        {statusLabel}
                      </div>
                      <div style={{ fontWeight: 800, fontSize: '1.3rem', color: '#0f172a' }}>
                        ${formattedTotal}
                      </div>
                    </div>
                  </div>

                  {/* Actions for New Orders */}
                  {isNew && (
                    <div style={{ display: 'flex', gap: 12, marginTop: 4 }}>
                      <button 
                        type="button"
                        disabled={actionLoadingId === order.id}
                        onClick={(e) => void handleRejectOrder(e, order.id)}
                        style={{
                          flex: 1,
                          padding: '10px 0',
                          borderRadius: 10,
                          border: '1px solid #fca5a5',
                          color: '#ef4444',
                          backgroundColor: '#fef2f2',
                          fontWeight: 600,
                          fontSize: '0.95rem',
                          cursor: 'pointer',
                          opacity: actionLoadingId === order.id ? 0.6 : 1,
                        }}
                      >
                        {actionLoadingId === order.id ? 'Rechazando...' : 'Rechazar'}
                      </button>
                      <button 
                        type="button"
                        disabled={actionLoadingId === order.id}
                        onClick={(e) => void handleAcceptOrder(e, order.id)}
                        style={{
                          flex: 1,
                          padding: '10px 0',
                          borderRadius: 10,
                          border: 'none',
                          color: '#ffffff',
                          backgroundColor: '#22c55e',
                          fontWeight: 600,
                          fontSize: '0.95rem',
                          cursor: 'pointer',
                          opacity: actionLoadingId === order.id ? 0.6 : 1,
                        }}
                      >
                        {actionLoadingId === order.id ? 'Aceptando...' : 'Aceptar'}
                      </button>
                    </div>
                  )}
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
          setFilter('PREP');
          void loadOrders();
        }}
        branchName={branchName}
      />

      {/* Menu QR Code Modal for Download and Sharing */}
      <MobileMenuQrModal
        isOpen={isQrModalOpen}
        onClose={() => setIsQrModalOpen(false)}
        branchName={branchName}
      />
    </div>
  );
};
