import React, { useState, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Button, Badge, Modal } from '@restaurantos/ui';
import { fetchApi } from '@restaurantos/api-client';
import {
  Share2,
  Copy,
  Check,
  Building2,
  Activity,
  Key,
  Trash2,
  Play,
  FileText,
  Download,
  Send,
  Zap,
  Globe,
  QrCode,
  Eye,
  EyeOff,
  Receipt,
} from 'lucide-react';
import '../../premium-catalogs.css';

interface ChannelConfig {
  id?: string;
  is_enabled: boolean;
  environment: string;
  client_id: string;
  client_secret: string;
  webhook_secret: string;
  auto_accept: boolean;
  default_prep_time_minutes: number;
}

interface FacturapiConfig {
  id?: string;
  is_enabled: boolean;
  environment: string;
  api_key: string;
  organization_legal_name: string;
  organization_rfc: string;
  organization_tax_system: string;
  organization_zip: string;
  default_product_sat_key: string;
  default_unit_sat_key: string;
  series: string;
  enable_self_invoicing: boolean;
  self_invoicing_domain: string;
  self_invoicing_days_valid: number;
  print_qr_on_ticket: boolean;
}

interface StoreMapping {
  id: string;
  branch_id: string;
  branch_name: string;
  branch_code: string;
  provider: string;
  external_store_id: string;
  is_active: boolean;
  created_at: string;
}

interface Branch {
  id: string;
  name: string;
  code: string;
  status: string;
}

interface WebhookLog {
  id: string;
  provider: string;
  event_type: string;
  event_id?: string;
  signature?: string;
  payload_raw: any;
  status: string;
  error_message?: string;
  created_at: string;
}

interface InvoiceRecord {
  id: string;
  folio_number: string;
  uuid_sat?: string;
  rfc_receptor: string;
  nombre_receptor: string;
  total_cents: number;
  currency: string;
  status: string;
  created_at: string;
  pdf_url?: string;
  xml_url?: string;
  verification_url?: string;
}

interface IntegrationsHubProps {
  defaultProvider?: 'UBER_EATS' | 'DIDI_FOOD' | 'RAPPI' | 'FACTURAPI';
}

export default function IntegrationsHub({ defaultProvider }: IntegrationsHubProps = {}) {
  const location = useLocation();
  const isInvoicingRoute = location.pathname.includes('/invoicing') || defaultProvider === 'FACTURAPI';
  const queryClient = useQueryClient();
  const [selectedProvider, setSelectedProvider] = useState<'UBER_EATS' | 'DIDI_FOOD' | 'RAPPI' | 'FACTURAPI'>(
    isInvoicingRoute ? 'FACTURAPI' : (defaultProvider || 'UBER_EATS')
  );

  useEffect(() => {
    if (isInvoicingRoute) {
      setSelectedProvider('FACTURAPI');
    }
  }, [isInvoicingRoute]);
  const [activeTab, setActiveTab] = useState<'config' | 'stores' | 'logs' | 'invoices'>('config');
  const [copied, setCopied] = useState(false);
  const [showApiKey, setShowApiKey] = useState(false);
  const [testOrderModalOpen, setTestOrderModalOpen] = useState(false);
  const [testOrderItemsCount, setTestOrderItemsCount] = useState(2);
  const [testOrderCustomer, setTestOrderCustomer] = useState('Carlos M. (Prueba)');
  const [testOrderResult, setTestOrderResult] = useState<string | null>(null);
  const [facturapiTestResult, setFacturapiTestResult] = useState<{ success: boolean; message: string } | null>(null);

  const [mappingModalOpen, setMappingModalOpen] = useState(false);
  const [newMappingBranchId, setNewMappingBranchId] = useState('');
  const [newMappingStoreId, setNewMappingStoreId] = useState('');

  // Queries for Uber/Delivery Channels
  const { data: config } = useQuery<ChannelConfig>({
    queryKey: ['integrations', selectedProvider, 'config'],
    queryFn: () => fetchApi('/integrations/' + selectedProvider.toLowerCase().replace('_', '-') + '/config'),
    enabled: selectedProvider !== 'FACTURAPI',
  });

  const { data: branches = [] } = useQuery<Branch[]>({
    queryKey: ['branches'],
    queryFn: () => fetchApi('/branches'),
  });

  const { data: storeMappings = [] } = useQuery<StoreMapping[]>({
    queryKey: ['integrations', selectedProvider, 'stores'],
    queryFn: () => fetchApi('/integrations/' + selectedProvider.toLowerCase().replace('_', '-') + '/stores'),
    enabled: selectedProvider !== 'FACTURAPI',
  });

  const { data: logs = [] } = useQuery<WebhookLog[]>({
    queryKey: ['integrations', selectedProvider, 'logs'],
    queryFn: () => fetchApi('/integrations/' + selectedProvider.toLowerCase().replace('_', '-') + '/logs'),
    refetchInterval: activeTab === 'logs' && selectedProvider !== 'FACTURAPI' ? 5000 : false,
    enabled: selectedProvider !== 'FACTURAPI',
  });

  // Queries for Facturapi
  const { data: facturapiConfig } = useQuery<FacturapiConfig>({
    queryKey: ['integrations', 'facturapi', 'config'],
    queryFn: () => fetchApi('/integrations/facturapi/config'),
    enabled: selectedProvider === 'FACTURAPI',
  });

  const { data: invoiceList = [] } = useQuery<InvoiceRecord[]>({
    queryKey: ['invoicing', 'invoices'],
    queryFn: () => fetchApi('/invoicing/invoices'),
    enabled: selectedProvider === 'FACTURAPI' && activeTab === 'invoices',
  });

  const [formData, setFormData] = useState<Partial<ChannelConfig>>({});
  const [facturapiForm, setFacturapiForm] = useState<Partial<FacturapiConfig>>({});

  React.useEffect(() => {
    if (config && selectedProvider !== 'FACTURAPI') {
      setFormData(config);
    }
  }, [config, selectedProvider]);

  React.useEffect(() => {
    if (facturapiConfig && selectedProvider === 'FACTURAPI') {
      setFacturapiForm(facturapiConfig);
    }
  }, [facturapiConfig, selectedProvider]);

  const saveConfigMutation = useMutation({
    mutationFn: (payload: Partial<ChannelConfig>) =>
      fetchApi('/integrations/' + selectedProvider.toLowerCase().replace('_', '-') + '/config', {
        method: 'PUT',
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['integrations', selectedProvider, 'config'] });
      alert('Configuración guardada exitosamente.');
    },
  });

  const saveFacturapiMutation = useMutation({
    mutationFn: (payload: Partial<FacturapiConfig>) =>
      fetchApi('/integrations/facturapi/config', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['integrations', 'facturapi', 'config'] });
      alert('Configuración de Facturapi guardada exitosamente.');
    },
  });

  const testFacturapiMutation = useMutation({
    mutationFn: () => fetchApi<{ status: string; legal_name?: string; rfc?: string }>('/integrations/facturapi/test-connection', {
      method: 'POST',
    }),
    onSuccess: (data) => {
      setFacturapiTestResult({
        success: true,
        message: `¡Conexión exitosa con Facturapi! Razón Social: ${data.legal_name || 'Restaurante'} (RFC: ${data.rfc || 'Válido'})`,
      });
    },
    onError: (err: any) => {
      setFacturapiTestResult({
        success: false,
        message: `Error de conexión: ${err.message || 'Verifica la Secret Key'}`,
      });
    },
  });

  const saveMappingMutation = useMutation({
    mutationFn: (payload: { branch_id: string; external_store_id: string }) =>
      fetchApi('/integrations/' + selectedProvider.toLowerCase().replace('_', '-') + '/stores', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['integrations', selectedProvider, 'stores'] });
      setMappingModalOpen(false);
      setNewMappingBranchId('');
      setNewMappingStoreId('');
    },
  });

  const deleteMappingMutation = useMutation({
    mutationFn: (mappingId: string) =>
      fetchApi('/integrations/' + selectedProvider.toLowerCase().replace('_', '-') + '/stores/' + mappingId, {
        method: 'DELETE',
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['integrations', selectedProvider, 'stores'] });
    },
  });

  const simulateOrderMutation = useMutation({
    mutationFn: (payload: { customer_name: string; items_count: number; store_id?: string }) =>
      fetchApi('/integrations/' + selectedProvider.toLowerCase().replace('_', '-') + '/test-order', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    onSuccess: (data: any) => {
      const providerLabel = selectedProvider === 'UBER_EATS' ? 'Uber Eats' : selectedProvider === 'DIDI_FOOD' ? 'DiDi Food' : selectedProvider === 'RAPPI' ? 'Rappi' : 'Delivery';
      setTestOrderResult(`¡Orden de prueba de ${providerLabel} generada con éxito! Folio: ` + (data.result?.folio || 'ORD-XXXX'));
      queryClient.invalidateQueries({ queryKey: ['integrations', selectedProvider, 'logs'] });
    },
    onError: (err: any) => {
      setTestOrderResult('Error al generar orden: ' + (err.message || 'Desconocido'));
    },
  });

  const webhookPath =
    selectedProvider === 'UBER_EATS'
      ? 'uber-eats'
      : selectedProvider === 'DIDI_FOOD'
      ? 'didi-food'
      : selectedProvider === 'RAPPI'
      ? 'rappi'
      : selectedProvider.toLowerCase().replace('_', '-');
  const webhookUrl = `${window.location.origin}/v1/integrations/${webhookPath}/webhook`;

  const copyToClipboard = () => {
    navigator.clipboard.writeText(webhookUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
  };

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto', paddingBottom: 40 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 32 }}>
        <div>
          <h1 className="premium-header-title" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            {isInvoicingRoute ? (
              <>
                <Receipt size={26} style={{ color: '#7e22ce' }} />
                Facturación Electrónica SAT (CFDI 4.0)
              </>
            ) : (
              <>
                <Share2 size={26} style={{ color: '#10b981' }} />
                Canales de Delivery (Apps de Comida)
              </>
            )}
          </h1>
          <p className="premium-header-subtitle">
            {isInvoicingRoute
              ? 'Emite y timbra facturas digitales válidas ante el SAT (Facturapi) o habilita autofactura QR para comensales.'
              : 'Recepción automática y unificada de pedidos de Uber Eats, DiDi Food y Rappi directamente en el POS y cocina.'}
          </p>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 16, marginBottom: 28 }}>
        {/* Uber Eats */}
        <div
          onClick={() => { setSelectedProvider('UBER_EATS'); setActiveTab('config'); }}
          style={{
            background: selectedProvider === 'UBER_EATS' ? '#064e3b' : '#fff',
            color: selectedProvider === 'UBER_EATS' ? '#fff' : '#0f172a',
            border: selectedProvider === 'UBER_EATS' ? '2px solid #10b981' : '1px solid #e2e8f0',
            borderRadius: 14,
            padding: '20px 24px',
            cursor: 'pointer',
            boxShadow: selectedProvider === 'UBER_EATS' ? '0 10px 20px -5px rgba(16, 185, 129, 0.3)' : '0 2px 4px rgba(0,0,0,0.02)',
            transition: 'all 0.2s',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
              <span style={{ fontSize: 20 }}>🟢</span>
              <strong style={{ fontSize: '1.1rem' }}>Uber Eats</strong>
            </div>
            <p style={{ margin: 0, fontSize: '0.8125rem', opacity: 0.85 }}>
              API Oficial v2 · Webhooks en vivo
            </p>
          </div>
          <Badge variant={selectedProvider === 'UBER_EATS' && formData.is_enabled ? 'success' : 'default'}>
            {selectedProvider === 'UBER_EATS' && formData.is_enabled ? 'Conectado' : 'Configurar'}
          </Badge>
        </div>

        {/* DiDi Food */}
        <div
          onClick={() => { setSelectedProvider('DIDI_FOOD'); setActiveTab('config'); }}
          style={{
            background: selectedProvider === 'DIDI_FOOD' ? '#7c2d12' : '#fff',
            color: selectedProvider === 'DIDI_FOOD' ? '#fff' : '#0f172a',
            border: selectedProvider === 'DIDI_FOOD' ? '2px solid #f97316' : '1px solid #e2e8f0',
            borderRadius: 14,
            padding: '20px 24px',
            cursor: 'pointer',
            boxShadow: selectedProvider === 'DIDI_FOOD' ? '0 10px 20px -5px rgba(249, 115, 22, 0.3)' : '0 2px 4px rgba(0,0,0,0.02)',
            transition: 'all 0.2s',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
              <span style={{ fontSize: 20 }}>🟠</span>
              <strong style={{ fontSize: '1.1rem' }}>DiDi Food</strong>
            </div>
            <p style={{ margin: 0, fontSize: '0.8125rem', opacity: 0.85 }}>
              OpenPlatform API · Pedidos & Menú
            </p>
          </div>
          <Badge variant={selectedProvider === 'DIDI_FOOD' && formData.is_enabled ? 'success' : 'default'}>
            {selectedProvider === 'DIDI_FOOD' && formData.is_enabled ? 'Conectado' : 'Configurar'}
          </Badge>
        </div>

        {/* Facturapi */}
        <div
          onClick={() => { setSelectedProvider('FACTURAPI'); setActiveTab('config'); }}
          style={{
            background: selectedProvider === 'FACTURAPI' ? '#3b0764' : '#fff',
            color: selectedProvider === 'FACTURAPI' ? '#fff' : '#0f172a',
            border: selectedProvider === 'FACTURAPI' ? '2px solid #a855f7' : '1px solid #e2e8f0',
            borderRadius: 14,
            padding: '20px 24px',
            cursor: 'pointer',
            boxShadow: selectedProvider === 'FACTURAPI' ? '0 10px 20px -5px rgba(168, 85, 247, 0.3)' : '0 2px 4px rgba(0,0,0,0.02)',
            transition: 'all 0.2s',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
              <span style={{ fontSize: 20 }}>🟣</span>
              <strong style={{ fontSize: '1.1rem' }}>Facturapi (CFDI 4.0)</strong>
            </div>
            <p style={{ margin: 0, fontSize: '0.8125rem', opacity: 0.85 }}>
              Timbrado SAT & Autofactura QR
            </p>
          </div>
          <Badge variant={facturapiForm.is_enabled ? 'success' : 'default'}>
            {facturapiForm.is_enabled ? 'Activo' : 'Configurar'}
          </Badge>
        </div>

        {/* Rappi */}
        <div
          onClick={() => { setSelectedProvider('RAPPI'); setActiveTab('config'); }}
          style={{
            background: selectedProvider === 'RAPPI' ? '#831843' : '#fff',
            color: selectedProvider === 'RAPPI' ? '#fff' : '#0f172a',
            border: selectedProvider === 'RAPPI' ? '2px solid #ec4899' : '1px solid #e2e8f0',
            borderRadius: 14,
            padding: '20px 24px',
            cursor: 'pointer',
            boxShadow: selectedProvider === 'RAPPI' ? '0 10px 20px -5px rgba(236, 72, 153, 0.3)' : '0 2px 4px rgba(0,0,0,0.02)',
            transition: 'all 0.2s',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
              <span style={{ fontSize: 20 }}>🔴</span>
              <strong style={{ fontSize: '1.1rem' }}>Rappi</strong>
            </div>
            <p style={{ margin: 0, fontSize: '0.8125rem', opacity: 0.85 }}>
              Rappi Partners API · Pedidos & Webhooks
            </p>
          </div>
          <Badge variant={selectedProvider === 'RAPPI' && formData.is_enabled ? 'success' : 'default'}>
            {selectedProvider === 'RAPPI' && formData.is_enabled ? 'Conectado' : 'Configurar'}
          </Badge>
        </div>
      </div>

      {/* Main Panel Content */}
      <div className="premium-card" style={{ padding: 0, overflow: 'hidden' }}>
        {/* Navigation Tabs */}
        <div style={{ display: 'flex', borderBottom: '1px solid #e2e8f0', background: '#f8fafc', padding: '0 16px' }}>
          <button
            type="button"
            onClick={() => setActiveTab('config')}
            style={{
              padding: '16px 20px',
              border: 'none',
              background: 'transparent',
              fontWeight: 600,
              fontSize: '0.9375rem',
              color: activeTab === 'config' ? (selectedProvider === 'FACTURAPI' ? '#a855f7' : '#10b981') : '#64748b',
              borderBottom: activeTab === 'config' ? `3px solid ${selectedProvider === 'FACTURAPI' ? '#a855f7' : '#10b981'}` : '3px solid transparent',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 8,
            }}
          >
            <Key size={18} />
            {selectedProvider === 'FACTURAPI' ? 'Configuración Fiscal & API' : 'Credenciales & Webhook'}
          </button>

          {selectedProvider === 'FACTURAPI' ? (
            <button
              type="button"
              onClick={() => setActiveTab('invoices')}
              style={{
                padding: '16px 20px',
                border: 'none',
                background: 'transparent',
                fontWeight: 600,
                fontSize: '0.9375rem',
                color: activeTab === 'invoices' ? '#a855f7' : '#64748b',
                borderBottom: activeTab === 'invoices' ? '3px solid #a855f7' : '3px solid transparent',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 8,
              }}
            >
              <FileText size={18} />
              Historial de Facturas Timbradas
            </button>
          ) : (
            <>
              <button
                type="button"
                onClick={() => setActiveTab('stores')}
                style={{
                  padding: '16px 20px',
                  border: 'none',
                  background: 'transparent',
                  fontWeight: 600,
                  fontSize: '0.9375rem',
                  color: activeTab === 'stores' ? '#10b981' : '#64748b',
                  borderBottom: activeTab === 'stores' ? '3px solid #10b981' : '3px solid transparent',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                }}
              >
                <Building2 size={18} />
                Mapeo de Sucursales ({storeMappings.length})
              </button>

              <button
                type="button"
                onClick={() => setActiveTab('logs')}
                style={{
                  padding: '16px 20px',
                  border: 'none',
                  background: 'transparent',
                  fontWeight: 600,
                  fontSize: '0.9375rem',
                  color: activeTab === 'logs' ? '#10b981' : '#64748b',
                  borderBottom: activeTab === 'logs' ? '3px solid #10b981' : '3px solid transparent',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                }}
              >
                <Activity size={18} />
                Bitácora de Webhooks ({logs.length})
              </button>
            </>
          )}
        </div>

        {/* Facturapi Config Tab */}
        {selectedProvider === 'FACTURAPI' && activeTab === 'config' && (
          <div style={{ padding: '32px 28px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 28, flexWrap: 'wrap', gap: 16 }}>
              <div>
                <h2 style={{ fontSize: '1.35rem', fontWeight: 800, margin: '0 0 6px', color: '#0f172a', display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span style={{ fontSize: '1.5rem' }}>🟣</span>
                  Conector Oficial Facturapi v2 (CFDI 4.0)
                </h2>
                <p style={{ margin: 0, fontSize: '0.9rem', color: '#64748b' }}>
                  Emite facturas electrónicas válidas ante el SAT directamente desde el mostrador del POS o mediante autofactura en línea para comensales.
                </p>
              </div>
              <div style={{ display: 'flex', gap: 12 }}>
                <Button
                  variant="secondary"
                  onClick={() => testFacturapiMutation.mutate()}
                  disabled={testFacturapiMutation.isPending}
                  style={{ display: 'flex', alignItems: 'center', gap: 8, borderColor: '#c084fc', color: '#7e22ce', borderRadius: 10, padding: '10px 18px', fontWeight: 600 }}
                >
                  <Zap size={17} />
                  {testFacturapiMutation.isPending ? 'Probando...' : 'Probar Conexión'}
                </Button>
                <Button
                  variant="primary"
                  onClick={() => saveFacturapiMutation.mutate(facturapiForm)}
                  disabled={saveFacturapiMutation.isPending}
                  style={{ background: '#7e22ce', borderColor: '#6b21a8', borderRadius: 10, padding: '10px 22px', fontWeight: 700, boxShadow: '0 4px 14px rgba(126, 34, 206, 0.3)' }}
                >
                  {saveFacturapiMutation.isPending ? 'Guardando...' : 'Guardar Configuración'}
                </Button>
              </div>
            </div>

            {facturapiTestResult && (
              <div
                style={{
                  padding: '14px 18px',
                  borderRadius: 12,
                  marginBottom: 28,
                  fontSize: '0.9rem',
                  fontWeight: 600,
                  background: facturapiTestResult.success ? '#f0fdf4' : '#fef2f2',
                  border: `1.5px solid ${facturapiTestResult.success ? '#86efac' : '#fca5a5'}`,
                  color: facturapiTestResult.success ? '#15803d' : '#b91c1c',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  boxShadow: '0 2px 6px rgba(0,0,0,0.03)',
                }}
              >
                <span style={{ fontSize: '1.2rem' }}>{facturapiTestResult.success ? '✅' : '❌'}</span>
                {facturapiTestResult.message}
              </div>
            )}

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(460px, 1fr))', gap: 24 }}>
              {/* Sección 1: Credenciales & Entorno */}
              <div style={{ background: '#ffffff', padding: 24, borderRadius: 16, border: '1.5px solid #e2e8f0', boxShadow: '0 4px 16px -2px rgba(0, 0, 0, 0.04)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
                  <div style={{ width: 40, height: 40, borderRadius: 10, background: '#f3e8ff', color: '#7e22ce', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Key size={20} />
                  </div>
                  <div>
                    <h3 style={{ fontSize: '1.05rem', fontWeight: 700, margin: 0, color: '#0f172a' }}>
                      1. Credenciales & Entorno
                    </h3>
                    <p style={{ margin: 0, fontSize: '0.8rem', color: '#64748b' }}>
                      Llave API de acceso a Facturapi
                    </p>
                  </div>
                </div>

                <div style={{ marginBottom: 18 }}>
                  <label
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 12,
                      cursor: 'pointer',
                      fontWeight: 600,
                      fontSize: '0.9rem',
                      background: facturapiForm.is_enabled ? '#faf5ff' : '#f8fafc',
                      padding: '14px 16px',
                      borderRadius: 12,
                      border: facturapiForm.is_enabled ? '1.5px solid #d8b4fe' : '1.5px solid #e2e8f0',
                      color: facturapiForm.is_enabled ? '#581c87' : '#475569',
                      transition: 'all 0.2s',
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={facturapiForm.is_enabled ?? false}
                      onChange={(e) => setFacturapiForm({ ...facturapiForm, is_enabled: e.target.checked })}
                      style={{ width: 19, height: 19, accentColor: '#7e22ce', cursor: 'pointer' }}
                    />
                    <span>Habilitar Facturación Electrónica en este Restaurante</span>
                  </label>
                </div>

                <div style={{ marginBottom: 18 }}>
                  <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 700, color: '#334155', marginBottom: 6 }}>
                    Entorno de Timbrado SAT
                  </label>
                  <select
                    className="premium-select"
                    value={facturapiForm.environment ?? 'sandbox'}
                    onChange={(e) => setFacturapiForm({ ...facturapiForm, environment: e.target.value })}
                  >
                    <option value="sandbox">🧪 Sandbox (Ambiente de Pruebas / Sin validez fiscal)</option>
                    <option value="live">🚀 Producción en Vivo (Timbrado Oficial SAT)</option>
                  </select>
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 700, color: '#334155', marginBottom: 6 }}>
                    Facturapi Secret Key ({facturapiForm.environment === 'sandbox' ? 'sk_test_...' : 'sk_live_...'})
                  </label>
                  <div style={{ position: 'relative' }}>
                    <input
                      type={showApiKey ? 'text' : 'password'}
                      className="premium-input"
                      placeholder="sk_test_..."
                      value={facturapiForm.api_key ?? ''}
                      onChange={(e) => setFacturapiForm({ ...facturapiForm, api_key: e.target.value })}
                      style={{ paddingRight: 44 }}
                    />
                    <button
                      type="button"
                      onClick={() => setShowApiKey(!showApiKey)}
                      style={{
                        position: 'absolute',
                        right: 12,
                        top: '50%',
                        transform: 'translateY(-50%)',
                        background: 'none',
                        border: 'none',
                        cursor: 'pointer',
                        color: '#64748b',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                      }}
                    >
                      {showApiKey ? <EyeOff size={18} /> : <Eye size={18} />}
                    </button>
                  </div>
                  <span style={{ fontSize: '0.75rem', color: '#64748b', marginTop: 6, display: 'block' }}>
                    Obtén tu llave secreta en el panel de <a href="https://dashboard.facturapi.io" target="_blank" rel="noreferrer" style={{ color: '#7e22ce', fontWeight: 600 }}>Facturapi Dashboard</a>.
                  </span>
                </div>
              </div>

              {/* Sección 2: Datos Fiscales del Emisor */}
              <div style={{ background: '#ffffff', padding: 24, borderRadius: 16, border: '1.5px solid #e2e8f0', boxShadow: '0 4px 16px -2px rgba(0, 0, 0, 0.04)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
                  <div style={{ width: 40, height: 40, borderRadius: 10, background: '#f3e8ff', color: '#7e22ce', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Building2 size={20} />
                  </div>
                  <div>
                    <h3 style={{ fontSize: '1.05rem', fontWeight: 700, margin: 0, color: '#0f172a' }}>
                      2. Datos Fiscales del Emisor
                    </h3>
                    <p style={{ margin: 0, fontSize: '0.8rem', color: '#64748b' }}>
                      Razón social y RFC registrado ante el SAT
                    </p>
                  </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 0.8fr', gap: 14, marginBottom: 16 }}>
                  <div>
                    <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 700, color: '#334155', marginBottom: 6 }}>
                      RFC del Emisor (Restaurante) *
                    </label>
                    <input
                      type="text"
                      className="premium-input"
                      placeholder="KIW210101ABC"
                      value={facturapiForm.organization_rfc ?? ''}
                      onChange={(e) => setFacturapiForm({ ...facturapiForm, organization_rfc: e.target.value.toUpperCase() })}
                    />
                  </div>

                  <div>
                    <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 700, color: '#334155', marginBottom: 6 }}>
                      C.P. Fiscal *
                    </label>
                    <input
                      type="text"
                      className="premium-input"
                      placeholder="80000"
                      value={facturapiForm.organization_zip ?? ''}
                      onChange={(e) => setFacturapiForm({ ...facturapiForm, organization_zip: e.target.value })}
                    />
                  </div>
                </div>

                <div style={{ marginBottom: 16 }}>
                  <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 700, color: '#334155', marginBottom: 6 }}>
                    Nombre o Razón Social (Emisor) *
                  </label>
                  <input
                    type="text"
                    className="premium-input"
                    placeholder="RESTAURANTE EJEMPLO SA DE CV"
                    value={facturapiForm.organization_legal_name ?? ''}
                    onChange={(e) => setFacturapiForm({ ...facturapiForm, organization_legal_name: e.target.value.toUpperCase() })}
                  />
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 700, color: '#334155', marginBottom: 6 }}>
                    Régimen Fiscal del Emisor *
                  </label>
                  <select
                    className="premium-select"
                    value={facturapiForm.organization_tax_system ?? '601'}
                    onChange={(e) => setFacturapiForm({ ...facturapiForm, organization_tax_system: e.target.value })}
                  >
                    <option value="601">601 - General de Ley Personas Morales</option>
                    <option value="612">612 - Personas Físicas con Actividades Empresariales</option>
                    <option value="626">626 - Régimen Simplificado de Confianza (RESICO)</option>
                    <option value="605">605 - Sueldos y Salarios e Ingresos Asimilados</option>
                    <option value="616">616 - Sin obligaciones fiscales</option>
                  </select>
                </div>
              </div>

              {/* Sección 3: Parámetros del CFDI */}
              <div style={{ background: '#ffffff', padding: 24, borderRadius: 16, border: '1.5px solid #e2e8f0', boxShadow: '0 4px 16px -2px rgba(0, 0, 0, 0.04)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
                  <div style={{ width: 40, height: 40, borderRadius: 10, background: '#f3e8ff', color: '#7e22ce', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <FileText size={20} />
                  </div>
                  <div>
                    <h3 style={{ fontSize: '1.05rem', fontWeight: 700, margin: 0, color: '#0f172a' }}>
                      3. Parámetros del Comprobante CFDI
                    </h3>
                    <p style={{ margin: 0, fontSize: '0.8rem', color: '#64748b' }}>
                      Series y claves del catálogo SAT
                    </p>
                  </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 16 }}>
                  <div>
                    <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 700, color: '#334155', marginBottom: 6 }}>
                      Serie de Factura
                    </label>
                    <input
                      type="text"
                      className="premium-input"
                      placeholder="F"
                      value={facturapiForm.series ?? 'F'}
                      onChange={(e) => setFacturapiForm({ ...facturapiForm, series: e.target.value.toUpperCase() })}
                    />
                  </div>

                  <div>
                    <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 700, color: '#334155', marginBottom: 6 }}>
                      Clave SAT Producto
                    </label>
                    <input
                      type="text"
                      className="premium-input"
                      placeholder="90101501"
                      value={facturapiForm.default_product_sat_key ?? '90101501'}
                      onChange={(e) => setFacturapiForm({ ...facturapiForm, default_product_sat_key: e.target.value })}
                    />
                  </div>
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 700, color: '#334155', marginBottom: 6 }}>
                    Clave Unidad SAT
                  </label>
                  <input
                    type="text"
                    className="premium-input"
                    placeholder="E48"
                    value={facturapiForm.default_unit_sat_key ?? 'E48'}
                    onChange={(e) => setFacturapiForm({ ...facturapiForm, default_unit_sat_key: e.target.value.toUpperCase() })}
                  />
                  <span style={{ fontSize: '0.75rem', color: '#64748b', marginTop: 6, display: 'block' }}>
                    💡 Clave <code>90101501</code> (Restaurantes) y <code>E48</code> (Unidad de servicio).
                  </span>
                </div>
              </div>

              {/* Sección 4: Autofacturación en Línea */}
              <div style={{ background: '#ffffff', padding: 24, borderRadius: 16, border: '1.5px solid #e2e8f0', boxShadow: '0 4px 16px -2px rgba(0, 0, 0, 0.04)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
                  <div style={{ width: 40, height: 40, borderRadius: 10, background: '#f3e8ff', color: '#7e22ce', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Globe size={20} />
                  </div>
                  <div>
                    <h3 style={{ fontSize: '1.05rem', fontWeight: 700, margin: 0, color: '#0f172a' }}>
                      4. Portal de Autofactura (Comensales)
                    </h3>
                    <p style={{ margin: 0, fontSize: '0.8rem', color: '#64748b' }}>
                      Facturación en línea vía código QR en ticket
                    </p>
                  </div>
                </div>

                <div style={{ marginBottom: 18 }}>
                  <label
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 12,
                      cursor: 'pointer',
                      fontWeight: 600,
                      fontSize: '0.9rem',
                      background: facturapiForm.enable_self_invoicing ? '#faf5ff' : '#f8fafc',
                      padding: '14px 16px',
                      borderRadius: 12,
                      border: facturapiForm.enable_self_invoicing ? '1.5px solid #d8b4fe' : '1.5px solid #e2e8f0',
                      color: facturapiForm.enable_self_invoicing ? '#581c87' : '#475569',
                      transition: 'all 0.2s',
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={facturapiForm.enable_self_invoicing ?? true}
                      onChange={(e) => setFacturapiForm({ ...facturapiForm, enable_self_invoicing: e.target.checked })}
                      style={{ width: 19, height: 19, accentColor: '#7e22ce', cursor: 'pointer' }}
                    />
                    <span>Habilitar Autofacturación vía QR / E-Receipts</span>
                  </label>
                </div>

                <div style={{ marginBottom: 16 }}>
                  <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 700, color: '#334155', marginBottom: 6 }}>
                    Subdominio en Factura.space
                  </label>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontSize: '0.875rem', color: '#64748b', fontWeight: 600, background: '#f1f5f9', padding: '10px 12px', borderRadius: 8, border: '1px solid #cbd5e1' }}>
                      factura.space/
                    </span>
                    <input
                      type="text"
                      className="premium-input"
                      placeholder="demo"
                      value={facturapiForm.self_invoicing_domain ?? 'demo'}
                      onChange={(e) => setFacturapiForm({ ...facturapiForm, self_invoicing_domain: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '') })}
                      style={{ flex: 1 }}
                    />
                  </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
                  <div>
                    <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 700, color: '#334155', marginBottom: 6 }}>
                      Días de Vigencia
                    </label>
                    <input
                      type="number"
                      className="premium-input"
                      value={facturapiForm.self_invoicing_days_valid ?? 30}
                      onChange={(e) => setFacturapiForm({ ...facturapiForm, self_invoicing_days_valid: parseInt(e.target.value) || 30 })}
                    />
                  </div>

                  <div>
                    <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 700, color: '#334155', marginBottom: 6 }}>
                      QR en Ticket
                    </label>
                    <select
                      className="premium-select"
                      value={facturapiForm.print_qr_on_ticket ? 'yes' : 'no'}
                      onChange={(e) => setFacturapiForm({ ...facturapiForm, print_qr_on_ticket: e.target.value === 'yes' })}
                    >
                      <option value="yes">Imprimir en Comanda</option>
                      <option value="no">No Imprimir</option>
                    </select>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Facturapi Invoices Tab */}
        {selectedProvider === 'FACTURAPI' && activeTab === 'invoices' && (
          <div style={{ padding: 28 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <div>
                <h2 style={{ fontSize: '1.25rem', fontWeight: 700, margin: '0 0 4px', color: '#0f172a' }}>
                  Comprobantes Fiscales Digitales (CFDI 4.0)
                </h2>
                <p style={{ margin: 0, fontSize: '0.875rem', color: '#64748b' }}>
                  Facturas emitidas y timbradas formalmente ante el SAT con sus archivos oficiales XML y PDF.
                </p>
              </div>
            </div>

            {invoiceList.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '48px 20px', color: '#64748b', background: '#f8fafc', borderRadius: 12 }}>
                <FileText size={48} style={{ opacity: 0.3, margin: '0 auto 12px' }} />
                <p style={{ fontWeight: 600, margin: '0 0 4px' }}>No hay facturas emitidas todavía</p>
                <p style={{ fontSize: '0.875rem', margin: 0 }}>
                  Las facturas emitidas desde la pestaña de <strong>Facturación</strong> en el POS aparecerán aquí.
                </p>
              </div>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table className="premium-table" style={{ width: '100%' }}>
                  <thead>
                    <tr>
                      <th>Folio</th>
                      <th>Folio Fiscal (UUID SAT)</th>
                      <th>Receptor</th>
                      <th>Fecha</th>
                      <th>Total</th>
                      <th>Estado</th>
                      <th>Descargas</th>
                    </tr>
                  </thead>
                  <tbody>
                    {invoiceList.map((inv) => (
                      <tr key={inv.id}>
                        <td><strong>{inv.folio_number}</strong></td>
                        <td style={{ fontSize: '0.8125rem', fontFamily: 'monospace', color: '#475569' }}>
                          {inv.uuid_sat || 'En proceso'}
                        </td>
                        <td>
                          <div><strong>{inv.nombre_receptor}</strong></div>
                          <span style={{ fontSize: '0.75rem', color: '#64748b' }}>RFC: {inv.rfc_receptor}</span>
                        </td>
                        <td style={{ fontSize: '0.8125rem' }}>{new Date(inv.created_at).toLocaleString()}</td>
                        <td><strong>${(inv.total_cents / 100).toFixed(2)} {inv.currency}</strong></td>
                        <td>
                          <Badge variant={inv.status === 'issued' ? 'success' : 'danger'}>
                            {inv.status === 'issued' ? 'Válida' : 'Cancelada'}
                          </Badge>
                        </td>
                        <td>
                          <div style={{ display: 'flex', gap: 8 }}>
                            {inv.pdf_url && (
                              <a href={inv.pdf_url} target="_blank" rel="noreferrer" className="btn btn-outline btn-sm" style={{ display: 'flex', alignItems: 'center', gap: 4, textDecoration: 'none', padding: '4px 8px', fontSize: '0.75rem' }}>
                                <Download size={14} /> PDF
                              </a>
                            )}
                            {inv.xml_url && (
                              <a href={inv.xml_url} target="_blank" rel="noreferrer" className="btn btn-outline btn-sm" style={{ display: 'flex', alignItems: 'center', gap: 4, textDecoration: 'none', padding: '4px 8px', fontSize: '0.75rem' }}>
                                <Download size={14} /> XML
                              </a>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* Uber Eats / Delivery Tabs */}
        {selectedProvider !== 'FACTURAPI' && activeTab === 'config' && (
          <div style={{ padding: 28 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
              <div>
                <h2 style={{ fontSize: '1.25rem', fontWeight: 700, margin: '0 0 4px', color: '#0f172a' }}>
                  Configuración de API & Webhooks ({selectedProvider})
                </h2>
                <p style={{ margin: 0, fontSize: '0.875rem', color: '#64748b' }}>
                  Registra estas credenciales en el Developer Portal de {selectedProvider} para recibir pedidos en vivo.
                </p>
              </div>
              <div style={{ display: 'flex', gap: 12 }}>
                <Button
                  variant="secondary"
                  onClick={() => setTestOrderModalOpen(true)}
                  style={{ display: 'flex', alignItems: 'center', gap: 8 }}
                >
                  <Play size={16} />
                  Simular Pedido de Prueba
                </Button>
                <Button
                  variant="primary"
                  onClick={() => saveConfigMutation.mutate(formData)}
                  disabled={saveConfigMutation.isPending}
                >
                  {saveConfigMutation.isPending ? 'Guardando...' : 'Guardar Cambios'}
                </Button>
              </div>
            </div>

            {/* Webhook URL Box */}
            <div style={{ background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 12, padding: '16px 20px', marginBottom: 24 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <strong style={{ color: '#166534', fontSize: '0.875rem', display: 'block', marginBottom: 4 }}>
                    URL Oficial del Webhook de RestaurantOS (Para registrar en el Developer Portal de {selectedProvider === 'UBER_EATS' ? 'Uber Eats' : selectedProvider === 'DIDI_FOOD' ? 'DiDi Food' : selectedProvider}):
                  </strong>
                  <code style={{ fontSize: '0.875rem', color: '#15803d', wordBreak: 'break-all' }}>{webhookUrl}</code>
                </div>
                <Button
                  variant="secondary"
                  onClick={copyToClipboard}
                  style={{ display: 'flex', alignItems: 'center', gap: 6, borderColor: '#10b981', color: '#047857' }}
                >
                  {copied ? <Check size={16} /> : <Copy size={16} />}
                  {copied ? '¡Copiado!' : 'Copiar URL'}
                </Button>
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 20 }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: '#475569', marginBottom: 6 }}>
                  Estado de la Integración
                </label>
                <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={formData.is_enabled ?? false}
                    onChange={(e) => setFormData({ ...formData, is_enabled: e.target.checked })}
                    style={{ width: 18, height: 18, accentColor: '#10b981' }}
                  />
                  <span style={{ fontWeight: 600 }}>Activar recepción de pedidos en tiempo real</span>
                </label>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: '#475569', marginBottom: 6 }}>
                  Ambiente
                </label>
                <select
                  className="premium-input"
                  value={formData.environment ?? 'sandbox'}
                  onChange={(e) => setFormData({ ...formData, environment: e.target.value })}
                >
                  <option value="sandbox">Sandbox (Pruebas de desarrollo)</option>
                  <option value="production">Producción en Vivo</option>
                </select>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: '#475569', marginBottom: 6 }}>
                  {selectedProvider === 'UBER_EATS' ? 'Client ID (App ID de Uber)' : selectedProvider === 'DIDI_FOOD' ? 'App ID (DiDi Food OpenPlatform)' : selectedProvider === 'RAPPI' ? 'Client ID (Rappi Partners API)' : 'Client ID'}
                </label>
                <input
                  type="text"
                  className="premium-input"
                  placeholder={selectedProvider === 'UBER_EATS' ? 'ub_client_id_...' : selectedProvider === 'DIDI_FOOD' ? 'didi_app_...' : selectedProvider === 'RAPPI' ? 'rp_client_id_...' : 'client_id_...'}
                  value={formData.client_id ?? ''}
                  onChange={(e) => setFormData({ ...formData, client_id: e.target.value })}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: '#475569', marginBottom: 6 }}>
                  {selectedProvider === 'UBER_EATS' ? 'Client Secret' : selectedProvider === 'DIDI_FOOD' ? 'App Secret' : selectedProvider === 'RAPPI' ? 'Client Secret (Rappi Partners)' : 'Client Secret'}
                </label>
                <input
                  type="password"
                  className="premium-input"
                  placeholder="••••••••••••••••"
                  value={formData.client_secret ?? ''}
                  onChange={(e) => setFormData({ ...formData, client_secret: e.target.value })}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: '#475569', marginBottom: 6 }}>
                  Webhook Signing Secret (Firma HMAC-SHA256)
                </label>
                <input
                  type="password"
                  className="premium-input"
                  placeholder="whsec_••••••••••••••••"
                  value={formData.webhook_secret ?? ''}
                  onChange={(e) => setFormData({ ...formData, webhook_secret: e.target.value })}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: '#475569', marginBottom: 6 }}>
                  Tiempo Estimado de Preparación por Defecto
                </label>
                <input
                  type="number"
                  className="premium-input"
                  value={formData.default_prep_time_minutes ?? 20}
                  onChange={(e) => setFormData({ ...formData, default_prep_time_minutes: parseInt(e.target.value) || 20 })}
                />
              </div>
            </div>
          </div>
        )}

        {/* Stores Mappings Tab */}
        {selectedProvider !== 'FACTURAPI' && activeTab === 'stores' && (
          <div style={{ padding: 28 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <div>
                <h2 style={{ fontSize: '1.25rem', fontWeight: 700, margin: '0 0 4px', color: '#0f172a' }}>
                  Vinculación de Sucursales Físicas con {selectedProvider === 'UBER_EATS' ? 'Uber Eats' : selectedProvider === 'DIDI_FOOD' ? 'DiDi Food' : selectedProvider === 'RAPPI' ? 'Rappi' : selectedProvider}
                </h2>
                <p style={{ margin: 0, fontSize: '0.875rem', color: '#64748b' }}>
                  Asocia el {selectedProvider === 'UBER_EATS' ? 'Store UUID' : selectedProvider === 'DIDI_FOOD' ? 'Shop ID / Store ID' : selectedProvider === 'RAPPI' ? 'Store ID de Rappi' : 'Store ID'} de cada tienda en la plataforma externa con tu sucursal en RestaurantOS.
                </p>
              </div>
              <Button variant="primary" onClick={() => setMappingModalOpen(true)}>
                + Vincular Sucursal
              </Button>
            </div>

            {storeMappings.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '48px 20px', color: '#64748b', background: '#f8fafc', borderRadius: 12 }}>
                <Building2 size={48} style={{ opacity: 0.3, margin: '0 auto 12px' }} />
                <p style={{ fontWeight: 600, margin: '0 0 4px' }}>No hay sucursales vinculadas aún</p>
                <p style={{ fontSize: '0.875rem', margin: 0 }}>
                  Agrega una vinculación para que los pedidos de {selectedProvider === 'UBER_EATS' ? 'Uber' : selectedProvider === 'DIDI_FOOD' ? 'DiDi' : selectedProvider === 'RAPPI' ? 'Rappi' : 'Delivery'} se dirijan a la cocina correcta.
                </p>
              </div>
            ) : (
              <table className="premium-table" style={{ width: '100%' }}>
                <thead>
                  <tr>
                    <th>Sucursal Local</th>
                    <th>Código</th>
                    <th>{selectedProvider === 'UBER_EATS' ? 'Store UUID Externo' : selectedProvider === 'DIDI_FOOD' ? 'Shop ID / Store ID' : selectedProvider === 'RAPPI' ? 'Store ID Rappi' : 'Store ID Externo'}</th>
                    <th>Estado</th>
                    <th>Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {storeMappings.map((m) => (
                    <tr key={m.id}>
                      <td><strong>{m.branch_name}</strong></td>
                      <td><Badge variant="default">{m.branch_code}</Badge></td>
                      <td><code style={{ fontSize: '0.8125rem' }}>{m.external_store_id}</code></td>
                      <td><Badge variant={m.is_active ? 'success' : 'default'}>{m.is_active ? 'Activa' : 'Inactiva'}</Badge></td>
                      <td>
                        <Button
                          variant="secondary"
                          onClick={() => deleteMappingMutation.mutate(m.id)}
                          style={{ color: '#ef4444', borderColor: '#fca5a5', padding: '4px 8px' }}
                        >
                          <Trash2 size={16} />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}

        {/* Logs Tab */}
        {selectedProvider !== 'FACTURAPI' && activeTab === 'logs' && (
          <div style={{ padding: 28 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <div>
                <h2 style={{ fontSize: '1.25rem', fontWeight: 700, margin: '0 0 4px', color: '#0f172a' }}>
                  Bitácora de Webhooks en Vivo ({selectedProvider === 'UBER_EATS' ? 'Uber Eats' : selectedProvider === 'DIDI_FOOD' ? 'DiDi Food' : selectedProvider})
                </h2>
                <p style={{ margin: 0, fontSize: '0.875rem', color: '#64748b' }}>
                  Monitorea las notificaciones HTTP enviadas por la plataforma en tiempo real.
                </p>
              </div>
            </div>

            {logs.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '48px 20px', color: '#64748b', background: '#f8fafc', borderRadius: 12 }}>
                <Activity size={48} style={{ opacity: 0.3, margin: '0 auto 12px' }} />
                <p style={{ fontWeight: 600, margin: '0 0 4px' }}>No hay eventos registrados</p>
                <p style={{ fontSize: '0.875rem', margin: 0 }}>
                  Los webhooks recibidos aparecerán aquí automáticamente.
                </p>
              </div>
            ) : (
              <table className="premium-table" style={{ width: '100%' }}>
                <thead>
                  <tr>
                    <th>Fecha / Hora</th>
                    <th>Evento</th>
                    <th>Estado</th>
                    <th>ID Externo</th>
                  </tr>
                </thead>
                <tbody>
                  {logs.map((log) => (
                    <tr key={log.id}>
                      <td style={{ fontSize: '0.8125rem' }}>{new Date(log.created_at).toLocaleString()}</td>
                      <td><strong>{log.event_type}</strong></td>
                      <td>
                        <Badge variant={log.status === 'processed' ? 'success' : log.status === 'failed' ? 'danger' : 'default'}>
                          {log.status}
                        </Badge>
                      </td>
                      <td><code style={{ fontSize: '0.8125rem' }}>{log.event_id || '-'}</code></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </div>

      {/* Modal Vincular Sucursal */}
      <Modal
        isOpen={mappingModalOpen}
        onClose={() => setMappingModalOpen(false)}
        title={`Vincular Sucursal con ${selectedProvider === 'UBER_EATS' ? 'Uber Eats' : selectedProvider === 'DIDI_FOOD' ? 'DiDi Food' : selectedProvider === 'RAPPI' ? 'Rappi' : selectedProvider}`}
      >
        <div style={{ padding: '8px 0' }}>
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: '#475569', marginBottom: 6 }}>
              Sucursal Local
            </label>
            <select
              className="premium-input"
              value={newMappingBranchId}
              onChange={(e) => setNewMappingBranchId(e.target.value)}
            >
              <option value="">Selecciona una sucursal...</option>
              {branches.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name} ({b.code})
                </option>
              ))}
            </select>
          </div>

          <div style={{ marginBottom: 20 }}>
            <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: '#475569', marginBottom: 6 }}>
              {selectedProvider === 'UBER_EATS' ? 'Store UUID de Uber Eats' : selectedProvider === 'DIDI_FOOD' ? 'Shop ID / Store ID de DiDi Food' : selectedProvider === 'RAPPI' ? 'Store ID de Rappi' : 'Store ID Externo'}
            </label>
            <input
              type="text"
              className="premium-input"
              placeholder={selectedProvider === 'UBER_EATS' ? 'e.g. 7c32e189-9e8a-495f-9e84-18349281a812' : selectedProvider === 'DIDI_FOOD' ? 'e.g. didi_shop_guadalajara_01' : selectedProvider === 'RAPPI' ? 'e.g. rappi_store_guadalajara_01' : 'e.g. store_id_01'}
              value={newMappingStoreId}
              onChange={(e) => setNewMappingStoreId(e.target.value)}
            />
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12 }}>
            <Button variant="secondary" onClick={() => setMappingModalOpen(false)}>
              Cancelar
            </Button>
            <Button
              variant="primary"
              disabled={!newMappingBranchId || !newMappingStoreId || saveMappingMutation.isPending}
              onClick={() =>
                saveMappingMutation.mutate({
                  branch_id: newMappingBranchId,
                  external_store_id: newMappingStoreId,
                })
              }
            >
              {saveMappingMutation.isPending ? 'Vinculando...' : 'Guardar Vinculación'}
            </Button>
          </div>
        </div>
      </Modal>

      {/* Modal Simular Pedido */}
      <Modal
        isOpen={testOrderModalOpen}
        onClose={() => { setTestOrderModalOpen(false); setTestOrderResult(null); }}
        title={`Simular Pedido de ${selectedProvider === 'UBER_EATS' ? 'Uber Eats' : selectedProvider === 'DIDI_FOOD' ? 'DiDi Food' : selectedProvider === 'RAPPI' ? 'Rappi' : selectedProvider} (Sandbox)`}
      >
        <div style={{ padding: '8px 0' }}>
          <p style={{ fontSize: '0.875rem', color: '#64748b', marginBottom: 16 }}>
            Esta herramienta genera una orden simulada que viajará por el mismo flujo que un pedido real de {selectedProvider === 'UBER_EATS' ? 'Uber Eats' : selectedProvider === 'DIDI_FOOD' ? 'DiDi Food' : selectedProvider === 'RAPPI' ? 'Rappi' : selectedProvider}.
          </p>

          <div style={{ marginBottom: 16 }}>
            <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: '#475569', marginBottom: 6 }}>
              Nombre del Cliente Simulado
            </label>
            <input
              type="text"
              className="premium-input"
              value={testOrderCustomer}
              onChange={(e) => setTestOrderCustomer(e.target.value)}
            />
          </div>

          <div style={{ marginBottom: 20 }}>
            <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: '#475569', marginBottom: 6 }}>
              Cantidad de Productos
            </label>
            <select
              className="premium-input"
              value={testOrderItemsCount}
              onChange={(e) => setTestOrderItemsCount(parseInt(e.target.value) || 1)}
            >
              <option value={1}>1 Producto aleatorio</option>
              <option value={2}>2 Productos aleatorios</option>
              <option value={3}>3 Productos aleatorios</option>
            </select>
          </div>

          {testOrderResult && (
            <div style={{ padding: 12, background: '#f8fafc', borderRadius: 8, border: '1px solid #e2e8f0', marginBottom: 20, fontSize: '0.875rem', fontWeight: 500 }}>
              {testOrderResult}
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12 }}>
            <Button variant="secondary" onClick={() => setTestOrderModalOpen(false)}>
              Cerrar
            </Button>
            <Button
              variant="primary"
              disabled={simulateOrderMutation.isPending}
              onClick={() =>
                simulateOrderMutation.mutate({
                  customer_name: testOrderCustomer,
                  items_count: testOrderItemsCount,
                })
              }
            >
              {simulateOrderMutation.isPending ? 'Enviando...' : 'Disparar Pedido'}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
