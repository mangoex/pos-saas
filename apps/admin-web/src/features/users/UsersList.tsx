import React, { useMemo, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Button, Badge, Modal, Input } from '@restaurantos/ui';
import { ApiError, fetchApi } from '@restaurantos/api-client';
import { Plus, Users, Edit, Trash2, ShieldCheck } from 'lucide-react';

interface User {
  id: string;
  display_name: string;
  email: string;
  employee_code: string | null;
  status: string;
  roles?: {
    role_id: string;
    role_name: string;
    scope?: string;
    branch_id?: string | null;
    branch_name?: string | null;
  }[];
}

interface Role {
  id: string;
  name: string;
  scope: string;
  permissions?: string[];
}

const CANONICAL_ROLES_META: Record<string, { rank: number; label: string; desc: string }> = {
  'cajero': { rank: 1, label: 'Cajero', desc: 'Operación POS, órdenes, cobros y retiros menores autorizados' },
  'cajero jefe': { rank: 2, label: 'Cajero Jefe', desc: 'Apertura/cierre turnos, arqueos, depósitos, compras locales y mermas' },
  'líder': { rank: 3, label: 'Líder', desc: 'Cortes por usuario (X/Z), cancelaciones de pedidos autorizados' },
  'lider': { rank: 3, label: 'Líder', desc: 'Cortes por usuario (X/Z), cancelaciones de pedidos autorizados' },
  'supervisor': { rank: 4, label: 'Supervisor', desc: 'Gestión de recetas, inventario/kardex, reportes de insumos y mermas' },
  'administrador de restaurante': { rank: 5, label: 'Administrador de Restaurante', desc: 'Control total del restaurante, sucursales, colaboradores y reportes' },
  'administrador': { rank: 5, label: 'Administrador de Restaurante', desc: 'Control total del restaurante, sucursales, colaboradores y reportes' },
  'dueño': { rank: 5, label: 'Administrador de Restaurante', desc: 'Control total del restaurante, sucursales, colaboradores y reportes' },
  'dueno': { rank: 5, label: 'Administrador de Restaurante', desc: 'Control total del restaurante, sucursales, colaboradores y reportes' },
  'owner': { rank: 5, label: 'Administrador de Restaurante', desc: 'Control total del restaurante, sucursales, colaboradores y reportes' },
};

const UsersList = () => {
  const queryClient = useQueryClient();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const [formData, setFormData] = useState({ display_name: '', email: '', employee_code: '', password: '', role_id: '', branch_id: '' });
  const [formError, setFormError] = useState('');

  const { data: users, isLoading, error } = useQuery<User[]>({
    queryKey: ['users'],
    queryFn: () => fetchApi('/users'),
  });

  const { data: rawRoles } = useQuery<Role[]>({
    queryKey: ['roles'],
    queryFn: () => fetchApi('/roles'),
  });

  const { data: branches } = useQuery<any[]>({
    queryKey: ['branches'],
    queryFn: () => fetchApi('/branches'),
  });

  // Filter and sort strictly the 6 official canonical roles
  const canonicalRoles = useMemo(() => {
    if (!rawRoles) return [];
    return rawRoles
      .filter((r) => {
        const norm = r.name.trim().toLowerCase();
        return norm in CANONICAL_ROLES_META;
      })
      .sort((a, b) => {
        const rankA = CANONICAL_ROLES_META[a.name.trim().toLowerCase()]?.rank || 99;
        const rankB = CANONICAL_ROLES_META[b.name.trim().toLowerCase()]?.rank || 99;
        return rankA - rankB;
      });
  }, [rawRoles]);

  const selectedRole = rawRoles?.find((role) => role.id === formData.role_id);
  const selectedRoleMeta = selectedRole ? CANONICAL_ROLES_META[selectedRole.name.trim().toLowerCase()] : null;
  const requiresBranch = selectedRole?.scope === 'branch';

  const saveMutation = useMutation({
    mutationFn: (data: typeof formData) => {
      const payload = {
        ...data,
        branch_id: requiresBranch ? data.branch_id : null,
      };
      if (editingUser) {
        return fetchApi(`/users/${editingUser.id}`, {
          method: 'PUT',
          body: JSON.stringify(payload),
        });
      }
      return fetchApi('/users', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
      setIsModalOpen(false);
      setFormError('');
    },
    onError: (reason) => setFormError(
      reason instanceof ApiError ? reason.message : 'No fue posible guardar el usuario.',
    ),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => fetchApi(`/users/${id}`, { method: 'DELETE' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['users'] })
  });

  const openModal = (user?: User) => {
    const primaryRole = user?.roles && user.roles.length > 0 ? user.roles[0] : null;
    const userRoleId = primaryRole?.role_id || '';
    const userBranchId = primaryRole?.branch_id || '';
    if (user) {
      setEditingUser(user);
      setFormData({ display_name: user.display_name, email: user.email, employee_code: user.employee_code || '', password: '', role_id: userRoleId, branch_id: userBranchId });
    } else {
      setEditingUser(null);
      setFormData({ display_name: '', email: '', employee_code: '', password: '', role_id: '', branch_id: branches?.[0]?.id || '' });
    }
    setFormError('');
    setIsModalOpen(true);
  };

  const saveUser = () => {
    const employeeCode = formData.employee_code.trim().toUpperCase();
    if (!/^[A-Z0-9]{6}$/.test(employeeCode)) {
      setFormError('El código debe tener exactamente 6 caracteres alfanuméricos.');
      return;
    }
    if (!formData.role_id) {
      setFormError('Debes seleccionar uno de los roles oficiales.');
      return;
    }
    if (requiresBranch && !formData.branch_id) {
      setFormError('Debes seleccionar la sucursal asignada para roles operativos (Cajero, Cajero Jefe, Líder).');
      return;
    }
    setFormError('');
    saveMutation.mutate({ ...formData, employee_code: employeeCode });
  };

  return (
    <>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 32 }}>
        <div>
          <h1 className="premium-header-title">Users & Access</h1>
          <p className="premium-header-subtitle">Administra cuentas, roles oficiales y sucursales operativas.</p>
        </div>
        <button className="premium-add-btn" onClick={() => openModal()}>
          <Plus size={18} />
          Nuevo usuario
        </button>
      </div>

      <div className="premium-card">
        {isLoading ? (
          <div style={{ padding: 40, textAlign: 'center', color: 'var(--color-text-muted)' }}>Cargando usuarios...</div>
        ) : error ? (
          <div style={{ padding: 40, textAlign: 'center', color: 'var(--color-red)' }}>
            {error instanceof ApiError ? error.message : 'Error al cargar los usuarios.'}
          </div>
        ) : !users || users.length === 0 ? (
          <div className="premium-empty-state">
            <Users size={64} className="premium-empty-icon" />
            <h3 style={{ marginBottom: 8, fontSize: '1.25rem', fontWeight: 600 }}>No hay usuarios</h3>
            <p style={{ color: 'var(--color-text-muted)' }}>Invita al primer usuario a la plataforma.</p>
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table className="premium-table">
              <thead>
                <tr>
                  <th>Usuario</th>
                  <th>Email</th>
                  <th>Código</th>
                  <th>Rol y sucursal</th>
                  <th>Status</th>
                  <th style={{ textAlign: 'right' }}>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {users.map((user) => (
                  <tr key={user.id}>
                    <td style={{ fontWeight: 500 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                        <div style={{ padding: 8, background: 'rgba(59, 130, 246, 0.1)', color: '#3b82f6', borderRadius: 8 }}>
                          <Users size={18} />
                        </div>
                        {user.display_name}
                      </div>
                    </td>
                    <td style={{ color: 'var(--color-text-muted)' }}>{user.email}</td>
                    <td style={{ color: user.employee_code ? '#0f172a' : 'var(--color-text-muted)', fontFamily: 'ui-monospace, SFMono-Regular, monospace' }}>
                      {user.employee_code || 'Sin código'}
                    </td>
                    <td>
                      {user.roles && user.roles.length > 0 ? (
                        user.roles.map((r: any) => {
                          const canonicalLabel = CANONICAL_ROLES_META[r.role_name?.trim()?.toLowerCase()]?.label || r.role_name;
                          return (
                            <div key={`${r.role_id}-${r.branch_id || 'org'}`} style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                              <Badge variant="info">{canonicalLabel}</Badge>
                              {r.branch_name && <span style={{ color: 'var(--color-text-muted)', fontSize: '0.8125rem' }}>{r.branch_name}</span>}
                            </div>
                          );
                        })
                      ) : (
                        <span style={{ color: 'var(--color-text-muted)', fontSize: '0.875rem' }}>Sin rol</span>
                      )}
                    </td>
                    <td>
                      <Badge variant={user.status === 'active' ? 'success' : user.status === 'invited' ? 'info' : 'default'}>
                        {user.status === 'active' ? 'Activo' : user.status === 'invited' ? 'Invitado' : 'Suspendido'}
                      </Badge>
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                        <button className="premium-action-btn edit" onClick={() => openModal(user)}><Edit size={18} /></button>
                        <button className="premium-action-btn delete" onClick={() => deleteMutation.mutate(user.id)}><Trash2 size={18} /></button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <Modal isOpen={isModalOpen} onClose={() => setIsModalOpen(false)} title={editingUser ? "Editar Usuario" : "Nuevo Usuario"}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500, fontSize: '0.875rem' }}>Código del empleado (6 caracteres alfanuméricos)</label>
            <Input
              maxLength={6}
              pattern="[A-Za-z0-9]{6}"
              title="6 caracteres alfanuméricos"
              placeholder="Ej. CAJ001"
              value={formData.employee_code}
              onChange={(e: any) => setFormData({...formData, employee_code: e.target.value.replace(/[^a-z0-9]/gi, '').toUpperCase()})}
            />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500, fontSize: '0.875rem' }}>Correo electrónico</label>
            <Input value={formData.email} onChange={(e: any) => setFormData({...formData, email: e.target.value})} placeholder="usuario@possaas.com" />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500, fontSize: '0.875rem' }}>Nombre a mostrar</label>
            <Input value={formData.display_name} onChange={(e: any) => setFormData({...formData, display_name: e.target.value})} placeholder="Nombre completo" />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500, fontSize: '0.875rem' }}>Rol Oficial</label>
            <select 
              value={formData.role_id} 
              onChange={(e) => setFormData({...formData, role_id: e.target.value})}
              style={{ width: '100%', padding: '10px 12px', borderRadius: 8, border: '1px solid #cbd5e1', background: '#fff', fontSize: '0.95rem', outline: 'none' }}
            >
              <option value="">Selecciona uno de los roles oficiales</option>
              {canonicalRoles.map(r => {
                const meta = CANONICAL_ROLES_META[r.name.trim().toLowerCase()];
                return (
                  <option key={r.id} value={r.id}>
                    {meta ? `${meta.rank}. ${meta.label} (${r.scope === 'organization' ? 'Corporativo' : 'Sucursal'})` : r.name}
                  </option>
                );
              })}
            </select>
            {selectedRoleMeta && (
              <p style={{ margin: '6px 0 0', color: '#047857', fontSize: '0.8125rem', background: '#f0fdf4', padding: '6px 10px', borderRadius: 6, display: 'flex', alignItems: 'center', gap: 6 }}>
                <ShieldCheck size={14} />
                <span><strong>{selectedRoleMeta.label}:</strong> {selectedRoleMeta.desc}</span>
              </p>
            )}
          </div>
          {requiresBranch && (
            <div>
              <label style={{ display: 'block', marginBottom: 4, fontWeight: 500, fontSize: '0.875rem' }}>Sucursal asignada al POS</label>
              <select
                value={formData.branch_id}
                onChange={(e) => setFormData({...formData, branch_id: e.target.value})}
                style={{ width: '100%', padding: '10px 12px', borderRadius: 8, border: '1px solid #cbd5e1', background: '#fff', fontSize: '0.95rem', outline: 'none' }}
              >
                <option value="">Selecciona una sucursal</option>
                {branches?.map(branch => (
                  <option key={branch.id} value={branch.id}>{branch.name}</option>
                ))}
              </select>
              <p style={{ margin: '6px 0 0', color: 'var(--color-text-muted)', fontSize: '0.8125rem' }}>
                Esta sucursal será la que el usuario verá por defecto en su terminal POS.
              </p>
            </div>
          )}
          <div>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500, fontSize: '0.875rem' }}>
              {editingUser ? "Nueva contraseña (dejar en blanco para mantener la actual)" : "Contraseña"}
            </label>
            <Input
              type="password"
              autoComplete="new-password"
              value={formData.password}
              onChange={(e: any) => setFormData({...formData, password: e.target.value})}
            />
          </div>
          {formError && <p role="alert" style={{ margin: 0, color: 'var(--color-red)' }}>{formError}</p>}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12, marginTop: 16 }}>
            <Button variant="secondary" onClick={() => setIsModalOpen(false)}>Cancelar</Button>
            <Button variant="primary" onClick={saveUser} disabled={saveMutation.isPending}>
              {saveMutation.isPending ? 'Guardando...' : 'Guardar'}
            </Button>
          </div>
        </div>
      </Modal>
    </>
  );
};
export default UsersList;
