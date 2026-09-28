import React from 'react';
import { BarChart3, LineChart, Wallet } from 'lucide-react';
import { CategoryHubView, HubCardItem } from './CategoryHubView';
import { canManageCashConcepts } from '../cash/cashConceptState';

export const ReportsHub: React.FC = () => {
  const currentUser = JSON.parse(localStorage.getItem('user') || '{}');
  const cards: HubCardItem[] = [
    ...(canManageCashConcepts(currentUser) ? [{
      title: 'Conceptos de Caja',
      description: 'Motivos autorizados de ingresos y egresos de efectivo.',
      icon: <Wallet size={26} />,
      iconBg: '#fff7ed',
      iconColor: '#c2410c',
      path: '/cash-concepts',
    }] : []),
    {
      title: 'Cierre y Reconciliación',
      description: 'Dashboard corporativo de reconciliación de turnos, ingresos y reembolsos.',
      icon: <BarChart3 size={26} />,
      iconBg: '#eff6ff',
      iconColor: '#2563eb',
      path: '/reports',
    },
    {
      title: 'Métricas y Rendimiento',
      description: 'Visualización de tendencias, ventas por categoría e indicadores clave.',
      icon: <LineChart size={26} />,
      iconBg: '#f0fdf4',
      iconColor: '#16a34a',
      path: '/analytics',
    },
  ];

  return (
    <CategoryHubView
      title="Cajas y Reportes"
      subtitle="Monitoreo financiero, cortes de turno y métricas de venta."
      cards={cards}
    />
  );
};
