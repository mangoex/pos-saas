import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowUpRight,
  BellRing,
  CalendarDays,
  CheckCircle2,
  ChevronDown,
  CircleDollarSign,
  Clock3,
  ExternalLink,
  Flame,
  Package,
  QrCode,
  ReceiptText,
  ShoppingBag,
  ShoppingCart,
  Sparkles,
  Store,
  TrendingUp,
  Utensils,
  WalletCards,
} from 'lucide-react';
import { fetchApi } from '@restaurantos/api-client';
import { redirectToPos } from '../../lib/posHandoff';
import { OnboardingWizardModal } from '../onboarding/OnboardingWizardModal';
import { QRCodeCard } from '../onboarding/QRCodeCard';
import './Overview.css';

type Branch = {
  id: string;
  name: string;
};

type DashboardData = {
  total_revenue_cents: number;
  total_orders: number;
  average_ticket_cents: number;
  total_products: number;
  period_from_utc: string;
  period_to_utc: string;
  order_types?: {
    mostrador: number;
    para_llevar: number;
    domicilio: number;
  };
  recent_transactions: Transaction[];
  activity_chart: ActivityPoint[];
  recent_notifications: NotificationItem[];
  popular_categories: CategoryItem[];
};

type ActivityPoint = {
  day: string;
  completed: number;
  pending: number;
};

type Transaction = {
  id: string;
  amount_cents: number;
  status: string;
  created_at: string;
  folio: string;
};

type NotificationItem = {
  id: string;
  action: string;
  created_at: string;
  register_code?: string;
  actor_name?: string;
};

type CategoryItem = {
  id: string;
  name: string;
  quantity: number;
  known_net_cents: number;
  share_bps: number;
};

type Product = {
  id: string;
  name: string;
  category_name?: string;
  price_cents?: number;
  image_url?: string | null;
};

const emptyDashboard: DashboardData = {
  total_revenue_cents: 0,
  total_orders: 0,
  average_ticket_cents: 0,
  total_products: 0,
  period_from_utc: '',
  period_to_utc: '',
  order_types: { mostrador: 0, para_llevar: 0, domicilio: 0 },
  recent_transactions: [],
  activity_chart: [],
  recent_notifications: [],
  popular_categories: [],
};

const monthFormatter = new Intl.DateTimeFormat('es-MX', { month: 'long', year: 'numeric' });
const dayFormatter = new Intl.DateTimeFormat('es-MX', { day: '2-digit', month: 'short' });

const formatCurrency = (cents: number) => {
  return new Intl.NumberFormat('es-MX', {
    style: 'currency',
    currency: 'MXN',
    maximumFractionDigits: 0,
  }).format(cents / 100);
};

const formatTime = (value: string) => {
  return new Date(value).toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' });
};

const formatDate = (value: string) => {
  return new Date(value).toLocaleDateString('es-MX', { day: '2-digit', month: 'short' });
};

const monthOptions = Array.from({ length: 5 }, (_, index) => {
  const date = new Date();
  date.setMonth(date.getMonth() - 2 + index);
  const value = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
  const label = monthFormatter.format(date);
  return { value, label: label.charAt(0).toUpperCase() + label.slice(1) };
});

export const Overview = () => {
  const navigate = useNavigate();
  const now = new Date();
  const currentMonthValue = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  const [data, setData] = useState<DashboardData>(emptyDashboard);
  const [products, setProducts] = useState<Product[]>([]);
  const [branches, setBranches] = useState<Branch[]>([]);
  const [selectedBranch, setSelectedBranch] = useState('');
  const [selectedMonth, setSelectedMonth] = useState(currentMonthValue);
  const [loading, setLoading] = useState(true);
  const [orgProfile, setOrgProfile] = useState<{
    id: string;
    name: string;
    slug: string;
    owner_phone?: string;
    trial_days_remaining: number;
    products_count: number;
  } | null>(null);
  const [isWizardOpen, setIsWizardOpen] = useState(false);
  const [onboardingStep, setOnboardingStep] = useState<'business' | 'menu' | 'register' | 'complete' | null>(null);

  useEffect(() => {
    fetchApi<{
      id: string;
      name: string;
      slug: string;
      owner_phone?: string;
      trial_days_remaining: number;
      products_count: number;
    }>('/organization/profile')
      .then((profile) => {
        if (profile) setOrgProfile(profile);
      })
      .catch((err) => {
        console.warn('Error al cargar perfil de organización en panel:', err);
      });
  }, []);

  useEffect(() => {
    fetchApi<{ step: 'business' | 'menu' | 'register' | 'complete' }>('/saas/onboarding')
      .then((setup) => setOnboardingStep(setup.step))
      .catch(() => setOnboardingStep(null));
  }, []);

  useEffect(() => {
    const fetchBranches = async () => {
      try {
        const response = await fetchApi<Branch[]>('/branches');
        setBranches(Array.isArray(response) ? response : []);
      } catch (error) {
        console.error(error);
      }
    };
    fetchBranches();
  }, []);

  useEffect(() => {
    const fetchDashboard = async () => {
      setLoading(true);
      try {
        const params = new URLSearchParams();
        if (selectedBranch) params.set('branch_id', selectedBranch);
        if (selectedMonth) params.set('month', selectedMonth);
        const suffix = params.toString() ? `?${params.toString()}` : '';
        const [overview, catalog] = await Promise.all([
          fetchApi<DashboardData>(`/dashboard/overview${suffix}`),
          fetchApi<Product[]>(
            selectedBranch
              ? `/catalog/products?branch_id=${encodeURIComponent(selectedBranch)}`
              : '/catalog/products'
          ),
        ]);
        setData(overview || emptyDashboard);
        setProducts(Array.isArray(catalog) ? catalog : []);
      } catch (error) {
        console.error('Error al cargar el panel', error);
      } finally {
        setLoading(false);
      }
    };
    fetchDashboard();
  }, [selectedBranch, selectedMonth]);

  const selectedBranchName = branches.find(branch => branch.id === selectedBranch)?.name || 'Todas las sucursales';
  const recentProducts = products.slice(0, 3);
  const maxActivity = Math.max(
    1,
    ...data.activity_chart.map(point => Math.max(point.completed, point.pending))
  );

  // Totales y distribución de canales
  const mostradorCount = data.order_types?.mostrador ?? 0;
  const llevarCount = data.order_types?.para_llevar ?? 0;
  const domicilioCount = data.order_types?.domicilio ?? 0;
  const totalChannelOrders = mostradorCount + llevarCount + domicilioCount;

  const mostradorPct = totalChannelOrders > 0 ? (mostradorCount / totalChannelOrders) * 100 : 0;
  const llevarPct = totalChannelOrders > 0 ? (llevarCount / totalChannelOrders) * 100 : 0;
  const domicilioPct = totalChannelOrders > 0 ? (domicilioCount / totalChannelOrders) * 100 : 0;

  const orderTypes = [
    { label: 'Mostrador', value: mostradorCount, pct: mostradorPct, color: '#10b981' },
    { label: 'Para llevar', value: llevarCount, pct: llevarPct, color: '#f97316' },
    { label: 'Domicilio', value: domicilioCount, pct: domicilioPct, color: '#0ea5e9' },
  ];

  const categoryColors = ['#10b981', '#f97316', '#0ea5e9', '#8b5cf6', '#64748b'];

  return (
    <main className="dash-container" aria-busy={loading}>
      {/* Header Ejecutivo */}
      <header className="dash-header">
        <div className="dash-header-left">
          <div className="dash-badge-eyebrow">
            <Store size={13} />
            <span>{selectedBranchName}</span>
          </div>
          <h1 className="dash-title">
            Hola, {orgProfile?.name || 'Administrador'} 👋
          </h1>
          <p className="dash-subtitle">
            Rendimiento de ventas, comensales y actividad operativa en tiempo real.
          </p>
        </div>

        <div className="dash-controls">
          {branches.length > 1 && (
            <label className="dash-select-pill">
              <Store size={15} color="#64748b" />
              <select
                value={selectedBranch}
                onChange={e => setSelectedBranch(e.target.value)}
                aria-label="Filtrar por sucursal"
              >
                <option value="">Todas las sucursales</option>
                {branches.map(b => (
                  <option key={b.id} value={b.id}>{b.name}</option>
                ))}
              </select>
              <ChevronDown size={14} color="#94a3b8" />
            </label>
          )}

          <label className="dash-select-pill">
            <CalendarDays size={15} color="#64748b" />
            <select
              value={selectedMonth}
              onChange={event => setSelectedMonth(event.target.value)}
              aria-label="Seleccionar mes del reporte"
            >
              {monthOptions.map(month => (
                <option key={month.value} value={month.value}>{month.label}</option>
              ))}
            </select>
            <ChevronDown size={14} color="#94a3b8" />
          </label>

          <button
            type="button"
            className="dash-cta-pos"
            onClick={() => void redirectToPos('pos').catch(() => navigate('/login'))}
          >
            <ShoppingCart size={16} />
            <span>Abrir POS</span>
          </button>
        </div>
      </header>

      {/* Asistente de Configuración Inicial (si está pendiente) */}
      {onboardingStep !== 'complete' && (
        <section
          style={{
            background: 'linear-gradient(135deg, #064e3b 0%, #047857 50%, #059669 100%)',
            borderRadius: 20,
            padding: '22px 28px',
            color: '#fff',
            boxShadow: '0 10px 25px -5px rgba(5, 150, 105, 0.25)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 20,
            flexWrap: 'wrap',
          }}
          aria-label="Asistente de configuración inicial"
        >
          <div style={{ maxWidth: 640 }}>
            <div
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                background: 'rgba(255, 255, 255, 0.2)',
                padding: '4px 12px',
                borderRadius: 9999,
                fontSize: '0.75rem',
                fontWeight: 700,
                marginBottom: 10,
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
              }}
            >
              <Sparkles size={14} /> Asistente de Configuración Inicial
            </div>
            <h2 style={{ fontSize: '1.35rem', fontWeight: 800, margin: '0 0 6px', color: '#fff', letterSpacing: '-0.02em' }}>
              ¡Bienvenido a RestaurantOS{orgProfile?.name ? `, ${orgProfile.name}` : ''}!
            </h2>
            <p style={{ margin: 0, fontSize: '0.9rem', color: '#d1fae5', lineHeight: 1.5 }}>
              Configura tu identidad comercial, carga tu menú inicial con 1 clic y genera tu Código QR listo para imprimir y recibir comandas.
            </p>
          </div>
          <div>
            <button
              type="button"
              onClick={() => setIsWizardOpen(true)}
              style={{
                background: '#fff',
                color: '#065f46',
                border: 'none',
                borderRadius: 14,
                padding: '12px 24px',
                fontWeight: 700,
                fontSize: '0.92rem',
                cursor: 'pointer',
                boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
                display: 'flex',
                alignItems: 'center',
                gap: 8,
              }}
            >
              <Sparkles size={16} style={{ color: '#10b981' }} />
              Iniciar Asistente (3 min)
            </button>
          </div>
        </section>
      )}

      {/* Grid de KPIs Superiores (4 métricas ejecutivas) */}
      <section className="dash-kpis-grid" aria-label="Métricas clave">
        {/* KPI 1: Ventas */}
        <article className="dash-kpi-card">
          <div className="dash-kpi-top">
            <div className="dash-kpi-icon-wrap emerald">
              <CircleDollarSign size={22} />
            </div>
            <span className="dash-kpi-pill emerald">
              <TrendingUp size={12} /> Confirmado
            </span>
          </div>
          <div className="dash-kpi-body">
            <span className="dash-kpi-label">Ventas del Período</span>
            <strong className="dash-kpi-value">{formatCurrency(data.total_revenue_cents)}</strong>
          </div>
          <p className="dash-kpi-footer">
            <CheckCircle2 size={13} style={{ color: '#10b981' }} />
            Ingresos netos por comandas pagadas
          </p>
        </article>

        {/* KPI 2: Total Órdenes */}
        <article className="dash-kpi-card">
          <div className="dash-kpi-top">
            <div className="dash-kpi-icon-wrap orange">
              <ShoppingBag size={22} />
            </div>
            <span className="dash-kpi-pill orange">
              En el mes
            </span>
          </div>
          <div className="dash-kpi-body">
            <span className="dash-kpi-label">Total de Comandas</span>
            <strong className="dash-kpi-value">{data.total_orders}</strong>
          </div>
          <p className="dash-kpi-footer">
            Mostrador, para llevar y servicio a domicilio
          </p>
        </article>

        {/* KPI 3: Ticket Promedio */}
        <article className="dash-kpi-card">
          <div className="dash-kpi-top">
            <div className="dash-kpi-icon-wrap indigo">
              <ReceiptText size={22} />
            </div>
            <span className="dash-kpi-pill indigo">
              Por orden
            </span>
          </div>
          <div className="dash-kpi-body">
            <span className="dash-kpi-label">Ticket Promedio</span>
            <strong className="dash-kpi-value">{formatCurrency(data.average_ticket_cents)}</strong>
          </div>
          <p className="dash-kpi-footer">
            Consumo promedio calculado
          </p>
        </article>

        {/* KPI 4: Catálogo Activo */}
        <article className="dash-kpi-card">
          <div className="dash-kpi-top">
            <div className="dash-kpi-icon-wrap slate">
              <Package size={22} />
            </div>
            <span className="dash-kpi-pill slate">
              Catálogo
            </span>
          </div>
          <div className="dash-kpi-body">
            <span className="dash-kpi-label">Productos Activos</span>
            <strong className="dash-kpi-value">{data.total_products}</strong>
          </div>
          <p className="dash-kpi-footer">
            Platillos y bebidas listados en menú
          </p>
        </article>
      </section>

      {/* Sección Central: Gráfica de Rendimiento + Widgets Laterales */}
      <section className="dash-middle-grid">
        {/* Card Principal: Actividad de Comandas & Distribución de Canales */}
        <div className="dash-card">
          <div className="dash-card-header">
            <div className="dash-card-header-left">
              <h2>
                <TrendingUp size={20} style={{ color: '#10b981' }} />
                Rendimiento de Comandas
              </h2>
              <p>Órdenes completadas y pendientes registradas durante los últimos días.</p>
            </div>
            <div className="dash-chart-legend">
              <div className="dash-chart-legend-item">
                <span className="dash-legend-dot" style={{ background: '#10b981' }} />
                <span>Completadas</span>
              </div>
              <div className="dash-chart-legend-item">
                <span className="dash-legend-dot" style={{ background: '#f97316' }} />
                <span>En proceso</span>
              </div>
            </div>
          </div>

          <div className="dash-chart-container">
            <div className="dash-chart-svg-wrap" aria-label="Gráfica de actividad de comandas">
              <svg viewBox="0 0 720 180" preserveAspectRatio="none">
                <defs>
                  <linearGradient id="completedGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#10b981" stopOpacity="0.28" />
                    <stop offset="100%" stopColor="#10b981" stopOpacity="0.01" />
                  </linearGradient>
                  <linearGradient id="pendingGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#f97316" stopOpacity="0.22" />
                    <stop offset="100%" stopColor="#f97316" stopOpacity="0.01" />
                  </linearGradient>
                </defs>

                {/* Gridlines */}
                {[30, 75, 120, 160].map(y => (
                  <line
                    key={y}
                    x1="0"
                    y1={y}
                    x2="720"
                    y2={y}
                    stroke="#f1f5f9"
                    strokeWidth="1"
                    strokeDasharray="4 4"
                  />
                ))}

                {/* Area fills */}
                {data.activity_chart.length > 0 && (
                  <>
                    <polygon
                      fill="url(#completedGradient)"
                      points={`0,170 ${data.activity_chart.map((point, index) => {
                        const x = data.activity_chart.length <= 1 ? 0 : (index / (data.activity_chart.length - 1)) * 720;
                        const y = 165 - (point.completed / maxActivity) * 135;
                        return `${x},${y}`;
                      }).join(' ')} 720,170`}
                    />
                    <polyline
                      fill="none"
                      stroke="#f97316"
                      strokeWidth="2.5"
                      strokeDasharray="5 4"
                      points={data.activity_chart.map((point, index) => {
                        const x = data.activity_chart.length <= 1 ? 0 : (index / (data.activity_chart.length - 1)) * 720;
                        const y = 165 - (point.pending / maxActivity) * 135;
                        return `${x},${y}`;
                      }).join(' ')}
                    />
                    <polyline
                      fill="none"
                      stroke="#10b981"
                      strokeWidth="3.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      points={data.activity_chart.map((point, index) => {
                        const x = data.activity_chart.length <= 1 ? 0 : (index / (data.activity_chart.length - 1)) * 720;
                        const y = 165 - (point.completed / maxActivity) * 135;
                        return `${x},${y}`;
                      }).join(' ')}
                    />
                  </>
                )}
              </svg>
            </div>

            <div className="dash-chart-axis-days">
              {(data.activity_chart.length ? data.activity_chart : [{ day: dayFormatter.format(now), completed: 0, pending: 0 }]).slice(-7).map(point => (
                <span key={point.day}>{point.day}</span>
              ))}
            </div>

            {/* Distribución por Canales de Venta */}
            <div className="dash-channels-block">
              <h3 className="dash-channels-title">Distribución por Canales de Venta</h3>

              <div className="dash-channels-bar-stacked">
                <div
                  className="dash-channel-segment"
                  style={{ width: `${mostradorPct}%`, background: '#10b981' }}
                  title={`Mostrador: ${mostradorCount} (${mostradorPct.toFixed(1)}%)`}
                />
                <div
                  className="dash-channel-segment"
                  style={{ width: `${llevarPct}%`, background: '#f97316' }}
                  title={`Para llevar: ${llevarCount} (${llevarPct.toFixed(1)}%)`}
                />
                <div
                  className="dash-channel-segment"
                  style={{ width: `${domicilioPct}%`, background: '#0ea5e9' }}
                  title={`Domicilio: ${domicilioCount} (${domicilioPct.toFixed(1)}%)`}
                />
              </div>

              <div className="dash-channels-stats">
                {orderTypes.map(item => (
                  <div key={item.label} className="dash-channel-stat-item">
                    <span className="dash-channel-stat-dot" style={{ background: item.color }} />
                    <div className="dash-channel-stat-info">
                      <span className="dash-channel-stat-label">{item.label}</span>
                      <strong className="dash-channel-stat-value">
                        {item.value} <span style={{ fontSize: '0.75rem', fontWeight: 600, color: '#94a3b8' }}>({item.pct.toFixed(0)}%)</span>
                      </strong>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Widgets Laterales: Lanzador POS + Menú Digital QR */}
        <aside className="dash-side-widgets">
          {/* Quick Action POS Launcher */}
          <div className="dash-pos-launcher-card">
            <div>
              <span className="dash-pos-launcher-badge">
                <ShoppingCart size={13} /> Caja y Comandas
              </span>
              <h3 className="dash-pos-launcher-title" style={{ marginTop: 12 }}>
                Punto de Venta POS
              </h3>
              <p className="dash-pos-launcher-desc">
                Accede rápidamente a la caja para tomar pedidos en mesa, mostrador y realizar cobros instantáneos.
              </p>
            </div>
            <button
              type="button"
              className="dash-pos-launcher-btn"
              onClick={() => void redirectToPos('pos').catch(() => navigate('/login'))}
            >
              <ShoppingCart size={16} />
              <span>Abrir Terminal POS</span>
            </button>
          </div>

          {/* Menú Digital QR Widget */}
          {orgProfile?.slug && (
            <div className="dash-card" style={{ padding: 20 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                <div>
                  <span className="dash-badge-eyebrow">
                    <QrCode size={13} /> Menú Digital QR
                  </span>
                  <h3 style={{ fontSize: '1.05rem', fontWeight: 800, margin: '6px 0 0', color: '#0f172a' }}>
                    Código de Mesa
                  </h3>
                </div>
                <button
                  type="button"
                  onClick={() => setIsWizardOpen(true)}
                  style={{
                    background: '#f1f5f9',
                    border: 'none',
                    borderRadius: 8,
                    padding: '5px 10px',
                    fontSize: '0.75rem',
                    cursor: 'pointer',
                    color: '#475569',
                    fontWeight: 600,
                  }}
                >
                  Asistente
                </button>
              </div>
              <QRCodeCard
                restaurantName={orgProfile.name}
                restaurantSlug={orgProfile.slug}
                whatsappPhone={orgProfile.owner_phone}
              />
            </div>
          )}
        </aside>
      </section>

      {/* Sección Inferior: Categorías Populares, Órdenes Recientes y Actividad de Caja */}
      <section className="dash-bottom-grid">
        {/* Categorías Principales */}
        <div className="dash-card">
          <div className="dash-card-header">
            <div className="dash-card-header-left">
              <h2>
                <Utensils size={18} style={{ color: '#10b981' }} />
                Categorías Populares
              </h2>
              <p>Distribución de ventas por grupo de productos.</p>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {data.popular_categories.slice(0, 5).map((category, index) => {
              const pct = (category.share_bps / 100).toFixed(1);
              const color = categoryColors[index % categoryColors.length];
              return (
                <div key={category.id} className="dash-category-item">
                  <div className="dash-category-item-head">
                    <span className="dash-category-name">
                      <span style={{ width: 8, height: 8, borderRadius: 9999, background: color }} />
                      {category.name}
                    </span>
                    <span className="dash-category-pct">{pct}%</span>
                  </div>
                  <div className="dash-category-bar-track">
                    <div
                      className="dash-category-bar-fill"
                      style={{ width: `${pct}%`, background: color }}
                    />
                  </div>
                </div>
              );
            })}

            {data.popular_categories.length === 0 && (
              <p className="dash-empty-state">No hay ventas por categoría registradas en este período.</p>
            )}
          </div>
        </div>

        {/* Órdenes Recientes (Tabla de Transacciones) */}
        <div className="dash-card">
          <div className="dash-card-header">
            <div className="dash-card-header-left">
              <h2>
                <WalletCards size={18} style={{ color: '#10b981' }} />
                Últimas Órdenes
              </h2>
              <p>Transacciones recientes registradas en el sistema.</p>
            </div>
            <button
              type="button"
              onClick={() => navigate('/orders')}
              style={{
                background: 'none',
                border: 'none',
                color: '#059669',
                fontSize: '0.82rem',
                fontWeight: 700,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 4,
              }}
            >
              <span>Ver todas</span>
              <ArrowUpRight size={14} />
            </button>
          </div>

          <div className="dash-table-wrapper">
            <table className="dash-table">
              <thead>
                <tr>
                  <th>Folio</th>
                  <th>Fecha</th>
                  <th>Estado</th>
                  <th style={{ textAlign: 'right' }}>Total</th>
                </tr>
              </thead>
              <tbody>
                {data.recent_transactions.slice(0, 6).map(transaction => (
                  <tr key={transaction.id}>
                    <td>
                      <span className="dash-folio-code">{transaction.folio}</span>
                    </td>
                    <td>{formatDate(transaction.created_at)}</td>
                    <td>
                      <span className="dash-status-badge">
                        <CheckCircle2 size={11} /> Confirmado
                      </span>
                    </td>
                    <td className="dash-amount-col">
                      {formatCurrency(transaction.amount_cents)}
                    </td>
                  </tr>
                ))}
                {data.recent_transactions.length === 0 && (
                  <tr>
                    <td colSpan={4} className="dash-empty-state">
                      Sin órdenes registradas en el período.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Actividad de Caja y Turnos */}
        <div className="dash-card">
          <div className="dash-card-header">
            <div className="dash-card-header-left">
              <h2>
                <BellRing size={18} style={{ color: '#10b981' }} />
                Turnos de Caja
              </h2>
              <p>Historial de aperturas y cierres operativos.</p>
            </div>
          </div>

          <div className="dash-shift-list">
            {data.recent_notifications.slice(0, 4).map(item => {
              const isOpen = item.action === 'cash_shift.opened';
              return (
                <div key={item.id} className="dash-shift-item">
                  <div className={`dash-shift-icon ${isOpen ? 'open' : 'closed'}`}>
                    {isOpen ? <CheckCircle2 size={18} /> : <Clock3 size={18} />}
                  </div>
                  <div className="dash-shift-details">
                    <h4 className="dash-shift-title">
                      {isOpen ? 'Caja Abierta' : 'Caja Cerrada'}
                    </h4>
                    <p className="dash-shift-meta">
                      {item.register_code || 'Caja'} • {item.actor_name || 'Sistema'}
                    </p>
                  </div>
                  <time className="dash-shift-time">
                    {formatTime(item.created_at)}
                  </time>
                </div>
              );
            })}

            {data.recent_notifications.length === 0 && (
              <p className="dash-empty-state">Sin aperturas o cierres de caja recientes.</p>
            )}
          </div>
        </div>
      </section>

      {/* Modal del Asistente de Configuración */}
      <OnboardingWizardModal
        isOpen={isWizardOpen}
        onClose={() => setIsWizardOpen(false)}
        onCompleted={() => {
          setOnboardingStep('complete');
          setIsWizardOpen(false);
        }}
      />
    </main>
  );
};

export default Overview;
