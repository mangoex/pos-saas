import React from 'react';
import { BarChart3, LineChart } from 'lucide-react';
import { CategoryHubView, HubCardItem } from './CategoryHubView';

export const ReportsHub: React.FC = () => {
  const cards: HubCardItem[] = [
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
