import React from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { ChevronLeft } from 'lucide-react';
import { canManageCashConcepts } from '../features/cash/cashConceptState';

interface SubNavItem {
  path: string;
  label: string;
  requiredPermission?: (user: any) => boolean;
}

interface CategoryNavConfig {
  hubPath: string;
  categoryTitle: string;
  items: SubNavItem[];
}

const CATEGORY_CONFIGS: CategoryNavConfig[] = [
  {
    hubPath: '/catalog',
    categoryTitle: 'Catálogo y Precios',
    items: [
      { path: '/products', label: 'Productos y Precios' },
      { path: '/categories', label: 'Categorías' },
      { path: '/ingredient-extras', label: 'Ingredientes Extra' },
      { path: '/variations', label: 'Notas de Comanda' },
    ],
  },
  {
    hubPath: '/inventory',
    categoryTitle: 'Inventario y Almacén',
    items: [
      { path: '/inventory/items', label: 'Insumos' },
      {
        path: '/warehouses',
        label: 'Almacenes',
        requiredPermission: (user: any) =>
          Boolean(user.is_superadmin || (user.permissions || []).includes('catalog.manage')),
      },
      { path: '/production', label: 'Producción de Lotes' },
      { path: '/inventory/waste', label: 'Mermas' },
      { path: '/inventory/transfers', label: 'Traspasos' },
      { path: '/inventory/counts', label: 'Conteos Físicos' },
      { path: '/inventory/units', label: 'Unidades' },
    ],
  },
  {
    hubPath: '/purchasing',
    categoryTitle: 'Compras y Proveedores',
    items: [
      { path: '/purchases', label: 'Compras directas' },
      { path: '/suppliers', label: 'Proveedores' },
      { path: '/purchase-presentations', label: 'Presentaciones' },
    ],
  },
  {
    hubPath: '/branches-hub',
    categoryTitle: 'Sucursales y Canales',
    items: [
      { path: '/branches', label: 'Datos del Negocio' },
      { path: '/integrations', label: 'Canales de Delivery (Apps)' },
      { path: '/invoicing', label: 'Facturación SAT' },
      { path: '/drivers', label: 'Repartidores' },
    ],
  },
  {
    hubPath: '/reports-hub',
    categoryTitle: 'Cajas y Reportes',
    items: [
      { path: '/reports', label: 'Cortes X/Z y Ventas' },
      {
        path: '/cash-concepts',
        label: 'Conceptos de Caja',
        requiredPermission: (user) => canManageCashConcepts(user),
      },
      { path: '/waste', label: 'Mermas y Desperdicios' },
    ],
  },
  {
    hubPath: '/admin-access-hub',
    categoryTitle: 'Equipo y Cajeros',
    items: [
      { path: '/users', label: 'Cajeros y Usuarios' },
      { path: '/roles', label: 'Roles y Permisos' },
      { path: '/customers', label: 'Directorio de Clientes' },
    ],
  },
];

export const CategorySubNav: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const currentUser = JSON.parse(localStorage.getItem('user') || '{}');

  // Find active category
  const activeCategory = CATEGORY_CONFIGS.find(
    (cat) =>
      cat.items.some((item) => item.path === location.pathname) &&
      cat.hubPath !== location.pathname
  );

  if (!activeCategory) return null;

  const visibleItems = activeCategory.items.filter(
    (item) => !item.requiredPermission || item.requiredPermission(currentUser)
  );

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: '12px',
        background: '#ffffff',
        padding: '8px 16px',
        borderRadius: '16px',
        border: '1px solid #e2e8f0',
        marginBottom: '24px',
        boxShadow: '0 2px 6px rgba(0,0,0,0.02)',
      }}
    >
      {/* Back button to Category Hub */}
      <button
        onClick={() => navigate(activeCategory.hubPath)}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '6px',
          background: '#f1f5f9',
          border: 'none',
          padding: '8px 14px',
          borderRadius: '10px',
          fontSize: '0.85rem',
          fontWeight: 600,
          color: '#334155',
          cursor: 'pointer',
          transition: 'all 0.15s ease',
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.background = '#e2e8f0';
          e.currentTarget.style.color = '#0f172a';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.background = '#f1f5f9';
          e.currentTarget.style.color = '#334155';
        }}
      >
        <ChevronLeft size={16} />
        <span>Menú {activeCategory.categoryTitle}</span>
      </button>

      {/* Pill tabs */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          overflowX: 'auto',
          paddingBottom: '2px',
        }}
      >
        {visibleItems.map((item) => {
          const isActive = location.pathname === item.path;
          return (
            <button
              key={item.path}
              onClick={() => navigate(item.path)}
              style={{
                padding: '7px 14px',
                borderRadius: '8px',
                border: isActive ? '1px solid #10b981' : '1px solid transparent',
                background: isActive ? '#ecfdf5' : 'transparent',
                color: isActive ? '#065f46' : '#64748b',
                fontWeight: isActive ? 700 : 500,
                fontSize: '0.85rem',
                cursor: 'pointer',
                transition: 'all 0.15s ease',
                whiteSpace: 'nowrap',
              }}
              onMouseEnter={(e) => {
                if (!isActive) {
                  e.currentTarget.style.background = '#f8fafc';
                  e.currentTarget.style.color = '#0f172a';
                }
              }}
              onMouseLeave={(e) => {
                if (!isActive) {
                  e.currentTarget.style.background = 'transparent';
                  e.currentTarget.style.color = '#64748b';
                }
              }}
            >
              {item.label}
            </button>
          );
        })}
      </div>
    </div>
  );
};
