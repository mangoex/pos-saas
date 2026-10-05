import { useEffect, useState } from 'react';
import { fetchApi } from '@restaurantos/api-client';
import { SubscriptionCheckout } from '../../../../../packages/ui/src/components/SubscriptionCheckout';
import { SUBSCRIPTION_PLANS, PLAN_NAMES, findPlanCatalogItem } from './subscriptionPlans';

type Subscription = { plan: string; subscription_status: string; trial_ends_at: string | null; access_block_reason: string | null; user_email?: string };

export default function SubscriptionStatus() {
  const [state, setState] = useState<Subscription | null>(null);
  const [error, setError] = useState('');
  const [showCheckout, setShowCheckout] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [selectedPlanCode, setSelectedPlanCode] = useState('starter_349');

  const load = () => { setError(''); void fetchApi<Subscription>('/subscription/status').then(setState).catch(() => setError('No pudimos consultar el estado. Inténtalo de nuevo.')); };
  useEffect(load, []);

  const handleTokenGenerated = async (tokenId: string, formData: any) => {
    setIsProcessing(true);
    try {
      await fetchApi('/api/subscriptions', {
        method: 'POST',
        body: JSON.stringify({
          package_name: selectedPlanCode === 'starter_349' ? 'esencial' : selectedPlanCode,
          card_token: tokenId,
          user_email: state?.user_email || formData.payer?.email || 'admin@restaurant.com'
        })
      });
      setShowCheckout(false);
      load();
    } catch (err) {
      setError('Error al procesar la suscripción. Inténtalo de nuevo.');
    } finally {
      setIsProcessing(false);
    }
  };

  const selectedPlan = findPlanCatalogItem(selectedPlanCode);

  return <main style={{ maxWidth: 560, margin: '64px auto', padding: 24 }}>
    <h1>Estado de suscripción</h1>
    {!state ? <><p role={error ? 'alert' : undefined}>{error || 'Consultando estado…'}</p><button onClick={load}>Actualizar estado</button></> : <>
      <p>Plan actual: <strong>{PLAN_NAMES[state.plan] || state.plan}</strong></p>
      <p>Estado: <strong>{state.access_block_reason === 'tenant_trial_expired' ? 'Prueba vencida' : state.subscription_status}</strong></p>
      {state.trial_ends_at && <p>Fin de prueba: {new Date(state.trial_ends_at).toLocaleString()}</p>}
      
      {(state.access_block_reason === 'tenant_trial_expired' || state.subscription_status === 'PAST_DUE' || state.subscription_status === 'TRIAL') && !showCheckout && (
        <div style={{ marginTop: '24px' }}>
          <p>Consulta las opciones de suscripción (Esencial, Conecta o Control) para continuar usando la plataforma.</p>
          <button onClick={() => setShowCheckout(true)}>Consultar opciones de pago</button>
        </div>
      )}

      {showCheckout && (
        <div style={{ marginTop: '24px', backgroundColor: '#ffffff', padding: 16, borderRadius: 16, border: '1px solid #e2e8f0' }}>
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: 'block', fontWeight: 700, marginBottom: 8, fontSize: '0.95rem', color: '#1e293b' }}>
              Plan de suscripción
              <select
                aria-label="Plan de suscripción"
                value={selectedPlanCode}
                onChange={(e) => setSelectedPlanCode(e.target.value)}
                style={{
                  display: 'block',
                  width: '100%',
                  padding: '12px 14px',
                  borderRadius: 10,
                  border: '1.5px solid #cbd5e1',
                  backgroundColor: '#f8fafc',
                  fontSize: '1rem',
                  fontWeight: 600,
                  color: '#0f172a',
                  marginTop: 6,
                }}
              >
                {SUBSCRIPTION_PLANS.map((item) => (
                  <option key={item.code} value={item.code}>
                    {item.name} — {item.priceFormatted}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {selectedPlan && (
            <div
              data-testid="selected-plan-details"
              style={{
                backgroundColor: '#f8fafc',
                border: '1px solid #e2e8f0',
                borderRadius: 12,
                padding: '16px',
                marginBottom: 16,
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 8 }}>
                <strong style={{ fontSize: '1.1rem', color: '#0f172a' }}>
                  Plan {selectedPlan.name}
                </strong>
                <span style={{ fontWeight: 800, fontSize: '1.05rem', color: '#0284c7' }}>
                  {selectedPlan.priceFormatted}
                </span>
              </div>
              <p style={{ margin: 0, fontSize: '0.875rem', color: '#475569', lineHeight: 1.5 }}>
                {selectedPlan.features}
              </p>
            </div>
          )}

          {selectedPlan?.checkoutUrl ? (
            <div style={{ marginBottom: 16 }}>
              <a
                href={selectedPlan.checkoutUrl}
                target="_blank"
                rel="noopener noreferrer"
                data-testid="mp-checkout-link"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 8,
                  width: '100%',
                  padding: '14px 16px',
                  backgroundColor: '#009ee3',
                  color: '#ffffff',
                  borderRadius: 12,
                  fontSize: '1rem',
                  fontWeight: 800,
                  textDecoration: 'none',
                  boxShadow: '0 4px 6px -1px rgba(0, 158, 227, 0.25)',
                  boxSizing: 'border-box',
                }}
              >
                <span>Pagar con Mercado Pago ({selectedPlan.priceFormatted})</span>
                <span aria-hidden="true">→</span>
              </a>
              <p style={{ margin: '8px 0 0', fontSize: '0.75rem', color: '#64748b', textAlign: 'center' }}>
                Pago recurrente seguro procesado directamente en Mercado Pago.
              </p>
            </div>
          ) : (
            <>
              <SubscriptionCheckout
                onTokenGenerated={handleTokenGenerated}
                onError={(err) => setError('Error en el checkout: ' + err.message)}
              />
              {isProcessing && <p>Procesando pago...</p>}
            </>
          )}

          <button style={{ marginTop: '16px' }} onClick={() => setShowCheckout(false)}>Cancelar</button>
        </div>
      )}

      {!showCheckout && <button style={{ marginTop: '16px' }} onClick={load}>Actualizar estado</button>}
    </>}
  </main>;
}
