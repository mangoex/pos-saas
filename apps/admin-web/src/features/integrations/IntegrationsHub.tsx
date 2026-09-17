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
  MessageSquare,
  Bot,
  Sparkles,
  ExternalLink,
  ShoppingCart,
  RefreshCw,
} from 'lucide-react';
import '../../premium-catalogs.css';

interface ChannelConfig {
  id?: string;
  is_enabled: boolean;
  environment: string;
  client_id: string;
  config_id?: string;
  client_secret: string;
  webhook_secret: string;
  auto_accept: boolean;
  default_prep_time_minutes: number;
  integration_status?: 'PENDING_VALIDATION';
  has_client_secret?: boolean;
  has_webhook_secret?: boolean;
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

interface WhatsAppKnowledgePreview {
  branch_id: string;
  branch_name: string;
  phone?: string;
  storefront_url: string;
  available_products_text: string;
  hours_text: string;
  promotions_text: string;
  categories_count: number;
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

export type ProviderType = 'UBER_EATS' | 'DIDI_FOOD' | 'RAPPI' | 'FACTURAPI' | 'WHATSAPP_BUSINESS';

interface IntegrationsHubProps {
  defaultProvider?: ProviderType;
}

export default function IntegrationsHub({ defaultProvider }: IntegrationsHubProps = {}) {
  const location = useLocation();
  const isInvoicingRoute = location.pathname.includes('/invoicing') || defaultProvider === 'FACTURAPI';
  const queryClient = useQueryClient();
  const [selectedProvider, setSelectedProvider] = useState<ProviderType>(
    isInvoicingRoute ? 'FACTURAPI' : (defaultProvider || 'UBER_EATS')
  );
  const isDeferredProvider = selectedProvider === 'DIDI_FOOD' || selectedProvider === 'RAPPI';

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

  // WhatsApp state
  const [selectedPreviewBranch, setSelectedPreviewBranch] = useState('');
  const [simulateMessage, setSimulateMessage] = useState('Hola, ¿qué tienen de comer y cuáles son sus horarios?');
  const [simulateChatHistory, setSimulateChatHistory] = useState<Array<{ sender: 'user' | 'bot'; text: string; time: string; parsedOrder?: any }>>([]);
  const [embeddedSignupOpen, setEmbeddedSignupOpen] = useState(false);
  const [signupCode, setSignupCode] = useState('');
  const [signupWabaId, setSignupWabaId] = useState('');
  const [signupPhoneNumberId, setSignupPhoneNumberId] = useState('');
  const [signupBranchId, setSignupBranchId] = useState('');

  // WhatsApp Notification Simulator state
  const [simulateNotificationStatus, setSimulateNotificationStatus] = useState('ACCEPTED');
  const [simulateNotificationName, setSimulateNotificationName] = useState('Carlos M.');
  const [simulateNotificationFolio, setSimulateNotificationFolio] = useState('FOL-1042');
  const [simulateNotificationOrderType, setSimulateNotificationOrderType] = useState('delivery');
  const [simulatedNotificationPreview, setSimulatedNotificationPreview] = useState<{
    status: string;
    message: string;
    tracking_url: string;
    smart_rating_url?: string | null;
  } | null>(null);

  // WhatsApp Marketing Campaigns & Opt-Out State
  const [selectedCampaignSegment, setSelectedCampaignSegment] = useState('churn_risk');
  const [campaignDiscountCode, setCampaignDiscountCode] = useState('VUELVE10');
  const [campaignCustomMessage, setCampaignCustomMessage] = useState('');
  const [campaignPreviewData, setCampaignPreviewData] = useState<{
    segment: string;
    total_eligible: number;
    discount_code: string;
    sample_message: string;
    sample_recipient?: string;
    storefront_url: string;
  } | null>(null);
  const [campaignDispatchResult, setCampaignDispatchResult] = useState<{
    status: string;
    segment: string;
    total_targets: number;
    sent_count: number;
    skipped_count: number;
    failed_count: number;
  } | null>(null);

  // Meta Message Templates & SDK State
  const [campaignUseTemplate, setCampaignUseTemplate] = useState(true);
  const [isLaunchingFb, setIsLaunchingFb] = useState(false);
  const [showManualSignup, setShowManualSignup] = useState(false);

  // Meta Message Templates (HSM) Query & Mutation
  const { data: templatesData, refetch: refetchTemplates } = useQuery<{
    waba_id: string;
    total_standard: number;
    templates: Array<{
      name: string;
      category: string;
      language: string;
      status: string;
      registered: boolean;
      description: string;
    }>;
  }>({
    queryKey: ['integrations', 'whatsapp', 'templates'],
    queryFn: () => fetchApi('/integrations/whatsapp/templates'),
    enabled: selectedProvider === 'WHATSAPP_BUSINESS' && activeTab === 'config',
  });

  const syncTemplatesMutation = useMutation({
    mutationFn: () => fetchApi('/integrations/whatsapp/templates/sync', { method: 'POST' }),
    onSuccess: () => {
      refetchTemplates();
    },
  });

  useEffect(() => {
    const handleMetaMessage = (event: MessageEvent) => {
      if (event.origin !== "https://www.facebook.com" && event.origin !== "https://web.facebook.com") return;
      try {
        const data = typeof event.data === 'string' ? JSON.parse(event.data) : event.data;
        if (data && data.type === 'WA_EMBEDDED_SIGNUP') {
          if (data.event === 'FINISH' && data.data) {
            if (data.data.phone_number_id) setSignupPhoneNumberId(String(data.data.phone_number_id));
            if (data.data.waba_id) setSignupWabaId(String(data.data.waba_id));
          }
        }
      } catch (_) {}
    };

    window.addEventListener('message', handleMetaMessage);
    return () => window.removeEventListener('message', handleMetaMessage);
  }, []);

  const handleLaunchMetaPopup = () => {
    const appId = (formData.client_id || '').trim();
    const configId = (formData.config_id || '').trim();

    if (!appId || !configId) {
      alert(
        "⚠️ Faltan datos de Tech Provider (Meta App ID y Configuration ID).\n\n" +
        "Para que Meta pueda abrir la ventana oficial de Embedded Signup, primero debes ingresar " +
        "el Meta App ID y el Configuration ID generados en tu Meta Developer App.\n\n" +
        "Puedes ingresarlos en el formulario de Tech Provider de esta ventana o en la sección de Credenciales."
      );
      setShowManualSignup(true);
      return;
    }

    setIsLaunchingFb(true);

    // Timeout de seguridad en caso de bloqueo de ventanas emergentes o cierre abrupto
    const safetyTimer = setTimeout(() => {
      setIsLaunchingFb(false);
    }, 12000);

    const launchLogin = () => {
      if (!(window as any).FB) {
        clearTimeout(safetyTimer);
        setIsLaunchingFb(false);
        setShowManualSignup(true);
        alert("El SDK de Meta no está disponible o fue bloqueado en este navegador. Puedes ingresar los datos manualmente.");
        return;
      }

      try {
        (window as any).FB.login((response: any) => {
          clearTimeout(safetyTimer);
          setIsLaunchingFb(false);
          if (response?.authResponse?.code) {
            setSignupCode(response.authResponse.code);
          }
        }, {
          config_id: configId,
          response_type: 'code',
          override_default_response_type: true,
          extras: {
            feature: 'whatsapp_embedded_signup',
            version: 2,
            sessionInfoVersion: 2,
          }
        });
      } catch (err) {
        clearTimeout(safetyTimer);
        setIsLaunchingFb(false);
        alert("Error al intentar abrir el popup de Meta: " + String(err));
      }
    };

    if ((window as any).FB) {
      launchLogin();
    } else {
      (window as any).fbAsyncInit = function() {
        try {
          (window as any).FB.init({
            appId: appId,
            autoLogAppEvents: true,
            xfbml: true,
            version: 'v20.0'
          });
        } catch (e) {
          console.error("FB.init error", e);
        }
        launchLogin();
      };
      if (!document.getElementById('facebook-jssdk')) {
        const script = document.createElement('script');
        script.id = 'facebook-jssdk';
        script.src = 'https://connect.facebook.net/es_LA/sdk.js';
        script.async = true;
        script.defer = true;
        script.crossOrigin = 'anonymous';
        script.onerror = () => {
          clearTimeout(safetyTimer);
          setIsLaunchingFb(false);
          setShowManualSignup(true);
          alert("No se pudo cargar el SDK de Facebook. Ingresa las credenciales manualmente en el formulario.");
        };
        document.body.appendChild(script);
      } else {
        launchLogin();
      }
    }
  };

  // Queries for Uber/Delivery Channels & WhatsApp
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
    mutationFn: (payload: Partial<ChannelConfig>) => {
      const { client_secret, webhook_secret, ...nonSecretFields } = payload;
      const preservedSecrets = {
        ...(client_secret?.trim() ? { client_secret: client_secret.trim() } : {}),
        ...(webhook_secret?.trim() ? { webhook_secret: webhook_secret.trim() } : {}),
      };
      return fetchApi('/integrations/' + selectedProvider.toLowerCase().replace('_', '-') + '/config', {
        method: 'PUT',
        body: JSON.stringify({ ...nonSecretFields, ...preservedSecrets, ...(isDeferredProvider ? { is_enabled: false } : {}) }),
      });
    },
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

  // WhatsApp Knowledge Preview Query
  const { data: knowledgePreview, isLoading: isLoadingPreview } = useQuery<WhatsAppKnowledgePreview>({
    queryKey: ['integrations', 'whatsapp', 'knowledge-preview', selectedPreviewBranch],
    queryFn: () => fetchApi('/integrations/whatsapp/knowledge-preview' + (selectedPreviewBranch ? `?branch_id=${selectedPreviewBranch}` : '')),
    enabled: selectedProvider === 'WHATSAPP_BUSINESS' && activeTab === 'config',
  });

  // WhatsApp Chat Simulation Mutation
  const simulateWhatsAppMutation = useMutation({
    mutationFn: (payload: { branch_id: string; message: string }) =>
      fetchApi<{ incoming_message: string; reply: string; knowledge_summary: any; parsed_order?: any }>('/integrations/whatsapp/simulate', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    onSuccess: (data) => {
      const nowTime = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      setSimulateChatHistory((prev) => [
        ...prev,
        { sender: 'user', text: data.incoming_message, time: nowTime },
        { sender: 'bot', text: data.reply, time: nowTime, parsedOrder: data.parsed_order },
      ]);
    },
    onError: (err: any) => {
      alert('Error al simular conversación: ' + (err.message || 'Desconocido'));
    },
  });

  // WhatsApp Embedded Signup Exchange Mutation
  const exchangeEmbeddedSignupMutation = useMutation({
    mutationFn: (payload: { code: string; waba_id: string; phone_number_id: string; branch_id: string }) =>
      fetchApi('/integrations/whatsapp/embedded-signup/exchange', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['integrations', 'WHATSAPP_BUSINESS'] });
      setEmbeddedSignupOpen(false);
      setSignupCode('');
      setSignupWabaId('');
      setSignupPhoneNumberId('');
      setSignupBranchId('');
      alert('¡Cuenta y número de WhatsApp Business vinculados con éxito!');
    },
    onError: (err: any) => {
      alert('Error al vincular con Meta: ' + (err.message || 'Código o IDs inválidos'));
    },
  });

  // WhatsApp Order Notification Simulation Mutation
  const simulateNotificationMutation = useMutation({
    mutationFn: (payload: {
      status: string;
      customer_name: string;
      folio: string;
      order_type: string;
      branch_name: string;
    }) =>
      fetchApi<{
        status: string;
        customer_name: string;
        folio: string;
        message: string;
        tracking_url: string;
        smart_rating_url?: string | null;
      }>('/integrations/whatsapp/simulate-notification', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    onSuccess: (data) => {
      setSimulatedNotificationPreview(data);
    },
    onError: (err: any) => {
      alert('Error al simular notificación: ' + (err.message || 'Desconocido'));
    },
  });

  // WhatsApp Marketing Campaign Segments Query
  const { data: campaignSegmentsData } = useQuery<{
    branch_id: string;
    segments: Record<string, { count: number; label: string }>;
    total_campaign_audience: number;
  }>({
    queryKey: ['integrations', 'whatsapp', 'campaigns', 'segments', selectedPreviewBranch],
    queryFn: () =>
      fetchApi(
        '/integrations/whatsapp/campaigns/segments' +
          (selectedPreviewBranch ? `?branch_id=${selectedPreviewBranch}` : '')
      ),
    enabled: selectedProvider === 'WHATSAPP_BUSINESS' && activeTab === 'config',
  });

  // WhatsApp Marketing Campaign Preview Mutation
  const previewCampaignMutation = useMutation({
    mutationFn: (payload: { branch_id?: string; segment: string; discount_code: string; custom_message?: string }) =>
      fetchApi<{
        segment: string;
        total_eligible: number;
        discount_code: string;
        sample_message: string;
        sample_recipient?: string;
        storefront_url: string;
      }>('/integrations/whatsapp/campaigns/preview', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    onSuccess: (data) => {
      setCampaignPreviewData(data);
      setCampaignDispatchResult(null);
    },
    onError: (err: any) => {
      alert('Error al previsualizar campaña: ' + (err.message || 'Desconocido'));
    },
  });

  // WhatsApp Marketing Campaign Dispatch Mutation
  const sendCampaignMutation = useMutation({
    mutationFn: (payload: { branch_id?: string; segment: string; discount_code: string; custom_message?: string; use_template?: boolean }) =>
      fetchApi<{
        status: string;
        segment: string;
        total_targets: number;
        sent_count: number;
        skipped_count: number;
        failed_count: number;
      }>('/integrations/whatsapp/campaigns/send', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    onSuccess: (data) => {
      setCampaignDispatchResult(data);
      alert(`¡Campaña enviada con éxito! Enviados: ${data.sent_count}, Omitidos/Bajas: ${data.skipped_count}`);
      queryClient.invalidateQueries({ queryKey: ['integrations', 'whatsapp', 'campaigns'] });
    },
    onError: (err: any) => {
      alert('Error al despachar campaña: ' + (err.message || 'Desconocido'));
    },
  });

  const webhookPath =
    selectedProvider === 'UBER_EATS'
      ? 'uber-eats'
      : selectedProvider === 'DIDI_FOOD'
      ? 'didi-food'
      : selectedProvider === 'RAPPI'
      ? 'rappi'
      : selectedProvider === 'WHATSAPP_BUSINESS'
      ? 'whatsapp'
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

        {/* WhatsApp Business */}
        <div
          onClick={() => { setSelectedProvider('WHATSAPP_BUSINESS'); setActiveTab('config'); }}
          style={{
            background: selectedProvider === 'WHATSAPP_BUSINESS' ? '#064e3b' : '#fff',
            color: selectedProvider === 'WHATSAPP_BUSINESS' ? '#fff' : '#0f172a',
            border: selectedProvider === 'WHATSAPP_BUSINESS' ? '2px solid #22c55e' : '1px solid #e2e8f0',
            borderRadius: 14,
            padding: '20px 24px',
            cursor: 'pointer',
            boxShadow: selectedProvider === 'WHATSAPP_BUSINESS' ? '0 10px 20px -5px rgba(34, 197, 94, 0.3)' : '0 2px 4px rgba(0,0,0,0.02)',
            transition: 'all 0.2s',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
              <span style={{ fontSize: 20 }}>💬</span>
              <strong style={{ fontSize: '1.1rem' }}>WhatsApp Business</strong>
            </div>
            <p style={{ margin: 0, fontSize: '0.8125rem', opacity: 0.85 }}>
              Embedded Signup · Menú & Horarios IA
            </p>
          </div>
          <Badge variant={selectedProvider === 'WHATSAPP_BUSINESS' && formData.is_enabled ? 'success' : 'default'}>
            {selectedProvider === 'WHATSAPP_BUSINESS' && formData.is_enabled ? 'Conectado' : 'Configurar'}
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
              color: activeTab === 'config' ? (selectedProvider === 'FACTURAPI' ? '#a855f7' : selectedProvider === 'WHATSAPP_BUSINESS' ? '#16a34a' : '#10b981') : '#64748b',
              borderBottom: activeTab === 'config' ? `3px solid ${selectedProvider === 'FACTURAPI' ? '#a855f7' : selectedProvider === 'WHATSAPP_BUSINESS' ? '#16a34a' : '#10b981'}` : '3px solid transparent',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 8,
            }}
          >
            <Key size={18} />
            {selectedProvider === 'FACTURAPI' ? 'Configuración Fiscal & API' : selectedProvider === 'WHATSAPP_BUSINESS' ? 'Credenciales & Asistente IA' : 'Credenciales & Webhook'}
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
                  color: activeTab === 'stores' ? (selectedProvider === 'WHATSAPP_BUSINESS' ? '#16a34a' : '#10b981') : '#64748b',
                  borderBottom: activeTab === 'stores' ? `3px solid ${selectedProvider === 'WHATSAPP_BUSINESS' ? '#16a34a' : '#10b981'}` : '3px solid transparent',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                }}
              >
                <Building2 size={18} />
                {selectedProvider === 'WHATSAPP_BUSINESS' ? 'Números & Sucursales' : 'Mapeo de Sucursales'} ({storeMappings.length})
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
                  color: activeTab === 'logs' ? (selectedProvider === 'WHATSAPP_BUSINESS' ? '#16a34a' : '#10b981') : '#64748b',
                  borderBottom: activeTab === 'logs' ? `3px solid ${selectedProvider === 'WHATSAPP_BUSINESS' ? '#16a34a' : '#10b981'}` : '3px solid transparent',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                }}
              >
                <Activity size={18} />
                {selectedProvider === 'WHATSAPP_BUSINESS' ? 'Bitácora de Mensajes' : 'Bitácora de Webhooks'} ({logs.length})
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

        {/* WhatsApp Business Config Tab */}
        {selectedProvider === 'WHATSAPP_BUSINESS' && activeTab === 'config' && (
          <div style={{ padding: '32px 28px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 28, flexWrap: 'wrap', gap: 16 }}>
              <div>
                <h2 style={{ fontSize: '1.35rem', fontWeight: 800, margin: '0 0 6px', color: '#0f172a', display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span style={{ fontSize: '1.5rem' }}>💬</span>
                  WhatsApp Business Platform (Cloud API & Embedded Signup)
                </h2>
                <p style={{ margin: 0, fontSize: '0.9rem', color: '#64748b' }}>
                  Conecta tu número oficial con Meta Embedded Signup para habilitar un asistente virtual con IA que responde menú, horarios y promociones en tiempo real.
                </p>
              </div>
              <div style={{ display: 'flex', gap: 12 }}>
                <Button
                  variant="secondary"
                  onClick={() => setEmbeddedSignupOpen(true)}
                  style={{ display: 'flex', alignItems: 'center', gap: 8, borderColor: '#22c55e', color: '#15803d', borderRadius: 10, padding: '10px 18px', fontWeight: 600 }}
                >
                  <Zap size={17} />
                  Meta Embedded Signup
                </Button>
                <Button
                  variant="primary"
                  onClick={() => saveConfigMutation.mutate(formData)}
                  disabled={saveConfigMutation.isPending}
                  style={{ background: '#16a34a', borderColor: '#15803d', borderRadius: 10, padding: '10px 22px', fontWeight: 700, boxShadow: '0 4px 14px rgba(22, 163, 74, 0.3)' }}
                >
                  {saveConfigMutation.isPending ? 'Guardando...' : 'Guardar Configuración'}
                </Button>
              </div>
            </div>

            {/* Webhook Configuration Box */}
            <div style={{ background: '#f0fdf4', border: '1.5px solid #86efac', borderRadius: 14, padding: '18px 22px', marginBottom: 28, boxShadow: '0 2px 8px rgba(34, 197, 94, 0.06)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 14 }}>
                <div style={{ flex: 1, minWidth: 280 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                    <span style={{ fontSize: 16 }}>🔗</span>
                    <strong style={{ color: '#166534', fontSize: '0.9375rem' }}>
                      URL de Webhook & Token de Verificación (Meta for Developers)
                    </strong>
                  </div>
                  <p style={{ margin: '0 0 10px', fontSize: '0.8125rem', color: '#15803d' }}>
                    Configura esta URL en tu Meta App (Webhooks &gt; WhatsApp Business Account &gt; suscribir al campo <code>messages</code>):
                  </p>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                    <div>
                      <span style={{ fontSize: '0.75rem', fontWeight: 700, color: '#166534', display: 'block' }}>Callback URL:</span>
                      <code style={{ fontSize: '0.8125rem', color: '#166534', background: '#dcfce7', padding: '4px 8px', borderRadius: 6, wordBreak: 'break-all' }}>{webhookUrl}</code>
                    </div>
                    <div>
                      <span style={{ fontSize: '0.75rem', fontWeight: 700, color: '#166534', display: 'block' }}>Verify Token:</span>
                      <code style={{ fontSize: '0.8125rem', color: '#166534', background: '#dcfce7', padding: '4px 8px', borderRadius: 6 }}>{formData.webhook_secret || 'mimenu_verify_secret_123'}</code>
                    </div>
                  </div>
                </div>
                <Button
                  variant="secondary"
                  onClick={copyToClipboard}
                  style={{ display: 'flex', alignItems: 'center', gap: 6, borderColor: '#22c55e', color: '#15803d', background: '#fff', fontWeight: 600 }}
                >
                  {copied ? <Check size={16} /> : <Copy size={16} />}
                  {copied ? '¡Copiado!' : 'Copiar URL'}
                </Button>
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(460px, 1fr))', gap: 24, marginBottom: 28 }}>
              {/* Sección 1: Credenciales & Entorno */}
              <div style={{ background: '#ffffff', padding: 24, borderRadius: 16, border: '1.5px solid #e2e8f0', boxShadow: '0 4px 16px -2px rgba(0, 0, 0, 0.04)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
                  <div style={{ width: 40, height: 40, borderRadius: 10, background: '#dcfce7', color: '#16a34a', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Key size={20} />
                  </div>
                  <div>
                    <h3 style={{ fontSize: '1.05rem', fontWeight: 700, margin: 0, color: '#0f172a' }}>
                      1. Credenciales de Meta Developer
                    </h3>
                    <p style={{ margin: 0, fontSize: '0.8rem', color: '#64748b' }}>
                      Tokens y llaves de acceso a WhatsApp Cloud API
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
                      background: formData.is_enabled ? '#f0fdf4' : '#f8fafc',
                      padding: '14px 16px',
                      borderRadius: 12,
                      border: formData.is_enabled ? '1.5px solid #86efac' : '1.5px solid #e2e8f0',
                      color: formData.is_enabled ? '#14532d' : '#475569',
                      transition: 'all 0.2s',
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={formData.is_enabled ?? false}
                      onChange={(e) => setFormData({ ...formData, is_enabled: e.target.checked })}
                      style={{ width: 19, height: 19, accentColor: '#16a34a', cursor: 'pointer' }}
                    />
                    <span>Habilitar Asistente de WhatsApp en este Restaurante</span>
                  </label>
                </div>

                <div style={{ marginBottom: 18 }}>
                  <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 700, color: '#334155', marginBottom: 6 }}>
                    Entorno
                  </label>
                  <select
                    className="premium-select"
                    value={formData.environment ?? 'sandbox'}
                    onChange={(e) => setFormData({ ...formData, environment: e.target.value })}
                  >
                    <option value="sandbox">🧪 Sandbox (Pruebas / Emulador local)</option>
                    <option value="production">🚀 Producción en Vivo (Meta Cloud API)</option>
                  </select>
                </div>

                <div style={{ marginBottom: 18 }}>
                  <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 700, color: '#334155', marginBottom: 6 }}>
                    Meta App ID
                  </label>
                  <input
                    type="text"
                    className="premium-input"
                    placeholder="e.g. 192837465019283"
                    value={formData.client_id ?? ''}
                    onChange={(e) => setFormData({ ...formData, client_id: e.target.value })}
                  />
                </div>

                <div style={{ marginBottom: 18 }}>
                  <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 700, color: '#334155', marginBottom: 6 }}>
                    Meta Configuration ID (Embedded Signup Config ID)
                  </label>
                  <input
                    type="text"
                    className="premium-input"
                    placeholder="e.g. 102938475610293 (ID del flujo en Meta App Dashboard)"
                    value={formData.config_id ?? ''}
                    onChange={(e) => setFormData({ ...formData, config_id: e.target.value })}
                  />
                  <small style={{ color: '#64748b', marginTop: 4, display: 'block' }}>
                    Requerido para lanzar el diálogo oficial popup de Meta Embedded Signup en un clic.
                  </small>
                </div>

                <div style={{ marginBottom: 18 }}>
                  <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 700, color: '#334155', marginBottom: 6 }}>
                    Meta App Secret (Firma HMAC-SHA256)
                  </label>
                  <input
                    type="password"
                    className="premium-input"
                    placeholder="••••••••••••••••"
                    value={formData.client_secret ?? ''}
                    onChange={(e) => setFormData({ ...formData, client_secret: e.target.value })}
                  />
                  {formData.has_client_secret && (
                    <small style={{ color: '#16a34a', marginTop: 4, display: 'block' }}>✓ Secreto guardado en servidor. Déjalo vacío para conservarlo.</small>
                  )}
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 700, color: '#334155', marginBottom: 6 }}>
                    Webhook Verify Token (Token de Validación)
                  </label>
                  <input
                    type="text"
                    className="premium-input"
                    placeholder="mimenu_verify_secret_123"
                    value={formData.webhook_secret ?? ''}
                    onChange={(e) => setFormData({ ...formData, webhook_secret: e.target.value })}
                  />
                </div>
              </div>

              {/* Sección 2: Base de Conocimiento en Vivo */}
              <div style={{ background: '#ffffff', padding: 24, borderRadius: 16, border: '1.5px solid #e2e8f0', boxShadow: '0 4px 16px -2px rgba(0, 0, 0, 0.04)' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <div style={{ width: 40, height: 40, borderRadius: 10, background: '#dcfce7', color: '#16a34a', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                      <Bot size={20} />
                    </div>
                    <div>
                      <h3 style={{ fontSize: '1.05rem', fontWeight: 700, margin: 0, color: '#0f172a' }}>
                        2. Base de Conocimiento en Vivo
                      </h3>
                      <p style={{ margin: 0, fontSize: '0.8rem', color: '#64748b' }}>
                        Menú, horarios y promociones sincronizados
                      </p>
                    </div>
                  </div>
                </div>

                <div style={{ marginBottom: 16 }}>
                  <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 700, color: '#334155', marginBottom: 6 }}>
                    Previsualizar Sucursal:
                  </label>
                  <select
                    className="premium-select"
                    value={selectedPreviewBranch}
                    onChange={(e) => setSelectedPreviewBranch(e.target.value)}
                  >
                    <option value="">Sucursal predeterminada</option>
                    {branches.map((b) => (
                      <option key={b.id} value={b.id}>
                        {b.name} ({b.code})
                      </option>
                    ))}
                  </select>
                </div>

                <div style={{ background: '#f8fafc', borderRadius: 12, padding: 16, border: '1px solid #e2e8f0', marginBottom: 14 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8, alignItems: 'center' }}>
                    <span style={{ fontSize: '0.8125rem', fontWeight: 700, color: '#334155' }}>
                      📍 Sucursal: {knowledgePreview?.branch_name || 'Cargando...'}
                    </span>
                    <Badge variant="success">86'd Auto-Filtrado</Badge>
                  </div>
                  <div style={{ fontSize: '0.8125rem', color: '#475569', marginBottom: 6 }}>
                    <strong>🕒 Horario:</strong> {knowledgePreview?.hours_text || 'Consultando...'}
                  </div>
                  <div style={{ fontSize: '0.8125rem', color: '#475569', marginBottom: 6 }}>
                    <strong>🎟️ Promociones:</strong> {knowledgePreview?.promotions_text || 'Sin cupones activos.'}
                  </div>
                  <div style={{ fontSize: '0.8125rem', color: '#475569', marginBottom: 10 }}>
                    <strong>🌐 Enlace Web:</strong>{' '}
                    <a href={knowledgePreview?.storefront_url} target="_blank" rel="noreferrer" style={{ color: '#16a34a', fontWeight: 600 }}>
                      {knowledgePreview?.storefront_url || 'https://mimenu.com'}
                    </a>
                  </div>
                  <div>
                    <span style={{ fontSize: '0.75rem', fontWeight: 700, color: '#64748b', display: 'block', marginBottom: 4 }}>
                      Resumen del Catálogo Activo (Excluye items agotados):
                    </span>
                    <pre style={{ margin: 0, padding: 10, background: '#ffffff', border: '1px solid #cbd5e1', borderRadius: 8, fontSize: '0.75rem', color: '#334155', maxHeight: 150, overflowY: 'auto', whiteSpace: 'pre-wrap', fontFamily: 'monospace' }}>
                      {knowledgePreview?.available_products_text || 'Cargando menú en vivo...'}
                    </pre>
                  </div>
                </div>

                <div style={{ fontSize: '0.75rem', color: '#15803d', background: '#f0fdf4', padding: '8px 12px', borderRadius: 8, border: '1px solid #bbf7d0' }}>
                  ✓ El bot consulta directamente PostgreSQL en tiempo real. Cualquier cambio en precio o disponibilidad se refleja al instante sin reentrenar.
                </div>
              </div>
            </div>

            {/* Sección 3: Simulador Interactivo de Conversación */}
            <div style={{ background: '#ffffff', padding: 24, borderRadius: 16, border: '1.5px solid #e2e8f0', boxShadow: '0 4px 16px -2px rgba(0, 0, 0, 0.04)' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 18, flexWrap: 'wrap', gap: 12 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <div style={{ width: 40, height: 40, borderRadius: 10, background: '#dcfce7', color: '#16a34a', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <MessageSquare size={20} />
                  </div>
                  <div>
                    <h3 style={{ fontSize: '1.05rem', fontWeight: 700, margin: 0, color: '#0f172a' }}>
                      3. Simulador de Conversación WhatsApp (Sandbox Interactivo)
                    </h3>
                    <p style={{ margin: 0, fontSize: '0.8rem', color: '#64748b' }}>
                      Escribe un mensaje como si fueras un comensal y prueba las respuestas del asistente
                    </p>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  <button
                    type="button"
                    onClick={() => setSimulateMessage('¿Qué tienen de comer y qué me recomiendas?')}
                    style={{ padding: '6px 12px', borderRadius: 8, border: '1px solid #cbd5e1', background: '#f8fafc', fontSize: '0.75rem', cursor: 'pointer', fontWeight: 600, color: '#334155' }}
                  >
                    🍽️ Ver Menú
                  </button>
                  <button
                    type="button"
                    onClick={() => setSimulateMessage('¿Cuáles son sus horarios de servicio?')}
                    style={{ padding: '6px 12px', borderRadius: 8, border: '1px solid #cbd5e1', background: '#f8fafc', fontSize: '0.75rem', cursor: 'pointer', fontWeight: 600, color: '#334155' }}
                  >
                    🕒 Horarios
                  </button>
                  <button
                    type="button"
                    onClick={() => setSimulateMessage('¿Tienen alguna promoción o cupón hoy?')}
                    style={{ padding: '6px 12px', borderRadius: 8, border: '1px solid #cbd5e1', background: '#f8fafc', fontSize: '0.75rem', cursor: 'pointer', fontWeight: 600, color: '#334155' }}
                  >
                    🎟️ Promociones
                  </button>
                  <button
                    type="button"
                    onClick={() => setSimulateMessage('Quiero 2 tacos al pastor y una gringa especial por favor')}
                    style={{ padding: '6px 12px', borderRadius: 8, border: '1.5px solid #86efac', background: '#f0fdf4', fontSize: '0.75rem', cursor: 'pointer', fontWeight: 700, color: '#166534' }}
                  >
                    🛒 Pedido Asistido
                  </button>
                </div>
              </div>

              {/* Chat Viewport */}
              <div style={{ background: '#efeae2', borderRadius: 14, padding: 18, minHeight: 180, maxHeight: 320, overflowY: 'auto', marginBottom: 16, border: '1px solid #d1d5db', display: 'flex', flexDirection: 'column', gap: 12 }}>
                {simulateChatHistory.length === 0 ? (
                  <div style={{ textAlign: 'center', padding: '30px 10px', color: '#64748b' }}>
                    <Bot size={32} style={{ opacity: 0.4, margin: '0 auto 8px' }} />
                    <p style={{ margin: 0, fontSize: '0.875rem', fontWeight: 600 }}>El simulador está listo</p>
                    <p style={{ margin: '4px 0 0', fontSize: '0.75rem' }}>Escribe una pregunta abajo o presiona uno de los botones rápidos para conversar con el asistente.</p>
                  </div>
                ) : (
                  simulateChatHistory.map((item, idx) => (
                    <div
                      key={idx}
                      style={{
                        alignSelf: item.sender === 'user' ? 'flex-end' : 'flex-start',
                        maxWidth: '80%',
                        background: item.sender === 'user' ? '#d9fdd3' : '#ffffff',
                        padding: '10px 14px',
                        borderRadius: 12,
                        boxShadow: '0 1px 2px rgba(0,0,0,0.1)',
                        fontSize: '0.875rem',
                        color: '#111827',
                        whiteSpace: 'pre-wrap',
                      }}
                    >
                      <div style={{ fontSize: '0.7rem', fontWeight: 700, color: item.sender === 'user' ? '#15803d' : '#0369a1', marginBottom: 4 }}>
                        {item.sender === 'user' ? '👤 Comensal' : '🤖 Asistente RestaurantOS'} · {item.time}
                      </div>
                      <div>{item.text}</div>
                      {item.sender === 'bot' && item.parsedOrder?.is_order_intent && item.parsedOrder.matched_items?.length > 0 && (
                        <div style={{ marginTop: 10, padding: '10px 12px', background: '#f0fdf4', border: '1.5px solid #86efac', borderRadius: 10, fontSize: '0.8rem' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#166534', fontWeight: 700 }}>
                              <ShoppingCart size={14} /> Carrito Asistido ({item.parsedOrder.matched_items.length} productos)
                            </div>
                            <span style={{ fontWeight: 800, color: '#15803d', fontSize: '0.875rem' }}>
                              ${(item.parsedOrder.total_cents / 100).toFixed(2)} MXN
                            </span>
                          </div>
                          {item.parsedOrder.cart_url && (
                            <a
                              href={item.parsedOrder.cart_url}
                              target="_blank"
                              rel="noreferrer"
                              style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: '#ffffff', background: '#16a34a', fontWeight: 700, textDecoration: 'none', padding: '6px 12px', borderRadius: 8, fontSize: '0.75rem', marginTop: 4, boxShadow: '0 2px 6px rgba(22, 163, 74, 0.25)' }}
                            >
                              <ExternalLink size={13} /> Abrir Carrito en Menú Digital
                            </a>
                          )}
                        </div>
                      )}
                    </div>
                  ))
                )}
              </div>

              {/* Chat Input Bar */}
              <div style={{ display: 'flex', gap: 10 }}>
                <input
                  type="text"
                  className="premium-input"
                  placeholder="Escribe un mensaje de WhatsApp (ej. ¿Qué venden?)..."
                  value={simulateMessage}
                  onChange={(e) => setSimulateMessage(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && simulateMessage.trim()) {
                      simulateWhatsAppMutation.mutate({
                        branch_id: selectedPreviewBranch,
                        message: simulateMessage,
                      });
                    }
                  }}
                  style={{ flex: 1 }}
                />
                <Button
                  variant="primary"
                  disabled={!simulateMessage.trim() || simulateWhatsAppMutation.isPending}
                  onClick={() =>
                    simulateWhatsAppMutation.mutate({
                      branch_id: selectedPreviewBranch,
                      message: simulateMessage,
                    })
                  }
                  style={{ background: '#16a34a', borderColor: '#15803d', display: 'flex', alignItems: 'center', gap: 6, fontWeight: 700 }}
                >
                  <Send size={16} />
                  {simulateWhatsAppMutation.isPending ? 'Enviando...' : 'Enviar'}
                </Button>
              </div>
            </div>

            {/* 4. Notificaciones Proactivas de Estado (Tracking en Vivo & Smart Rating) */}
            <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 16, padding: 24, marginTop: 24, boxShadow: '0 4px 6px -1px rgba(0,0,0,0.05)' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <div style={{ background: '#dbeafe', color: '#1d4ed8', padding: 8, borderRadius: 10 }}>
                    <Zap size={20} />
                  </div>
                  <div>
                    <h3 style={{ fontSize: '1.1rem', fontWeight: 700, margin: 0, color: '#0f172a' }}>
                      4. Notificaciones Proactivas de Estado (Tracking &amp; Smart Rating)
                    </h3>
                    <p style={{ margin: 0, fontSize: '0.85rem', color: '#64748b' }}>
                      Previsualiza los mensajes transaccionales automatizados con enlaces de seguimiento en vivo y encuestas Smart Rating.
                    </p>
                  </div>
                </div>
                <Badge variant="info" style={{ background: '#eff6ff', color: '#1d4ed8', border: '1px solid #bfdbfe' }}>
                  PRD-FR-094 &amp; PRD-FR-735
                </Badge>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16, marginBottom: 16 }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: '#334155', marginBottom: 6 }}>
                    Estado del Pedido
                  </label>
                  <select
                    className="premium-input"
                    value={simulateNotificationStatus}
                    onChange={(e) => setSimulateNotificationStatus(e.target.value)}
                    style={{ width: '100%' }}
                  >
                    <option value="ACCEPTED">ACCEPTED (En Cocina)</option>
                    <option value="READY">READY (Listo para Recoger / Despachar)</option>
                    <option value="IN_DELIVERY">IN_DELIVERY (Repartidor en Camino)</option>
                    <option value="DELIVERED">DELIVERED (Entregado con Smart Rating)</option>
                    <option value="CANCELLED">CANCELLED (Cancelado)</option>
                  </select>
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: '#334155', marginBottom: 6 }}>
                    Tipo de Entrega
                  </label>
                  <select
                    className="premium-input"
                    value={simulateNotificationOrderType}
                    onChange={(e) => setSimulateNotificationOrderType(e.target.value)}
                    style={{ width: '100%' }}
                  >
                    <option value="delivery">Delivery (A Domicilio)</option>
                    <option value="takeout">Takeout / Pickup (Para Llevar)</option>
                  </select>
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: '#334155', marginBottom: 6 }}>
                    Nombre del Cliente
                  </label>
                  <input
                    type="text"
                    className="premium-input"
                    value={simulateNotificationName}
                    onChange={(e) => setSimulateNotificationName(e.target.value)}
                    placeholder="Ej. Carlos M."
                    style={{ width: '100%' }}
                  />
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: '#334155', marginBottom: 6 }}>
                    Folio
                  </label>
                  <input
                    type="text"
                    className="premium-input"
                    value={simulateNotificationFolio}
                    onChange={(e) => setSimulateNotificationFolio(e.target.value)}
                    placeholder="Ej. FOL-1042"
                    style={{ width: '100%' }}
                  />
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
                <Button
                  variant="primary"
                  disabled={simulateNotificationMutation.isPending}
                  onClick={() => {
                    const branchName = knowledgePreview?.branch_name || 'Restaurante';
                    simulateNotificationMutation.mutate({
                      status: simulateNotificationStatus,
                      customer_name: simulateNotificationName,
                      folio: simulateNotificationFolio,
                      order_type: simulateNotificationOrderType,
                      branch_name: branchName,
                    });
                  }}
                  style={{ background: '#2563eb', borderColor: '#1d4ed8', display: 'flex', alignItems: 'center', gap: 6, fontWeight: 700 }}
                >
                  <Sparkles size={16} />
                  {simulateNotificationMutation.isPending ? 'Simulando...' : 'Generar Vista Previa WhatsApp'}
                </Button>
              </div>

              {simulatedNotificationPreview && (
                <div style={{ background: '#efeae2', borderRadius: 12, padding: 16, border: '1px solid #d1d7db' }}>
                  <div style={{ fontSize: '0.8rem', fontWeight: 700, color: '#54656f', marginBottom: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span>MENSAJE SALIENTE SIMULADO (WHATSAPP CLOUD API)</span>
                    <span style={{ background: '#22c55e', color: '#fff', padding: '2px 8px', borderRadius: 12, fontSize: '0.75rem' }}>
                      Estado: {simulatedNotificationPreview.status}
                    </span>
                  </div>
                  <div style={{ background: '#d9fdd3', padding: '12px 16px', borderRadius: 8, maxWidth: 520, boxShadow: '0 1px 0.5px rgba(11,20,26,.13)', whiteSpace: 'pre-wrap', fontSize: '0.9rem', color: '#111b21', lineHeight: 1.5 }}>
                    {simulatedNotificationPreview.message}
                  </div>
                  {simulatedNotificationPreview.smart_rating_url && (
                    <div style={{ marginTop: 10, display: 'inline-flex', alignItems: 'center', gap: 6, background: '#fef3c7', border: '1px solid #fde047', borderRadius: 8, padding: '6px 12px', fontSize: '0.8rem', color: '#92400e', fontWeight: 600 }}>
                      <Sparkles size={14} color="#d97706" />
                      Smart Rating Activo: Captura satisfacción 1-5 estrellas y promueve reseñas públicas en Google Maps.
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* 5. Campañas de Marketing & Re-engagement (Marketing HSM & Opt-Out) */}
            <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 16, padding: 24, marginTop: 24, boxShadow: '0 4px 6px -1px rgba(0,0,0,0.05)' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <div style={{ background: '#fef3c7', color: '#b45309', padding: 8, borderRadius: 10 }}>
                    <Sparkles size={20} />
                  </div>
                  <div>
                    <h3 style={{ fontSize: '1.1rem', fontWeight: 700, margin: 0, color: '#0f172a' }}>
                      5. Campañas de Marketing &amp; Re-engagement (WhatsApp Cloud API)
                    </h3>
                    <p style={{ margin: 0, fontSize: '0.85rem', color: '#64748b' }}>
                      Reactiva clientes inactivos y premia a comensales VIP con cupones directos y cláusula obligatoria de desuscripción (Opt-Out).
                    </p>
                  </div>
                </div>
                <Badge variant="info" style={{ background: '#fef9c3', color: '#854d0e', border: '1px solid #fde047' }}>
                  PRD-FR-095 &amp; SDD-ADR-039
                </Badge>
              </div>

              {/* CRM Segment Cards */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 16, marginBottom: 20 }}>
                <div
                  onClick={() => setSelectedCampaignSegment('churn_risk')}
                  style={{
                    border: selectedCampaignSegment === 'churn_risk' ? '2px solid #ef4444' : '1px solid #e2e8f0',
                    background: selectedCampaignSegment === 'churn_risk' ? '#fef2f2' : '#f8fafc',
                    borderRadius: 12,
                    padding: 16,
                    cursor: 'pointer',
                    transition: 'all 0.2s',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                    <span style={{ fontSize: '0.85rem', fontWeight: 700, color: '#991b1b' }}>En Riesgo (Churn)</span>
                    <Badge variant="danger">
                      {campaignSegmentsData?.segments?.churn_risk?.count ?? 0}
                    </Badge>
                  </div>
                  <p style={{ margin: 0, fontSize: '0.8rem', color: '#64748b' }}>
                    Clientes sin compras en más de 30 días.
                  </p>
                </div>

                <div
                  onClick={() => setSelectedCampaignSegment('vip')}
                  style={{
                    border: selectedCampaignSegment === 'vip' ? '2px solid #f59e0b' : '1px solid #e2e8f0',
                    background: selectedCampaignSegment === 'vip' ? '#fffbeb' : '#f8fafc',
                    borderRadius: 12,
                    padding: 16,
                    cursor: 'pointer',
                    transition: 'all 0.2s',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                    <span style={{ fontSize: '0.85rem', fontWeight: 700, color: '#92400e' }}>Clientes VIP</span>
                    <Badge variant="warning">
                      {campaignSegmentsData?.segments?.vip?.count ?? 0}
                    </Badge>
                  </div>
                  <p style={{ margin: 0, fontSize: '0.8rem', color: '#64748b' }}>
                    Comensales de alta recurrencia o consumo &gt; $500.
                  </p>
                </div>

                <div
                  onClick={() => setSelectedCampaignSegment('new_customers')}
                  style={{
                    border: selectedCampaignSegment === 'new_customers' ? '2px solid #10b981' : '1px solid #e2e8f0',
                    background: selectedCampaignSegment === 'new_customers' ? '#ecfdf5' : '#f8fafc',
                    borderRadius: 12,
                    padding: 16,
                    cursor: 'pointer',
                    transition: 'all 0.2s',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                    <span style={{ fontSize: '0.85rem', fontWeight: 700, color: '#065f46' }}>Nuevos Clientes</span>
                    <Badge variant="success">
                      {campaignSegmentsData?.segments?.new_customers?.count ?? 0}
                    </Badge>
                  </div>
                  <p style={{ margin: 0, fontSize: '0.8rem', color: '#64748b' }}>
                    Primer pedido en los últimos 14 días.
                  </p>
                </div>
              </div>

              {/* Controls */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 16, marginBottom: 16 }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: '#334155', marginBottom: 6 }}>
                    Cupón de Descuento Promocional
                  </label>
                  <input
                    type="text"
                    className="premium-input"
                    value={campaignDiscountCode}
                    onChange={(e) => setCampaignDiscountCode(e.target.value.toUpperCase())}
                    placeholder="Ej. VUELVE10"
                    style={{ width: '100%', textTransform: 'uppercase', fontWeight: 700 }}
                  />
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: '#334155', marginBottom: 6 }}>
                    Mensaje Personalizado (Opcional)
                  </label>
                  <input
                    type="text"
                    className="premium-input"
                    value={campaignCustomMessage}
                    onChange={(e) => setCampaignCustomMessage(e.target.value)}
                    placeholder="Dejar en blanco para usar copia inteligente de IA..."
                    style={{ width: '100%' }}
                  />
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginBottom: 16 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 10 }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.8125rem', fontWeight: 600, color: '#334155', cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={campaignUseTemplate}
                      onChange={(e) => setCampaignUseTemplate(e.target.checked)}
                      style={{ accentColor: '#16a34a' }}
                    />
                    <span>Enviar como Plantilla Oficial de Meta (HSM Pre-Aprobada para entrega fuera de 24h)</span>
                  </label>
                </div>
              </div>

              <div style={{ display: 'flex', gap: 12, marginBottom: 20 }}>
                <Button
                  variant="secondary"
                  disabled={previewCampaignMutation.isPending}
                  onClick={() =>
                    previewCampaignMutation.mutate({
                      segment: selectedCampaignSegment,
                      discount_code: campaignDiscountCode,
                      custom_message: campaignCustomMessage || undefined,
                    })
                  }
                  style={{ display: 'flex', alignItems: 'center', gap: 6 }}
                >
                  <Eye size={16} />
                  {previewCampaignMutation.isPending ? 'Cargando...' : 'Previsualizar Mensaje'}
                </Button>

                <Button
                  variant="primary"
                  disabled={sendCampaignMutation.isPending}
                  onClick={() => {
                    if (
                      window.confirm(
                        `¿Estás seguro de enviar esta campaña por WhatsApp al segmento "${selectedCampaignSegment}"?`
                      )
                    ) {
                      sendCampaignMutation.mutate({
                        segment: selectedCampaignSegment,
                        discount_code: campaignDiscountCode,
                        custom_message: campaignCustomMessage || undefined,
                        use_template: campaignUseTemplate,
                      });
                    }
                  }}
                  style={{ background: '#16a34a', borderColor: '#15803d', display: 'flex', alignItems: 'center', gap: 6, fontWeight: 700 }}
                >
                  <Send size={16} />
                  {sendCampaignMutation.isPending ? 'Despachando...' : 'Despachar Campaña WhatsApp'}
                </Button>
              </div>

              {/* Preview Box */}
              {campaignPreviewData && (
                <div style={{ background: '#efeae2', borderRadius: 12, padding: 16, border: '1px solid #d1d7db', marginTop: 12 }}>
                  <div style={{ fontSize: '0.8rem', fontWeight: 700, color: '#54656f', marginBottom: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span>VISTA PREVIA DE MENSAJE PROMOCIONAL (META WHATSAPP)</span>
                    <span style={{ background: '#0284c7', color: '#fff', padding: '2px 8px', borderRadius: 12, fontSize: '0.75rem' }}>
                      Audiencia estimada: {campaignPreviewData.total_eligible} comensales
                    </span>
                  </div>
                  <div style={{ background: '#d9fdd3', padding: '12px 16px', borderRadius: 8, maxWidth: 540, boxShadow: '0 1px 0.5px rgba(11,20,26,.13)', whiteSpace: 'pre-wrap', fontSize: '0.9rem', color: '#111b21', lineHeight: 1.5 }}>
                    {campaignPreviewData.sample_message}
                  </div>
                  <div style={{ marginTop: 10, display: 'inline-flex', alignItems: 'center', gap: 6, background: '#f1f5f9', border: '1px solid #cbd5e1', borderRadius: 8, padding: '6px 12px', fontSize: '0.8rem', color: '#475569' }}>
                    <Zap size={14} color="#64748b" />
                    Cumple políticas de Meta: incluye cláusula de desuscripción y detección automática de STOP/BAJA.
                  </div>
                </div>
              )}

              {/* Results Report */}
              {campaignDispatchResult && (
                <div style={{ marginTop: 16, padding: 16, borderRadius: 12, background: '#f0fdf4', border: '1px solid #bbf7d0' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                    <Check size={18} color="#16a34a" />
                    <strong style={{ color: '#166534', fontSize: '0.95rem' }}>Resumen de Ejecución de Campaña</strong>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 12, fontSize: '0.85rem' }}>
                    <div>Total Objetivos: <strong>{campaignDispatchResult.total_targets}</strong></div>
                    <div>Enviados con Éxito: <strong style={{ color: '#16a34a' }}>{campaignDispatchResult.sent_count}</strong></div>
                    <div>Omitidos (Opt-Out): <strong style={{ color: '#ea580c' }}>{campaignDispatchResult.skipped_count}</strong></div>
                    <div>Fallidos: <strong style={{ color: '#dc2626' }}>{campaignDispatchResult.failed_count}</strong></div>
                  </div>
                </div>
              )}
            </div>

            {/* 6. Plantillas Oficiales de Mensajes HSM (Meta Cloud API) */}
            <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 16, padding: 24, marginTop: 24, boxShadow: '0 4px 6px -1px rgba(0,0,0,0.05)' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16, flexWrap: 'wrap', gap: 12 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <div style={{ background: '#fdf4ff', color: '#a855f7', padding: 8, borderRadius: 10 }}>
                    <MessageSquare size={20} />
                  </div>
                  <div>
                    <h3 style={{ fontSize: '1.1rem', fontWeight: 700, margin: 0, color: '#0f172a' }}>
                      6. Plantillas Oficiales de Mensajes HSM (Meta Cloud API)
                    </h3>
                    <p style={{ margin: 0, fontSize: '0.85rem', color: '#64748b' }}>
                      Meta exige plantillas pre-aprobadas para mensajes iniciados fuera de la ventana de 24 horas (seguimiento de órdenes y campañas).
                    </p>
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <Badge variant="info" style={{ background: '#faf5ff', color: '#9333ea', border: '1px solid #e9d5ff' }}>
                    PRD-FR-096 &amp; SDD-ADR-040
                  </Badge>
                  <Button
                    variant="secondary"
                    disabled={syncTemplatesMutation.isPending}
                    onClick={() => syncTemplatesMutation.mutate()}
                    style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.8125rem', borderColor: '#a855f7', color: '#7e22ce' }}
                  >
                    <RefreshCw size={14} className={syncTemplatesMutation.isPending ? 'animate-spin' : ''} />
                    {syncTemplatesMutation.isPending ? 'Sincronizando...' : 'Sincronizar con Meta'}
                  </Button>
                </div>
              </div>

              {/* Templates Catalog Grid */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: 16 }}>
                {(templatesData?.templates || [
                  {
                    name: 'restaurantos_order_update',
                    category: 'UTILITY',
                    language: 'es_MX',
                    status: 'APPROVED',
                    registered: true,
                    description: 'Notificación transaccional de cambio de estado de pedido (Utilidad)',
                  },
                  {
                    name: 'restaurantos_reengagement_offer',
                    category: 'MARKETING',
                    language: 'es_MX',
                    status: 'APPROVED',
                    registered: true,
                    description: 'Campaña de reactivación y cupones con cláusula de Opt-Out (Marketing)',
                  },
                ]).map((tpl) => (
                  <div
                    key={tpl.name}
                    style={{
                      border: '1.5px solid #e2e8f0',
                      borderRadius: 12,
                      padding: 18,
                      background: '#f8fafc',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
                      <div>
                        <code style={{ fontSize: '0.9rem', fontWeight: 700, color: '#0f172a' }}>{tpl.name}</code>
                        <div style={{ display: 'flex', gap: 6, marginTop: 4 }}>
                          <span style={{ fontSize: '0.7rem', fontWeight: 700, background: tpl.category === 'UTILITY' ? '#dbeafe' : '#fef3c7', color: tpl.category === 'UTILITY' ? '#1e40af' : '#92400e', padding: '2px 6px', borderRadius: 4 }}>
                            {tpl.category}
                          </span>
                          <span style={{ fontSize: '0.7rem', color: '#64748b', background: '#e2e8f0', padding: '2px 6px', borderRadius: 4 }}>
                            {tpl.language}
                          </span>
                        </div>
                      </div>
                      <Badge variant={tpl.status === 'APPROVED' ? 'success' : tpl.status === 'PENDING' ? 'warning' : 'default'}>
                        {tpl.status}
                      </Badge>
                    </div>
                    <p style={{ fontSize: '0.8rem', color: '#475569', margin: '0 0 10px' }}>
                      {tpl.description}
                    </p>
                    <div style={{ fontSize: '0.75rem', color: '#64748b', background: '#fff', border: '1px solid #cbd5e1', padding: '8px 10px', borderRadius: 6, fontStyle: 'italic' }}>
                      {tpl.name === 'restaurantos_order_update'
                        ? '¡Hola {{1}}! Tu pedido #{{2}} en {{3}} ahora está: {{4}}. Sigue el estado en vivo aquí: {{5}}'
                        : '¡Hola {{1}}! En {{2}} te extrañamos. {{3}} Usa el cupón {{4}} en tu próxima compra: {{5}}. Para no recibir más promociones, responde STOP o BAJA. [Botón: STOP]'}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Uber Eats / Delivery Tabs */}
        {selectedProvider !== 'FACTURAPI' && selectedProvider !== 'WHATSAPP_BUSINESS' && activeTab === 'config' && (
          <div style={{ padding: 28 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
              <div>
                <h2 style={{ fontSize: '1.25rem', fontWeight: 700, margin: '0 0 4px', color: '#0f172a' }}>
                  Configuración de API & Webhooks ({selectedProvider})
                </h2>
                <p style={{ margin: 0, fontSize: '0.875rem', color: '#64748b' }}>
                  {isDeferredProvider
                    ? 'Guarda los datos de tu cuenta. Este proveedor queda pendiente de validación y no se conecta al guardarlo.'
                    : `Registra estas credenciales en el Developer Portal de ${selectedProvider} para recibir pedidos en vivo.`}
                </p>
              </div>
              <div style={{ display: 'flex', gap: 12 }}>
                {!isDeferredProvider && <Button
                  variant="secondary"
                  onClick={() => setTestOrderModalOpen(true)}
                  style={{ display: 'flex', alignItems: 'center', gap: 8 }}
                >
                  <Play size={16} />
                  Simular Pedido de Prueba
                </Button>}
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
            {!isDeferredProvider && <div style={{ background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 12, padding: '16px 20px', marginBottom: 24 }}>
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
            </div>}

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 20 }}>
              {!isDeferredProvider ? <div>
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
              </div> : <div style={{ color: '#92400e', fontSize: '0.875rem', paddingTop: 22 }}>
                <strong>Pendiente de validación.</strong> Guardar no habilita recepción, webhooks ni sincronización externa.
              </div>}

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
                {isDeferredProvider && formData.has_client_secret && (
                  <small style={{ color: '#64748b' }}>Secreto guardado. Déjalo vacío para conservarlo.</small>
                )}
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
                {isDeferredProvider && formData.has_webhook_secret && (
                  <small style={{ color: '#64748b' }}>Secreto guardado. Déjalo vacío para conservarlo.</small>
                )}
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
                  Vinculación de Sucursales con {selectedProvider === 'UBER_EATS' ? 'Uber Eats' : selectedProvider === 'DIDI_FOOD' ? 'DiDi Food' : selectedProvider === 'RAPPI' ? 'Rappi' : selectedProvider === 'WHATSAPP_BUSINESS' ? 'WhatsApp Business' : selectedProvider}
                </h2>
                <p style={{ margin: 0, fontSize: '0.875rem', color: '#64748b' }}>
                  Asocia el {selectedProvider === 'UBER_EATS' ? 'Store UUID' : selectedProvider === 'DIDI_FOOD' ? 'Shop ID / Store ID' : selectedProvider === 'RAPPI' ? 'Store ID de Rappi' : selectedProvider === 'WHATSAPP_BUSINESS' ? 'Phone Number ID de WhatsApp' : 'Store ID'} de cada tienda con tu sucursal en RestaurantOS.
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
                  Agrega una vinculación para que los pedidos de {selectedProvider === 'UBER_EATS' ? 'Uber' : selectedProvider === 'DIDI_FOOD' ? 'DiDi' : selectedProvider === 'RAPPI' ? 'Rappi' : selectedProvider === 'WHATSAPP_BUSINESS' ? 'WhatsApp' : 'Delivery'} se dirijan a la sucursal correcta.
                </p>
              </div>
            ) : (
              <table className="premium-table" style={{ width: '100%' }}>
                <thead>
                  <tr>
                    <th>Sucursal Local</th>
                    <th>Código</th>
                    <th>{selectedProvider === 'UBER_EATS' ? 'Store UUID Externo' : selectedProvider === 'DIDI_FOOD' ? 'Shop ID / Store ID' : selectedProvider === 'RAPPI' ? 'Store ID Rappi' : selectedProvider === 'WHATSAPP_BUSINESS' ? 'Phone Number ID de WhatsApp' : 'Store ID Externo'}</th>
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
                  Bitácora de Webhooks en Vivo ({selectedProvider === 'UBER_EATS' ? 'Uber Eats' : selectedProvider === 'DIDI_FOOD' ? 'DiDi Food' : selectedProvider === 'RAPPI' ? 'Rappi' : selectedProvider === 'WHATSAPP_BUSINESS' ? 'WhatsApp Business' : selectedProvider})
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
        title={`Vincular Sucursal con ${selectedProvider === 'UBER_EATS' ? 'Uber Eats' : selectedProvider === 'DIDI_FOOD' ? 'DiDi Food' : selectedProvider === 'RAPPI' ? 'Rappi' : selectedProvider === 'WHATSAPP_BUSINESS' ? 'WhatsApp Business' : selectedProvider}`}
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
              {selectedProvider === 'UBER_EATS' ? 'Store UUID de Uber Eats' : selectedProvider === 'DIDI_FOOD' ? 'Shop ID / Store ID de DiDi Food' : selectedProvider === 'RAPPI' ? 'Store ID de Rappi' : selectedProvider === 'WHATSAPP_BUSINESS' ? 'Phone Number ID de WhatsApp' : 'Store ID Externo'}
            </label>
            <input
              type="text"
              className="premium-input"
              placeholder={selectedProvider === 'UBER_EATS' ? 'e.g. 7c32e189-9e8a-495f-9e84-18349281a812' : selectedProvider === 'DIDI_FOOD' ? 'e.g. didi_shop_guadalajara_01' : selectedProvider === 'RAPPI' ? 'e.g. rappi_store_guadalajara_01' : selectedProvider === 'WHATSAPP_BUSINESS' ? 'e.g. 109876543210987' : 'e.g. store_id_01'}
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

      {/* Modal Meta Embedded Signup */}
      <Modal
        isOpen={embeddedSignupOpen}
        onClose={() => setEmbeddedSignupOpen(false)}
        title="Conectar WhatsApp Business (Meta Embedded Signup)"
      >
        <div style={{ padding: '8px 0' }}>
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: '#475569', marginBottom: 6 }}>
              1. Selecciona la Sucursal a Vincular
            </label>
            <select
              className="premium-input"
              value={signupBranchId}
              onChange={(e) => setSignupBranchId(e.target.value)}
            >
              <option value="">Selecciona una sucursal...</option>
              {branches.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name} ({b.code})
                </option>
              ))}
            </select>
          </div>

          {/* Alerta y formulario de Tech Provider si faltan App ID o Config ID */}
          {(!formData.client_id || !formData.config_id) && (
            <div style={{ background: '#fffbeb', border: '1.5px solid #fde68a', borderRadius: 12, padding: 14, marginBottom: 16 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                <span style={{ fontSize: 16 }}>⚠️</span>
                <strong style={{ color: '#92400e', fontSize: '0.875rem' }}>Datos de Tech Provider Requeridos</strong>
              </div>
              <p style={{ margin: '0 0 10px', fontSize: '0.8rem', color: '#78350f', lineHeight: 1.4 }}>
                Para abrir el diálogo oficial de Meta, debes ingresar el <strong>Meta App ID</strong> y el <strong>Configuration ID</strong> creados en Meta for Developers. Puedes ingresarlos aquí mismo:
              </p>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 10 }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: '#78350f', marginBottom: 4 }}>
                    Meta App ID:
                  </label>
                  <input
                    type="text"
                    className="premium-input"
                    placeholder="e.g. 192837465019283"
                    value={formData.client_id ?? ''}
                    onChange={(e) => setFormData({ ...formData, client_id: e.target.value })}
                    style={{ fontSize: '0.8rem', padding: '6px 10px' }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: '#78350f', marginBottom: 4 }}>
                    Configuration ID:
                  </label>
                  <input
                    type="text"
                    className="premium-input"
                    placeholder="e.g. 102938475610293"
                    value={formData.config_id ?? ''}
                    onChange={(e) => setFormData({ ...formData, config_id: e.target.value })}
                    style={{ fontSize: '0.8rem', padding: '6px 10px' }}
                  />
                </div>
              </div>
              <Button
                variant="secondary"
                disabled={saveConfigMutation.isPending || !formData.client_id || !formData.config_id}
                onClick={() => saveConfigMutation.mutate(formData)}
                style={{ fontSize: '0.75rem', padding: '6px 12px', background: '#fff', borderColor: '#d97706', color: '#92400e', fontWeight: 600 }}
              >
                {saveConfigMutation.isPending ? 'Guardando...' : '💾 Guardar Tech Provider'}
              </Button>
            </div>
          )}

          {/* Tarjeta de Inicio de Popup Meta SDK */}
          <div style={{ background: '#eff6ff', border: '1.5px solid #bfdbfe', borderRadius: 12, padding: 18, marginBottom: 20 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
              <div style={{ width: 32, height: 32, borderRadius: 8, background: '#dbeafe', color: '#1d4ed8', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Zap size={18} />
              </div>
              <div>
                <strong style={{ color: '#1e40af', fontSize: '0.95rem' }}>Conexión Oficial con Meta (Popup Nativo)</strong>
                <p style={{ margin: 0, fontSize: '0.75rem', color: '#3b82f6' }}>Flujo interactivo con SDK oficial de Facebook</p>
              </div>
            </div>
            <p style={{ margin: '0 0 14px', fontSize: '0.8125rem', color: '#334155', lineHeight: 1.4 }}>
              Abre el diálogo emergente oficial de Meta para iniciar sesión con tu cuenta de Facebook, seleccionar tu cuenta de WhatsApp Business (WABA) y verificar tu número sin copiar códigos.
            </p>
            <Button
              variant="primary"
              onClick={handleLaunchMetaPopup}
              disabled={isLaunchingFb || !signupBranchId || !formData.client_id || !formData.config_id}
              style={{ background: '#2563eb', borderColor: '#1d4ed8', width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, fontWeight: 700, padding: '10px 16px', opacity: (!formData.client_id || !formData.config_id) ? 0.6 : 1 }}
            >
              <Zap size={16} />
              {isLaunchingFb ? 'Abriendo Meta Login...' : '🚀 Iniciar Conexión Oficial con Meta (Popup)'}
            </Button>
            {!signupBranchId ? (
              <small style={{ color: '#ef4444', display: 'block', marginTop: 6, fontSize: '0.75rem' }}>
                * Selecciona primero la sucursal arriba para habilitar el botón.
              </small>
            ) : (!formData.client_id || !formData.config_id) ? (
              <small style={{ color: '#d97706', display: 'block', marginTop: 6, fontSize: '0.75rem' }}>
                * Guarda primero el Meta App ID y Configuration ID de Tech Provider arriba para abrir el popup.
              </small>
            ) : null}
          </div>

          <div style={{ marginBottom: 16 }}>
            <button
              type="button"
              onClick={() => setShowManualSignup(!showManualSignup)}
              style={{ background: 'none', border: 'none', color: '#64748b', fontSize: '0.8125rem', cursor: 'pointer', textDecoration: 'underline', padding: 0 }}
            >
              {showManualSignup ? '▲ Ocultar campos de credenciales manuales' : '▼ ¿Deseas verificar o ingresar los datos manualmente? (Modo Desarrollador)'}
            </button>
          </div>

          {(showManualSignup || signupCode || signupPhoneNumberId) && (
            <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 10, padding: 14, marginBottom: 16 }}>
              <div style={{ marginBottom: 14 }}>
                <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: '#475569', marginBottom: 6 }}>
                  Meta Authorization Code (OAuth Code)
                </label>
                <input
                  type="text"
                  className="premium-input"
                  placeholder="AQD... (Capturado automáticamente o devuelto por Meta login)"
                  value={signupCode}
                  onChange={(e) => setSignupCode(e.target.value)}
                />
              </div>

              <div style={{ marginBottom: 14 }}>
                <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: '#475569', marginBottom: 6 }}>
                  WhatsApp Business Account ID (WABA ID)
                </label>
                <input
                  type="text"
                  className="premium-input"
                  placeholder="e.g. 104928374829102"
                  value={signupWabaId}
                  onChange={(e) => setSignupWabaId(e.target.value)}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: '#475569', marginBottom: 6 }}>
                  Phone Number ID de WhatsApp
                </label>
                <input
                  type="text"
                  className="premium-input"
                  placeholder="e.g. 109876543210987"
                  value={signupPhoneNumberId}
                  onChange={(e) => setSignupPhoneNumberId(e.target.value)}
                />
              </div>
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12 }}>
            <Button variant="secondary" onClick={() => setEmbeddedSignupOpen(false)}>
              Cancelar
            </Button>
            <Button
              variant="primary"
              disabled={!signupBranchId || !signupCode || !signupPhoneNumberId || exchangeEmbeddedSignupMutation.isPending}
              onClick={() =>
                exchangeEmbeddedSignupMutation.mutate({
                  branch_id: signupBranchId,
                  code: signupCode,
                  waba_id: signupWabaId,
                  phone_number_id: signupPhoneNumberId,
                })
              }
              style={{ background: '#16a34a', borderColor: '#15803d' }}
            >
              {exchangeEmbeddedSignupMutation.isPending ? 'Vinculando...' : 'Completar Conexión'}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
