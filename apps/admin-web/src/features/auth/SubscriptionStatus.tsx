import { useEffect, useState } from 'react';
import { fetchApi } from '@restaurantos/api-client';

type Subscription = { plan: string; subscription_status: string; trial_ends_at: string | null; access_block_reason: string | null };

export default function SubscriptionStatus() {
  const [state, setState] = useState<Subscription | null>(null);
  const [error, setError] = useState('');
  const load = () => { setError(''); void fetchApi<Subscription>('/subscription/status').then(setState).catch(() => setError('No pudimos consultar el estado. Inténtalo de nuevo.')); };
  useEffect(load, []);
  return <main style={{ maxWidth: 560, margin: '64px auto', padding: 24 }}>
    <h1>Estado de suscripción</h1>
    {!state ? <><p role={error ? 'alert' : undefined}>{error || 'Consultando estado…'}</p><button onClick={load}>Actualizar estado</button></> : <>
      <p>Plan seleccionado: <strong>{state.plan}</strong></p>
      <p>Estado: <strong>{state.access_block_reason === 'tenant_trial_expired' ? 'Prueba vencida' : state.subscription_status}</strong></p>
      {state.trial_ends_at && <p>Fin de prueba: {new Date(state.trial_ends_at).toLocaleString()}</p>}
      <p>La renovación es administrada por la plataforma. Cuando se active el plan, vuelve a consultar este estado.</p>
      <button onClick={load}>Actualizar estado</button>
    </>}
  </main>;
}
