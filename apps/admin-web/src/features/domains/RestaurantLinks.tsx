import React, { useEffect, useState } from 'react';
import { fetchApi } from '@restaurantos/api-client';
import { QRCodeCard } from '../onboarding/QRCodeCard';
import './RestaurantLinks.css';

type Domain = {
  id: string; hostname: string; status: 'pending_dns' | 'pending_tls' | 'active' | 'disabled';
  last_result: string | null; txt_name: string; txt_value: string; cname_target: string;
  organization_name?: string; organization_slug?: string; organization_preferred_slug?: string;
  organization_id?: string;
};
type Links = {
  name: string; canonical_slug: string; preferred_slug: string;
  links: Record<'admin' | 'pos' | 'kds' | 'menu', string>;
  canonical_menu_url: string; domains: Domain[]; domain_routing_enabled: boolean;
};
type TenantOverview = {
  organization_id: string;
  organization_name: string;
  canonical_slug: string;
  preferred_slug: string;
  menu_url: string;
  domains: Domain[];
  active_domain: string | null;
  domain_status: string;
};
const labels = { admin: 'Administración', pos: 'Punto de venta', kds: 'Cocina', menu: 'Menú y pedidos' };
const states = { pending_dns: 'Pendiente de DNS', pending_tls: 'Pendiente de HTTPS', active: 'Activo', disabled: 'Desactivado' };

export default function RestaurantLinks({ supervision = false }: { supervision?: boolean }) {
  const [data, setData] = useState<Links | null>(null);
  const [domains, setDomains] = useState<Domain[]>([]);
  const [tenants, setTenants] = useState<TenantOverview[]>([]);
  const [selectedTenantId, setSelectedTenantId] = useState('');
  const [assignHostname, setAssignHostname] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [alias, setAlias] = useState('');
  const [hostname, setHostname] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [confirmed, setConfirmed] = useState<Record<string, boolean>>({});

  async function reload() {
    if (supervision) {
      const [domList, tenList] = await Promise.all([
        fetchApi<Domain[]>('/saas/domains/supervision'),
        fetchApi<TenantOverview[]>('/saas/domains/supervision/tenants').catch(() => []),
      ]);
      setDomains(domList);
      setTenants(tenList);
      if (tenList.length > 0 && !selectedTenantId) {
        setSelectedTenantId(tenList[0].organization_id);
      }
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

  const filteredTenants = tenants.filter(t =>
    t.organization_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    t.canonical_slug.toLowerCase().includes(searchTerm.toLowerCase()) ||
    (t.active_domain && t.active_domain.toLowerCase().includes(searchTerm.toLowerCase()))
  );

  return <main className="restaurant-links">
    <header><span className="links-eyebrow">{supervision ? 'Superadministración' : 'Tu restaurante en línea'}</span>
      <h1>{supervision ? 'Dominios y Enlaces de Clientes' : 'Enlaces y dominio'}</h1>
      <p>{supervision ? 'Supervisa los enlaces de menú de tus clientes y gestiona la activación de sus dominios propios.' : 'Comparte tu menú y encuentra los accesos para tu equipo.'}</p>
    </header>
    {error && <div className="links-error" role="alert">{error} <button disabled={busy} onClick={() => void run(reload)}>Volver a cargar</button></div>}
    {notice && <p role="status" className="links-notice">{notice}</p>}
    {busy && <p role="status">Procesando…</p>}

    {supervision && <>
      <section className="links-panel">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12, marginBottom: 16 }}>
          <div>
            <h2>Todos los Restaurantes y sus Enlaces</h2>
            <p style={{ margin: 0 }}>Consulta los accesos públicos y el estado de dominios configurados por tus clientes.</p>
          </div>
          <input
            type="search"
            placeholder="Buscar por restaurante o dominio..."
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
            style={{ padding: '8px 12px', borderRadius: 8, border: '1px solid #cbd5e1', fontSize: '0.875rem', minWidth: 260 }}
          />
        </div>

        {tenants.length === 0 && !busy ? (
          <p>No se encontraron restaurantes registrados.</p>
        ) : (
          <div className="links-table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Restaurante</th>
                  <th>Menú Web (Subdominio / Ruta)</th>
                  <th>Dominio Propio</th>
                  <th>Estado</th>
                  <th>Acción</th>
                </tr>
              </thead>
              <tbody>
                {filteredTenants.map(t => (
                  <tr key={t.organization_id}>
                    <td>
                      <strong>{t.organization_name}</strong>
                      <div style={{ fontSize: '0.75rem', color: '#64748b' }}>slug: {t.preferred_slug || t.canonical_slug}</div>
                    </td>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <a href={t.menu_url} target="_blank" rel="noopener noreferrer">{t.menu_url}</a>
                        <button
                          type="button"
                          onClick={() => void copy(t.menu_url)}
                          style={{ padding: '4px 8px', fontSize: '0.75rem' }}
                          title="Copiar enlace"
                        >
                          Copiar
                        </button>
                      </div>
                    </td>
                    <td>
                      {t.active_domain ? (
                        <strong>{t.active_domain}</strong>
                      ) : t.domains.length > 0 ? (
                        <span>{t.domains[0].hostname}</span>
                      ) : (
                        <span style={{ color: '#94a3b8' }}>Sin dominio propio</span>
                      )}
                    </td>
                    <td>
                      {t.active_domain ? (
                        <span className="domain-state active">Activo</span>
                      ) : t.domains.length > 0 ? (
                        <span className={`domain-state ${t.domains[0].status}`}>
                          {states[t.domains[0].status] || t.domains[0].status}
                        </span>
                      ) : (
                        <span style={{ color: '#94a3b8', fontSize: '0.85rem' }}>Subdominio estándar</span>
                      )}
                    </td>
                    <td>
                      <button
                        type="button"
                        className="links-secondary"
                        style={{ padding: '6px 10px', fontSize: '0.8rem' }}
                        onClick={() => {
                          setSelectedTenantId(t.organization_id);
                          const el = document.getElementById('assign-domain-form');
                          if (el) el.scrollIntoView({ behavior: 'smooth' });
                        }}
                      >
                        Asignar dominio
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="links-panel" id="assign-domain-form">
        <h2>Conectar o Asignar Dominio Propio a un Cliente</h2>
        <p>Registra un dominio personalizado (ej. <code>pedidos.elrestaurante.com</code>) directamente para un restaurante.</p>
        <form onSubmit={event => {
          event.preventDefault();
          if (!selectedTenantId || !assignHostname) return;
          void run(async () => {
            await fetchApi('/saas/domains/supervision/assign', {
              method: 'POST',
              body: JSON.stringify({ organization_id: selectedTenantId, hostname: assignHostname }),
            });
            setAssignHostname('');
            await reload();
            setNotice('Dominio registrado exitosamente para el cliente. Ahora configura los registros DNS y confirma HTTPS.');
          });
        }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 12, marginBottom: 12 }}>
            <div>
              <label htmlFor="assign-tenant" style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: 4 }}>
                Seleccionar Restaurante
              </label>
              <select
                id="assign-tenant"
                value={selectedTenantId}
                onChange={e => setSelectedTenantId(e.target.value)}
                style={{ width: '100%', padding: 11, borderRadius: 7, border: '1px solid #acbdb3', fontSize: '0.9rem', background: '#ffffff' }}
                required
              >
                {tenants.map(t => (
                  <option key={t.organization_id} value={t.organization_id}>
                    {t.organization_name} ({t.preferred_slug || t.canonical_slug})
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="assign-hostname" style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: 4 }}>
                Dominio o subdominio personalizado
              </label>
              <input
                id="assign-hostname"
                type="text"
                placeholder="pedidos.turestaurante.com"
                value={assignHostname}
                onChange={e => setAssignHostname(e.target.value)}
                style={{ width: '100%', boxSizing: 'border-box', padding: 11, borderRadius: 7, border: '1px solid #acbdb3', fontSize: '0.9rem' }}
                required
              />
            </div>
          </div>
          <button disabled={busy || !assignHostname.trim()} style={{ marginTop: 4 }}>
            Registrar Dominio para Cliente
          </button>
        </form>
      </section>
    </>}

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
      {supervision && <h2>Solicitudes y Dominios Registrados</h2>}
      {supervision && !busy && !error && domains.length === 0 && <p>No hay solicitudes de dominio registradas aún.</p>}
      {domains.map(domain => <article className="links-panel" key={domain.id}>
        <div className="links-domain-heading">
          <h2>{domain.hostname}</h2>
          <span className={`domain-state ${domain.status}`}>{states[domain.status]}</span>
          {supervision && domain.organization_name && (
            <span style={{ fontSize: '0.875rem', fontWeight: 600, color: '#047857', backgroundColor: '#ecfdf5', padding: '4px 10px', borderRadius: 8 }}>
              Cliente: {domain.organization_name}
            </span>
          )}
        </div>

        <p>Agrega estos registros en el proveedor de tu dominio. El nombre TXT completo es distinto al CNAME.</p>
        <div className="links-table-scroll"><table><thead><tr><th>Tipo</th><th>Nombre completo</th><th>Valor</th></tr></thead><tbody>
          <tr><td>CNAME</td><td>{domain.hostname}</td><td>{domain.cname_target}</td></tr>
          <tr><td>TXT</td><td>{domain.txt_name}</td><td>{domain.txt_value}</td></tr>
        </tbody></table></div>

        {!supervision && <>
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
          <button
            type="button"
            className="links-secondary"
            disabled={busy}
            style={{ color: '#ef4444' }}
            onClick={() => {
              if (window.confirm(`¿Estás seguro de eliminar la configuración del dominio ${domain.hostname}?`)) {
                void run(async () => {
                  await fetchApi(`/saas/domains/${domain.id}/supervise`, { method: 'POST', body: JSON.stringify({ action: 'delete' }) });
                  await reload();
                  setNotice('Dominio eliminado.');
                });
              }
            }}
          >
            Eliminar
          </button>
        </div>}
      </article>)}
    </section>
  </main>;
}
