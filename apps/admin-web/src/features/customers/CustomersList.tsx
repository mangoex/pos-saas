import React, { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Button, Modal, Input } from '@restaurantos/ui';
import { fetchApi } from '@restaurantos/api-client';
import {
  Users, Search, Plus, MapPin, ReceiptText, Phone, Mail,
  Store, ShoppingBag, MessageCircle, ChevronLeft, ChevronRight,
  Star, MessageSquare, Crown, Building, Globe
} from 'lucide-react';
import { getSessionUser } from '../../lib/branchContext';

interface CustomerPhone {
  id?: string;
  captured_number: string;
  normalized_number?: string;
  is_primary: boolean;
  type?: string;
}

interface CustomerAddress {
  id: string;
  alias: string;
  street: string;
  exterior_number: string;
  interior_number?: string;
  neighborhood: string;
  postal_code: string;
  city: string;
  municipality: string;
  state: string;
  notes?: string;
  is_default: boolean;
  status: string;
}

interface TaxProfile {
  legal_name: string;
  tax_id: string;
  tax_regime: string;
  fiscal_postal_code: string;
  cfdi_use?: string;
  billing_email?: string;
}

export interface CustomerFeedbackItem {
  id: string;
  rating: number;
  comment?: string | null;
  order_folio?: string | null;
  customer_name?: string | null;
  customer_phone?: string | null;
  created_at: string;
  branch_name?: string | null;
  branch_code?: string | null;
}

export interface CustomerRatingSummary {
  average_rating: number | null;
  rating_count: number;
  recent_feedbacks: CustomerFeedbackItem[];
}

interface Customer {
  id: string;
  name: string;
  email?: string | null;
  origin_branch_id?: string | null;
  origin_branch_name?: string | null;
  organization_id?: string | null;
  organization_name?: string | null;
  phones: CustomerPhone[];
  addresses: CustomerAddress[];
  tax_profile?: TaxProfile | null;
  order_summary: {
    order_count: number;
    average_ticket_cents: number;
    last_order_at?: string | null;
  };
  rating_summary?: CustomerRatingSummary;
  created_at: string;
}

interface TenantOption {
  id: string;
  name: string;
  business_type?: string | null;
  status?: string;
}

interface CustomerPage {
  items: Customer[];
  total: number;
  limit: number;
  offset: number;
}

interface Branch {
  id: string;
  name: string;
  code: string;
  status: string;
}

const formatMoney = (cents: number): string => {
  return (cents / 100).toLocaleString('es-MX', { style: 'currency', currency: 'MXN' });
};

const emptyCustomerForm = {
  name: '',
  email: '',
  phone: '',
  branch_id: '',
};

const emptyAddressForm = {
  alias: 'Casa',
  street: '',
  exterior_number: '',
  interior_number: '',
  neighborhood: '',
  postal_code: '',
  city: 'Mazatlán',
  municipality: 'Mazatlán',
  state: 'Sinaloa',
  notes: '',
  is_default: false,
};

const emptyTaxForm = {
  legal_name: '',
  tax_id: '',
  tax_regime: '612',
  fiscal_postal_code: '',
  cfdi_use: 'G03',
  billing_email: '',
};

export const CustomersList: React.FC = () => {
  const queryClient = useQueryClient();
  const currentUser = getSessionUser();
  const isSuperadmin = Boolean(currentUser.is_superadmin && !localStorage.getItem('impersonation_info'));
  const [selectedTenantId, setSelectedTenantId] = useState<string>('all');
  const [selectedBranchId, setSelectedBranchId] = useState<string>('');
  const [search, setSearch] = useState<string>('');
  const [filterTab, setFilterTab] = useState<'all' | 'vip' | 'churn_risk' | 'new' | 'with_orders' | 'with_addresses' | 'with_tax'>('all');
  const [offset, setOffset] = useState<number>(0);
  const pageSize = 50;

  const { data: tenants = [] } = useQuery<TenantOption[]>({
    queryKey: ['saas-tenants-list'],
    queryFn: () => fetchApi<TenantOption[]>('/superadmin/tenants'),
    enabled: isSuperadmin,
  });

  const [isCustomerModalOpen, setIsCustomerModalOpen] = useState(false);
  const [editingCustomer, setEditingCustomer] = useState<Customer | null>(null);
  const [customerForm, setCustomerForm] = useState(emptyCustomerForm);

  const [activeAddressCustomer, setActiveAddressCustomer] = useState<Customer | null>(null);
  const [addressForm, setAddressForm] = useState(emptyAddressForm);

  const [activeTaxCustomer, setActiveTaxCustomer] = useState<Customer | null>(null);
  const [taxForm, setTaxForm] = useState(emptyTaxForm);

  const [activeFeedbacksCustomer, setActiveFeedbacksCustomer] = useState<Customer | null>(null);

  const [formError, setFormError] = useState<string>('');

  const { data: branches = [] } = useQuery<Branch[]>({
    queryKey: ['branches'],
    queryFn: () => fetchApi('/branches'),
  });

  const { data: customerFeedbacks = [], isLoading: isLoadingFeedbacks } = useQuery<CustomerFeedbackItem[]>({
    queryKey: ['customer_feedbacks', activeFeedbacksCustomer?.id],
    queryFn: () => fetchApi(`/customers/${activeFeedbacksCustomer!.id}/feedbacks`),
    enabled: Boolean(activeFeedbacksCustomer?.id),
  });

  const { data: crmData } = useQuery<{
    vip_customers: any[];
    churn_risk_customers: any[];
    new_customers: any[];
    summary: { total_customers: number; vip_count: number; churn_risk_count: number; new_count: number };
  }>({
    queryKey: ['customer-crm-segments', selectedBranchId],
    queryFn: () =>
      fetchApi(`/admin-ai/customer-crm-segments${selectedBranchId ? `?branch_id=${selectedBranchId}` : ''}`),
  });

  const branchNameMap = useMemo(() => {
    const map = new Map<string, string>();
    branches.forEach((b) => map.set(b.id, b.name));
    return map;
  }, [branches]);

  const {
    data: customerPage,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery<CustomerPage>({
    queryKey: ['admin_customers', isSuperadmin, selectedTenantId, selectedBranchId, search, offset, pageSize],
    queryFn: async () => {
      const params = new URLSearchParams({
        limit: String(pageSize),
        offset: String(offset),
      });
      if (isSuperadmin) {
        if (selectedTenantId === 'all') {
          params.set('all_organizations', 'true');
        } else if (selectedTenantId) {
          params.set('organization_id', selectedTenantId);
        }
      }
      if (selectedBranchId) params.set('branch_id', selectedBranchId);
      if (search.trim()) params.set('q', search.trim());
      return fetchApi<CustomerPage>(`/customers?${params.toString()}`);
    },
  });

  const rawCustomers = customerPage?.items || [];
  const totalCount = customerPage?.total || 0;

  const filteredCustomers = useMemo(() => {
    if (filterTab === 'vip') {
      const vipIds = new Set((crmData?.vip_customers || []).map((c) => c.customer_id));
      return rawCustomers.filter((c) => vipIds.has(c.id));
    }
    if (filterTab === 'churn_risk') {
      const churnIds = new Set((crmData?.churn_risk_customers || []).map((c) => c.customer_id));
      return rawCustomers.filter((c) => churnIds.has(c.id));
    }
    if (filterTab === 'new') {
      const newIds = new Set((crmData?.new_customers || []).map((c) => c.customer_id));
      return rawCustomers.filter((c) => newIds.has(c.id));
    }
    if (filterTab === 'with_orders') {
      return rawCustomers.filter((c) => (c.order_summary?.order_count || 0) > 0);
    }
    if (filterTab === 'with_addresses') {
      return rawCustomers.filter((c) => (c.addresses || []).length > 0);
    }
    if (filterTab === 'with_tax') {
      return rawCustomers.filter((c) => Boolean(c.tax_profile?.tax_id));
    }
    return rawCustomers;
  }, [rawCustomers, filterTab, crmData]);

  const stats = useMemo(() => {
    const totalWithOrders = rawCustomers.filter((c) => (c.order_summary?.order_count || 0) > 0).length;
    const totalWithAddresses = rawCustomers.filter((c) => (c.addresses || []).length > 0).length;
    const totalWithTax = rawCustomers.filter((c) => Boolean(c.tax_profile?.tax_id)).length;
    const totalTicketsCents = rawCustomers.reduce(
      (acc, c) => acc + (c.order_summary?.average_ticket_cents || 0),
      0
    );
    const avgTicketCents = totalWithOrders > 0 ? Math.round(totalTicketsCents / totalWithOrders) : 0;

    const rated = rawCustomers.filter((c) => c.rating_summary && c.rating_summary.rating_count > 0);
    const totalRatings = rated.reduce((acc, c) => acc + (c.rating_summary?.rating_count || 0), 0);
    const sumRatings = rated.reduce((acc, c) => acc + ((c.rating_summary?.average_rating || 0) * (c.rating_summary?.rating_count || 0)), 0);
    const avgRating = totalRatings > 0 ? Math.round((sumRatings / totalRatings) * 10) / 10 : null;

    return {
      total: totalCount,
      withOrders: totalWithOrders,
      withAddresses: totalWithAddresses,
      withTax: totalWithTax,
      avgTicketCents,
      totalRatings,
      avgRating,
    };
  }, [rawCustomers, totalCount]);

  const createOrUpdateCustomerMutation = useMutation({
    mutationFn: async () => {
      if (editingCustomer) {
        return fetchApi(`/customers/${editingCustomer.id}`, {
          method: 'PUT',
          body: JSON.stringify({
            name: customerForm.name.trim(),
            email: customerForm.email.trim() || null,
            branch_id: customerForm.branch_id || selectedBranchId || branches[0]?.id || undefined,
          }),
        });
      } else {
        return fetchApi('/customers', {
          method: 'POST',
          body: JSON.stringify({
            name: customerForm.name.trim(),
            email: customerForm.email.trim() || undefined,
            branch_id: customerForm.branch_id || selectedBranchId || branches[0]?.id || undefined,
            phones: customerForm.phone.trim()
              ? [{ number: customerForm.phone.trim(), is_primary: true, whatsapp_enabled: true }]
              : [],
          }),
        });
      }
    },
    onSuccess: () => {
      setIsCustomerModalOpen(false);
      setCustomerForm(emptyCustomerForm);
      setEditingCustomer(null);
      setFormError('');
      void queryClient.invalidateQueries({ queryKey: ['admin_customers'] });
    },
    onError: (err: any) => {
      setFormError(err?.message || 'Error al guardar el cliente');
    },
  });

  const saveAddressMutation = useMutation({
    mutationFn: async () => {
      if (!activeAddressCustomer) return;
      return fetchApi(`/customers/${activeAddressCustomer.id}/addresses`, {
        method: 'POST',
        body: JSON.stringify({
          branch_id: activeAddressCustomer.origin_branch_id || selectedBranchId || branches[0]?.id || undefined,
          ...addressForm,
        }),
      });
    },
    onSuccess: () => {
      setActiveAddressCustomer(null);
      setAddressForm(emptyAddressForm);
      setFormError('');
      void queryClient.invalidateQueries({ queryKey: ['admin_customers'] });
    },
    onError: (err: any) => {
      setFormError(err?.message || 'Error al guardar el domicilio');
    },
  });

  const saveTaxMutation = useMutation({
    mutationFn: async () => {
      if (!activeTaxCustomer) return;
      return fetchApi(`/customers/${activeTaxCustomer.id}/tax-profile`, {
        method: 'PUT',
        body: JSON.stringify({
          branch_id: activeTaxCustomer.origin_branch_id || selectedBranchId || branches[0]?.id || undefined,
          ...taxForm,
        }),
      });
    },
    onSuccess: () => {
      setActiveTaxCustomer(null);
      setTaxForm(emptyTaxForm);
      setFormError('');
      void queryClient.invalidateQueries({ queryKey: ['admin_customers'] });
    },
    onError: (err: any) => {
      setFormError(err?.message || 'Error al guardar los datos fiscales');
    },
  });

  const openNewCustomerModal = () => {
    setEditingCustomer(null);
    setCustomerForm({
      ...emptyCustomerForm,
      branch_id: selectedBranchId || branches[0]?.id || '',
    });
    setFormError('');
    setIsCustomerModalOpen(true);
  };

  const openEditCustomerModal = (customer: Customer) => {
    setEditingCustomer(customer);
    const primaryPhone = customer.phones.find((p) => p.is_primary)?.captured_number || customer.phones[0]?.captured_number || '';
    setCustomerForm({
      name: customer.name,
      email: customer.email || '',
      phone: primaryPhone,
      branch_id: customer.origin_branch_id || '',
    });
    setFormError('');
    setIsCustomerModalOpen(true);
  };

  const openAddressModal = (customer: Customer) => {
    setActiveAddressCustomer(customer);
    setAddressForm(emptyAddressForm);
    setFormError('');
  };

  const openTaxModal = (customer: Customer) => {
    setActiveTaxCustomer(customer);
    setTaxForm(
      customer.tax_profile
        ? {
            legal_name: customer.tax_profile.legal_name || '',
            tax_id: customer.tax_profile.tax_id || '',
            tax_regime: customer.tax_profile.tax_regime || '612',
            fiscal_postal_code: customer.tax_profile.fiscal_postal_code || '',
            cfdi_use: customer.tax_profile.cfdi_use || 'G03',
            billing_email: customer.tax_profile.billing_email || '',
          }
        : emptyTaxForm
    );
    setFormError('');
  };

  const getInitials = (name: string) => {
    const parts = name.trim().split(/\s+/);
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0][0] + parts[1][0]).toUpperCase();
  };

  return (
    <div style={{ padding: '24px 32px', maxWidth: '1440px', margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '24px', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '6px' }}>
            <div style={{ background: '#fdf4ff', color: '#a855f7', padding: '8px', borderRadius: '12px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Users size={24} />
            </div>
            <h1 style={{ fontSize: '1.75rem', fontWeight: 800, color: '#0f172a', margin: 0 }}>
              Directorio Global de Clientes
            </h1>
          </div>
          <p style={{ color: '#64748b', fontSize: '0.95rem', margin: 0 }}>
            Catálogo consolidado de clientes a nivel corporativo, historial de consumo y direcciones de entrega.
          </p>
        </div>

        <Button
          variant="primary"
          onClick={openNewCustomerModal}
          style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', padding: '10px 20px', borderRadius: '12px', fontWeight: 700 }}
        >
          <Plus size={18} />
          <span>+ Nuevo Cliente</span>
        </Button>
      </div>

      {isSuperadmin && (
        <div
          style={{
            background: 'linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%)',
            border: '1.5px solid #fde68a',
            borderRadius: '16px',
            padding: '16px 20px',
            marginBottom: '24px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: '16px',
            boxShadow: '0 4px 12px rgba(245, 158, 11, 0.08)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div
              style={{
                background: '#f59e0b',
                color: '#ffffff',
                borderRadius: '12px',
                padding: '10px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: '0 2px 6px rgba(245, 158, 11, 0.3)',
              }}
            >
              <Crown size={22} />
            </div>
            <div>
              <div style={{ fontWeight: 800, color: '#92400e', fontSize: '1rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span>Vista Super Administrador (Red Global mimenu)</span>
                <span style={{ background: '#f59e0b', color: '#fff', fontSize: '10px', padding: '2px 8px', borderRadius: '9999px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Cross-Tenant
                </span>
              </div>
              <div style={{ color: '#b45309', fontSize: '0.86rem', marginTop: '2px' }}>
                Estás visualizando los clientes de todos los restaurantes de la red. Puedes filtrar por restaurante individual o ver toda la base consolidada.
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', background: '#ffffff', padding: '6px 14px', borderRadius: '12px', border: '1.5px solid #fcd34d' }}>
            <Building size={18} style={{ color: '#d97706' }} />
            <span style={{ fontSize: '0.85rem', fontWeight: 700, color: '#92400e' }}>Restaurante:</span>
            <select
              value={selectedTenantId}
              onChange={(e) => {
                setSelectedTenantId(e.target.value);
                setOffset(0);
              }}
              style={{
                background: 'transparent',
                border: 'none',
                fontSize: '0.9rem',
                fontWeight: 700,
                color: '#0f172a',
                outline: 'none',
                cursor: 'pointer',
              }}
            >
              <option value="all">🌐 Toda la red (Todos los restaurantes)</option>
              {tenants.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </div>
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px', marginBottom: '24px' }}>
        <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '16px', padding: '16px 20px', boxShadow: '0 2px 4px rgba(0,0,0,0.02)' }}>
          <span style={{ fontSize: '0.8rem', fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Total Clientes Registrados
          </span>
          <div style={{ fontSize: '1.8rem', fontWeight: 800, color: '#0f172a', marginTop: '6px' }}>
            {stats.total.toLocaleString('es-MX')}
          </div>
          <span style={{ fontSize: '0.8rem', color: '#10b981', fontWeight: 600 }}>
            Catálogo Corporativo Global
          </span>
        </div>

        <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '16px', padding: '16px 20px', boxShadow: '0 2px 4px rgba(0,0,0,0.02)' }}>
          <span style={{ fontSize: '0.8rem', fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Con Domicilio de Entrega
          </span>
          <div style={{ fontSize: '1.8rem', fontWeight: 800, color: '#0f172a', marginTop: '6px' }}>
            {stats.withAddresses.toLocaleString('es-MX')}
          </div>
          <span style={{ fontSize: '0.8rem', color: '#64748b', fontWeight: 500 }}>
            Direcciones activas mapeadas
          </span>
        </div>

        <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '16px', padding: '16px 20px', boxShadow: '0 2px 4px rgba(0,0,0,0.02)' }}>
          <span style={{ fontSize: '0.8rem', fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Clientes con Pedidos
          </span>
          <div style={{ fontSize: '1.8rem', fontWeight: 800, color: '#10b981', marginTop: '6px' }}>
            {stats.withOrders.toLocaleString('es-MX')}
          </div>
          <span style={{ fontSize: '0.8rem', color: '#64748b', fontWeight: 500 }}>
            Historial de compra activo
          </span>
        </div>

        <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '16px', padding: '16px 20px', boxShadow: '0 2px 4px rgba(0,0,0,0.02)' }}>
          <span style={{ fontSize: '0.8rem', fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Ticket Promedio Global
          </span>
          <div style={{ fontSize: '1.8rem', fontWeight: 800, color: '#0f172a', marginTop: '6px' }}>
            {formatMoney(stats.avgTicketCents)}
          </div>
          <span style={{ fontSize: '0.8rem', color: '#64748b', fontWeight: 500 }}>
            Por orden completada
          </span>
        </div>

        <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '16px', padding: '16px 20px', boxShadow: '0 2px 4px rgba(0,0,0,0.02)' }}>
          <span style={{ fontSize: '0.8rem', fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Satisfacción Promedio
          </span>
          <div style={{ fontSize: '1.8rem', fontWeight: 800, color: '#d97706', marginTop: '6px', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Star size={24} fill="#eab308" color="#d97706" />
            <span>{stats.avgRating !== null ? `${stats.avgRating.toFixed(1)} / 5` : '—'}</span>
          </div>
          <span style={{ fontSize: '0.8rem', color: '#64748b', fontWeight: 500 }}>
            {stats.totalRatings} {stats.totalRatings === 1 ? 'opinión registrada' : 'opiniones registradas'}
          </span>
        </div>
      </div>

      <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '16px', padding: '16px 20px', marginBottom: '24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flex: '1 1 500px', flexWrap: 'wrap' }}>
          <div style={{ position: 'relative', flex: '1 1 260px' }}>
            <Search size={18} style={{ position: 'absolute', left: 14, top: 12, color: '#94a3b8' }} />
            <Input
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setOffset(0);
              }}
              placeholder="Buscar por nombre, teléfono o correo..."
              style={{ paddingLeft: '40px', width: '100%', height: '42px', borderRadius: '12px', fontSize: '0.9rem' }}
            />
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: '220px' }}>
            <Store size={18} style={{ color: '#64748b' }} />
            <select
              value={selectedBranchId}
              onChange={(e) => {
                setSelectedBranchId(e.target.value);
                setOffset(0);
              }}
              style={{
                height: '42px',
                padding: '0 12px',
                borderRadius: '12px',
                border: '1px solid #cbd5e1',
                background: '#ffffff',
                color: '#0f172a',
                fontSize: '0.9rem',
                fontWeight: 600,
                outline: 'none',
                cursor: 'pointer',
                flex: 1,
              }}
            >
              <option value="">🏢 Todas las sucursales</option>
              {branches.map((b) => (
                <option key={b.id} value={b.id}>
                  📍 {b.name} ({b.code})
                </option>
              ))}
            </select>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', background: '#f1f5f9', padding: '4px', borderRadius: '12px' }}>
          {[
            { key: 'all', label: 'Todos' },
            { key: 'vip', label: `⭐ VIPs (${crmData?.summary?.vip_count ?? 0})` },
            { key: 'churn_risk', label: `⚠️ En Riesgo (${crmData?.summary?.churn_risk_count ?? 0})` },
            { key: 'new', label: `🌱 Nuevos (${crmData?.summary?.new_count ?? 0})` },
            { key: 'with_orders', label: 'Con Pedidos' },
            { key: 'with_addresses', label: 'Con Domicilio' },
            { key: 'with_tax', label: 'Fiscales' },
          ].map((tab) => {
            const isActive = filterTab === tab.key;
            return (
              <button
                key={tab.key}
                onClick={() => setFilterTab(tab.key as any)}
                style={{
                  padding: '6px 14px',
                  borderRadius: '8px',
                  border: 'none',
                  background: isActive ? '#ffffff' : 'transparent',
                  color: isActive ? '#0f172a' : '#64748b',
                  fontWeight: isActive ? 700 : 500,
                  fontSize: '0.85rem',
                  cursor: 'pointer',
                  boxShadow: isActive ? '0 1px 3px rgba(0,0,0,0.05)' : 'none',
                  transition: 'all 0.15s ease',
                }}
              >
                {tab.label}
              </button>
            );
          })}
        </div>
      </div>

      <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '20px', overflow: 'hidden', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.02)' }}>
        {isLoading ? (
          <div style={{ padding: '60px', textAlign: 'center', color: '#64748b' }}>
            <div style={{ fontSize: '1.8rem', marginBottom: '12px' }}>⏳</div>
            <strong style={{ fontSize: '1.1rem', color: '#0f172a' }}>Cargando catálogo de clientes...</strong>
            <p style={{ margin: '6px 0 0', fontSize: '0.9rem' }}>Sincronizando registros corporativos.</p>
          </div>
        ) : isError ? (
          <div style={{ padding: '60px', textAlign: 'center', color: '#dc2626' }}>
            <div style={{ fontSize: '1.8rem', marginBottom: '12px' }}>⚠️</div>
            <strong style={{ fontSize: '1.1rem' }}>No fue posible cargar el directorio</strong>
            <p style={{ margin: '6px 0 16px', fontSize: '0.9rem' }}>{(error as any)?.message || 'Error de conexión'}</p>
            <Button variant="secondary" onClick={() => refetch()}>Reintentar</Button>
          </div>
        ) : filteredCustomers.length === 0 ? (
          <div style={{ padding: '60px', textAlign: 'center', color: '#64748b' }}>
            <div style={{ fontSize: '2.2rem', marginBottom: '12px' }}>👤</div>
            <strong style={{ fontSize: '1.15rem', color: '#0f172a' }}>No se encontraron clientes</strong>
            <p style={{ margin: '6px 0 16px', fontSize: '0.9rem', maxWidth: '400px', marginInline: 'auto' }}>
              {search || selectedBranchId || filterTab !== 'all'
                ? 'No hay registros que coincidan con los filtros seleccionados. Prueba modificando la búsqueda.'
                : 'Aún no hay clientes registrados en la organización.'}
            </p>
            <Button variant="primary" onClick={openNewCustomerModal}>+ Registrar Primer Cliente</Button>
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', minWidth: '950px' }}>
              <thead>
                <tr style={{ background: '#f8fafc', borderBottom: '1px solid #e2e8f0', color: '#475569', fontSize: '0.85rem', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  <th style={{ padding: '16px 20px', fontWeight: 700 }}>Cliente</th>
                  <th style={{ padding: '16px 20px', fontWeight: 700 }}>Contacto</th>
                  <th style={{ padding: '16px 20px', fontWeight: 700 }}>Sucursal Origen</th>
                  <th style={{ padding: '16px 20px', fontWeight: 700 }}>Domicilios</th>
                  <th style={{ padding: '16px 20px', fontWeight: 700 }}>Historial Pedidos</th>
                  <th style={{ padding: '16px 20px', fontWeight: 700 }}>Calificación</th>
                  <th style={{ padding: '16px 20px', fontWeight: 700 }}>Fiscal (CFDI)</th>
                  <th style={{ padding: '16px 20px', fontWeight: 700, textAlign: 'right' }}>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {filteredCustomers.map((customer) => {
                  const primaryPhone = customer.phones.find((p) => p.is_primary) || customer.phones[0];
                  const cleanPhoneDigits = primaryPhone?.captured_number?.replace(/[^\d]/g, '') || '';
                  const branchName = customer.origin_branch_name || (customer.origin_branch_id ? branchNameMap.get(customer.origin_branch_id) || 'Sucursal Registrada' : 'Corporativo / Todas');
                  const defaultAddress = customer.addresses.find((a) => a.is_default) || customer.addresses[0];

                  return (
                    <tr
                      key={customer.id}
                      style={{ borderBottom: '1px solid #f1f5f9', transition: 'background 0.15s ease' }}
                      onMouseEnter={(e) => (e.currentTarget.style.background = '#f8fafc')}
                      onMouseLeave={(e) => (e.currentTarget.style.background = '#ffffff')}
                    >
                      <td style={{ padding: '16px 20px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                          <div
                            style={{
                              width: '40px',
                              height: '40px',
                              borderRadius: '50%',
                              background: 'linear-gradient(135deg, #10b981, #059669)',
                              color: '#ffffff',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              fontWeight: 800,
                              fontSize: '0.95rem',
                              flexShrink: 0,
                            }}
                          >
                            {getInitials(customer.name)}
                          </div>
                          <div>
                            <div style={{ fontWeight: 700, color: '#0f172a', fontSize: '0.95rem' }}>
                              {customer.name}
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap', marginTop: '3px' }}>
                              {customer.organization_name && (
                                <span
                                  style={{
                                    fontSize: '0.72rem',
                                    background: '#eff6ff',
                                    color: '#1d4ed8',
                                    border: '1px solid #bfdbfe',
                                    padding: '1px 6px',
                                    borderRadius: '6px',
                                    fontWeight: 600,
                                    display: 'inline-flex',
                                    alignItems: 'center',
                                    gap: '3px',
                                  }}
                                >
                                  <Building size={11} />
                                  <span>{customer.organization_name}</span>
                                </span>
                              )}
                              <span style={{ fontSize: '0.78rem', color: '#94a3b8' }}>
                                ID: {customer.id.slice(0, 8)}...
                              </span>
                            </div>
                          </div>
                        </div>
                      </td>

                      <td style={{ padding: '16px 20px' }}>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                          {primaryPhone ? (
                            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                              <Phone size={14} style={{ color: '#10b981' }} />
                              <span style={{ fontWeight: 600, color: '#334155', fontSize: '0.88rem' }}>
                                {primaryPhone.captured_number}
                              </span>
                              {cleanPhoneDigits.length >= 10 && (
                                <a
                                  href={`https://wa.me/52${cleanPhoneDigits.slice(-10)}`}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  title="Abrir WhatsApp"
                                  style={{ color: '#22c55e', display: 'inline-flex', alignItems: 'center', marginLeft: '4px' }}
                                >
                                  <MessageCircle size={15} />
                                </a>
                              )}
                            </div>
                          ) : (
                            <span style={{ color: '#94a3b8', fontSize: '0.85rem' }}>Sin teléfono</span>
                          )}

                          {customer.email ? (
                            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#64748b', fontSize: '0.82rem' }}>
                              <Mail size={13} />
                              <span>{customer.email}</span>
                            </div>
                          ) : null}
                        </div>
                      </td>

                      <td style={{ padding: '16px 20px' }}>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                          <span
                            style={{
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '5px',
                              background: customer.origin_branch_id ? '#eff6ff' : '#f8fafc',
                              color: customer.origin_branch_id ? '#1e40af' : '#64748b',
                              border: `1px solid ${customer.origin_branch_id ? '#bfdbfe' : '#e2e8f0'}`,
                              padding: '4px 10px',
                              borderRadius: '9999px',
                              fontSize: '0.8rem',
                              fontWeight: 600,
                              width: 'fit-content',
                            }}
                          >
                            <Store size={13} />
                            <span>{branchName}</span>
                          </span>
                          {customer.organization_name && (
                            <span
                              style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '4px',
                                fontSize: '0.75rem',
                                color: '#6366f1',
                                fontWeight: 600,
                              }}
                            >
                              <Building size={12} />
                              <span>{customer.organization_name}</span>
                            </span>
                          )}
                        </div>
                      </td>

                      <td style={{ padding: '16px 20px' }}>
                        {customer.addresses.length > 0 ? (
                          <div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '2px' }}>
                              <MapPin size={14} style={{ color: '#ef4444' }} />
                              <strong style={{ fontSize: '0.85rem', color: '#0f172a' }}>
                                {defaultAddress?.alias || 'Principal'}
                              </strong>
                              <span style={{ fontSize: '0.75rem', background: '#fee2e2', color: '#991b1b', padding: '1px 6px', borderRadius: '4px', fontWeight: 600 }}>
                                {customer.addresses.length} dir.
                              </span>
                            </div>
                            <p style={{ fontSize: '0.8rem', color: '#64748b', margin: 0, maxWidth: '220px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                              {defaultAddress?.street} #{defaultAddress?.exterior_number}, {defaultAddress?.neighborhood}
                            </p>
                          </div>
                        ) : (
                          <span style={{ color: '#94a3b8', fontSize: '0.85rem' }}>Sin domicilios</span>
                        )}
                      </td>

                      <td style={{ padding: '16px 20px' }}>
                        {customer.order_summary?.order_count > 0 ? (
                          <div>
                            <div style={{ display: 'inline-flex', alignItems: 'center', gap: '5px', background: '#ecfdf5', color: '#065f46', border: '1px solid #a7f3d0', padding: '3px 9px', borderRadius: '8px', fontSize: '0.82rem', fontWeight: 700 }}>
                              <ShoppingBag size={13} />
                              <span>{customer.order_summary.order_count} pedidos</span>
                            </div>
                            <div style={{ fontSize: '0.78rem', color: '#64748b', marginTop: '4px' }}>
                              Promedio: <strong>{formatMoney(customer.order_summary.average_ticket_cents)}</strong>
                            </div>
                          </div>
                        ) : (
                          <span style={{ color: '#94a3b8', fontSize: '0.85rem' }}>0 compras</span>
                        )}
                      </td>

                      <td style={{ padding: '16px 20px' }}>
                        {customer.rating_summary && customer.rating_summary.rating_count > 0 ? (
                          <button
                            type="button"
                            onClick={() => setActiveFeedbacksCustomer(customer)}
                            style={{
                              background: '#fefce8',
                              border: '1px solid #fef08a',
                              color: '#854d0e',
                              padding: '4px 10px',
                              borderRadius: '8px',
                              fontSize: '0.82rem',
                              fontWeight: 700,
                              cursor: 'pointer',
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '5px',
                            }}
                            title="Ver opiniones y comentarios del cliente"
                          >
                            <Star size={14} fill="#eab308" color="#ca8a04" />
                            <span>{customer.rating_summary.average_rating?.toFixed(1) || '—'}</span>
                            <span style={{ fontSize: '0.75rem', color: '#a16207', fontWeight: 600 }}>
                              ({customer.rating_summary.rating_count})
                            </span>
                          </button>
                        ) : (
                          <span style={{ color: '#94a3b8', fontSize: '0.82rem' }}>Sin calif.</span>
                        )}
                      </td>

                      <td style={{ padding: '16px 20px' }}>
                        {customer.tax_profile?.tax_id ? (
                          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                            <span style={{ background: '#fdf4ff', color: '#86198f', border: '1px solid #f5d0fe', padding: '3px 8px', borderRadius: '6px', fontSize: '0.8rem', fontWeight: 700 }}>
                              {customer.tax_profile.tax_id}
                            </span>
                          </div>
                        ) : (
                          <span style={{ color: '#94a3b8', fontSize: '0.85rem' }}>No registrado</span>
                        )}
                      </td>

                      <td style={{ padding: '16px 20px', textAlign: 'right' }}>
                        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '6px' }}>
                          <button
                            onClick={() => setActiveFeedbacksCustomer(customer)}
                            title="Ver opiniones y comentarios"
                            style={{
                              background: '#fefce8',
                              border: '1px solid #fef08a',
                              color: '#854d0e',
                              padding: '6px 10px',
                              borderRadius: '8px',
                              fontSize: '0.8rem',
                              fontWeight: 600,
                              cursor: 'pointer',
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '4px',
                            }}
                          >
                            <Star size={13} fill="#eab308" color="#ca8a04" />
                            <span>Reseñas</span>
                          </button>

                          <button
                            onClick={() => openAddressModal(customer)}
                            title="Gestionar domicilios"
                            style={{
                              background: '#f1f5f9',
                              border: 'none',
                              color: '#334155',
                              padding: '6px 10px',
                              borderRadius: '8px',
                              fontSize: '0.8rem',
                              fontWeight: 600,
                              cursor: 'pointer',
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '4px',
                            }}
                          >
                            <MapPin size={13} />
                            <span>Dirección</span>
                          </button>

                          <button
                            onClick={() => openTaxModal(customer)}
                            title="Gestionar datos fiscales"
                            style={{
                              background: '#f1f5f9',
                              border: 'none',
                              color: '#334155',
                              padding: '6px 10px',
                              borderRadius: '8px',
                              fontSize: '0.8rem',
                              fontWeight: 600,
                              cursor: 'pointer',
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '4px',
                            }}
                          >
                            <ReceiptText size={13} />
                            <span>Fiscal</span>
                          </button>

                          <button
                            onClick={() => openEditCustomerModal(customer)}
                            title="Editar cliente"
                            style={{
                              background: '#f8fafc',
                              border: '1px solid #cbd5e1',
                              color: '#0f172a',
                              padding: '6px 10px',
                              borderRadius: '8px',
                              fontSize: '0.8rem',
                              fontWeight: 700,
                              cursor: 'pointer',
                            }}
                          >
                            Editar
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        <div style={{ padding: '14px 20px', background: '#f8fafc', borderTop: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px' }}>
          <span style={{ color: '#64748b', fontSize: '0.85rem' }}>
            Mostrando {totalCount === 0 ? 0 : offset + 1}–{Math.min(offset + pageSize, totalCount)} de {totalCount.toLocaleString('es-MX')} clientes totales
          </span>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Button
              variant="secondary"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - pageSize))}
              style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', padding: '6px 12px' }}
            >
              <ChevronLeft size={16} />
              <span>Anterior</span>
            </Button>
            <Button
              variant="secondary"
              disabled={offset + pageSize >= totalCount}
              onClick={() => setOffset(offset + pageSize)}
              style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', padding: '6px 12px' }}
            >
              <span>Siguiente</span>
              <ChevronRight size={16} />
            </Button>
          </div>
        </div>
      </div>

      <Modal
        isOpen={isCustomerModalOpen}
        onClose={() => setIsCustomerModalOpen(false)}
        title={editingCustomer ? `Editar Cliente · ${editingCustomer.name}` : 'Registrar Nuevo Cliente'}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', paddingTop: '8px' }}>
          {formError && (
            <div role="alert" style={{ background: '#fef2f2', border: '1px solid #fecaca', color: '#b91c1c', padding: '10px 14px', borderRadius: '10px', fontSize: '0.85rem' }}>
              {formError}
            </div>
          )}

          <label style={{ display: 'grid', gap: '4px' }}>
            <span style={{ fontWeight: 600, fontSize: '0.9rem', color: '#334155' }}>Nombre Completo *</span>
            <Input
              value={customerForm.name}
              onChange={(e) => setCustomerForm({ ...customerForm, name: e.target.value })}
              placeholder="Ej. Juan Pérez González"
            />
          </label>

          <label style={{ display: 'grid', gap: '4px' }}>
            <span style={{ fontWeight: 600, fontSize: '0.9rem', color: '#334155' }}>Teléfono Móvil (10 dígitos)</span>
            <Input
              value={customerForm.phone}
              onChange={(e) => setCustomerForm({ ...customerForm, phone: e.target.value })}
              placeholder="Ej. 6691234567"
            />
          </label>

          <label style={{ display: 'grid', gap: '4px' }}>
            <span style={{ fontWeight: 600, fontSize: '0.9rem', color: '#334155' }}>Correo Electrónico</span>
            <Input
              value={customerForm.email}
              onChange={(e) => setCustomerForm({ ...customerForm, email: e.target.value })}
              placeholder="Ej. cliente@ejemplo.com"
            />
          </label>

          <label style={{ display: 'grid', gap: '4px' }}>
            <span style={{ fontWeight: 600, fontSize: '0.9rem', color: '#334155' }}>Sucursal de Origen / Asignación</span>
            <select
              value={customerForm.branch_id}
              onChange={(e) => setCustomerForm({ ...customerForm, branch_id: e.target.value })}
              style={{
                height: '40px',
                padding: '0 12px',
                borderRadius: '8px',
                border: '1px solid #cbd5e1',
                fontSize: '0.9rem',
                outline: 'none',
              }}
            >
              <option value="">🏢 General (Todas las sucursales)</option>
              {branches.map((b) => (
                <option key={b.id} value={b.id}>
                  📍 {b.name} ({b.code})
                </option>
              ))}
            </select>
          </label>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '16px' }}>
            <Button variant="secondary" onClick={() => setIsCustomerModalOpen(false)}>
              Cancelar
            </Button>
            <Button
              variant="primary"
              disabled={createOrUpdateCustomerMutation.isPending || !customerForm.name.trim()}
              onClick={() => createOrUpdateCustomerMutation.mutate()}
            >
              {createOrUpdateCustomerMutation.isPending ? 'Guardando...' : 'Guardar Cliente'}
            </Button>
          </div>
        </div>
      </Modal>

      <Modal
        isOpen={Boolean(activeAddressCustomer)}
        onClose={() => setActiveAddressCustomer(null)}
        title={`Domicilio de Entrega · ${activeAddressCustomer?.name || ''}`}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', paddingTop: '8px' }}>
          {formError && (
            <div role="alert" style={{ background: '#fef2f2', border: '1px solid #fecaca', color: '#b91c1c', padding: '10px 14px', borderRadius: '10px', fontSize: '0.85rem' }}>
              {formError}
            </div>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
            <label style={{ display: 'grid', gap: '4px' }}>
              <span style={{ fontWeight: 600, fontSize: '0.85rem', color: '#334155' }}>Alias (Ej. Casa, Oficina)</span>
              <Input
                value={addressForm.alias}
                onChange={(e) => setAddressForm({ ...addressForm, alias: e.target.value })}
              />
            </label>
            <label style={{ display: 'grid', gap: '4px' }}>
              <span style={{ fontWeight: 600, fontSize: '0.85rem', color: '#334155' }}>Código Postal</span>
              <Input
                value={addressForm.postal_code}
                onChange={(e) => setAddressForm({ ...addressForm, postal_code: e.target.value })}
                placeholder="82000"
              />
            </label>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr', gap: '10px' }}>
            <label style={{ display: 'grid', gap: '4px' }}>
              <span style={{ fontWeight: 600, fontSize: '0.85rem', color: '#334155' }}>Calle *</span>
              <Input
                value={addressForm.street}
                onChange={(e) => setAddressForm({ ...addressForm, street: e.target.value })}
                placeholder="Av. Principal"
              />
            </label>
            <label style={{ display: 'grid', gap: '4px' }}>
              <span style={{ fontWeight: 600, fontSize: '0.85rem', color: '#334155' }}>Núm. Exterior *</span>
              <Input
                value={addressForm.exterior_number}
                onChange={(e) => setAddressForm({ ...addressForm, exterior_number: e.target.value })}
                placeholder="123"
              />
            </label>
            <label style={{ display: 'grid', gap: '4px' }}>
              <span style={{ fontWeight: 600, fontSize: '0.85rem', color: '#334155' }}>Núm. Interior</span>
              <Input
                value={addressForm.interior_number}
                onChange={(e) => setAddressForm({ ...addressForm, interior_number: e.target.value })}
                placeholder="4B"
              />
            </label>
          </div>

          <label style={{ display: 'grid', gap: '4px' }}>
            <span style={{ fontWeight: 600, fontSize: '0.85rem', color: '#334155' }}>Colonia / Fraccionamiento *</span>
            <Input
              value={addressForm.neighborhood}
              onChange={(e) => setAddressForm({ ...addressForm, neighborhood: e.target.value })}
              placeholder="Centro"
            />
          </label>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
            <label style={{ display: 'grid', gap: '4px' }}>
              <span style={{ fontWeight: 600, fontSize: '0.85rem', color: '#334155' }}>Ciudad / Municipio</span>
              <Input
                value={addressForm.city}
                onChange={(e) => setAddressForm({ ...addressForm, city: e.target.value, municipality: e.target.value })}
              />
            </label>
            <label style={{ display: 'grid', gap: '4px' }}>
              <span style={{ fontWeight: 600, fontSize: '0.85rem', color: '#334155' }}>Estado</span>
              <Input
                value={addressForm.state}
                onChange={(e) => setAddressForm({ ...addressForm, state: e.target.value })}
              />
            </label>
          </div>

          <label style={{ display: 'grid', gap: '4px' }}>
            <span style={{ fontWeight: 600, fontSize: '0.85rem', color: '#334155' }}>Referencias de Entrega</span>
            <Input
              value={addressForm.notes}
              onChange={(e) => setAddressForm({ ...addressForm, notes: e.target.value })}
              placeholder="Portón blanco frente al parque..."
            />
          </label>

          <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', marginTop: '6px' }}>
            <input
              type="checkbox"
              checked={addressForm.is_default}
              onChange={(e) => setAddressForm({ ...addressForm, is_default: e.target.checked })}
              style={{ width: '16px', height: '16px' }}
            />
            <span style={{ fontSize: '0.9rem', color: '#334155', fontWeight: 600 }}>
              Marcar como domicilio predeterminado
            </span>
          </label>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '16px' }}>
            <Button variant="secondary" onClick={() => setActiveAddressCustomer(null)}>
              Cancelar
            </Button>
            <Button
              variant="primary"
              disabled={saveAddressMutation.isPending || !addressForm.street.trim() || !addressForm.exterior_number.trim()}
              onClick={() => saveAddressMutation.mutate()}
            >
              {saveAddressMutation.isPending ? 'Guardando...' : 'Guardar Domicilio'}
            </Button>
          </div>
        </div>
      </Modal>

      <Modal
        isOpen={Boolean(activeTaxCustomer)}
        onClose={() => setActiveTaxCustomer(null)}
        title={`Datos Fiscales CFDI · ${activeTaxCustomer?.name || ''}`}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', paddingTop: '8px' }}>
          {formError && (
            <div role="alert" style={{ background: '#fef2f2', border: '1px solid #fecaca', color: '#b91c1c', padding: '10px 14px', borderRadius: '10px', fontSize: '0.85rem' }}>
              {formError}
            </div>
          )}

          <label style={{ display: 'grid', gap: '4px' }}>
            <span style={{ fontWeight: 600, fontSize: '0.85rem', color: '#334155' }}>Razón Social / Nombre Fiscal *</span>
            <Input
              value={taxForm.legal_name}
              onChange={(e) => setTaxForm({ ...taxForm, legal_name: e.target.value })}
              placeholder="Ej. JUAN PEREZ GONZALEZ"
            />
          </label>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
            <label style={{ display: 'grid', gap: '4px' }}>
              <span style={{ fontWeight: 600, fontSize: '0.85rem', color: '#334155' }}>RFC *</span>
              <Input
                value={taxForm.tax_id}
                onChange={(e) => setTaxForm({ ...taxForm, tax_id: e.target.value.toUpperCase() })}
                placeholder="XAXX010101000"
              />
            </label>
            <label style={{ display: 'grid', gap: '4px' }}>
              <span style={{ fontWeight: 600, fontSize: '0.85rem', color: '#334155' }}>Código Postal Fiscal *</span>
              <Input
                value={taxForm.fiscal_postal_code}
                onChange={(e) => setTaxForm({ ...taxForm, fiscal_postal_code: e.target.value })}
                placeholder="82000"
              />
            </label>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
            <label style={{ display: 'grid', gap: '4px' }}>
              <span style={{ fontWeight: 600, fontSize: '0.85rem', color: '#334155' }}>Régimen Fiscal (Clave SAT)</span>
              <Input
                value={taxForm.tax_regime}
                onChange={(e) => setTaxForm({ ...taxForm, tax_regime: e.target.value })}
                placeholder="612 - Personas Físicas con Actividades Empresariales"
              />
            </label>
            <label style={{ display: 'grid', gap: '4px' }}>
              <span style={{ fontWeight: 600, fontSize: '0.85rem', color: '#334155' }}>Uso de CFDI</span>
              <Input
                value={taxForm.cfdi_use}
                onChange={(e) => setTaxForm({ ...taxForm, cfdi_use: e.target.value })}
                placeholder="G03 - Gastos en general"
              />
            </label>
          </div>

          <label style={{ display: 'grid', gap: '4px' }}>
            <span style={{ fontWeight: 600, fontSize: '0.85rem', color: '#334155' }}>Correo para Envío de Facturas</span>
            <Input
              value={taxForm.billing_email}
              onChange={(e) => setTaxForm({ ...taxForm, billing_email: e.target.value })}
              placeholder="facturacion@empresa.com"
            />
          </label>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '16px' }}>
            <Button variant="secondary" onClick={() => setActiveTaxCustomer(null)}>
              Cancelar
            </Button>
            <Button
              variant="primary"
              disabled={saveTaxMutation.isPending || !taxForm.legal_name.trim() || !taxForm.tax_id.trim() || !taxForm.fiscal_postal_code.trim()}
              onClick={() => saveTaxMutation.mutate()}
            >
              {saveTaxMutation.isPending ? 'Guardando...' : 'Guardar Datos Fiscales'}
            </Button>
          </div>
        </div>
      </Modal>

      <Modal
        isOpen={Boolean(activeFeedbacksCustomer)}
        onClose={() => setActiveFeedbacksCustomer(null)}
        title={`Historial de Opiniones · ${activeFeedbacksCustomer?.name || ''}`}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', paddingTop: '8px' }}>
          <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '12px', padding: '14px 18px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div>
              <span style={{ fontSize: '0.8rem', color: '#64748b', fontWeight: 600 }}>Calificación Promedio</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '2px' }}>
                <Star size={20} fill="#eab308" color="#d97706" />
                <strong style={{ fontSize: '1.25rem', color: '#0f172a' }}>
                  {activeFeedbacksCustomer?.rating_summary?.average_rating !== null && activeFeedbacksCustomer?.rating_summary?.average_rating !== undefined
                    ? activeFeedbacksCustomer.rating_summary.average_rating.toFixed(1)
                    : '—'}
                </strong>
                <span style={{ color: '#64748b', fontSize: '0.85rem' }}>/ 5.0</span>
              </div>
            </div>
            <span style={{ fontSize: '0.85rem', color: '#475569', fontWeight: 600, background: '#f1f5f9', padding: '4px 10px', borderRadius: '8px' }}>
              {customerFeedbacks.length} {customerFeedbacks.length === 1 ? 'opinión' : 'opiniones'}
            </span>
          </div>

          {isLoadingFeedbacks ? (
            <div style={{ padding: '30px', textAlign: 'center', color: '#64748b' }}>
              Cargando opiniones...
            </div>
          ) : customerFeedbacks.length === 0 ? (
            <div style={{ padding: '30px', textAlign: 'center', color: '#94a3b8' }}>
              <MessageSquare size={32} style={{ margin: '0 auto 8px', display: 'block', color: '#cbd5e1' }} />
              <p style={{ margin: 0, fontSize: '0.9rem' }}>Este cliente aún no ha registrado calificaciones o comentarios.</p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', maxHeight: '420px', overflowY: 'auto' }}>
              {customerFeedbacks.map((fb) => {
                const isNegative = fb.rating < 4;
                return (
                  <div
                    key={fb.id}
                    style={{
                      border: `1px solid ${isNegative ? '#fed7aa' : '#e2e8f0'}`,
                      background: isNegative ? '#fffbeb' : '#ffffff',
                      borderRadius: '12px',
                      padding: '12px 16px',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                        {[1, 2, 3, 4, 5].map((s) => (
                          <Star
                            key={s}
                            size={16}
                            fill={s <= fb.rating ? '#eab308' : '#e2e8f0'}
                            color={s <= fb.rating ? '#ca8a04' : '#cbd5e1'}
                          />
                        ))}
                        <strong style={{ marginLeft: '4px', fontSize: '0.88rem', color: '#0f172a' }}>
                          {fb.rating} / 5
                        </strong>
                      </div>
                      <span style={{ fontSize: '0.78rem', color: '#64748b' }}>
                        {new Date(fb.created_at).toLocaleDateString('es-MX', { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                      </span>
                    </div>

                    {fb.comment ? (
                      <div style={{
                        background: isNegative ? '#fef3c7' : '#f8fafc',
                        border: `1px solid ${isNegative ? '#fde68a' : '#e2e8f0'}`,
                        borderRadius: '8px',
                        padding: '8px 12px',
                        fontSize: '0.85rem',
                        color: isNegative ? '#92400e' : '#334155',
                        margin: '6px 0',
                        lineHeight: 1.4,
                      }}>
                        {isNegative && <strong style={{ display: 'block', fontSize: '0.75rem', textTransform: 'uppercase', color: '#b45309', marginBottom: '2px' }}>⚠️ Comentario para gerencia:</strong>}
                        <span>"{fb.comment}"</span>
                      </div>
                    ) : (
                      <span style={{ fontSize: '0.8rem', color: '#94a3b8', fontStyle: 'italic' }}>Sin comentarios adicionales</span>
                    )}

                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.75rem', color: '#64748b', marginTop: '6px' }}>
                      {fb.branch_name ? <span>📍 {fb.branch_name}</span> : <span>📍 Sucursal</span>}
                      {fb.order_folio ? <span>Pedido: #{fb.order_folio}</span> : null}
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '8px' }}>
            <Button variant="secondary" onClick={() => setActiveFeedbacksCustomer(null)}>
              Cerrar
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default CustomersList;
