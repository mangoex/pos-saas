import React, { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Button, Badge, Modal, Input } from '@restaurantos/ui';
import { fetchApi } from '@restaurantos/api-client';
import { Plus, Shield, Edit, Trash2 } from 'lucide-react';

import '../../premium-catalogs.css';

interface Role {
  id: string;
  name: string;
  scope: string;
  created_at: string;
}

interface Permission {
  id: string;
  code: string;
  description: string;
}

const EXCLUDED_PERMISSION_PATTERNS = [
  'recipes.',
  'waste',
  'ingredient_sales',
  'production.',
  'transfer',
  'sync.events',
  'purchases.',
  'warehouses',
  'count',
];

interface PermissionCategory {
  title: string;
  icon: string;
  codes: string[];
}

const PERMISSION_CATEGORIES: PermissionCategory[] = [
  {
    title: 'Punto de Venta y Comandas (POS)',
    icon: '🛒',
    codes: [
      'pos.operate',
      'orders.read',
      'orders.create',
      'orders.amend',
      'orders.cancel',
      'orders.fulfill',
      'payments.read',
      'payments.confirm',
    ],
  },
  {
    title: 'Caja, Turnos y Arqueos',
    icon: '💵',
    codes: [
      'cash.shift.read',
      'cash.shift.open',
      'cash.shift.close',
      'cash.movement.read',
      'cash.movement.withdraw',
      'cash.movement.deposit',
      'cash.concept.read',
      'cash.concept.manage',
      'cash.user_cut.read',
      'cash.user_cut.create',
      'cash.withdraw',
    ],
  },
  {
    title: 'Catálogo y Menú',
    icon: '🍽️',
    codes: [
      'catalog.manage',
      'catalog.branch.manage',
    ],
  },
  {
    title: 'Ventas y Reportes',
    icon: '📊',
    codes: [
      'dashboard.read',
      'reports.sales.read',
      'reports.expenses.read',
    ],
  },
  {
    title: 'Administración y Equipo',
    icon: '⚙️',
    codes: [
      'admin.manage',
      'branch.admin.access',
      'branch.staff.read',
      'access.organization.all_branches',
    ],
  },
];

const RolesList = () => {
  const queryClient = useQueryClient();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingRole, setEditingRole] = useState<Role | null>(null);
  const [formData, setFormData] = useState({ name: '', scope: 'branch' });
  const [selectedPermissions, setSelectedPermissions] = useState<string[]>([]);

  const { data: roles, isLoading, error } = useQuery<Role[]>({
    queryKey: ['roles'],
    queryFn: () => fetchApi('/roles'),
  });

  const { data: permissions } = useQuery<Permission[]>({
    queryKey: ['permissions'],
    queryFn: () => fetchApi('/permissions'),
  });

  const { data: rolePermissions } = useQuery<string[]>({
    queryKey: ['roles', editingRole?.id, 'permissions'],
    queryFn: () => fetchApi(`/roles/${editingRole?.id}/permissions`),
    enabled: !!editingRole,
  });

  // Update selectedPermissions when rolePermissions loads
  React.useEffect(() => {
    if (rolePermissions) {
      setSelectedPermissions(rolePermissions);
    }
  }, [rolePermissions]);

  const activePermissions = useMemo(() => {
    if (!permissions) return [];
    return permissions.filter((perm) => {
      const code = perm.code.toLowerCase();
      return !EXCLUDED_PERMISSION_PATTERNS.some((pattern) => code.includes(pattern));
    });
  }, [permissions]);

  const groupedPermissions = useMemo(() => {
    const map: Record<string, Permission[]> = {};
    const usedIds = new Set<string>();

    for (const cat of PERMISSION_CATEGORIES) {
      map[cat.title] = [];
      for (const code of cat.codes) {
        const found = activePermissions.find((p) => p.code === code);
        if (found) {
          map[cat.title].push(found);
          usedIds.add(found.id);
        }
      }
    }

    const unmapped = activePermissions.filter((p) => !usedIds.has(p.id));
    if (unmapped.length > 0) {
      map['Otros Permisos Operativos'] = unmapped;
    }

    return map;
  }, [activePermissions]);

  const saveMutation = useMutation({
    mutationFn: async (data: typeof formData) => {
      let roleId = editingRole?.id;
      if (editingRole) {
        await fetchApi(`/roles/${roleId}`, {
          method: 'PUT',
          body: JSON.stringify(data),
        });
      } else {
        const response = await fetchApi('/roles', {
          method: 'POST',
          body: JSON.stringify(data),
        });
        roleId = (response as { id: string }).id;
      }
      
      if (roleId) {
        await fetchApi(`/roles/${roleId}/permissions`, {
          method: 'PUT',
          body: JSON.stringify({ permission_ids: selectedPermissions }),
        });
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['roles'] });
      setIsModalOpen(false);
    }
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => fetchApi(`/roles/${id}`, { method: 'DELETE' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['roles'] })
  });

  const openModal = (role?: Role) => {
    if (role) {
      setEditingRole(role);
      setFormData({ name: role.name, scope: role.scope });
      setSelectedPermissions([]); // Will load from query
    } else {
      setEditingRole(null);
      setFormData({ name: '', scope: 'branch' });
      setSelectedPermissions([]);
    }
    setIsModalOpen(true);
  };

  const togglePermission = (id: string) => {
    setSelectedPermissions(prev => 
      prev.includes(id) ? prev.filter(p => p !== id) : [...prev, id]
    );
  };

  return (
    <>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 32 }}>
        <div>
          <h1 className="premium-header-title">Roles de Usuario</h1>
          <p className="premium-header-subtitle">Configura los roles y sus permisos detallados.</p>
        </div>
        <button className="premium-add-btn" onClick={() => openModal()}>
          <Plus size={18} />
          Nuevo Rol
        </button>
      </div>

      <div className="premium-card">
        {isLoading ? (
          <div style={{ padding: 40, textAlign: 'center', color: 'var(--color-text-muted)' }}>Cargando roles...</div>
        ) : error ? (
          <div style={{ padding: 40, textAlign: 'center', color: 'var(--color-red)' }}>Error al cargar los roles.</div>
        ) : !roles || roles.length === 0 ? (
          <div className="premium-empty-state">
            <Shield size={64} className="premium-empty-icon" />
            <h3 style={{ marginBottom: 8, fontSize: '1.25rem', fontWeight: 600 }}>No hay roles registrados</h3>
            <p style={{ color: 'var(--color-text-muted)' }}>Agrega el primer rol para asignar a tus usuarios.</p>
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table className="premium-table">
              <thead>
                <tr>
                  <th>Nombre del Rol</th>
                  <th>Alcance (Scope)</th>
                  <th style={{ textAlign: 'right' }}>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {roles.map((role) => (
                  <tr key={role.id}>
                    <td style={{ fontWeight: 500 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                        <div style={{ padding: 8, background: 'rgba(59, 130, 246, 0.1)', color: '#3b82f6', borderRadius: 8 }}>
                          <Shield size={18} />
                        </div>
                        {role.name}
                      </div>
                    </td>
                    <td><Badge variant="info">{role.scope}</Badge></td>
                    <td style={{ textAlign: 'right' }}>
                      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                        <button className="premium-action-btn edit" onClick={() => openModal(role)}><Edit size={18} /></button>
                        <button className="premium-action-btn delete" onClick={() => deleteMutation.mutate(role.id)}><Trash2 size={18} /></button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <Modal isOpen={isModalOpen} onClose={() => setIsModalOpen(false)} title={editingRole ? "Editar Rol" : "Nuevo Rol"}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500, fontSize: '0.875rem' }}>Nombre del Rol</label>
            <Input value={formData.name} onChange={(e: any) => setFormData({...formData, name: e.target.value})} placeholder="Ej. Supervisor de Turno" />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500, fontSize: '0.875rem' }}>Alcance de Operación</label>
            <select
              value={formData.scope}
              onChange={(e) => setFormData({ ...formData, scope: e.target.value })}
              style={{ width: '100%', padding: '10px 12px', borderRadius: 8, border: '1px solid #cbd5e1', background: '#fff', fontSize: '0.95rem' }}
            >
              <option value="branch">Sucursal (Asignado a colaboradores de una sucursal específica)</option>
              <option value="organization">Restaurante Global (Acceso general en todas las sucursales)</option>
            </select>
          </div>

          <div style={{ marginTop: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
              <h4 style={{ margin: 0, fontWeight: 600, fontSize: '0.95rem' }}>Permisos del Rol ({selectedPermissions.length} seleccionados)</h4>
            </div>
            <p style={{ margin: '0 0 12px', fontSize: '0.8rem', color: '#64748b' }}>
              Selecciona las opciones operativas autorizadas para este rol en el sistema.
            </p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 12, maxHeight: '340px', overflowY: 'auto', paddingRight: 4 }}>
              {Object.entries(groupedPermissions).map(([catTitle, perms]) => {
                if (perms.length === 0) return null;
                const categoryDef = PERMISSION_CATEGORIES.find((c) => c.title === catTitle);
                const allSelected = perms.every((p) => selectedPermissions.includes(p.id));
                const toggleGroup = () => {
                  if (allSelected) {
                    setSelectedPermissions((prev) => prev.filter((id) => !perms.some((p) => p.id === id)));
                  } else {
                    const idsToAdd = perms.map((p) => p.id);
                    setSelectedPermissions((prev) => Array.from(new Set([...prev, ...idsToAdd])));
                  }
                };

                return (
                  <div key={catTitle} style={{ border: '1px solid #e2e8f0', borderRadius: 8, overflow: 'hidden', background: '#fff' }}>
                    <div
                      onClick={toggleGroup}
                      style={{
                        padding: '8px 12px',
                        background: '#f8fafc',
                        borderBottom: '1px solid #e2e8f0',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        cursor: 'pointer',
                        userSelect: 'none',
                      }}
                    >
                      <div style={{ fontWeight: 600, fontSize: '0.875rem', color: '#1e293b', display: 'flex', alignItems: 'center', gap: 6 }}>
                        <span>{categoryDef?.icon || '📋'}</span>
                        <span>{catTitle}</span>
                      </div>
                      <span style={{ fontSize: '0.75rem', color: '#0284c7', fontWeight: 600 }}>
                        {allSelected ? 'Deseleccionar grupo' : 'Seleccionar todos'}
                      </span>
                    </div>

                    <div style={{ padding: '8px 12px', display: 'flex', flexDirection: 'column', gap: 6 }}>
                      {perms.map((perm) => {
                        const isChecked = selectedPermissions.includes(perm.id);
                        return (
                          <label key={perm.id} style={{ display: 'flex', alignItems: 'flex-start', gap: 8, cursor: 'pointer' }}>
                            <input
                              type="checkbox"
                              checked={isChecked}
                              onChange={() => togglePermission(perm.id)}
                              style={{ marginTop: 2 }}
                            />
                            <div style={{ fontSize: '0.85rem' }}>
                              <span style={{ color: '#0f172a', fontWeight: isChecked ? 600 : 400 }}>
                                {perm.description}
                              </span>
                              <span style={{ color: '#94a3b8', fontSize: '0.75rem', marginLeft: 6 }}>
                                ({perm.code})
                              </span>
                            </div>
                          </label>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12, marginTop: 16 }}>
            <Button variant="secondary" onClick={() => setIsModalOpen(false)}>Cancelar</Button>
            <Button variant="primary" onClick={() => saveMutation.mutate(formData)} disabled={saveMutation.isPending}>
              {saveMutation.isPending ? 'Guardando...' : 'Guardar'}
            </Button>
          </div>
        </div>
      </Modal>
    </>
  );
};
export default RolesList;
