import { useEffect, useState } from 'react';
import { fetchApi } from '@restaurantos/api-client';
import { SubscriptionCheckout } from '../../../../../packages/ui/src/components/SubscriptionCheckout';

type Subscription = { plan: string; subscription_status: string; trial_ends_at: string | null; access_block_reason: string | null; user_email?: string };

export default function SubscriptionStatus() {
  const [state, setState] = useState<Subscription | null>(null);
  const [error, setError] = useState('');
  const [showCheckout, setShowCheckout] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);

  const load = () => { setError(''); void fetchApi<Subscription>('/subscription/status').then(setState).catch(() => setError('No pudimos consultar el estado. Inténtalo de nuevo.')); };
  useEffect(load, []);

  const handleTokenGenerated = async (tokenId: string, formData: any) => {
    setIsProcessing(true);
    try {
      await fetchApi('/api/subscriptions', {
        method: 'POST',
        body: JSON.stringify({
          package_name: 'lite',
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

  return <main style={{ maxWidth: 560, margin: '64px auto', padding: 24 }}>
    <h1>Estado de suscripción</h1>
    {!state ? <><p role={error ? 'alert' : undefined}>{error || 'Consultando estado…'}</p><button onClick={load}>Actualizar estado</button></> : <>
      <p>Plan actual: <strong>{state.plan}</strong></p>
      <p>Estado: <strong>{state.access_block_reason === 'tenant_trial_expired' ? 'Prueba vencida' : state.subscription_status}</strong></p>
      {state.trial_ends_at && <p>Fin de prueba: {new Date(state.trial_ends_at).toLocaleString()}</p>}
      
      {(state.access_block_reason === 'tenant_trial_expired' || state.subscription_status === 'PAST_DUE' || state.subscription_status === 'TRIAL') && !showCheckout && (
        <div style={{ marginTop: '24px' }}>
          <p>Adquiere el paquete Lite por $349 MXN/mes para continuar usando la plataforma.</p>
          <button onClick={() => setShowCheckout(true)}>Pagar ahora</button>
        </div>
      )}

      {showCheckout && (
        <div style={{ marginTop: '24px' }}>
          <SubscriptionCheckout 
            onTokenGenerated={handleTokenGenerated} 
            onError={(err) => setError('Error en el checkout: ' + err.message)} 
          />
          {isProcessing && <p>Procesando pago...</p>}
          <button style={{ marginTop: '16px' }} onClick={() => setShowCheckout(false)}>Cancelar</button>
        </div>
      )}

      {!showCheckout && <button style={{ marginTop: '16px' }} onClick={load}>Actualizar estado</button>}
    </>}
  </main>;
}
