import React from 'react';
import { BarChart3, LineChart, Wallet, Trash2 } from 'lucide-react';
import { CategoryHubView, HubCardItem } from './CategoryHubView';
import { canManageCashConcepts } from '../cash/cashConceptState';

export const ReportsHub: React.FC = () => {
  const currentUser = JSON.parse(localStorage.getItem('user') || '{}');
  const hasCashConceptManage = canManageCashConcepts(currentUser);

  const cards: HubCardItem[] = [
    {
      title: 'Cierre y Reconciliación',
      description: 'Dashboard corporativo de reconciliación de turnos, ingresos y reembolsos.',
      icon: <BarChart3 size={26} />,
      iconBg: '#eff6ff',
      iconColor: '#2563eb',
      path: '/reports',
    },
    ...(hasCashConceptManage
      ? [
          {
            title: 'Conceptos de Caja',
            description: 'Motivos autorizados para ingresos y egresos de efectivo en turnos de caja.',
            icon: <Wallet size={26} />,
            iconBg: '#ecfdf5',
            iconColor: '#047857',
            path: '/cash-concepts',
          },
        ]
      : []),
    {
      title: 'Mermas y Desperdicios',
      description: 'Auditoría de alimentos descartados, pérdidas de cocina y cancelaciones de sucursal.',
      icon: <Trash2 size={26} />,
      iconBg: '#fef2f2',
      iconColor: '#dc2626',
      path: '/waste',
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
      subtitle="Monitoreo financiero, control de conceptos de caja, cortes de turno y métricas de venta."
      cards={cards}
    />
  );
};
