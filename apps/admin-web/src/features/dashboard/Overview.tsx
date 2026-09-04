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
  Download,
  Flame,
  Package,
  ReceiptText,
  Search,
  ShoppingBag,
  Store,
  Utensils,
  WalletCards,
  Carrot,
  Box,
  Truck,
  ClipboardCheck,
  Receipt,
  Briefcase,
  Bike,
  Share2,
  BarChart2,
  FileText,
  Users,
  Database,
  Tags,
  MessageSquareText,
  Plus,
  ShoppingCart,
  Layers,
  Trash2,
} from 'lucide-react';
import { fetchApi } from '@restaurantos/api-client';
import { redirectToPos } from '../../lib/posHandoff';
import { ExecutiveCopilot } from './ExecutiveCopilot';

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

const StatCard = ({
  title,
  value,
  helper,
  icon,
  tone,
}: {
  title: string;
  value: string;
  helper: string;
  icon: React.ReactNode;
  tone: 'green' | 'orange' | 'blue' | 'dark';
}) => (
  <section className={`admin-kpi-card ${tone}`}>
    <div className="admin-kpi-icon">{icon}</div>
    <div>
      <p>{title}</p>
      <strong>{value}</strong>
      <span>
        <ArrowUpRight size={14} />
        {helper}
      </span>
    </div>
  </section>
);

const Overview = () => {
  const navigate = useNavigate();
  const now = new Date();
  const currentMonthValue = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  const [data, setData] = useState<DashboardData>(emptyDashboard);
  const [products, setProducts] = useState<Product[]>([]);
  const [branches, setBranches] = useState<Branch[]>([]);
  const [selectedBranch, setSelectedBranch] = useState('');
  const [selectedMonth, setSelectedMonth] = useState(currentMonthValue);
  const [loading, setLoading] = useState(true);

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
  const orderTypes = [
    { label: 'Mostrador', value: data.order_types?.mostrador ?? 0, color: '#22c55e' },
    { label: 'Para llevar', value: data.order_types?.para_llevar ?? 0, color: '#f97316' },
    { label: 'Domicilio', value: data.order_types?.domicilio ?? 0, color: '#0f766e' },
  ];


  return (
    <main className="admin-dashboard-modern" aria-busy={loading}>
      <div className="admin-dashboard-heading">
        <div>
          <span className="admin-eyebrow">Resumen operativo</span>
          <h1>Panel administrativo</h1>
          <p>Ventas, turnos, productos y movimientos.</p>
        </div>
        <div className="admin-dashboard-filters">
          <label>
            <CalendarDays size={16} />
            <select value={selectedMonth} onChange={event => setSelectedMonth(event.target.value)}>
              {monthOptions.map(month => (
                <option key={month.value} value={month.value}>{month.label}</option>
              ))}
            </select>
            <ChevronDown size={15} />
          </label>
        </div>
      </div>

      <ExecutiveCopilot selectedBranchId={selectedBranch} branches={branches} />

      <section className="admin-kpi-grid">
        <StatCard
          title="Ventas del periodo"
          value={formatCurrency(data.total_revenue_cents)}
          helper="Actualizado con pagos confirmados"
          icon={<CircleDollarSign size={24} />}
          tone="green"
        />
        <StatCard
          title="Ordenes"
          value={String(data.total_orders)}
          helper="Incluye POS por sucursal"
          icon={<ShoppingBag size={24} />}
          tone="orange"
        />
        <StatCard
          title="Ticket promedio"
          value={formatCurrency(data.average_ticket_cents)}
          helper="Calculado por el backend"
          icon={<ReceiptText size={24} />}
          tone="blue"
        />
        <StatCard
          title="Productos activos"
          value={String(data.total_products)}
          helper="Catalogo disponible"
          icon={<Package size={24} />}
          tone="dark"
        />
      </section>

      {/* Central Modules Hub Menu */}
      <section className="admin-modules-section" aria-label="Módulos del sistema">
        <div className="admin-modules-section-header">
          <div>
            <h2>
              <Layers size={22} style={{ color: '#10b981' }} />
              Centro de Módulos Operativos
            </h2>
            <p>Acceso rápido a los módulos organizados por áreas de negocio.</p>
          </div>
        </div>

        <div className="admin-modules-grid">
          {/* 1. Catálogo y Menú */}
          <div className="admin-module-card">
            <div className="admin-module-header">
              <div className="admin-module-icon green">
                <Utensils size={24} />
              </div>
              <div className="admin-module-title-group">
                <h3>Catálogo y Menú</h3>
                <p>Platillos, recetas, categorías, modificadores e ingredientes extra.</p>
              </div>
            </div>
            <div className="admin-module-actions">
              <button type="button" className="admin-module-chip" onClick={() => navigate('/products')}>
                <Package size={13} /> Productos
              </button>
              <button type="button" className="admin-module-chip" onClick={() => navigate('/recipes')}>
                <Utensils size={13} /> Recetas
              </button>
              <button type="button" className="admin-module-chip" onClick={() => navigate('/categories')}>
                <Tags size={13} /> Categorías
              </button>
              <button type="button" className="admin-module-chip" onClick={() => navigate('/variations')}>
                <MessageSquareText size={13} /> Modificadores
              </button>
              <button type="button" className="admin-module-chip" onClick={() => navigate('/ingredient-extras')}>
                <Plus size={13} /> Extras
              </button>
            </div>
          </div>

          {/* 2. Inventario y Almacén */}
          <div className="admin-module-card">
            <div className="admin-module-header">
              <div className="admin-module-icon amber">
                <Box size={24} />
              </div>
              <div className="admin-module-title-group">
                <h3>Inventario y Almacén</h3>
                <p>Insumos base, almacenes, lotes de producción, mermas y traspasos.</p>
              </div>
            </div>
            <div className="admin-module-actions">
              <button type="button" className="admin-module-chip" onClick={() => navigate('/inventory/items')}>
                <Carrot size={13} /> Insumos
              </button>
              <button type="button" className="admin-module-chip" onClick={() => navigate('/warehouses')}>
                <Box size={13} /> Almacenes
              </button>
              <button type="button" className="admin-module-chip" onClick={() => navigate('/production')}>
                <Flame size={13} /> Producción
              </button>
              <button type="button" className="admin-module-chip" onClick={() => navigate('/inventory/waste')}>
                <Trash2 size={13} /> Mermas
              </button>
              <button type="button" className="admin-module-chip" onClick={() => navigate('/inventory/transfers')}>
                <Truck size={13} /> Traspasos
              </button>
              <button type="button" className="admin-module-chip" onClick={() => navigate('/inventory/counts')}>
                <ClipboardCheck size={13} /> Conteos
              </button>
            </div>
          </div>

          {/* 3. Compras y Proveedores */}
          <div className="admin-module-card">
            <div className="admin-module-header">
              <div className="admin-module-icon blue">
                <Receipt size={24} />
              </div>
              <div className="admin-module-title-group">
                <h3>Compras y Proveedores</h3>
                <p>Facturas de compras, catálogo de proveedores y presentaciones de compra.</p>
              </div>
            </div>
            <div className="admin-module-actions">
              <button type="button" className="admin-module-chip" onClick={() => navigate('/purchases')}>
                <Receipt size={13} /> Compras
              </button>
              <button type="button" className="admin-module-chip" onClick={() => navigate('/suppliers')}>
                <Briefcase size={13} /> Proveedores
              </button>
              <button type="button" className="admin-module-chip" onClick={() => navigate('/purchase-presentations')}>
                <Package size={13} /> Presentaciones
              </button>
            </div>
          </div>

          {/* 4. Sucursales y Canales */}
          <div className="admin-module-card">
            <div className="admin-module-header">
              <div className="admin-module-icon purple">
                <Store size={24} />
              </div>
              <div className="admin-module-title-group">
                <h3>Sucursales y Canales</h3>
                <p>Sucursales activas, repartidores e integraciones Uber Eats.</p>
              </div>
            </div>
            <div className="admin-module-actions">
              <button type="button" className="admin-module-chip" onClick={() => navigate('/branches')}>
                <Store size={13} /> Sucursales
              </button>
              <button type="button" className="admin-module-chip" onClick={() => navigate('/drivers')}>
                <Bike size={13} /> Repartidores
              </button>
              <button type="button" className="admin-module-chip primary-action" onClick={() => navigate('/integrations')}>
                <Share2 size={13} /> Integraciones Uber
              </button>
              <button type="button" className="admin-module-chip" onClick={() => navigate('/cash-concepts')}>
                <Briefcase size={13} /> Conceptos Caja
              </button>
            </div>
          </div>

          {/* 5. Ventas y Reportes */}
          <div className="admin-module-card">
            <div className="admin-module-header">
              <div className="admin-module-icon teal">
                <BarChart2 size={24} />
              </div>
              <div className="admin-module-title-group">
                <h3>Ventas y Reportes</h3>
                <p>Monitor de ventas en vivo, reportes históricos, comandas y reembolsos.</p>
              </div>
            </div>
            <div className="admin-module-actions">
              <button
                type="button"
                className="admin-module-chip"
                onClick={() => void redirectToPos('/sales-monitor').catch(() => navigate('/login'))}
              >
                <BarChart2 size={13} /> Monitor Ventas
              </button>
              <button
                type="button"
                className="admin-module-chip"
                onClick={() => void redirectToPos('/historical-reports').catch(() => navigate('/login'))}
              >
                <FileText size={13} /> Reportes Históricos
              </button>
              <button type="button" className="admin-module-chip" onClick={() => navigate('/orders')}>
                <ReceiptText size={13} /> Órdenes
              </button>
              <button type="button" className="admin-module-chip" onClick={() => navigate('/reports')}>
                <WalletCards size={13} /> Reembolsos
              </button>
            </div>
          </div>

          {/* 6. Punto de Venta & Sistema */}
          <div className="admin-module-card">
            <div className="admin-module-header">
              <div className="admin-module-icon dark">
                <ShoppingCart size={24} />
              </div>
              <div className="admin-module-title-group">
                <h3>Punto de Venta & Accesos</h3>
                <p>Operación en caja, usuarios, permisos corporativos e importaciones.</p>
              </div>
            </div>
            <div className="admin-module-actions">
              <button
                type="button"
                className="admin-module-chip primary-action"
                onClick={() => void redirectToPos('pos').catch(() => navigate('/login'))}
              >
                <ShoppingCart size={13} /> Abrir Punto de Venta POS
              </button>
              <button type="button" className="admin-module-chip" onClick={() => navigate('/users')}>
                <Users size={13} /> Usuarios
              </button>
              <button type="button" className="admin-module-chip" onClick={() => navigate('/imports')}>
                <Database size={13} /> Importaciones
              </button>
            </div>
          </div>
        </div>
      </section>

      <section className="admin-dashboard-grid">
        <div className="admin-card admin-revenue-card">
          <div className="admin-card-header">
            <div>
              <span>Ventas</span>
              <h2>Actividad del periodo</h2>
            </div>
            <span className="admin-soft-pill">
              <WalletCards size={15} />
              {formatCurrency(data.total_revenue_cents)}
            </span>
          </div>
          <div className="admin-line-chart" aria-label="Grafica de actividad de ordenes">
            <svg viewBox="0 0 720 220" role="img">
              <defs>
                <linearGradient id="adminRevenueFill" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0%" stopColor="#22c55e" stopOpacity="0.24" />
                  <stop offset="100%" stopColor="#22c55e" stopOpacity="0.02" />
                </linearGradient>
              </defs>
              {[40, 80, 120, 160, 200].map(y => (
                <line key={y} x1="0" y1={y} x2="720" y2={y} className="admin-chart-gridline" />
              ))}
              <polyline
                className="admin-chart-line secondary"
                points={data.activity_chart.map((point, index) => {
                  const x = data.activity_chart.length <= 1 ? 0 : (index / (data.activity_chart.length - 1)) * 720;
                  const y = 210 - (point.pending / maxActivity) * 170;
                  return `${x},${y}`;
                }).join(' ')}
              />
              <polyline
                className="admin-chart-line"
                points={data.activity_chart.map((point, index) => {
                  const x = data.activity_chart.length <= 1 ? 0 : (index / (data.activity_chart.length - 1)) * 720;
                  const y = 210 - (point.completed / maxActivity) * 170;
                  return `${x},${y}`;
                }).join(' ')}
              />
            </svg>
          </div>
          <div className="admin-chart-days">
            {(data.activity_chart.length ? data.activity_chart : [{ day: dayFormatter.format(now), completed: 0, pending: 0 }]).slice(-7).map(point => (
              <span key={point.day}>{point.day}</span>
            ))}
          </div>
        </div>

        <div className="admin-card admin-donut-card">
          <div className="admin-card-header">
            <div>
              <span>Catalogo</span>
              <h2>Categorias principales</h2>
            </div>
          </div>
          <div className="admin-donut-wrap">
            <div className="admin-donut" />
            <div className="admin-donut-center">
              <strong>{data.popular_categories.length}</strong>
              <span>categorias</span>
            </div>
          </div>
          <div className="admin-category-list">
            {data.popular_categories.slice(0, 4).map((category, index) => (
              <div key={category.id}>
                <span className={`admin-category-dot dot-${index + 1}`} />
                <p>{category.name}</p>
                <strong>{(category.share_bps / 100).toFixed(1)}%</strong>
              </div>
            ))}
            {data.popular_categories.length === 0 && <p className="admin-empty-copy">Sin categorias registradas.</p>}
          </div>
        </div>

        <div className="admin-card admin-orders-card">
          <div className="admin-card-header">
            <div>
              <span>Ordenes</span>
              <h2>Resumen por tipo</h2>
            </div>
          </div>
          <div className="admin-order-type-list">
            {orderTypes.map(item => (
              <div key={item.label}>
                <div>
                  <span style={{ background: item.color }} />
                  <p>{item.label}</p>
                </div>
                <strong>{item.value}</strong>
              </div>
            ))}
          </div>
        </div>

        <aside className="admin-side-column">
          <div className="admin-card admin-trending-card">
            <div className="admin-card-header">
              <div>
                <span>Menu</span>
                <h2>Productos destacados</h2>
              </div>
              <Flame size={18} />
            </div>
            <div className="admin-product-list">
              {recentProducts.map(product => (
                <article key={product.id}>
                  <div className="admin-product-thumb">
                    {product.image_url ? (
                      <img src={product.image_url} alt={product.name} />
                    ) : (
                      <Utensils size={28} />
                    )}
                  </div>
                  <div>
                    <h3>{product.name}</h3>
                    <p>{product.category_name || 'Sin categoria'}</p>
                    <strong>{formatCurrency(product.price_cents || 0)}</strong>
                  </div>
                </article>
              ))}
              {recentProducts.length === 0 && <p className="admin-empty-copy">Agrega productos para verlos aqui.</p>}
            </div>
          </div>

          <div className="admin-card admin-activity-card">
            <div className="admin-card-header">
              <div>
                <span>Turnos</span>
                <h2>Actividad reciente</h2>
              </div>
              <BellRing size={18} />
            </div>
            <div className="admin-activity-list">
              {data.recent_notifications.slice(0, 5).map(item => {
                const isOpen = item.action === 'cash_shift.opened';
                return (
                  <article key={item.id}>
                    <div className={isOpen ? 'open' : 'closed'}>
                      {isOpen ? <CheckCircle2 size={17} /> : <Clock3 size={17} />}
                    </div>
                    <div>
                      <strong>{isOpen ? 'Caja abierta' : 'Caja cerrada'}</strong>
                      <p>{item.register_code || 'Caja'} por {item.actor_name || 'Sistema'}</p>
                    </div>
                    <time>{formatTime(item.created_at)}</time>
                  </article>
                );
              })}
              {data.recent_notifications.length === 0 && <p className="admin-empty-copy">Sin actividad de caja reciente.</p>}
            </div>
          </div>
        </aside>

        <div className="admin-card admin-transactions-card">
          <div className="admin-card-header">
            <div>
              <span>Pagos</span>
              <h2>Ordenes recientes</h2>
            </div>
            <div className="admin-table-actions">
              <Search size={16} />
              <Download size={16} />
            </div>
          </div>
          <div className="admin-table-shell">
            <table className="admin-modern-table">
              <thead>
                <tr>
                  <th>Folio</th>
                  <th>Fecha</th>
                  <th>Estado</th>
                  <th>Monto</th>
                </tr>
              </thead>
              <tbody>
                {data.recent_transactions.map(transaction => (
                  <tr key={transaction.id}>
                    <td>{transaction.folio}</td>
                    <td>{formatDate(transaction.created_at)}</td>
                    <td><span className="admin-status-pill">Confirmado</span></td>
                    <td>{formatCurrency(transaction.amount_cents)}</td>
                  </tr>
                ))}
                {data.recent_transactions.length === 0 && (
                  <tr>
                    <td colSpan={4}>No hay transacciones recientes.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </main>
  );
};

export default Overview;
