import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchApi } from '@restaurantos/api-client';
import {
  TrendingUp,
  DollarSign,
  ShoppingBag,
  CreditCard,
  Utensils,
  Calendar,
  RefreshCw,
  Award,
  Layers,
} from 'lucide-react';

interface Branch {
  id: string;
  name: string;
}

interface PaymentMethodStat {
  method_key: string;
  label: string;
  total: number;
  percentage: number;
}

interface OrderChannelStat {
  channel_key: string;
  label: string;
  orders_count: number;
  total: number;
  percentage: number;
}

interface TopProductStat {
  product_name: string;
  quantity: number;
  total: number;
}

interface DailyTrendStat {
  date: string;
  total_sales: number;
  orders_count: number;
}

interface AnalyticsData {
  date_from: string;
  date_to: string;
  summary: {
    total_sales: number;
    orders_count: number;
    average_ticket: number;
    items_sold_count: number;
  };
  payment_methods: PaymentMethodStat[];
  order_channels: OrderChannelStat[];
  top_products: TopProductStat[];
  daily_trend: DailyTrendStat[];
}

const money = (val: number) =>
  new Intl.NumberFormat('es-MX', { style: 'currency', currency: 'MXN' }).format(val);

export const AnalyticsDashboard: React.FC = () => {
  const getTodayStr = () => new Date().toLocaleDateString('en-CA');
  const getFirstDayOfMonth = () => {
    const today = new Date();
    return `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-01`;
  };

  const [dateFrom, setDateFrom] = useState(getFirstDayOfMonth());
  const [dateTo, setDateTo] = useState(getTodayStr());
  const [selectedBranchId, setSelectedBranchId] = useState('');

  const { data: branches = [] } = useQuery<Branch[]>({
    queryKey: ['branches'],
    queryFn: () => fetchApi('/branches'),
  });

  const {
    data,
    isLoading,
    isFetching,
    error,
    refetch,
  } = useQuery<AnalyticsData>({
    queryKey: ['business-analytics', dateFrom, dateTo, selectedBranchId],
    queryFn: () => {
      const params = new URLSearchParams({
        date_from: dateFrom,
        date_to: dateTo,
      });
      if (selectedBranchId) params.set('branch_id', selectedBranchId);
      return fetchApi(`/reports/analytics?${params.toString()}`);
    },
  });

  const applyPreset = (preset: 'today' | 'last7' | 'month') => {
    const today = new Date();
    const todayStr = getTodayStr();

    if (preset === 'today') {
      setDateFrom(todayStr);
      setDateTo(todayStr);
    } else if (preset === 'last7') {
      const d = new Date();
      d.setDate(today.getDate() - 6);
      setDateFrom(d.toLocaleDateString('en-CA'));
      setDateTo(todayStr);
    } else if (preset === 'month') {
      setDateFrom(getFirstDayOfMonth());
      setDateTo(todayStr);
    }
  };

  const summary = data?.summary;
  const paymentMethods = data?.payment_methods || [];
  const channels = data?.order_channels || [];
  const topProducts = data?.top_products || [];
  const dailyTrend = data?.daily_trend || [];

  return (
    <div style={{ padding: 24, maxWidth: 1200, margin: '0 auto', fontFamily: 'system-ui, sans-serif' }}>
      {/* Header & Controls */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 16, marginBottom: 24 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: '1.75rem', fontWeight: 800, color: '#0f172a', display: 'flex', alignItems: 'center', gap: 10 }}>
            <TrendingUp size={28} color="#16a34a" /> Métricas y Rendimiento
          </h1>
          <p style={{ margin: '4px 0 0', color: '#64748b', fontSize: '0.9rem' }}>
            Indicadores ejecutivos de venta, mix de cobro, canales de pedidos y productos líderes
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          {/* Quick Presets */}
          <div style={{ display: 'flex', backgroundColor: '#f1f5f9', borderRadius: 8, padding: 2, gap: 2 }}>
            <button
              type="button"
              onClick={() => applyPreset('today')}
              style={{
                border: 'none',
                padding: '6px 12px',
                borderRadius: 6,
                fontSize: '0.8rem',
                fontWeight: 600,
                cursor: 'pointer',
                backgroundColor: dateFrom === getTodayStr() && dateTo === getTodayStr() ? '#ffffff' : 'transparent',
                color: dateFrom === getTodayStr() && dateTo === getTodayStr() ? '#0f172a' : '#64748b',
                boxShadow: dateFrom === getTodayStr() && dateTo === getTodayStr() ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
              }}
            >
              Hoy
            </button>
            <button
              type="button"
              onClick={() => applyPreset('last7')}
              style={{
                border: 'none',
                padding: '6px 12px',
                borderRadius: 6,
                fontSize: '0.8rem',
                fontWeight: 600,
                cursor: 'pointer',
                backgroundColor: 'transparent',
                color: '#64748b',
              }}
            >
              Últimos 7 días
            </button>
            <button
              type="button"
              onClick={() => applyPreset('month')}
              style={{
                border: 'none',
                padding: '6px 12px',
                borderRadius: 6,
                fontSize: '0.8rem',
                fontWeight: 600,
                cursor: 'pointer',
                backgroundColor: dateFrom === getFirstDayOfMonth() && dateTo === getTodayStr() ? '#ffffff' : 'transparent',
                color: dateFrom === getFirstDayOfMonth() && dateTo === getTodayStr() ? '#0f172a' : '#64748b',
                boxShadow: dateFrom === getFirstDayOfMonth() && dateTo === getTodayStr() ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
              }}
            >
              Este Mes
            </button>
          </div>

          <select
            value={selectedBranchId}
            onChange={(e) => setSelectedBranchId(e.target.value)}
            style={{ padding: '8px 12px', borderRadius: 8, border: '1px solid #cbd5e1', fontSize: '0.85rem' }}
          >
            <option value="">🏢 Todas las Sucursales</option>
            {branches.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </select>

          <label style={{ fontSize: '0.85rem', color: '#475569', display: 'flex', alignItems: 'center', gap: 6 }}>
            Desde:
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              style={{ padding: '6px 8px', borderRadius: 6, border: '1px solid #cbd5e1', fontSize: '0.85rem' }}
            />
          </label>

          <label style={{ fontSize: '0.85rem', color: '#475569', display: 'flex', alignItems: 'center', gap: 6 }}>
            Hasta:
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              style={{ padding: '6px 8px', borderRadius: 6, border: '1px solid #cbd5e1', fontSize: '0.85rem' }}
            />
          </label>

          <button
            type="button"
            onClick={() => void refetch()}
            disabled={isFetching}
            style={{
              padding: '8px',
              borderRadius: 8,
              border: '1px solid #cbd5e1',
              backgroundColor: '#ffffff',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
            title="Recargar métricas"
          >
            <RefreshCw size={16} className={isFetching ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {isLoading && <p style={{ color: '#64748b' }}>Calculando métricas del periodo…</p>}
      {error && (
        <div role="alert" style={{ padding: 14, borderRadius: 10, background: '#fee2e2', color: '#b91c1c', marginBottom: 20 }}>
          Error al cargar las métricas de rendimiento. Verifica la conexión o el rango de fechas.
        </div>
      )}

      {summary && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
          {/* Main KPI Cards */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 16 }}>
            <div style={{ background: '#ffffff', padding: 18, borderRadius: 12, border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.05)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ color: '#64748b', fontSize: '0.8rem', fontWeight: 700, textTransform: 'uppercase' }}>Ventas Totales</span>
                <div style={{ width: 36, height: 36, borderRadius: 8, backgroundColor: '#dcfce7', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#15803d' }}>
                  <DollarSign size={20} />
                </div>
              </div>
              <div style={{ fontSize: '1.6rem', fontWeight: 800, color: '#0f172a', marginTop: 8 }}>
                {money(summary.total_sales)}
              </div>
              <div style={{ fontSize: '0.75rem', color: '#64748b', marginTop: 4 }}>
                Facturación neta confirmada
              </div>
            </div>

            <div style={{ background: '#ffffff', padding: 18, borderRadius: 12, border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.05)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ color: '#64748b', fontSize: '0.8rem', fontWeight: 700, textTransform: 'uppercase' }}>Pedidos Pagados</span>
                <div style={{ width: 36, height: 36, borderRadius: 8, backgroundColor: '#eff6ff', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#2563eb' }}>
                  <ShoppingBag size={20} />
                </div>
              </div>
              <div style={{ fontSize: '1.6rem', fontWeight: 800, color: '#0f172a', marginTop: 8 }}>
                {summary.orders_count.toLocaleString()}
              </div>
              <div style={{ fontSize: '0.75rem', color: '#64748b', marginTop: 4 }}>
                Órdenes finalizadas y cobradas
              </div>
            </div>

            <div style={{ background: '#ffffff', padding: 18, borderRadius: 12, border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.05)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ color: '#64748b', fontSize: '0.8rem', fontWeight: 700, textTransform: 'uppercase' }}>Ticket Promedio</span>
                <div style={{ width: 36, height: 36, borderRadius: 8, backgroundColor: '#f5f3ff', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#7c3aed' }}>
                  <TrendingUp size={20} />
                </div>
              </div>
              <div style={{ fontSize: '1.6rem', fontWeight: 800, color: '#0f172a', marginTop: 8 }}>
                {money(summary.average_ticket)}
              </div>
              <div style={{ fontSize: '0.75rem', color: '#64748b', marginTop: 4 }}>
                Promedio por cliente u orden
              </div>
            </div>

            <div style={{ background: '#ffffff', padding: 18, borderRadius: 12, border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.05)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ color: '#64748b', fontSize: '0.8rem', fontWeight: 700, textTransform: 'uppercase' }}>Platillos Vendidos</span>
                <div style={{ width: 36, height: 36, borderRadius: 8, backgroundColor: '#fff7ed', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#ea580c' }}>
                  <Utensils size={20} />
                </div>
              </div>
              <div style={{ fontSize: '1.6rem', fontWeight: 800, color: '#0f172a', marginTop: 8 }}>
                {summary.items_sold_count.toLocaleString()}
              </div>
              <div style={{ fontSize: '0.75rem', color: '#64748b', marginTop: 4 }}>
                Unidades servidas o entregadas
              </div>
            </div>
          </div>

          {/* Zero state banner if no sales */}
          {summary.orders_count === 0 && (
            <div style={{ background: '#f8fafc', border: '1px dashed #cbd5e1', borderRadius: 12, padding: 32, textAlign: 'center' }}>
              <div style={{ color: '#64748b', fontWeight: 700, fontSize: '1.1rem', marginBottom: 6 }}>
                Sin ventas registradas en el periodo
              </div>
              <p style={{ color: '#94a3b8', fontSize: '0.875rem', margin: 0 }}>
                No se encontraron cobros en el rango de fechas ({dateFrom} al {dateTo}). Prueba cambiando el periodo o registrando órdenes en el Punto de Venta.
              </p>
            </div>
          )}

          {/* Grid: Métodos de Pago y Canales de Venta */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: 20 }}>
            {/* Payment Methods */}
            <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: 12, padding: 20, boxShadow: '0 1px 3px rgba(0,0,0,0.03)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 700, color: '#0f172a', marginBottom: 16 }}>
                <CreditCard size={18} color="#2563eb" />
                <span>Mix de Métodos de Pago</span>
              </div>
              {paymentMethods.length === 0 ? (
                <div style={{ color: '#94a3b8', fontSize: '0.85rem' }}>Sin cobros registrados en este periodo.</div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                  {paymentMethods.map((pm) => (
                    <div key={pm.method_key}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', marginBottom: 4 }}>
                        <span style={{ fontWeight: 600, color: '#334155' }}>{pm.label}</span>
                        <span style={{ fontWeight: 700, color: '#0f172a' }}>
                          {money(pm.total)}{' '}
                          <span style={{ color: '#64748b', fontWeight: 500 }}>({pm.percentage}%)</span>
                        </span>
                      </div>
                      <div style={{ height: 8, width: '100%', backgroundColor: '#f1f5f9', borderRadius: 4, overflow: 'hidden' }}>
                        <div
                          style={{
                            height: '100%',
                            width: `${pm.percentage}%`,
                            backgroundColor: pm.method_key === 'cash' ? '#10b981' : pm.method_key === 'card' ? '#3b82f6' : '#8b5cf6',
                            borderRadius: 4,
                          }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Service Channels */}
            <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: 12, padding: 20, boxShadow: '0 1px 3px rgba(0,0,0,0.03)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 700, color: '#0f172a', marginBottom: 16 }}>
                <Layers size={18} color="#059669" />
                <span>Canales de Servicio</span>
              </div>
              {channels.length === 0 ? (
                <div style={{ color: '#94a3b8', fontSize: '0.85rem' }}>Sin pedidos registrados en este periodo.</div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                  {channels.map((ch) => (
                    <div key={ch.channel_key}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', marginBottom: 4 }}>
                        <span style={{ fontWeight: 600, color: '#334155' }}>
                          {ch.label} ({ch.orders_count} órdenes)
                        </span>
                        <span style={{ fontWeight: 700, color: '#0f172a' }}>
                          {money(ch.total)}{' '}
                          <span style={{ color: '#64748b', fontWeight: 500 }}>({ch.percentage}%)</span>
                        </span>
                      </div>
                      <div style={{ height: 8, width: '100%', backgroundColor: '#f1f5f9', borderRadius: 4, overflow: 'hidden' }}>
                        <div
                          style={{
                            height: '100%',
                            width: `${ch.percentage}%`,
                            backgroundColor: '#059669',
                            borderRadius: 4,
                          }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Top Products Table */}
          <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: 12, overflow: 'hidden', boxShadow: '0 1px 3px rgba(0,0,0,0.03)' }}>
            <div style={{ padding: '14px 20px', borderBottom: '1px solid #e2e8f0', display: 'flex', alignItems: 'center', gap: 8, fontWeight: 700, color: '#0f172a', background: '#f8fafc' }}>
              <Award size={18} color="#d97706" />
              <span>Top Platillos y Productos Más Vendidos</span>
            </div>
            {topProducts.length === 0 ? (
              <div style={{ padding: 24, color: '#94a3b8', fontSize: '0.85rem', textAlign: 'center' }}>
                No hay productos vendidos en este periodo.
              </div>
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid #e2e8f0', color: '#64748b', textAlign: 'left', background: '#ffffff' }}>
                    <th style={{ padding: '12px 20px', width: 50 }}>#</th>
                    <th style={{ padding: '12px 20px' }}>Producto / Platillo</th>
                    <th style={{ padding: '12px 20px', textAlign: 'right' }}>Cantidad Vendida</th>
                    <th style={{ padding: '12px 20px', textAlign: 'right' }}>Recaudación Total</th>
                  </tr>
                </thead>
                <tbody>
                  {topProducts.map((prod, idx) => (
                    <tr key={prod.product_name} style={{ borderBottom: '1px solid #f1f5f9' }}>
                      <td style={{ padding: '12px 20px', fontWeight: 700, color: '#94a3b8' }}>
                        {idx + 1}
                      </td>
                      <td style={{ padding: '12px 20px', fontWeight: 600, color: '#0f172a' }}>
                        {prod.product_name}
                      </td>
                      <td style={{ padding: '12px 20px', textAlign: 'right', fontWeight: 700, color: '#334155' }}>
                        {prod.quantity.toLocaleString()} uds.
                      </td>
                      <td style={{ padding: '12px 20px', textAlign: 'right', fontWeight: 800, color: '#059669' }}>
                        {money(prod.total)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* Daily Trend Table */}
          {dailyTrend.length > 1 && (
            <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: 12, overflow: 'hidden', boxShadow: '0 1px 3px rgba(0,0,0,0.03)' }}>
              <div style={{ padding: '14px 20px', borderBottom: '1px solid #e2e8f0', display: 'flex', alignItems: 'center', gap: 8, fontWeight: 700, color: '#0f172a', background: '#f8fafc' }}>
                <Calendar size={18} color="#4f46e5" />
                <span>Tendencia Diaria de Ventas</span>
              </div>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid #e2e8f0', color: '#64748b', textAlign: 'left', background: '#ffffff' }}>
                    <th style={{ padding: '12px 20px' }}>Fecha</th>
                    <th style={{ padding: '12px 20px', textAlign: 'right' }}>Órdenes Pagadas</th>
                    <th style={{ padding: '12px 20px', textAlign: 'right' }}>Venta Total ($ MXN)</th>
                  </tr>
                </thead>
                <tbody>
                  {dailyTrend.map((day) => (
                    <tr key={day.date} style={{ borderBottom: '1px solid #f1f5f9' }}>
                      <td style={{ padding: '12px 20px', fontWeight: 600, color: '#0f172a' }}>
                        {day.date}
                      </td>
                      <td style={{ padding: '12px 20px', textAlign: 'right', color: '#475569' }}>
                        {day.orders_count}
                      </td>
                      <td style={{ padding: '12px 20px', textAlign: 'right', fontWeight: 800, color: '#059669' }}>
                        {money(day.total_sales)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
