import React, { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ChefHat, CircleDollarSign, Utensils, Store } from 'lucide-react';
import { MobileOrdersMonitor } from '../mobile-orders/MobileOrdersMonitor';
import { MobileCashShiftTab } from './MobileCashShiftTab';
import { MobileMenuManagerTab } from './MobileMenuManagerTab';
import { MobileBranchSettingsTab } from './MobileBranchSettingsTab';

interface MobileAdminShellProps {
  branchId: string;
  branchName?: string;
  onSwitchToDesktop?: () => void;
}

export type MobileTab = 'orders' | 'cash' | 'menu' | 'settings';

export const MobileAdminShell: React.FC<MobileAdminShellProps> = ({
  branchId,
  branchName,
  onSwitchToDesktop,
}) => {
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = (searchParams.get('tab') as MobileTab) || 'orders';
  const [currentTab, setCurrentTab] = useState<MobileTab>(
    ['orders', 'cash', 'menu', 'settings'].includes(tabParam) ? tabParam : 'orders'
  );

  useEffect(() => {
    const nextTab = searchParams.get('tab') as MobileTab;
    if (nextTab && ['orders', 'cash', 'menu', 'settings'].includes(nextTab)) {
      setCurrentTab(nextTab);
    }
  }, [searchParams]);

  const handleTabChange = (tab: MobileTab) => {
    setCurrentTab(tab);
    setSearchParams({ tab }, { replace: true });
  };

  return (
    <div style={{ minHeight: '100vh', width: '100vw', backgroundColor: '#f8fafc', position: 'relative' }}>
      {/* Active Tab View */}
      <div style={{ minHeight: '100vh' }}>
        {currentTab === 'orders' && (
          <MobileOrdersMonitor branchId={branchId} branchName={branchName} />
        )}
        {currentTab === 'cash' && (
          <MobileCashShiftTab branchId={branchId} branchName={branchName} />
        )}
        {currentTab === 'menu' && (
          <MobileMenuManagerTab branchId={branchId} branchName={branchName} />
        )}
        {currentTab === 'settings' && (
          <MobileBranchSettingsTab
            branchId={branchId}
            branchName={branchName}
            onSwitchToDesktop={onSwitchToDesktop}
          />
        )}
      </div>

      {/* Fixed Bottom Navigation Bar */}
      <nav
        role="navigation"
        aria-label="Navegación Móvil Principal"
        style={{
          position: 'fixed',
          bottom: 0,
          left: 0,
          right: 0,
          height: 64,
          backgroundColor: '#0f172a',
          borderTop: '1px solid #1e293b',
          display: 'flex',
          justifyContent: 'space-around',
          alignItems: 'center',
          zIndex: 50,
          boxShadow: '0 -4px 10px rgba(0, 0, 0, 0.15)',
          paddingBottom: 'env(safe-area-inset-bottom, 0px)',
        }}
      >
        {/* Tab 1: Pedidos */}
        <button
          type="button"
          onClick={() => handleTabChange('orders')}
          style={{
            flex: 1,
            height: '100%',
            background: 'none',
            border: 'none',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 4,
            cursor: 'pointer',
            color: currentTab === 'orders' ? '#38bdf8' : '#94a3b8',
            padding: 0,
          }}
        >
          <ChefHat size={22} color={currentTab === 'orders' ? '#38bdf8' : '#94a3b8'} />
          <span style={{ fontSize: '0.725rem', fontWeight: currentTab === 'orders' ? 800 : 600 }}>
            Pedidos
          </span>
        </button>

        {/* Tab 2: Caja */}
        <button
          type="button"
          onClick={() => handleTabChange('cash')}
          style={{
            flex: 1,
            height: '100%',
            background: 'none',
            border: 'none',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 4,
            cursor: 'pointer',
            color: currentTab === 'cash' ? '#38bdf8' : '#94a3b8',
            padding: 0,
          }}
        >
          <CircleDollarSign size={22} color={currentTab === 'cash' ? '#38bdf8' : '#94a3b8'} />
          <span style={{ fontSize: '0.725rem', fontWeight: currentTab === 'cash' ? 800 : 600 }}>
            Caja
          </span>
        </button>

        {/* Tab 3: Menú */}
        <button
          type="button"
          onClick={() => handleTabChange('menu')}
          style={{
            flex: 1,
            height: '100%',
            background: 'none',
            border: 'none',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 4,
            cursor: 'pointer',
            color: currentTab === 'menu' ? '#38bdf8' : '#94a3b8',
            padding: 0,
          }}
        >
          <Utensils size={22} color={currentTab === 'menu' ? '#38bdf8' : '#94a3b8'} />
          <span style={{ fontSize: '0.725rem', fontWeight: currentTab === 'menu' ? 800 : 600 }}>
            Menú
          </span>
        </button>

        {/* Tab 4: Sucursal */}
        <button
          type="button"
          onClick={() => handleTabChange('settings')}
          style={{
            flex: 1,
            height: '100%',
            background: 'none',
            border: 'none',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 4,
            cursor: 'pointer',
            color: currentTab === 'settings' ? '#38bdf8' : '#94a3b8',
            padding: 0,
          }}
        >
          <Store size={22} color={currentTab === 'settings' ? '#38bdf8' : '#94a3b8'} />
          <span style={{ fontSize: '0.725rem', fontWeight: currentTab === 'settings' ? 800 : 600 }}>
            Sucursal
          </span>
        </button>
      </nav>
    </div>
  );
};
