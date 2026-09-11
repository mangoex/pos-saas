import React, { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ChefHat, CircleDollarSign, Utensils, Store, Sparkles } from 'lucide-react';
import { fetchApi } from '@restaurantos/api-client';
import { MobileOrdersMonitor } from '../mobile-orders/MobileOrdersMonitor';
import { MobileCashShiftTab } from './MobileCashShiftTab';
import { MobileMenuManagerTab } from './MobileMenuManagerTab';
import { MobileBranchSettingsTab } from './MobileBranchSettingsTab';
import { OnboardingWizardModal } from '../onboarding/OnboardingWizardModal';

interface MobileAdminShellProps {
  branchId: string;
  branchName?: string;
  onSwitchToDesktop?: () => void;
}

interface ErrorBoundaryProps {
  children: React.ReactNode;
  tabName: string;
}

interface ErrorBoundaryState {
  hasError: boolean;
}

class MobileTabErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error(`Error in MobileTab [${this.props.tabName}]:`, error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div
          style={{
            padding: 24,
            margin: '24px 16px',
            backgroundColor: '#fff1f2',
            border: '1px solid #fecdd3',
            borderRadius: 14,
            textAlign: 'center',
          }}
        >
          <div style={{ fontSize: '1.8rem', marginBottom: 8 }}>⚠️</div>
          <h3 style={{ fontSize: '1rem', fontWeight: 800, color: '#9f1239', margin: '0 0 8px' }}>
            No pudimos cargar la pestaña de {this.props.tabName}
          </h3>
          <p style={{ fontSize: '0.8rem', color: '#be123c', margin: '0 0 16px', lineHeight: 1.4 }}>
            Ocurrió un error inesperado al procesar los datos. Puedes intentar recargar la pestaña.
          </p>
          <button
            type="button"
            onClick={() => this.setState({ hasError: false })}
            style={{
              backgroundColor: '#be123c',
              color: '#ffffff',
              border: 'none',
              borderRadius: 8,
              padding: '8px 18px',
              fontSize: '0.85rem',
              fontWeight: 700,
              cursor: 'pointer',
            }}
          >
            Reintentar
          </button>
        </div>
      );
    }
    return this.props.children;
  }
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
  const [onboardingStatus, setOnboardingStatus] = useState<string | null>(null);
  const [isOnboardingModalOpen, setIsOnboardingModalOpen] = useState(false);

  useEffect(() => {
    fetchApi<{ step: 'business' | 'menu' | 'register' | 'complete' }>('/saas/onboarding')
      .then((setup) => {
        setOnboardingStatus(setup.step);
        if (setup.step !== 'complete') {
          try {
            const prompted = sessionStorage.getItem('restaurantos_mobile_onboarding_prompted');
            if (!prompted) {
              sessionStorage.setItem('restaurantos_mobile_onboarding_prompted', 'true');
              setIsOnboardingModalOpen(true);
            }
          } catch {
            // ignore
          }
        }
      })
      .catch(() => setOnboardingStatus(null));
  }, []);

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
      {/* Quickstart Onboarding Banner for Mobile */}
      {onboardingStatus && onboardingStatus !== 'complete' && (
        <section
          aria-label="Asistente de configuración inicial móvil"
          style={{
            background: 'linear-gradient(135deg, #064e3b 0%, #047857 50%, #059669 100%)',
            padding: '12px 16px',
            color: '#ffffff',
            boxShadow: '0 4px 12px rgba(5, 150, 105, 0.25)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 12,
            position: 'sticky',
            top: 0,
            zIndex: 40,
          }}
        >
          <div style={{ flex: 1 }}>
            <div
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 4,
                background: 'rgba(255, 255, 255, 0.2)',
                padding: '2px 8px',
                borderRadius: 9999,
                fontSize: '0.65rem',
                fontWeight: 800,
                textTransform: 'uppercase',
                marginBottom: 2,
              }}
            >
              <Sparkles size={11} /> Configuración Inicial
            </div>
            <div style={{ fontSize: '0.88rem', fontWeight: 800, lineHeight: 1.2 }}>
              ¡Bienvenido! Activa tu Menú y QR
            </div>
            <div style={{ fontSize: '0.72rem', color: '#d1fae5', marginTop: 2 }}>
              Carga tu catálogo con IA, sube tu carta o hazlo manual en 3 minutos.
            </div>
          </div>
          <button
            type="button"
            onClick={() => setIsOnboardingModalOpen(true)}
            style={{
              backgroundColor: '#ffffff',
              color: '#065f46',
              border: 'none',
              borderRadius: 10,
              padding: '8px 14px',
              fontSize: '0.8rem',
              fontWeight: 800,
              cursor: 'pointer',
              whiteSpace: 'nowrap',
              boxShadow: '0 2px 4px rgba(0, 0, 0, 0.1)',
            }}
          >
            Configurar
          </button>
        </section>
      )}

      {/* Active Tab View */}
      <div style={{ minHeight: '100vh', paddingBottom: 72 }}>
        {currentTab === 'orders' && (
          <MobileTabErrorBoundary tabName="Pedidos">
            <MobileOrdersMonitor branchId={branchId} branchName={branchName} />
          </MobileTabErrorBoundary>
        )}
        {currentTab === 'cash' && (
          <MobileTabErrorBoundary tabName="Caja">
            <MobileCashShiftTab branchId={branchId} branchName={branchName} />
          </MobileTabErrorBoundary>
        )}
        {currentTab === 'menu' && (
          <MobileTabErrorBoundary tabName="Menú">
            <MobileMenuManagerTab branchId={branchId} branchName={branchName} />
          </MobileTabErrorBoundary>
        )}
        {currentTab === 'settings' && (
          <MobileTabErrorBoundary tabName="Ajustes">
            <MobileBranchSettingsTab
              branchId={branchId}
              branchName={branchName}
              onSwitchToDesktop={onSwitchToDesktop}
              onOpenOnboarding={() => setIsOnboardingModalOpen(true)}
              onboardingPending={onboardingStatus !== 'complete'}
            />
          </MobileTabErrorBoundary>
        )}
      </div>

      {/* Onboarding Wizard Modal for Mobile */}
      <OnboardingWizardModal
        isOpen={isOnboardingModalOpen}
        isMobileView={true}
        onClose={() => setIsOnboardingModalOpen(false)}
        onCompleted={() => {
          setIsOnboardingModalOpen(false);
          setOnboardingStatus('complete');
        }}
      />

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
