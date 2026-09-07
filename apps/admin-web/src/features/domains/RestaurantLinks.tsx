import React, { useEffect, useState } from 'react';
import { fetchApi } from '@restaurantos/api-client';
import { QRCodeCard } from '../onboarding/QRCodeCard';
import './RestaurantLinks.css';

type Domain = {
  id: string; hostname: string; status: 'pending_dns' | 'pending_tls' | 'active' | 'disabled';
  last_result: string | null; txt_name: string; txt_value: string; cname_target: string;
};
type Links = {
  name: string; canonical_slug: string; preferred_slug: string;
  links: Record<'admin' | 'pos' | 'kds' | 'menu', string>;
  canonical_menu_url: string; domains: Domain[]; domain_routing_enabled: boolean;
};
const labels = { admin: 'Administración', pos: 'Punto de venta', kds: 'Cocina', menu: 'Menú y pedidos' };
const states = { pending_dns: 'Pendiente de DNS', pending_tls: 'Pendiente de HTTPS', active: 'Activo', disabled: 'Desactivado' };

export default function RestaurantLinks({ supervision = false }: { supervision?: boolean }) {
  const [data, setData] = useState<Links | null>(null);
  const [domains, setDomains] = useState<Domain[]>([]);
  const [alias, setAlias] = useState('');
  const [hostname, setHostname] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [confirmed, setConfirmed] = useState<Record<string, boolean>>({});

  async function reload() {
    if (supervision) {
      setDomains(await fetchApi<Domain[]>('/saas/domains/supervision'));
    } else {
      const result = await fetchApi<Links>('/saas/links');
      setData(result); setAlias(result.preferred_slug); setDomains(result.domains);
    }
  }
  async function run(action: () => Promise<void>) {
    setBusy(true); setError(''); setNotice('');
    try { await action(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'No se pudo completar la operación. Intenta nuevamente.'); }
    finally { setBusy(false); }
  }
  useEffect(() => { void run(reload); }, [supervision]);

  async function copy(value: string) {
    try { await navigator.clipboard.writeText(value); setNotice('Enlace copiado.'); }
    catch { setError('No se pudo copiar. Puedes seleccionar el enlace y copiarlo manualmente.'); }
  }

  return <main className="restaurant-links">
    <header><span className="links-eyebrow">{supervision ? 'Superadministración' : 'Tu restaurante en línea'}</span>
      <h1>{supervision ? 'Activación de dominios' : 'Enlaces y dominio'}</h1>
      <p>{supervision ? 'Verifica la configuración del dominio antes de habilitarlo.' : 'Comparte tu menú y encuentra los accesos para tu equipo.'}</p>
    </header>
    {error && <div className="links-error" role="alert">{error} <button disabled={busy} onClick={() => void run(reload)}>Volver a cargar</button></div>}
    {notice && <p role="status" className="links-notice">{notice}</p>}
    {busy && <p role="status">Procesando…</p>}
    {data && !supervision && <>
      <section className="links-panel"><h2>{data.name}</h2>
        <p>Admin, POS y Cocina requieren una cuenta autorizada de tu restaurante.</p>
        <div className="links-grid">{(Object.keys(labels) as Array<keyof typeof labels>).map(key =>
          <article className="link-card" key={key}><h3>{labels[key]}</h3>
            <a href={data.links[key]} target="_blank" rel="noopener noreferrer">{data.links[key]}</a>
            <button type="button" onClick={() => void copy(data.links[key])}>Copiar enlace de {labels[key]}</button>
          </article>)}</div>
      </section>
      <section className="links-panel"><h2>Nombre de tu enlace público</h2>
        <p>Usa letras minúsculas, números y guiones. Tus enlaces anteriores seguirán funcionando.</p>
        <form onSubmit={event => { event.preventDefault(); void run(async () => {
          await fetchApi('/saas/links/alias', { method: 'PUT', body: JSON.stringify({ alias }) });
          await reload(); setNotice('Enlace actualizado. Los enlaces anteriores se conservan.');
        }); }}><label htmlFor="restaurant-alias">Nombre personalizado</label>
          <div className="links-form-row"><input id="restaurant-alias" value={alias} onChange={event => setAlias(event.target.value)}
            required minLength={3} maxLength={80} pattern="[a-z0-9]+(-[a-z0-9]+)*" placeholder="tacos-el-guero" />
          <button disabled={busy}>Guardar nombre</button></div>
        </form>
        <p>Enlace permanente: <a href={data.canonical_menu_url}>{data.canonical_menu_url}</a></p>
      </section>
      <QRCodeCard restaurantName={data.name} restaurantSlug={data.canonical_slug} fullUrl={data.links.menu} />
      <section className="links-panel"><h2>Conectar tu dominio</h2>
        <p>Por ejemplo, pedidos.turestaurante.com. Puedes conservar tu sitio principal.</p>
        <form onSubmit={event => { event.preventDefault(); void run(async () => {
          await fetchApi('/saas/domains', { method: 'POST', body: JSON.stringify({ hostname }) });
          setHostname(''); await reload(); setNotice('Solicitud guardada. Configura los registros DNS indicados.');
        }); }}><label htmlFor="restaurant-domain">Dominio o subdominio</label>
          <div className="links-form-row"><input id="restaurant-domain" value={hostname} onChange={event => setHostname(event.target.value)}
            required maxLength={253} placeholder="pedidos.turestaurante.com" autoCapitalize="none" />
          <button disabled={busy}>Solicitar dominio</button></div>
        </form>
        <p>Después de verificar DNS, el equipo de la plataforma configurará HTTPS y activará tu dominio.</p>
      </section>
    </>}
    <section aria-label="Dominios registrados">
      {supervision && !busy && !error && domains.length === 0 && <p>No hay solicitudes de dominio.</p>}
      {domains.map(domain => <article className="links-panel" key={domain.id}>
        <div className="links-domain-heading"><h2>{domain.hostname}</h2><span className={`domain-state ${domain.status}`}>{states[domain.status]}</span></div>
        {!supervision && <>
          <p>Agrega estos registros en el proveedor de tu dominio. El nombre TXT completo es distinto al CNAME.</p>
          <div className="links-table-scroll"><table><thead><tr><th>Tipo</th><th>Nombre completo</th><th>Valor</th></tr></thead><tbody>
            <tr><td>CNAME</td><td>{domain.hostname}</td><td>{domain.cname_target}</td></tr>
            <tr><td>TXT</td><td>{domain.txt_name}</td><td>{domain.txt_value}</td></tr>
          </tbody></table></div>
          <p>Para un dominio raíz, solicita al equipo la IP para un registro A o confirma que tu proveedor admite CNAME en la raíz.</p>
          <button disabled={busy || domain.status === 'disabled'} onClick={() => void run(async () => {
            const result = await fetchApi<Domain>(`/saas/domains/${domain.id}/verify`, { method: 'POST' });
            await reload(); setNotice(result.last_result === 'dns_verified'
              ? 'Propiedad verificada. La activación requiere HTTPS y revisión de la plataforma.'
              : 'No se pudo verificar el TXT. Revisa el registro o espera la propagación y vuelve a intentar.');
          })}>Verificar DNS</button>
        </>}
        {domain.last_result && <p>Última verificación: {({ dns_verified: 'TXT correcto', dns_mismatch: 'TXT no encontrado o diferente', dns_unavailable: 'Servicio DNS no disponible' } as Record<string, string>)[domain.last_result] || domain.last_result}</p>}
        {supervision && <div className="links-supervision">
          <label><input type="checkbox" checked={confirmed[domain.id] || false} onChange={event => setConfirmed({ ...confirmed, [domain.id]: event.target.checked })} /> Confirmé el dominio en EasyPanel, destino pos-saas:8000 y certificado HTTPS válido.</label>
          <button disabled={busy || !confirmed[domain.id] || domain.status === 'active'} onClick={() => void run(async () => {
            await fetchApi(`/saas/domains/${domain.id}/supervise`, { method: 'POST', body: JSON.stringify({ action: 'activate', tls_confirmed: true }) });
            await reload(); setNotice('Dominio activado.');
          })}>Revalidar DNS y activar</button>
          <button className="links-secondary" disabled={busy || domain.status === 'disabled'} onClick={() => void run(async () => {
            await fetchApi(`/saas/domains/${domain.id}/supervise`, { method: 'POST', body: JSON.stringify({ action: 'disable' }) });
            await reload(); setNotice('Dominio desactivado. Su reserva e historial se conservan.');
          })}>Desactivar</button>
        </div>}
      </article>)}
    </section>
  </main>;
}
