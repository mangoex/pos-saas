import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Overview from './features/dashboard/Overview';
import Login from './features/auth/Login';
import AdminLayout from './components/AdminLayout';
import ProductsList from './features/catalog/ProductsList';
import CategoriesList from './features/catalog/CategoriesList';
import BranchesList from './features/branches/BranchesList';
import WarehousesList from './features/branches/WarehousesList';
import UnitsList from './features/inventory/UnitsList';
import ItemsList from './features/inventory/ItemsList';
import UsersList from './features/users/UsersList';
import RolesList from './features/users/RolesList';
import CustomersList from './features/customers/CustomersList';
import SuppliersList from './features/purchasing/SuppliersList';
import PurchasesList from './features/purchasing/PurchasesList';
import PresentationsList from './features/purchasing/PresentationsList';
import ProductionList from './features/production/ProductionList';
import WasteList from './features/inventory/WasteList';
import TransferList from './features/inventory/TransferList';
import PhysicalCountList from './features/inventory/PhysicalCountList';
import LegacyImportReview from './features/imports/LegacyImportReview';
import VariationNotes from './features/catalog/VariationNotes';
import IngredientExtras from './features/catalog/IngredientExtras';
import DriversList from './features/delivery/DriversList';
import CategoryOptionManager from './features/catalog/CategoryOptionManager';
import CashConceptsManager from './features/cash/CashConceptsManager';
import RecipesWorkspace from './features/recipes/RecipesWorkspace';
import CorporateReconciliationDashboard from './features/reports/CorporateReconciliationDashboard';
import IntegrationsHub from './features/integrations/IntegrationsHub';
import { CatalogHub } from './features/hubs/CatalogHub';
import { InventoryHub } from './features/hubs/InventoryHub';
import { PurchasingHub } from './features/hubs/PurchasingHub';
import { BranchesHub } from './features/hubs/BranchesHub';
import { ReportsHub } from './features/hubs/ReportsHub';
import { AdminAccessHub } from './features/hubs/AdminAccessHub';
import { canManageCashConcepts } from './features/cash/cashConceptState';
import { redirectToPos } from './lib/posHandoff';
import { SaaSConsoleView } from './features/superadmin/SaaSConsoleView';

const SuperadminRoute = ({ children }: { children: React.ReactNode }) => {
  const user = JSON.parse(localStorage.getItem('user') || '{}');
  if (!user.is_superadmin) {
    return <Navigate to="/" replace />;
  }
  return <>{children}</>;
};

const ProtectedRoute = ({ children }: { children: React.ReactNode }) => {
  const token = localStorage.getItem('auth_token') || sessionStorage.getItem('auth_token');
  if (!token) {
    return <Navigate to="/login" replace />;
  }
  try {
    const user = JSON.parse(localStorage.getItem('user') || '{}');
    const userRoles: string[] = user.roles || [];
    const permissions: string[] = user.permissions || [];
    const isPureCashier = userRoles.includes('Cajero')
      && userRoles.length === 1
      && !userRoles.includes('Cajero Jefe')
      && !userRoles.includes('Líder')
      && !userRoles.includes('Supervisor')
      && !userRoles.includes('Administrador')
      && !userRoles.includes('Administrador de Restaurante')
      && !userRoles.includes('Dueño')
      && !permissions.includes('admin.manage')
      && !permissions.includes('dashboard.read')
      && !permissions.includes('branch.admin.access')
      && !permissions.includes('purchases.read')
      && !permissions.includes('inventory.read')
      && !permissions.includes('inventory.waste');

    if (isPureCashier) {
      const handleLogoutAndSwitch = () => {
        localStorage.removeItem('auth_token');
        localStorage.removeItem('user');
        sessionStorage.removeItem('auth_token');
        window.location.href = '/admin/login';
      };

      const goToPos = () => {
        void redirectToPos('pos').catch(() => {
          window.location.href = '/admin/login';
        });
      };

      return (
        <div style={{ display: 'flex', minHeight: '100vh', alignItems: 'center', justifyContent: 'center', background: '#f8fafc', padding: 20 }}>
          <div style={{ maxWidth: 480, width: '100%', background: '#fff', padding: 32, borderRadius: 16, border: '1px solid #e2e8f0', textAlign: 'center', boxShadow: '0 10px 25px -5px rgba(0,0,0,0.05)' }}>
            <div style={{ fontSize: 48, marginBottom: 12 }}>🏷️</div>
            <h2 style={{ margin: '0 0 8px', color: '#0f172a', fontSize: '1.4rem' }}>Acceso al Panel de Administración</h2>
            <p style={{ color: '#64748b', fontSize: '0.9375rem', marginBottom: 24 }}>
              La cuenta activa <strong>{user.display_name || user.email}</strong> tiene rol de <strong>Cajero</strong> exclusivo para operación de terminal POS.
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <button
                onClick={goToPos}
                style={{ padding: '12px 20px', borderRadius: 8, background: '#10b981', color: '#fff', border: 'none', fontWeight: 600, fontSize: '0.95rem', cursor: 'pointer' }}
              >
                Abrir Punto de Venta (POS)
              </button>
              <button
                onClick={handleLogoutAndSwitch}
                style={{ padding: '10px 20px', borderRadius: 8, background: 'transparent', color: '#ef4444', border: '1px solid #fca5a5', fontWeight: 600, fontSize: '0.95rem', cursor: 'pointer' }}
              >
                Cerrar sesión / Cambiar de cuenta
              </button>
            </div>
          </div>
        </div>
      );
    }
  } catch (e) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
};

const CatalogManageRoute = ({ children }: { children: React.ReactNode }) => {
  const user = JSON.parse(localStorage.getItem('user') || '{}');
  const permissions: string[] = user.permissions || [];
  if (!user.is_superadmin && !permissions.includes('catalog.manage')) {
    return <Navigate to="/" replace />;
  }
  return <>{children}</>;
};

const RecipesManageRoute = ({ children }: { children: React.ReactNode }) => {
  const user = JSON.parse(localStorage.getItem('user') || '{}');
  const permissions: string[] = user.permissions || [];
  if (!permissions.includes('recipes.manage')) return <Navigate to="/" replace />;
  return <>{children}</>;
};

const CashConceptManageRoute = ({ children }: { children: React.ReactNode }) => {
  const user = JSON.parse(localStorage.getItem('user') || '{}');
  const permissions: string[] = user.permissions || [];
  if (!canManageCashConcepts({ permissions })) {
    return <Navigate to="/" replace />;
  }
  return <>{children}</>;
};

export const App = () => {
  return (
    <BrowserRouter basename="/admin">
      <Routes>
        <Route path="/login" element={<Login />} />
        
        <Route path="/" element={
          <ProtectedRoute>
            <AdminLayout />
          </ProtectedRoute>
        }>
          <Route index element={<Overview />} />
          <Route path="superadmin" element={<SuperadminRoute><SaaSConsoleView /></SuperadminRoute>} />

          {/* Category Hubs (POS Style Grid Views) */}
          <Route path="catalog" element={<CatalogHub />} />
          <Route path="inventory" element={<InventoryHub />} />
          <Route path="purchasing" element={<PurchasingHub />} />
          <Route path="branches-hub" element={<BranchesHub />} />
          <Route path="reports-hub" element={<ReportsHub />} />
          <Route path="admin-access-hub" element={<AdminAccessHub />} />

          {/* Subroutes: Catálogo y Menú */}
          <Route path="products" element={<ProductsList />} />
          <Route path="recipes" element={<RecipesManageRoute><RecipesWorkspace /></RecipesManageRoute>} />
          <Route path="categories" element={<CategoriesList />} />
          <Route path="variations" element={<VariationNotes />} />
          <Route path="ingredient-extras" element={<IngredientExtras />} />
          <Route path="category-options" element={<CatalogManageRoute><CategoryOptionManager /></CatalogManageRoute>} />

          {/* Subroutes: Inventario y Almacén */}
          <Route path="inventory/items" element={<ItemsList />} />
          <Route path="warehouses" element={<CatalogManageRoute><WarehousesList /></CatalogManageRoute>} />
          <Route path="production" element={<ProductionList />} />
          <Route path="inventory/waste" element={<WasteList />} />
          <Route path="inventory/transfers" element={<TransferList />} />
          <Route path="inventory/counts" element={<PhysicalCountList />} />
          <Route path="inventory/units" element={<UnitsList />} />

          {/* Subroutes: Compras y Proveedores */}
          <Route path="purchases" element={<PurchasesList />} />
          <Route path="suppliers" element={<SuppliersList />} />
          <Route path="purchase-presentations" element={<PresentationsList />} />

          {/* Subroutes: Sucursales y Canales */}
          <Route path="branches" element={<BranchesList />} />
          <Route path="drivers" element={<DriversList />} />
          <Route path="integrations" element={<IntegrationsHub />} />
          <Route path="invoicing" element={<IntegrationsHub defaultProvider="FACTURAPI" />} />
          <Route path="cash-concepts" element={<CashConceptManageRoute><CashConceptsManager /></CashConceptManageRoute>} />

          {/* Subroutes: Ventas y Reportes */}
          <Route path="reports" element={<CorporateReconciliationDashboard />} />
          <Route path="waste" element={<WasteList />} />
          <Route path="analytics" element={<div style={{ padding: 24 }}><h2>Analytics</h2><p>Panel de Métricas en vivo...</p></div>} />

          {/* Subroutes: Administración y Accesos */}
          <Route path="users" element={<UsersList />} />
          <Route path="roles" element={<RolesList />} />
          <Route path="customers" element={<CustomersList />} />
          <Route path="imports" element={<LegacyImportReview />} />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
};

export default App;
