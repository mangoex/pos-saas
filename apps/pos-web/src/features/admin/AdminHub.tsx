import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchApi } from '@restaurantos/api-client';
import { Link } from 'react-router-dom';
import {
  Building2, Package, Receipt,
  ShieldCheck, Trash2, Clock3,
  BarChart3, Lock,
} from 'lucide-react';
import { usePosSession } from '../../session';

const UNIT_TYPE_LABELS: Record<string, string> = {
  restaurant: 'Restaurante',
  bakery: 'Panadería',
  production: 'Producción',
  other: 'Otro',
};

interface EnabledCard {
  to: string;
  label: string;
  description: string;
  icon: React.ComponentType<{ size?: number; color?: string }>;
  permission?: string | string[];
}

interface BranchImportSummary {
  id: string;
  status: string;
  entity_summary: Record<string, Record<string, number>>;
}

const enabledCards: EnabledCard[] = [
  {
    to: '/administration/attendance',
    label: 'Reporte de Asistencia',
    description: 'Reporte de entradas y salidas del personal con filtros por fecha, código y sucursal.',
    icon: Clock3,
    permission: 'branch.staff.read',
  },
  {
    to: '/sales-monitor',
    label: 'Monitor de ventas',
    description: 'Consulta de ventas y operaciones del turno en tiempo real.',
    icon: BarChart3,
    permission: 'reports.sales.read',
  },
  {
    to: '/administration/products',
    label: 'Disponibilidad de Menú',
    description: 'Activar o apagar productos e insumos agotados (86) en la sucursal.',
    icon: Package,
    permission: ['catalog.branch.manage', 'branch.admin.access', 'admin.manage'],
  },
  {
    to: '/administration/suppliers',
    label: 'Proveedores',
    description: 'Consulta de proveedores, contactos y presentaciones disponibles para comprar.',
    icon: Building2,
    permission: 'purchases.read',
  },
  {
    to: '/administration/purchases',
    label: 'Compras',
    description: 'Consulta de recepciones, costos y conciliación con caja de la sucursal.',
    icon: Receipt,
    permission: 'purchases.read',
  },
  {
    to: '/administration/waste',
    label: 'Mermas',
    description: 'Consulta de registros, autorizaciones y reversas auditables de la sucursal.',
    icon: Trash2,
    permission: 'inventory.waste',
  },
];

export function branchAdministrationCards(canManageVariations: boolean): EnabledCard[] {
  return enabledCards;
}

const AdminHub: React.FC = () => {
  const { session, hasPermission } = usePosSession();
  const branch = session?.active_branch;
  const importsQuery = useQuery<BranchImportSummary[]>({
    queryKey: ['branch-imports', branch?.id],
    queryFn: () => fetchApi(`/branch-administration/imports?branch_id=${encodeURIComponent(branch?.id || '')}`),
    enabled: Boolean(branch?.id) && hasPermission('branch.admin.access'),
  });
  const latestImport = importsQuery.data?.[0];
  const visibleCards = branchAdministrationCards(hasPermission('catalog.branch.manage'));

  const isCardAuthorized = (card: EnabledCard): boolean => {
    if (
      hasPermission('admin.manage') ||
      hasPermission('branch.admin.access') ||
      Boolean(session?.roles?.some((r) => r.name.toLowerCase().includes('admin')))
    ) {
      return true;
    }
    if (!card.permission) return true;
    if (Array.isArray(card.permission)) {
      return card.permission.some((p) => hasPermission(p));
    }
    return hasPermission(card.permission);
  };

  return (
    <div style={{ padding: 32, maxWidth: 1280, margin: '0 auto' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 8 }}>
        <div style={{ padding: 12, borderRadius: 14, color: '#047857', background: '#d1fae5' }}>
          <ShieldCheck size={30} />
        </div>
        <div>
          <h1 style={{ margin: 0, color: '#0f172a' }}>Administración de sucursal</h1>
          <p style={{ margin: '5px 0 0', color: '#64748b' }}>
            Gestiona la operación de tu sucursal sin abandonar el POS.
          </p>
        </div>
      </div>

      {branch && (
        <div
          style={{
            marginTop: 16,
            padding: '12px 16px',
            borderRadius: 12,
            background: '#fff',
            border: '1px solid #e2e8f0',
            display: 'flex',
            flexWrap: 'wrap',
            gap: '0.5rem 1.5rem',
            alignItems: 'center',
            fontSize: 14,
            color: '#334155',
          }}
        >
          <strong style={{ color: '#16a34a' }}>Administración de sucursal</strong>
          <span>{branch.name} ({branch.code})</span>
          <span>{branch.business_unit.name}</span>
          <span>
            Tipo: {UNIT_TYPE_LABELS[branch.business_unit.unit_type] || branch.business_unit.unit_type}
          </span>
          <span>Razón social: {branch.legal_entity.name}</span>
          {branch.warehouse && <span>Almacén: {branch.warehouse.name}</span>}
        </div>
      )}

      {latestImport && (
        <section style={{ marginTop: 18, padding: 16, borderRadius: 14, background: '#fffbeb', border: '1px solid #fde68a' }}>
          <strong style={{ color: '#92400e' }}>Datos heredados de esta sucursal</strong>
          <p style={{ color: '#78350f', margin: '6px 0 10px', fontSize: 14 }}>
            Los catálogos ya están separados por sucursal. Los datos incompletos permanecen protegidos hasta que el administrador corporativo los concluya.
          </p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {Object.entries(latestImport.entity_summary).map(([entity, counts]) => (
              <span key={entity} style={{ padding: '5px 9px', borderRadius: 999, background: '#fff', color: '#78350f', fontSize: 12 }}>
                {entity}: {Object.entries(counts).map(([status, count]) => `${status} ${count}`).join(' · ')}
              </span>
            ))}
          </div>
        </section>
      )}

      <div
        role="list"
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
          gap: 16,
          marginTop: 28,
        }}
      >
        {visibleCards.map((card) => {
          const { to, label, description, icon: Icon } = card;
          const isAuthorized = isCardAuthorized(card);

          if (isAuthorized) {
            return (
              <Link
                role="listitem"
                key={to}
                to={to}
                style={{
                  display: 'block',
                  padding: 20,
                  borderRadius: 14,
                  border: '1px solid #e2e8f0',
                  background: '#fff',
                  color: '#0f172a',
                  textDecoration: 'none',
                  boxShadow: '0 6px 18px rgba(15, 23, 42, 0.05)',
                  transition: 'transform 0.15s, box-shadow 0.15s',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <Icon size={24} color="#10b981" />
                </div>
                <h2 style={{ fontSize: 17, margin: '12px 0 6px', color: '#0f172a' }}>{label}</h2>
                <p style={{ color: '#64748b', fontSize: 14, lineHeight: 1.45, margin: 0 }}>{description}</p>
              </Link>
            );
          }

          return (
            <div
              role="listitem"
              key={to}
              onClick={(e) => e.preventDefault()}
              style={{
                display: 'block',
                padding: 20,
                borderRadius: 14,
                border: '1px solid #e2e8f0',
                background: '#f8fafc',
                color: '#94a3b8',
                cursor: 'not-allowed',
                opacity: 0.7,
                userSelect: 'none',
              }}
              title="Tu rol actual no tiene permisos para acceder a esta sección"
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Icon size={24} color="#94a3b8" />
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 4,
                    padding: '3px 8px',
                    borderRadius: 6,
                    background: '#e2e8f0',
                    color: '#64748b',
                    fontSize: 11,
                    fontWeight: 600,
                  }}
                >
                  <Lock size={12} />
                  Restringido
                </span>
              </div>
              <h2 style={{ fontSize: 17, margin: '12px 0 6px', color: '#64748b' }}>{label}</h2>
              <p style={{ color: '#94a3b8', fontSize: 14, lineHeight: 1.45, margin: 0 }}>{description}</p>
            </div>
          );
        })}
      </div>

    </div>
  );
};

export default AdminHub;
