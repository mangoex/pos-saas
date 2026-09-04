import React from 'react';
import { ArrowLeft, ShieldAlert } from 'lucide-react';

export const ImpersonationBanner: React.FC = () => {
  const masterToken = localStorage.getItem('saas_master_token');
  const infoStr = localStorage.getItem('impersonation_info');

  if (!masterToken || !infoStr) {
    return null;
  }

  let info: { tenant_name?: string; email?: string } = {};
  try {
    info = JSON.parse(infoStr);
  } catch (e) {
    info = {};
  }

  const handleExitImpersonation = () => {
    // Restore master token, user and branch
    const originalToken = localStorage.getItem('saas_master_token');
    const originalUser = localStorage.getItem('saas_master_user');
    const originalBranch = localStorage.getItem('saas_master_branch_id');

    if (originalToken) {
      localStorage.setItem('auth_token', originalToken);
      localStorage.setItem('token', originalToken);
    }
    if (originalUser) {
      localStorage.setItem('user', originalUser);
    }
    if (originalBranch) {
      localStorage.setItem('admin_branch_id', originalBranch);
      localStorage.setItem('pos_branch_id', originalBranch);
    } else {
      localStorage.removeItem('admin_branch_id');
      localStorage.removeItem('pos_branch_id');
    }

    localStorage.removeItem('saas_master_token');
    localStorage.removeItem('saas_master_user');
    localStorage.removeItem('saas_master_branch_id');
    localStorage.removeItem('impersonation_info');

    window.location.href = '/superadmin';
  };

  return (
    <div
      style={{
        background: 'linear-gradient(90deg, #f59e0b 0%, #d97706 100%)',
        color: '#0f172a',
        padding: '10px 24px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        fontSize: '13px',
        fontWeight: 700,
        boxShadow: '0 2px 8px rgba(217, 119, 6, 0.3)',
        position: 'sticky',
        top: 0,
        zIndex: 9998,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <ShieldAlert size={18} color="#0f172a" />
        <span>
          MODO SOPORTE TÉCNICO ACTIVO: Estás viendo y operando como el cliente{' '}
          <u>{info.tenant_name || 'Restaurante'}</u> ({info.email})
        </span>
      </div>

      <button
        type="button"
        onClick={handleExitImpersonation}
        style={{
          background: '#0f172a',
          color: '#ffffff',
          border: 'none',
          padding: '6px 14px',
          borderRadius: '9999px',
          fontSize: '12px',
          fontWeight: 800,
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
        }}
      >
        <ArrowLeft size={14} />
        <span>Salir de Soporte y Volver a Consola Master</span>
      </button>
    </div>
  );
};
