import React from 'react';
import { ArrowLeft } from 'lucide-react';
import { Link } from 'react-router-dom';
import { usePosSession } from '../../session';

interface BranchAdminPageProps {
  title: string;
  description: string;
  icon: React.ComponentType<{ size?: number; color?: string }>;
  children: React.ReactNode;
}
export function BranchAdminPage({
  title,
  description,
  icon: Icon,
  children,
}: BranchAdminPageProps) {
  const { session } = usePosSession();
  const branch = session?.active_branch;

  return (
    <div style={{ padding: 32, maxWidth: 1280, margin: '0 auto' }}>
      <Link
        to="/administration"
        style={{
          color: '#10b981',
          display: 'inline-flex',
          alignItems: 'center',
          gap: 6,
          marginBottom: 20,
          textDecoration: 'none',
          fontWeight: 600,
        }}
      >
        <ArrowLeft size={17} /> Administración
      </Link>

      <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 8 }}>
        <div style={{ padding: 12, borderRadius: 14, color: '#047857', background: '#d1fae5' }}>
          <Icon size={28} />
        </div>
        <div>
          <h1 style={{ margin: 0, color: '#0f172a', fontSize: 28 }}>{title}</h1>
          <p style={{ margin: '5px 0 0', color: '#64748b' }}>{description}</p>
        </div>
      </div>

      {branch && (
        <div
          style={{
            margin: '18px 0 24px',
            padding: '12px 16px',
            borderRadius: 12,
            background: '#fff',
            border: '1px solid #e2e8f0',
            display: 'flex',
            flexWrap: 'wrap',
            gap: '0.5rem 1.5rem',
            color: '#475569',
            fontSize: 14,
          }}
        >
          <strong style={{ color: '#16a34a' }}>{branch.name.replace(/kiwi/gi, 'RestaurantOS')}</strong>
          <span>{branch.business_unit?.name?.toLowerCase().includes('kiwi') ? 'Operaciones Sucursal' : branch.business_unit?.name}</span>
          <span>{branch.legal_entity?.name?.toLowerCase().includes('kiwi') ? 'Razón Social Principal' : branch.legal_entity?.name}</span>
          {branch.warehouse && <span>Almacén: {branch.warehouse.name?.replace(/kiwi/gi, 'RestaurantOS')}</span>}
        </div>
      )}

      {children}
    </div>
  );
}
