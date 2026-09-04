import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchApi } from '@restaurantos/api-client';
import {
  Crown,
  Building,
  DollarSign,
  ShoppingBag,
  TrendingUp,
  Search,
  Plus,
  LogIn,
  PauseCircle,
  PlayCircle,
  Edit,
  Sparkles,
  CheckCircle2,
  AlertCircle,
  Store,
  FileText,
  X,
  Phone,
  Mail,
  User,
  Key,
  Copy,
  Eye,
  EyeOff,
  Check,
} from 'lucide-react';

interface SaaSMetrics {
  total_tenants: number;
  active_tenants: number;
  suspended_tenants: number;
  trialing_tenants: number;
  mrr_cents: number;
  total_orders: number;
  gmv_cents: number;
}

interface Tenant {
  id: string;
  name: string;
  status: string;
  plan: string;
  subscription_status: string;
  monthly_fee_cents: number;
  suspended_reason?: string | null;
  owner_name?: string | null;
  owner_email?: string | null;
  owner_phone?: string | null;
  business_type?: string | null;
  created_at?: string | null;
  branches_count: number;
  products_count: number;
  orders_count: number;
}

export const SaaSConsoleView: React.FC = () => {
  const queryClient = useQueryClient();
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [planFilter, setPlanFilter] = useState<string>('all');

  // Modal states
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [selectedTenantForPlan, setSelectedTenantForPlan] = useState<Tenant | null>(null);
  const [selectedTenantForStatus, setSelectedTenantForStatus] = useState<Tenant | null>(null);
  const [selectedTenantForEdit, setSelectedTenantForEdit] = useState<Tenant | null>(null);

  // Form states for creating a new tenant
  const [formBusinessName, setFormBusinessName] = useState('');
  const [formOwnerName, setFormOwnerName] = useState('');
  const [formEmail, setFormEmail] = useState('');
  const [formPhone, setFormPhone] = useState('');
  const [formBusinessType, setFormBusinessType] = useState('taqueria');
  const [formPlan, setFormPlan] = useState('starter_349');
  const [formMenuMode, setFormMenuMode] = useState<'generate_by_type' | 'ai_import' | 'blank'>('generate_by_type');
  const [formAiMenuText, setFormAiMenuText] = useState('');
  const [formPassword, setFormPassword] = useState('Password123!');
  const [showFormPassword, setShowFormPassword] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  // States for created credentials modal
  const [createdCredentials, setCreatedCredentials] = useState<{
    restaurant_name: string;
    owner_name: string;
    email: string;
    password: string;
    branch_name?: string;
    tenant_id?: string;
  } | null>(null);
  const [copiedCredentials, setCopiedCredentials] = useState(false);

  // Form states for edit tenant modal
  const [editName, setEditName] = useState('');
  const [editBusinessType, setEditBusinessType] = useState('taqueria');
  const [editOwnerName, setEditOwnerName] = useState('');
  const [editEmail, setEditEmail] = useState('');
  const [editPhone, setEditPhone] = useState('');
  const [editPlan, setEditPlan] = useState('starter_349');
  const [editStatus, setEditStatus] = useState('active');

  // Form states for status/plan updates
  const [newPlan, setNewPlan] = useState('pro_599');
  const [suspendReason, setSuspendReason] = useState('Falta de pago mensual');

  // Queries
  const { data: metrics } = useQuery<SaaSMetrics>({
    queryKey: ['saas-metrics'],
    queryFn: () => fetchApi<SaaSMetrics>('/superadmin/metrics'),
    refetchInterval: 30000,
  });

  const { data: tenants = [], isLoading: isLoadingTenants } = useQuery<Tenant[]>({
    queryKey: ['saas-tenants', searchTerm, statusFilter, planFilter],
    queryFn: () => {
      const params = new URLSearchParams();
      if (searchTerm.trim()) params.set('search', searchTerm.trim());
      if (statusFilter !== 'all') params.set('status', statusFilter);
      if (planFilter !== 'all') params.set('plan', planFilter);
      return fetchApi<Tenant[]>(`/superadmin/tenants?${params.toString()}`);
    },
  });

  // Mutations
  const createTenantMutation = useMutation({
    mutationFn: (payload: any) =>
      fetchApi('/superadmin/tenants', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    onSuccess: (data: any) => {
      queryClient.invalidateQueries({ queryKey: ['saas-tenants'] });
      queryClient.invalidateQueries({ queryKey: ['saas-metrics'] });
      setIsCreateModalOpen(false);
      if (data?.credentials) {
        setCreatedCredentials({
          restaurant_name: data.tenant?.name || formBusinessName,
          owner_name: data.credentials.display_name || formOwnerName,
          email: data.credentials.email || formEmail,
          password: data.credentials.password || formPassword,
          branch_name: data.branch?.name || 'Sucursal Matriz',
          tenant_id: data.tenant?.id,
        });
      }
      resetForm();
    },
    onError: (err: any) => {
      setCreateError(err.message || 'Error al crear el restaurante');
    },
  });

  const updateTenantMutation = useMutation({
    mutationFn: ({ tenantId, payload }: { tenantId: string; payload: any }) =>
      fetchApi(`/superadmin/tenants/${tenantId}`, {
        method: 'PUT',
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['saas-tenants'] });
      queryClient.invalidateQueries({ queryKey: ['saas-metrics'] });
      setSelectedTenantForEdit(null);
    },
    onError: (err: any) => {
      alert(err.message || 'Error al actualizar restaurante');
    },
  });

  const updateStatusMutation = useMutation({
    mutationFn: ({ tenantId, status, reason }: { tenantId: string; status: string; reason?: string }) =>
      fetchApi(`/superadmin/tenants/${tenantId}/status`, {
        method: 'PATCH',
        body: JSON.stringify({ status, reason }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['saas-tenants'] });
      queryClient.invalidateQueries({ queryKey: ['saas-metrics'] });
      setSelectedTenantForStatus(null);
    },
  });

  const updatePlanMutation = useMutation({
    mutationFn: ({ tenantId, plan }: { tenantId: string; plan: string }) =>
      fetchApi(`/superadmin/tenants/${tenantId}/plan`, {
        method: 'PATCH',
        body: JSON.stringify({ plan }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['saas-tenants'] });
      queryClient.invalidateQueries({ queryKey: ['saas-metrics'] });
      setSelectedTenantForPlan(null);
    },
  });

  const impersonateMutation = useMutation({
    mutationFn: (tenantId: string) =>
      fetchApi<{
        token: string;
        target_email: string;
        target_tenant_name: string;
        target_user?: any;
        target_branch_id?: string;
        target_branch_name?: string;
      }>(
        `/superadmin/tenants/${tenantId}/impersonate`,
        { method: 'POST' }
      ),
    onSuccess: (data) => {
      // Preserve superadmin token and user to return later
      const currentToken = localStorage.getItem('auth_token') || localStorage.getItem('token');
      const currentUser = localStorage.getItem('user');
      const currentBranch = localStorage.getItem('admin_branch_id');

      if (currentToken) {
        localStorage.setItem('saas_master_token', currentToken);
        if (currentUser) localStorage.setItem('saas_master_user', currentUser);
        if (currentBranch) localStorage.setItem('saas_master_branch_id', currentBranch);
      }

      // Set target tenant credentials
      localStorage.setItem('auth_token', data.token);
      localStorage.setItem('token', data.token);
      if (data.target_user) {
        localStorage.setItem('user', JSON.stringify(data.target_user));
      }
      if (data.target_branch_id) {
        localStorage.setItem('admin_branch_id', data.target_branch_id);
        localStorage.setItem('pos_branch_id', data.target_branch_id);
      } else {
        localStorage.removeItem('admin_branch_id');
        localStorage.removeItem('pos_branch_id');
      }

      localStorage.setItem(
        'impersonation_info',
        JSON.stringify({
          active: true,
          tenant_name: data.target_tenant_name,
          email: data.target_email,
        })
      );
      // Reload into normal tenant admin dashboard
      window.location.href = '/';
    },
  });

  const resetForm = () => {
    setFormBusinessName('');
    setFormOwnerName('');
    setFormEmail('');
    setFormPhone('');
    setFormBusinessType('taqueria');
    setFormPlan('starter_349');
    setFormMenuMode('generate_by_type');
    setFormAiMenuText('');
    setFormPassword('Password123!');
    setCreateError(null);
  };

  const handleCreateSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setCreateError(null);
    createTenantMutation.mutate({
      business_name: formBusinessName,
      owner_name: formOwnerName,
      email: formEmail,
      phone: formPhone || null,
      business_type: formBusinessType,
      plan: formPlan,
      menu_mode: formMenuMode,
      ai_menu_text: formMenuMode === 'ai_import' ? formAiMenuText : null,
      password: formPassword,
    });
  };

  const formatMoney = (cents: number) => {
    return new Intl.NumberFormat('es-MX', { style: 'currency', currency: 'MXN' }).format(cents / 100);
  };

  return (
    <div style={{ padding: '28px', maxWidth: '1400px', margin: '0 auto', color: '#0f172a' }}>
      {/* Header Banner */}
      <div
        style={{
          background: 'linear-gradient(135deg, #0f172a 0%, #1e293b 100%)',
          borderRadius: '20px',
          padding: '28px 32px',
          color: '#fff',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          boxShadow: '0 10px 25px -5px rgba(15, 23, 42, 0.2)',
          marginBottom: '28px',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '8px' }}>
            <Crown size={28} color="#f59e0b" />
            <h1 style={{ margin: 0, fontSize: '1.75rem', fontWeight: 800, letterSpacing: '-0.02em' }}>
              Consola de Superadministrador SaaS
            </h1>
            <span
              style={{
                background: '#f59e0b',
                color: '#0f172a',
                fontSize: '11px',
                fontWeight: 800,
                padding: '3px 8px',
                borderRadius: '6px',
                textTransform: 'uppercase',
              }}
            >
              Master Platform
            </span>
          </div>
          <p style={{ margin: 0, color: '#94a3b8', fontSize: '0.95rem' }}>
            Gestión centralizada de restaurantes clientes, métricas de suscripción y aprovisionamiento asistido por IA.
          </p>
        </div>

        <button
          type="button"
          onClick={() => {
            resetForm();
            setIsCreateModalOpen(true);
          }}
          style={{
            background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
            color: '#fff',
            border: 'none',
            borderRadius: '12px',
            padding: '14px 22px',
            fontWeight: 700,
            fontSize: '14px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            boxShadow: '0 4px 12px rgba(16, 185, 129, 0.3)',
          }}
        >
          <Plus size={18} />
          <span>+ Dar de Alta Restaurante</span>
        </button>
      </div>

      {/* KPI Cards */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
          gap: '20px',
          marginBottom: '28px',
        }}
      >
        {/* Total Tenants */}
        <div
          style={{
            background: '#fff',
            borderRadius: '16px',
            padding: '20px',
            border: '1px solid #e2e8f0',
            boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
            <span style={{ fontSize: '13px', fontWeight: 600, color: '#64748b' }}>Restaurantes Clientes</span>
            <div style={{ background: '#e0f2fe', padding: '8px', borderRadius: '10px', color: '#0284c7' }}>
              <Building size={20} />
            </div>
          </div>
          <div style={{ fontSize: '28px', fontWeight: 800, color: '#0f172a' }}>{metrics?.total_tenants ?? 0}</div>
          <div style={{ fontSize: '12px', color: '#10b981', marginTop: '6px', fontWeight: 600 }}>
            🟢 {metrics?.active_tenants ?? 0} activos • 🟡 {metrics?.trialing_tenants ?? 0} en prueba • 🔴{' '}
            {metrics?.suspended_tenants ?? 0} suspendidos
          </div>
        </div>

        {/* MRR */}
        <div
          style={{
            background: '#fff',
            borderRadius: '16px',
            padding: '20px',
            border: '1px solid #e2e8f0',
            boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
            <span style={{ fontSize: '13px', fontWeight: 600, color: '#64748b' }}>MRR (Recurrencia Mensual)</span>
            <div style={{ background: '#dcfce7', padding: '8px', borderRadius: '10px', color: '#16a34a' }}>
              <DollarSign size={20} />
            </div>
          </div>
          <div style={{ fontSize: '28px', fontWeight: 800, color: '#0f172a' }}>
            {formatMoney(metrics?.mrr_cents ?? 0)}
          </div>
          <div style={{ fontSize: '12px', color: '#64748b', marginTop: '6px' }}>Ingresos mensuales proyectados</div>
        </div>

        {/* GMV */}
        <div
          style={{
            background: '#fff',
            borderRadius: '16px',
            padding: '20px',
            border: '1px solid #e2e8f0',
            boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
            <span style={{ fontSize: '13px', fontWeight: 600, color: '#64748b' }}>GMV Transaccionado</span>
            <div style={{ background: '#fef3c7', padding: '8px', borderRadius: '10px', color: '#d97706' }}>
              <TrendingUp size={20} />
            </div>
          </div>
          <div style={{ fontSize: '28px', fontWeight: 800, color: '#0f172a' }}>
            {formatMoney(metrics?.gmv_cents ?? 0)}
          </div>
          <div style={{ fontSize: '12px', color: '#64748b', marginTop: '6px' }}>Ventas operadas en POS</div>
        </div>

        {/* Total Orders */}
        <div
          style={{
            background: '#fff',
            borderRadius: '16px',
            padding: '20px',
            border: '1px solid #e2e8f0',
            boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
            <span style={{ fontSize: '13px', fontWeight: 600, color: '#64748b' }}>Pedidos Procesados</span>
            <div style={{ background: '#f3e8ff', padding: '8px', borderRadius: '10px', color: '#9333ea' }}>
              <ShoppingBag size={20} />
            </div>
          </div>
          <div style={{ fontSize: '28px', fontWeight: 800, color: '#0f172a' }}>
            {metrics?.total_orders.toLocaleString() ?? 0}
          </div>
          <div style={{ fontSize: '12px', color: '#64748b', marginTop: '6px' }}>Comandas salón y delivery</div>
        </div>
      </div>

      {/* Filters Bar */}
      <div
        style={{
          background: '#fff',
          borderRadius: '16px',
          padding: '16px 20px',
          border: '1px solid #e2e8f0',
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          gap: '16px',
          marginBottom: '20px',
        }}
      >
        <div style={{ flex: 1, minWidth: '240px', position: 'relative' }}>
          <Search size={18} color="#94a3b8" style={{ position: 'absolute', left: '12px', top: '11px' }} />
          <input
            type="text"
            placeholder="Buscar por restaurante, dueño o correo..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            style={{
              width: '100%',
              padding: '10px 12px 10px 38px',
              borderRadius: '10px',
              border: '1px solid #cbd5e1',
              fontSize: '13px',
              boxSizing: 'border-box',
              outline: 'none',
            }}
          />
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <label style={{ fontSize: '12px', fontWeight: 600, color: '#64748b' }}>Estado:</label>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            style={{
              padding: '8px 12px',
              borderRadius: '8px',
              border: '1px solid #cbd5e1',
              fontSize: '13px',
              fontWeight: 500,
            }}
          >
            <option value="all">Todos los estados</option>
            <option value="active">Activos</option>
            <option value="trialing">En Prueba</option>
            <option value="suspended">Suspendidos</option>
          </select>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <label style={{ fontSize: '12px', fontWeight: 600, color: '#64748b' }}>Plan:</label>
          <select
            value={planFilter}
            onChange={(e) => setPlanFilter(e.target.value)}
            style={{
              padding: '8px 12px',
              borderRadius: '8px',
              border: '1px solid #cbd5e1',
              fontSize: '13px',
              fontWeight: 500,
            }}
          >
            <option value="all">Todos los planes</option>
            <option value="starter_349">Básico ($349)</option>
            <option value="pro_599">Pro ($599)</option>
            <option value="trial">Prueba (14 días)</option>
          </select>
        </div>
      </div>

      {/* Tenants Table */}
      <div
        style={{
          background: '#fff',
          borderRadius: '16px',
          border: '1px solid #e2e8f0',
          overflow: 'hidden',
          boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
        }}
      >
        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '13px' }}>
          <thead>
            <tr style={{ background: '#f8fafc', borderBottom: '1px solid #e2e8f0', color: '#475569' }}>
              <th style={{ padding: '14px 18px', fontWeight: 700 }}>Restaurante</th>
              <th style={{ padding: '14px 18px', fontWeight: 700 }}>Dueño y Contacto</th>
              <th style={{ padding: '14px 18px', fontWeight: 700 }}>Plan y Cuota</th>
              <th style={{ padding: '14px 18px', fontWeight: 700 }}>Estado Suscripción</th>
              <th style={{ padding: '14px 18px', fontWeight: 700 }}>Catálogo & POS</th>
              <th style={{ padding: '14px 18px', fontWeight: 700, textAlign: 'right' }}>Acciones Master</th>
            </tr>
          </thead>
          <tbody>
            {isLoadingTenants ? (
              <tr>
                <td colSpan={6} style={{ padding: '32px', textAlign: 'center', color: '#64748b' }}>
                  Cargando directorio de restaurantes...
                </td>
              </tr>
            ) : tenants.length === 0 ? (
              <tr>
                <td colSpan={6} style={{ padding: '32px', textAlign: 'center', color: '#64748b' }}>
                  No se encontraron restaurantes con los filtros aplicados.
                </td>
              </tr>
            ) : (
              tenants.map((t) => {
                const isSuspended = t.subscription_status === 'suspended';
                return (
                  <tr key={t.id} style={{ borderBottom: '1px solid #f1f5f9', transition: 'background 0.2s' }}>
                    <td style={{ padding: '14px 18px' }}>
                      <strong style={{ fontSize: '14px', color: '#0f172a', display: 'block' }}>{t.name}</strong>
                      <span
                        style={{
                          display: 'inline-block',
                          fontSize: '11px',
                          color: '#64748b',
                          background: '#f1f5f9',
                          padding: '2px 6px',
                          borderRadius: '4px',
                          marginTop: '4px',
                          textTransform: 'capitalize',
                        }}
                      >
                        {t.business_type || 'General'}
                      </span>
                    </td>

                    <td style={{ padding: '14px 18px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#334155' }}>
                        <User size={13} color="#64748b" />
                        <span>{t.owner_name || 'Sin nombre'}</span>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#64748b', fontSize: '12px', marginTop: '2px' }}>
                        <Mail size={12} />
                        <span>{t.owner_email || 'Sin correo'}</span>
                      </div>
                      {t.owner_phone && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#64748b', fontSize: '12px', marginTop: '2px' }}>
                          <Phone size={12} />
                          <span>{t.owner_phone}</span>
                        </div>
                      )}
                    </td>

                    <td style={{ padding: '14px 18px' }}>
                      <span
                        style={{
                          fontWeight: 700,
                          fontSize: '12px',
                          color: t.plan === 'pro_599' ? '#7c3aed' : '#0284c7',
                          background: t.plan === 'pro_599' ? '#f5f3ff' : '#f0f9ff',
                          padding: '3px 8px',
                          borderRadius: '6px',
                          display: 'inline-block',
                          marginBottom: '4px',
                        }}
                      >
                        {t.plan === 'pro_599'
                          ? 'Plan Pro ($599/mes)'
                          : t.plan === 'starter_349'
                          ? 'Plan Básico ($349/mes)'
                          : 'Prueba (14 días)'}
                      </span>
                      <div style={{ fontSize: '12px', color: '#64748b', fontWeight: 600 }}>
                        {formatMoney(t.monthly_fee_cents)}/mes
                      </div>
                    </td>

                    <td style={{ padding: '14px 18px' }}>
                      {isSuspended ? (
                        <span
                          style={{
                            background: '#fee2e2',
                            color: '#b91c1c',
                            fontWeight: 700,
                            fontSize: '11px',
                            padding: '4px 10px',
                            borderRadius: '9999px',
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '4px',
                          }}
                        >
                          <PauseCircle size={12} />
                          <span>Suspendido</span>
                        </span>
                      ) : (
                        <span
                          style={{
                            background: '#dcfce7',
                            color: '#15803d',
                            fontWeight: 700,
                            fontSize: '11px',
                            padding: '4px 10px',
                            borderRadius: '9999px',
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '4px',
                          }}
                        >
                          <CheckCircle2 size={12} />
                          <span>Activo</span>
                        </span>
                      )}
                      {t.suspended_reason && (
                        <div style={{ fontSize: '11px', color: '#dc2626', marginTop: '4px' }}>
                          ↳ {t.suspended_reason}
                        </div>
                      )}
                    </td>

                    <td style={{ padding: '14px 18px', color: '#64748b' }}>
                      <div>🍽️ <strong>{t.products_count}</strong> platillos</div>
                      <div style={{ fontSize: '12px', marginTop: '2px' }}>🏪 {t.branches_count} sucursal(es)</div>
                    </td>

                    <td style={{ padding: '14px 18px', textAlign: 'right' }}>
                      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '6px' }}>
                        <button
                          type="button"
                          title="Entrar al panel de este cliente como soporte"
                          onClick={() => impersonateMutation.mutate(t.id)}
                          style={{
                            background: '#0f172a',
                            color: '#fff',
                            border: 'none',
                            borderRadius: '8px',
                            padding: '6px 12px',
                            fontSize: '12px',
                            fontWeight: 600,
                            cursor: 'pointer',
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '4px',
                          }}
                        >
                          <LogIn size={13} />
                          <span>Soporte</span>
                        </button>

                        <button
                          type="button"
                          title="Editar datos del restaurante y plan"
                          onClick={() => {
                            setSelectedTenantForEdit(t);
                            setEditName(t.name);
                            setEditBusinessType(t.business_type || 'general');
                            setEditOwnerName(t.owner_name || '');
                            setEditEmail(t.owner_email || '');
                            setEditPhone(t.owner_phone || '');
                            setEditPlan(t.plan || 'starter_349');
                            setEditStatus(t.subscription_status || 'active');
                          }}
                          style={{
                            background: '#f8fafc',
                            color: '#334155',
                            border: '1px solid #cbd5e1',
                            borderRadius: '8px',
                            padding: '6px 8px',
                            cursor: 'pointer',
                          }}
                        >
                          <Edit size={13} />
                        </button>

                        <button
                          type="button"
                          title={isSuspended ? 'Reactivar acceso' : 'Suspender acceso por falta de pago'}
                          onClick={() => {
                            if (isSuspended) {
                              updateStatusMutation.mutate({ tenantId: t.id, status: 'active' });
                            } else {
                              setSelectedTenantForStatus(t);
                            }
                          }}
                          style={{
                            background: isSuspended ? '#dcfce7' : '#fee2e2',
                            color: isSuspended ? '#15803d' : '#b91c1c',
                            border: 'none',
                            borderRadius: '8px',
                            padding: '6px 8px',
                            cursor: 'pointer',
                          }}
                        >
                          {isSuspended ? <PlayCircle size={13} /> : <PauseCircle size={13} />}
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Modal 1: Alta Manual de Restaurante Cliente */}
      {isCreateModalOpen && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(15, 23, 42, 0.65)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 9999,
            padding: '20px',
          }}
        >
          <div
            style={{
              background: '#fff',
              borderRadius: '20px',
              maxWidth: '620px',
              width: '100%',
              maxHeight: '90vh',
              overflowY: 'auto',
              boxShadow: '0 25px 50px -12px rgba(0,0,0,0.25)',
              padding: '28px',
              boxSizing: 'border-box',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <div style={{ background: '#e0f2fe', padding: '8px', borderRadius: '10px', color: '#0284c7' }}>
                  <Building size={22} />
                </div>
                <div>
                  <h2 style={{ margin: 0, fontSize: '1.25rem', fontWeight: 800 }}>Dar de Alta Nuevo Restaurante</h2>
                  <p style={{ margin: 0, fontSize: '12px', color: '#64748b' }}>Aprovisionamiento de cuenta SaaS</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setIsCreateModalOpen(false)}
                style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: '#94a3b8' }}
              >
                <X size={20} />
              </button>
            </div>

            {createError && (
              <div
                style={{
                  background: '#fef2f2',
                  border: '1px solid #fecaca',
                  color: '#b91c1c',
                  padding: '12px',
                  borderRadius: '10px',
                  fontSize: '13px',
                  marginBottom: '16px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                }}
              >
                <AlertCircle size={16} />
                <span>{createError}</span>
              </div>
            )}

            <form onSubmit={handleCreateSubmit}>
              {/* Sección 1: Datos del Restaurante */}
              <div style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 700, color: '#334155', marginBottom: '4px' }}>
                  Nombre Comercial del Restaurante *
                </label>
                <input
                  type="text"
                  required
                  placeholder="ej. Taquería El Pastorcito"
                  value={formBusinessName}
                  onChange={(e) => setFormBusinessName(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '10px 12px',
                    borderRadius: '8px',
                    border: '1px solid #cbd5e1',
                    fontSize: '13px',
                    boxSizing: 'border-box',
                  }}
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px', marginBottom: '16px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 700, color: '#334155', marginBottom: '4px' }}>
                    Giro Gastronómico *
                  </label>
                  <select
                    value={formBusinessType}
                    onChange={(e) => setFormBusinessType(e.target.value)}
                    style={{
                      width: '100%',
                      padding: '10px 12px',
                      borderRadius: '8px',
                      border: '1px solid #cbd5e1',
                      fontSize: '13px',
                      boxSizing: 'border-box',
                      fontWeight: 600,
                    }}
                  >
                    <option value="taqueria">🌮 Taquería</option>
                    <option value="cafeteria">☕ Cafetería / Panadería</option>
                    <option value="pizzeria">🍕 Pizzería</option>
                    <option value="general">🍽️ Restaurante / Fonda / General</option>
                  </select>
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 700, color: '#334155', marginBottom: '4px' }}>
                    Teléfono / WhatsApp
                  </label>
                  <input
                    type="tel"
                    placeholder="5512345678"
                    value={formPhone}
                    onChange={(e) => setFormPhone(e.target.value)}
                    style={{
                      width: '100%',
                      padding: '10px 12px',
                      borderRadius: '8px',
                      border: '1px solid #cbd5e1',
                      fontSize: '13px',
                      boxSizing: 'border-box',
                    }}
                  />
                </div>
              </div>

              {/* Sección 2: Cuenta de Usuario Administrador del Restaurante */}
              <div style={{ marginBottom: '18px', background: '#f8fafc', padding: '16px', borderRadius: '12px', border: '1px solid #e2e8f0' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                  <Key size={16} color="#0284c7" />
                  <strong style={{ fontSize: '13px', color: '#0f172a' }}>
                    Cuenta de Usuario Administrador del Restaurante
                  </strong>
                </div>
                <p style={{ margin: '0 0 12px', fontSize: '12px', color: '#64748b' }}>
                  Credenciales con las que el cliente/dueño iniciará sesión en su Punto de Venta (POS) y Panel Web.
                </p>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px', marginBottom: '12px' }}>
                  <div>
                    <label style={{ display: 'block', fontSize: '12px', fontWeight: 700, color: '#334155', marginBottom: '4px' }}>
                      Nombre del Administrador *
                    </label>
                    <input
                      type="text"
                      required
                      placeholder="ej. Mateo Morales"
                      value={formOwnerName}
                      onChange={(e) => setFormOwnerName(e.target.value)}
                      style={{
                        width: '100%',
                        padding: '10px 12px',
                        borderRadius: '8px',
                        border: '1px solid #cbd5e1',
                        fontSize: '13px',
                        boxSizing: 'border-box',
                      }}
                    />
                  </div>

                  <div>
                    <label style={{ display: 'block', fontSize: '12px', fontWeight: 700, color: '#334155', marginBottom: '4px' }}>
                      Correo de Acceso (Usuario Login) *
                    </label>
                    <input
                      type="email"
                      required
                      placeholder="mateo@pastorcito.com"
                      value={formEmail}
                      onChange={(e) => setFormEmail(e.target.value)}
                      style={{
                        width: '100%',
                        padding: '10px 12px',
                        borderRadius: '8px',
                        border: '1px solid #cbd5e1',
                        fontSize: '13px',
                        boxSizing: 'border-box',
                      }}
                    />
                  </div>
                </div>

                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                    <label style={{ fontSize: '12px', fontWeight: 700, color: '#334155' }}>
                      Contraseña de Acceso *
                    </label>
                    <button
                      type="button"
                      onClick={() => {
                        const chars = 'abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#$%';
                        let pw = '';
                        for (let i = 0; i < 10; i++) pw += chars.charAt(Math.floor(Math.random() * chars.length));
                        setFormPassword(pw);
                        setShowFormPassword(true);
                      }}
                      style={{ background: 'none', border: 'none', color: '#0284c7', fontSize: '11px', fontWeight: 700, cursor: 'pointer', padding: 0 }}
                    >
                      🎲 Generar contraseña segura
                    </button>
                  </div>
                  <div style={{ position: 'relative' }}>
                    <input
                      type={showFormPassword ? 'text' : 'password'}
                      required
                      minLength={8}
                      placeholder="Mínimo 8 caracteres"
                      value={formPassword}
                      onChange={(e) => setFormPassword(e.target.value)}
                      style={{
                        width: '100%',
                        padding: '10px 42px 10px 12px',
                        borderRadius: '8px',
                        border: '1px solid #cbd5e1',
                        fontSize: '13px',
                        boxSizing: 'border-box',
                      }}
                    />
                    <button
                      type="button"
                      onClick={() => setShowFormPassword(!showFormPassword)}
                      style={{
                        position: 'absolute',
                        right: '10px',
                        top: '50%',
                        transform: 'translateY(-50%)',
                        background: 'none',
                        border: 'none',
                        cursor: 'pointer',
                        color: '#64748b',
                      }}
                    >
                      {showFormPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                    </button>
                  </div>
                </div>
              </div>

              {/* Sección 2: Plan SaaS */}
              <div style={{ marginBottom: '16px', background: '#f8fafc', padding: '14px', borderRadius: '12px', border: '1px solid #e2e8f0' }}>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 700, color: '#0f172a', marginBottom: '8px' }}>
                  Plan de Suscripción SaaS
                </label>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '10px' }}>
                  <button
                    type="button"
                    onClick={() => setFormPlan('starter_349')}
                    style={{
                      padding: '10px',
                      borderRadius: '8px',
                      border: formPlan === 'starter_349' ? '2px solid #0284c7' : '1px solid #cbd5e1',
                      background: formPlan === 'starter_349' ? '#f0f9ff' : '#fff',
                      textAlign: 'center',
                      cursor: 'pointer',
                    }}
                  >
                    <strong style={{ display: 'block', fontSize: '13px', color: '#0f172a' }}>Básico</strong>
                    <span style={{ fontSize: '12px', color: '#0284c7', fontWeight: 700 }}>$349 MXN/mes</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => setFormPlan('pro_599')}
                    style={{
                      padding: '10px',
                      borderRadius: '8px',
                      border: formPlan === 'pro_599' ? '2px solid #7c3aed' : '1px solid #cbd5e1',
                      background: formPlan === 'pro_599' ? '#f5f3ff' : '#fff',
                      textAlign: 'center',
                      cursor: 'pointer',
                    }}
                  >
                    <strong style={{ display: 'block', fontSize: '13px', color: '#0f172a' }}>Pro</strong>
                    <span style={{ fontSize: '12px', color: '#7c3aed', fontWeight: 700 }}>$599 MXN/mes</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => setFormPlan('trial')}
                    style={{
                      padding: '10px',
                      borderRadius: '8px',
                      border: formPlan === 'trial' ? '2px solid #10b981' : '1px solid #cbd5e1',
                      background: formPlan === 'trial' ? '#ecfdf5' : '#fff',
                      textAlign: 'center',
                      cursor: 'pointer',
                    }}
                  >
                    <strong style={{ display: 'block', fontSize: '13px', color: '#0f172a' }}>Prueba</strong>
                    <span style={{ fontSize: '12px', color: '#10b981', fontWeight: 700 }}>14 Días Gratis</span>
                  </button>
                </div>
              </div>

              {/* Sección 3: Menú Inicial & Extractor IA (Pregunta Solicitada) */}
              <div style={{ marginBottom: '20px', background: '#f8fafc', padding: '14px', borderRadius: '12px', border: '1px solid #e2e8f0' }}>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 700, color: '#0f172a', marginBottom: '8px' }}>
                  ¿Cómo deseas configurar el menú de este restaurante?
                </label>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '12px' }}>
                  <label
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px',
                      fontSize: '13px',
                      cursor: 'pointer',
                      padding: '8px 12px',
                      borderRadius: '8px',
                      background: formMenuMode === 'generate_by_type' ? '#eff6ff' : '#fff',
                      border: '1px solid ' + (formMenuMode === 'generate_by_type' ? '#bfdbfe' : '#e2e8f0'),
                    }}
                  >
                    <input
                      type="radio"
                      name="menu_mode"
                      value="generate_by_type"
                      checked={formMenuMode === 'generate_by_type'}
                      onChange={() => setFormMenuMode('generate_by_type')}
                    />
                    <span>
                      🌱 <strong>Generar menú sugerido por su giro</strong> (Crea platillos típicos listos para vender)
                    </span>
                  </label>

                  <label
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px',
                      fontSize: '13px',
                      cursor: 'pointer',
                      padding: '8px 12px',
                      borderRadius: '8px',
                      background: formMenuMode === 'ai_import' ? '#f5f3ff' : '#fff',
                      border: '1px solid ' + (formMenuMode === 'ai_import' ? '#ddd6fe' : '#e2e8f0'),
                    }}
                  >
                    <input
                      type="radio"
                      name="menu_mode"
                      value="ai_import"
                      checked={formMenuMode === 'ai_import'}
                      onChange={() => setFormMenuMode('ai_import')}
                    />
                    <span>
                      ✨ <strong>Subir o Pegar Menú / Carta con IA</strong> (Extrae platillos, precios y categorías automáticamente)
                    </span>
                  </label>

                  <label
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px',
                      fontSize: '13px',
                      cursor: 'pointer',
                      padding: '8px 12px',
                      borderRadius: '8px',
                      background: formMenuMode === 'blank' ? '#f1f5f9' : '#fff',
                      border: '1px solid ' + (formMenuMode === 'blank' ? '#cbd5e1' : '#e2e8f0'),
                    }}
                  >
                    <input
                      type="radio"
                      name="menu_mode"
                      value="blank"
                      checked={formMenuMode === 'blank'}
                      onChange={() => setFormMenuMode('blank')}
                    />
                    <span>
                      📄 <strong>Menú en blanco</strong> (Comenzar con catálogo limpio desde cero)
                    </span>
                  </label>
                </div>

                {formMenuMode === 'ai_import' && (
                  <div style={{ marginTop: '10px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '6px' }}>
                      <Sparkles size={14} color="#7c3aed" />
                      <span style={{ fontSize: '12px', fontWeight: 700, color: '#6d28d9' }}>
                        Pega aquí el contenido de la carta o menú del cliente:
                      </span>
                    </div>
                    <textarea
                      rows={5}
                      required={formMenuMode === 'ai_import'}
                      value={formAiMenuText}
                      onChange={(e) => setFormAiMenuText(e.target.value)}
                      placeholder={'ENTRADAS\nGuacamole con totopos $85\nQueso fundido con chorizo $110\n\nTACOS\nTaco de Sirloin $45\nTaco de Ribeye $55'}
                      style={{
                        width: '100%',
                        padding: '10px',
                        borderRadius: '8px',
                        border: '1px solid #c4b5fd',
                        fontSize: '12px',
                        fontFamily: 'monospace',
                        boxSizing: 'border-box',
                        resize: 'vertical',
                      }}
                    />
                    <p style={{ fontSize: '11px', color: '#64748b', margin: '4px 0 0' }}>
                      Tip: El extractor IA detectará automáticamente los encabezados de categorías y precios con símbolo $.
                    </p>
                  </div>
                )}
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
                <button
                  type="button"
                  onClick={() => setIsCreateModalOpen(false)}
                  style={{
                    padding: '10px 18px',
                    borderRadius: '8px',
                    border: '1px solid #cbd5e1',
                    background: '#fff',
                    color: '#64748b',
                    fontSize: '13px',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  Cancelar
                </button>

                <button
                  type="submit"
                  disabled={createTenantMutation.isPending}
                  style={{
                    padding: '10px 22px',
                    borderRadius: '8px',
                    border: 'none',
                    background: '#10b981',
                    color: '#fff',
                    fontSize: '13px',
                    fontWeight: 700,
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                  }}
                >
                  <Plus size={16} />
                  <span>{createTenantMutation.isPending ? 'Aprovisionando...' : 'Crear Restaurante Ahora'}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal 2: Cambiar Plan */}
      {selectedTenantForPlan && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(15, 23, 42, 0.65)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 9999,
            padding: '20px',
          }}
        >
          <div
            style={{
              background: '#fff',
              borderRadius: '16px',
              maxWidth: '420px',
              width: '100%',
              padding: '24px',
              boxSizing: 'border-box',
            }}
          >
            <h3 style={{ margin: '0 0 8px', fontSize: '1.15rem' }}>Cambiar Plan de Suscripción</h3>
            <p style={{ margin: '0 0 16px', fontSize: '13px', color: '#64748b' }}>
              Restaurante: <strong>{selectedTenantForPlan.name}</strong>
            </p>

            <div style={{ marginBottom: '16px' }}>
              <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: '6px' }}>
                Selecciona el nuevo plan:
              </label>
              <select
                value={newPlan}
                onChange={(e) => setNewPlan(e.target.value)}
                style={{ width: '100%', padding: '10px', borderRadius: '8px', border: '1px solid #cbd5e1' }}
              >
                <option value="starter_349">Plan Básico ($349 MXN/mes)</option>
                <option value="pro_599">Plan Pro ($599 MXN/mes)</option>
                <option value="trial">Periodo de Prueba (14 Días)</option>
              </select>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              <button
                type="button"
                onClick={() => setSelectedTenantForPlan(null)}
                style={{ padding: '8px 14px', borderRadius: '8px', border: '1px solid #cbd5e1', background: '#fff' }}
              >
                Cancelar
              </button>
              <button
                type="button"
                onClick={() => updatePlanMutation.mutate({ tenantId: selectedTenantForPlan.id, plan: newPlan })}
                style={{ padding: '8px 18px', borderRadius: '8px', border: 'none', background: '#0284c7', color: '#fff', fontWeight: 700 }}
              >
                Guardar Plan
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal 3: Suspender Acceso */}
      {selectedTenantForStatus && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(15, 23, 42, 0.65)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 9999,
            padding: '20px',
          }}
        >
          <div
            style={{
              background: '#fff',
              borderRadius: '16px',
              maxWidth: '420px',
              width: '100%',
              padding: '24px',
              boxSizing: 'border-box',
            }}
          >
            <h3 style={{ margin: '0 0 8px', fontSize: '1.15rem', color: '#dc2626' }}>Suspender Acceso del Restaurante</h3>
            <p style={{ margin: '0 0 16px', fontSize: '13px', color: '#64748b' }}>
              Restaurante: <strong>{selectedTenantForStatus.name}</strong>
            </p>

            <div style={{ marginBottom: '16px' }}>
              <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: '6px' }}>
                Motivo de suspensión (visible al comensal/cajero):
              </label>
              <input
                type="text"
                value={suspendReason}
                onChange={(e) => setSuspendReason(e.target.value)}
                style={{ width: '100%', padding: '10px', borderRadius: '8px', border: '1px solid #cbd5e1' }}
              />
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              <button
                type="button"
                onClick={() => setSelectedTenantForStatus(null)}
                style={{ padding: '8px 14px', borderRadius: '8px', border: '1px solid #cbd5e1', background: '#fff' }}
              >
                Cancelar
              </button>
              <button
                type="button"
                onClick={() =>
                  updateStatusMutation.mutate({
                    tenantId: selectedTenantForStatus.id,
                    status: 'suspended',
                    reason: suspendReason,
                  })
                }
                style={{ padding: '8px 18px', borderRadius: '8px', border: 'none', background: '#dc2626', color: '#fff', fontWeight: 700 }}
              >
                Confirmar Suspensión
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal 4: Editar Restaurante Completo */}
      {selectedTenantForEdit && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(15, 23, 42, 0.65)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 9999,
            padding: '20px',
          }}
        >
          <div
            style={{
              background: '#fff',
              borderRadius: '16px',
              maxWidth: '560px',
              width: '100%',
              maxHeight: '90vh',
              overflowY: 'auto',
              padding: '28px',
              boxSizing: 'border-box',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <div>
                <h3 style={{ margin: 0, fontSize: '1.25rem', fontWeight: 800, color: '#0f172a' }}>
                  Editar Restaurante Cliente
                </h3>
                <p style={{ margin: '4px 0 0', fontSize: '13px', color: '#64748b' }}>
                  Modifica los datos del negocio, contacto y paquete SaaS.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setSelectedTenantForEdit(null)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#64748b' }}
              >
                <X size={20} />
              </button>
            </div>

            <form
              onSubmit={(e) => {
                e.preventDefault();
                updateTenantMutation.mutate({
                  tenantId: selectedTenantForEdit.id,
                  payload: {
                    name: editName,
                    business_type: editBusinessType,
                    owner_name: editOwnerName,
                    owner_email: editEmail,
                    owner_phone: editPhone || null,
                    plan: editPlan,
                    subscription_status: editStatus,
                  },
                });
              }}
            >
              <div style={{ marginBottom: '14px' }}>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 700, color: '#334155', marginBottom: '4px' }}>
                  Nombre Comercial *
                </label>
                <input
                  type="text"
                  required
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  style={{ width: '100%', padding: '10px 12px', borderRadius: '8px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box' }}
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '14px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 700, color: '#334155', marginBottom: '4px' }}>
                    Giro Gastronómico
                  </label>
                  <select
                    value={editBusinessType}
                    onChange={(e) => setEditBusinessType(e.target.value)}
                    style={{ width: '100%', padding: '10px 12px', borderRadius: '8px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box', fontWeight: 600 }}
                  >
                    <option value="taqueria">🌮 Taquería</option>
                    <option value="cafeteria">☕ Cafetería / Panadería</option>
                    <option value="pizzeria">🍕 Pizzería</option>
                    <option value="general">🍽️ Restaurante / Fonda / General</option>
                  </select>
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 700, color: '#334155', marginBottom: '4px' }}>
                    Teléfono / WhatsApp
                  </label>
                  <input
                    type="tel"
                    value={editPhone}
                    onChange={(e) => setEditPhone(e.target.value)}
                    style={{ width: '100%', padding: '10px 12px', borderRadius: '8px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box' }}
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '14px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 700, color: '#334155', marginBottom: '4px' }}>
                    Nombre del Dueño / Contacto
                  </label>
                  <input
                    type="text"
                    value={editOwnerName}
                    onChange={(e) => setEditOwnerName(e.target.value)}
                    style={{ width: '100%', padding: '10px 12px', borderRadius: '8px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box' }}
                  />
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 700, color: '#334155', marginBottom: '4px' }}>
                    Correo Electrónico (Login) *
                  </label>
                  <input
                    type="email"
                    required
                    value={editEmail}
                    onChange={(e) => setEditEmail(e.target.value)}
                    style={{ width: '100%', padding: '10px 12px', borderRadius: '8px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box' }}
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '20px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 700, color: '#334155', marginBottom: '4px' }}>
                    Plan SaaS
                  </label>
                  <select
                    value={editPlan}
                    onChange={(e) => setEditPlan(e.target.value)}
                    style={{ width: '100%', padding: '10px 12px', borderRadius: '8px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box', fontWeight: 600 }}
                  >
                    <option value="starter_349">Plan Básico ($349 MXN/mes)</option>
                    <option value="pro_599">Plan Pro ($599 MXN/mes)</option>
                    <option value="trial">Periodo de Prueba (14 Días)</option>
                    <option value="enterprise">Plan Enterprise ($1,200 MXN/mes)</option>
                  </select>
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 700, color: '#334155', marginBottom: '4px' }}>
                    Estado de Suscripción
                  </label>
                  <select
                    value={editStatus}
                    onChange={(e) => setEditStatus(e.target.value)}
                    style={{ width: '100%', padding: '10px 12px', borderRadius: '8px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box', fontWeight: 600 }}
                  >
                    <option value="active">Activo</option>
                    <option value="suspended">Suspendido</option>
                    <option value="trialing">En Prueba</option>
                  </select>
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
                <button
                  type="button"
                  onClick={() => setSelectedTenantForEdit(null)}
                  style={{ padding: '10px 18px', borderRadius: '8px', border: '1px solid #cbd5e1', background: '#fff', fontSize: '13px', fontWeight: 600, cursor: 'pointer' }}
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={updateTenantMutation.isPending}
                  style={{ padding: '10px 22px', borderRadius: '8px', border: 'none', background: '#0284c7', color: '#fff', fontSize: '13px', fontWeight: 700, cursor: 'pointer' }}
                >
                  {updateTenantMutation.isPending ? 'Guardando...' : 'Guardar Cambios'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal 5: Confirmación y Credenciales Creadas */}
      {createdCredentials && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(15, 23, 42, 0.75)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 9999,
            padding: '20px',
          }}
        >
          <div
            style={{
              background: '#fff',
              borderRadius: '20px',
              maxWidth: '480px',
              width: '100%',
              padding: '30px',
              boxSizing: 'border-box',
              boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
            }}
          >
            <div style={{ textAlign: 'center', marginBottom: '20px' }}>
              <div
                style={{
                  width: '56px',
                  height: '56px',
                  borderRadius: '50%',
                  background: '#ecfdf5',
                  color: '#10b981',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  margin: '0 auto 12px',
                }}
              >
                <CheckCircle2 size={32} />
              </div>
              <h3 style={{ margin: 0, fontSize: '1.3rem', fontWeight: 800, color: '#0f172a' }}>
                ¡Restaurante y Cuenta Creados!
              </h3>
              <p style={{ margin: '6px 0 0', fontSize: '13px', color: '#64748b' }}>
                El restaurante <strong>{createdCredentials.restaurant_name}</strong> y su cuenta administradora ya están listos para operar.
              </p>
            </div>

            {/* Tarjeta de Credenciales */}
            <div
              style={{
                background: '#f8fafc',
                borderRadius: '12px',
                border: '1px solid #e2e8f0',
                padding: '16px',
                marginBottom: '20px',
              }}
            >
              <div style={{ fontSize: '12px', color: '#64748b', marginBottom: '8px' }}>
                🏪 Sucursal Inicial: <strong style={{ color: '#0f172a' }}>{createdCredentials.branch_name}</strong>
              </div>
              <div style={{ fontSize: '12px', color: '#64748b', marginBottom: '8px' }}>
                👤 Administrador: <strong style={{ color: '#0f172a' }}>{createdCredentials.owner_name}</strong>
              </div>
              <div style={{ fontSize: '12px', color: '#64748b', marginBottom: '8px' }}>
                📧 Correo / Usuario: <strong style={{ color: '#0284c7' }}>{createdCredentials.email}</strong>
              </div>
              <div style={{ fontSize: '12px', color: '#64748b' }}>
                🔑 Contraseña: <strong style={{ color: '#0f172a', fontFamily: 'monospace', fontSize: '13px', background: '#e2e8f0', padding: '2px 6px', borderRadius: '4px' }}>{createdCredentials.password}</strong>
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              <button
                type="button"
                onClick={() => {
                  const text = `🍽️ Acceso a RestaurantOS para ${createdCredentials.restaurant_name}:\n\n👤 Administrador: ${createdCredentials.owner_name}\n📧 Correo: ${createdCredentials.email}\n🔑 Contraseña: ${createdCredentials.password}\n🏪 Sucursal: ${createdCredentials.branch_name}\n\n¡Ya puedes ingresar a tu Punto de Venta y Panel Web!`;
                  navigator.clipboard.writeText(text);
                  setCopiedCredentials(true);
                  setTimeout(() => setCopiedCredentials(false), 3000);
                }}
                style={{
                  padding: '12px',
                  borderRadius: '10px',
                  border: '1px solid #cbd5e1',
                  background: copiedCredentials ? '#f0fdf4' : '#fff',
                  color: copiedCredentials ? '#16a34a' : '#0f172a',
                  fontWeight: 700,
                  fontSize: '13px',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '8px',
                }}
              >
                {copiedCredentials ? <Check size={16} /> : <Copy size={16} />}
                <span>{copiedCredentials ? '¡Credenciales Copiadas al Portapapeles!' : 'Copiar Credenciales para el Cliente'}</span>
              </button>

              {createdCredentials.tenant_id && (
                <button
                  type="button"
                  onClick={() => {
                    const tId = createdCredentials.tenant_id;
                    setCreatedCredentials(null);
                    if (tId) impersonateMutation.mutate(tId);
                  }}
                  style={{
                    padding: '12px',
                    borderRadius: '10px',
                    border: 'none',
                    background: '#0f172a',
                    color: '#fff',
                    fontWeight: 700,
                    fontSize: '13px',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '8px',
                  }}
                >
                  <LogIn size={16} />
                  <span>Entrar como Soporte Técnico Ahora</span>
                </button>
              )}

              <button
                type="button"
                onClick={() => setCreatedCredentials(null)}
                style={{
                  padding: '10px',
                  borderRadius: '10px',
                  border: 'none',
                  background: 'transparent',
                  color: '#64748b',
                  fontWeight: 600,
                  fontSize: '13px',
                  cursor: 'pointer',
                }}
              >
                Cerrar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
