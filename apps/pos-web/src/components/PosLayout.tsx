import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useLocation, Outlet } from 'react-router-dom';
import { fetchApi } from '@restaurantos/api-client';
import {
  ShoppingCart,
  Users,
  Clock,
  Settings,
  LogOut,
  ChevronLeft,
  ChevronRight,
  ShieldCheck,
  Timer,
  Wallet,
  BarChart3,
  Share2,
  Bike,
  ShoppingBag,
  FileText,
} from 'lucide-react';
import { usePosSession, clearPosSession } from '../session';
import AttendanceClockModal from '../features/attendance/AttendanceClockModal';

interface PendingOrderCountResponse {
  count: number;
}

const PENDING_ORDER_REFRESH_MS = 15_000;

const PosLayout = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [isAttendanceOpen, setIsAttendanceOpen] = useState(false);
  const { session, hasPermission } = usePosSession();
  const branchId = session?.active_branch?.id || '';
  const canReadOrders = hasPermission('orders.read');
  const [pendingOrderCount, setPendingOrderCount] = useState(0);
  const [uberOrderCount, setUberOrderCount] = useState(0);
  const [didiOrderCount, setDidiOrderCount] = useState(0);
  const [rappiOrderCount, setRappiOrderCount] = useState(0);
  const pendingOrderRequestSequence = useRef(0);

  const refreshPendingOrderCount = useCallback(async () => {
    const sequence = ++pendingOrderRequestSequence.current;
    if (!branchId || !canReadOrders) {
      setPendingOrderCount(0);
      setUberOrderCount(0);
      setDidiOrderCount(0);
      setRappiOrderCount(0);
      return;
    }
    try {
      const data = await fetchApi<PendingOrderCountResponse>(
        `/orders/pending-count?branch_id=${encodeURIComponent(branchId)}`,
        { headers: { 'Cache-Control': 'no-cache' } },
      );
      if (
        sequence === pendingOrderRequestSequence.current
        && Number.isSafeInteger(data.count)
        && data.count >= 0
      ) {
        setPendingOrderCount(data.count);
      }
    } catch {
      // Preserve last known count on transient error
    }

    try {
      const uberOrders = await fetchApi<Array<{ status: string }>>(
        `/pos/uber-eats/orders?branch_id=${encodeURIComponent(branchId)}`,
        { headers: { 'Cache-Control': 'no-cache' } }
      );
      if (Array.isArray(uberOrders)) {
        const activeCount = uberOrders.filter((o) => ['PENDING', 'ACCEPTED', 'PREPARING', 'READY'].includes(o.status)).length;
        setUberOrderCount(activeCount);
      }
    } catch {
      // Ignore transient errors
    }

    try {
      const didiOrders = await fetchApi<Array<{ status: string }>>(
        `/pos/didi-food/orders?branch_id=${encodeURIComponent(branchId)}`,
        { headers: { 'Cache-Control': 'no-cache' } }
      );
      if (Array.isArray(didiOrders)) {
        const activeCount = didiOrders.filter((o) => ['PENDING', 'ACCEPTED', 'PREPARING', 'READY'].includes(o.status)).length;
        setDidiOrderCount(activeCount);
      }
    } catch {
      // Ignore transient errors
    }

    try {
      const rappiOrders = await fetchApi<Array<{ status: string }>>(
        `/pos/rappi/orders?branch_id=${encodeURIComponent(branchId)}`,
        { headers: { 'Cache-Control': 'no-cache' } }
      );
      if (Array.isArray(rappiOrders)) {
        const activeCount = rappiOrders.filter((o) => ['PENDING', 'ACCEPTED', 'PREPARING', 'READY'].includes(o.status)).length;
        setRappiOrderCount(activeCount);
      }
    } catch {
      // Ignore transient errors
    }
  }, [branchId, canReadOrders]);

  useEffect(() => {
    setPendingOrderCount(0);
    setUberOrderCount(0);
    setDidiOrderCount(0);
    setRappiOrderCount(0);
    void refreshPendingOrderCount();
    const interval = window.setInterval(() => void refreshPendingOrderCount(), PENDING_ORDER_REFRESH_MS);
    const refreshOnFocus = () => void refreshPendingOrderCount();
    const refreshOnOrderChange = () => void refreshPendingOrderCount();
    const refreshOnVisibility = () => {
      if (document.visibilityState === 'visible') void refreshPendingOrderCount();
    };
    window.addEventListener('focus', refreshOnFocus);
    window.addEventListener('pos:pending-orders-changed', refreshOnOrderChange);
    document.addEventListener('visibilitychange', refreshOnVisibility);
    return () => {
      pendingOrderRequestSequence.current += 1;
      window.clearInterval(interval);
      window.removeEventListener('focus', refreshOnFocus);
      window.removeEventListener('pos:pending-orders-changed', refreshOnOrderChange);
      document.removeEventListener('visibilitychange', refreshOnVisibility);
    };
  }, [refreshPendingOrderCount]);

  const navItems = [
    { path: '/pos', label: 'Punto de Venta', icon: <ShoppingCart size={22} /> },
    { path: '/customers', label: 'Clientes', icon: <Users size={22} /> },
    { path: '/history', label: 'Pedidos', icon: <Clock size={22} /> },
    { path: '/uber-orders', label: 'Uber Eats', icon: <Share2 size={22} style={{ color: '#10b981' }} /> },
    { path: '/didi-orders', label: 'DiDi Food', icon: <Bike size={22} style={{ color: '#f97316' }} /> },
    { path: '/rappi-orders', label: 'Rappi', icon: <ShoppingBag size={22} style={{ color: '#ec4899' }} /> },
    { path: '/invoicing', label: 'Facturación', icon: <FileText size={22} /> },
    { path: '__attendance__', label: 'Checador', icon: <Timer size={22} /> },
    ...(hasPermission('cash.movement.read') || hasPermission('cash.movement.withdraw') || hasPermission('cash.movement.deposit') ? [{ path: '/cash-movements', label: 'Movimientos de caja', icon: <Wallet size={22} /> }] : []),
    ...(hasPermission('branch.admin.access') || hasPermission('admin.manage')
      ? [{ path: '/administration', label: 'Administración', icon: <ShieldCheck size={22} /> }]
      : []),
  ];

  return (
    <div style={{ display: 'flex', height: '100vh', width: '100vw', overflow: 'hidden', background: '#f8fafc' }}>
      {/* Light POS Sidebar */}
      <div style={{ 
        width: isCollapsed ? '80px' : '260px', 
        transition: 'width 0.3s', 
        display: 'flex', 
        flexDirection: 'column', 
        background: '#fff', 
        borderRight: '1px solid #e2e8f0',
        zIndex: 10
      }}>
        <div style={{ display: 'flex', justifyContent: isCollapsed ? 'center' : 'space-between', alignItems: 'center', padding: isCollapsed ? '24px 0' : '24px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', fontSize: '1.25rem', fontWeight: 800, color: '#10b981' }}>
            <span>🍽️</span>
            {!isCollapsed && <span>{session?.active_branch?.business_unit?.name || 'RestaurantOS'}</span>}
          </div>
          <button 
            onClick={() => setIsCollapsed(!isCollapsed)}
            style={{ background: 'transparent', border: 'none', color: '#64748b', cursor: 'pointer', padding: 0, display: isCollapsed ? 'none' : 'block' }}
          >
            <ChevronLeft size={20} />
          </button>
        </div>
        
        {isCollapsed && (
          <div style={{ textAlign: 'center', paddingBottom: '16px' }}>
            <button 
              onClick={() => setIsCollapsed(false)}
              style={{ background: 'transparent', border: 'none', color: '#64748b', cursor: 'pointer', padding: 0 }}
            >
              <ChevronRight size={20} />
            </button>
          </div>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', flex: 1 }}>
          {navItems.map((item) => {
            const isActive = item.path === '/pos'
              ? (location.pathname === '/' || location.pathname === '/pos' || location.pathname.startsWith('/pos/'))
              : (location.pathname === item.path || location.pathname.startsWith(`${item.path}/`));
            const isOrdersItem = item.path === '/history';
            const isUberItem = item.path === '/uber-orders';
            const isDidiItem = item.path === '/didi-orders';
            const isRappiItem = item.path === '/rappi-orders';
            const badgeCount = isOrdersItem
              ? pendingOrderCount
              : isUberItem
              ? uberOrderCount
              : isDidiItem
              ? didiOrderCount
              : isRappiItem
              ? rappiOrderCount
              : 0;
            const accessibleLabel = badgeCount > 0
              ? `${item.label}, ${badgeCount} pedidos pendientes`
              : item.label;
            return (
              <button
                type="button"
                aria-label={accessibleLabel}
                aria-current={isActive ? 'page' : undefined}
                key={item.path} 
                onClick={() => item.path === '__attendance__' ? setIsAttendanceOpen(true) : navigate(item.path)}
                style={{ 
                  display: 'flex', 
                  alignItems: 'center', 
                  gap: '16px',
                  justifyContent: isCollapsed ? 'center' : 'flex-start', 
                  padding: isCollapsed ? '12px 0' : '12px 24px',
                  cursor: 'pointer',
                  color: isActive ? '#10b981' : '#64748b',
                  background: isActive ? '#ecfdf5' : 'transparent',
                  border: 'none',
                  borderRight: isActive ? '3px solid #10b981' : '3px solid transparent',
                  width: '100%',
                  fontSize: 'inherit',
                  textAlign: 'left',
                  fontWeight: isActive ? 600 : 500,
                  transition: 'all 0.2s'
                }}
                title={isCollapsed ? accessibleLabel : undefined}
                onMouseEnter={(e) => { if (!isActive) e.currentTarget.style.background = '#f1f5f9'; }}
                onMouseLeave={(e) => { if (!isActive) e.currentTarget.style.background = 'transparent'; }}
              >
                <span className="pos-nav-icon-wrap">
                  {item.icon}
                  {isCollapsed && badgeCount > 0 ? (
                    <span className="pos-nav-pending-badge is-collapsed" aria-hidden="true" style={{ background: isUberItem ? '#059669' : undefined }}>{badgeCount}</span>
                  ) : null}
                </span>
                {!isCollapsed && <span>{item.label}</span>}
                {!isCollapsed && badgeCount > 0 ? (
                  <span className="pos-nav-pending-badge" aria-hidden="true" style={{ background: isUberItem ? '#059669' : undefined }}>{badgeCount}</span>
                ) : null}
              </button>
            );
          })}
        </div>
        <span className="pos-sr-only" aria-live="polite">
          {pendingOrderCount > 0 ? `${pendingOrderCount} pedidos por aceptar` : ''}
          {uberOrderCount > 0 ? `${uberOrderCount} pedidos de Uber Eats activos` : ''}
        </span>
        
        {/* User profile snippet */}
        {!isCollapsed && session?.user && (
          <div style={{ padding: '12px 20px', borderTop: '1px solid #e2e8f0', background: '#f8fafc', fontSize: '0.8125rem' }}>
            <div style={{ fontWeight: 600, color: '#0f172a', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              👤 {session.user.display_name}
            </div>
            <div style={{ color: '#16a34a', fontWeight: 500, marginTop: 2, fontSize: '0.75rem' }}>
              🏷️ {session.roles?.[0]?.name || 'Operador'} · {session.active_branch?.name || 'Sucursal'}
            </div>
          </div>
        )}

        {/* Configuración & Logout at the bottom */}
        <div style={{ padding: '12px 0', borderTop: '1px solid #e2e8f0' }}>
           <button
             type="button"
             aria-current={location.pathname === '/settings' ? 'page' : undefined}
             onClick={() => navigate('/settings')}
             style={{ 
               display: 'flex', alignItems: 'center', gap: '16px', justifyContent: isCollapsed ? 'center' : 'flex-start', 
               padding: isCollapsed ? '12px 0' : '12px 24px', cursor: 'pointer', color: location.pathname === '/settings' ? '#10b981' : '#64748b',
               background: location.pathname === '/settings' ? '#ecfdf5' : 'transparent',
               fontWeight: location.pathname === '/settings' ? 600 : 500, border: 'none', width: '100%', fontSize: 'inherit', textAlign: 'left',
             }}
             title={isCollapsed ? 'Configuración' : undefined}
             onMouseEnter={(e) => { if (location.pathname !== '/settings') e.currentTarget.style.background = '#f1f5f9'; }}
             onMouseLeave={(e) => { if (location.pathname !== '/settings') e.currentTarget.style.background = 'transparent'; }}
           >
             <Settings size={22} />
             {!isCollapsed && <span>Configuración</span>}
           </button>
           <button
              type="button"
              onClick={() => {
                clearPosSession();
                window.location.href = '/admin/login';
              }}
              style={{ 
                display: 'flex', alignItems: 'center', gap: '16px', justifyContent: isCollapsed ? 'center' : 'flex-start', 
                padding: isCollapsed ? '12px 0' : '12px 24px', cursor: 'pointer', color: '#ef4444', fontWeight: 500, border: 'none', width: '100%', fontSize: 'inherit', textAlign: 'left'
              }}
              title={isCollapsed ? 'Cerrar sesión' : undefined}
              onMouseEnter={(e) => e.currentTarget.style.background = '#fef2f2'}
              onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
            >
              <LogOut size={22} />
              {!isCollapsed && <span>Cerrar sesión</span>}
            </button>
        </div>
      </div>

      <main style={{ flex: 1, overflow: 'auto' }}>
        <Outlet />
      </main>
      <AttendanceClockModal isOpen={isAttendanceOpen} onClose={() => setIsAttendanceOpen(false)} />
    </div>
  );
};

export default PosLayout;
