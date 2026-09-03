import React from 'react';
import { Store, Bike, Share2, Receipt } from 'lucide-react';
import { CategoryHubView, HubCardItem } from './CategoryHubView';

export const BranchesHub: React.FC = () => {
  const cards: HubCardItem[] = [
    {
      title: 'Sucursales',
      description: 'Configuración de sucursales, razones sociales, domicilios y datos de tickets.',
      icon: <Store size={26} />,
      iconBg: '#eff6ff',
      iconColor: '#1d4ed8',
      path: '/branches',
    },
    {
      title: 'Repartidores',
      description: 'Gestión de la flotilla de repartidores para entrega a domicilio propia.',
      icon: <Bike size={26} />,
      iconBg: '#fff7ed',
      iconColor: '#c2410c',
      path: '/drivers',
    },
    {
      title: 'Canales de Delivery (Apps)',
      description: 'Recepción unificada de pedidos de Uber Eats, DiDi Food, Rappi y tienda web directo al POS y KDS.',
      icon: <Share2 size={26} />,
      iconBg: '#ecfdf5',
      iconColor: '#059669',
      badge: 'Recepción POS',
      path: '/integrations',
    },
    {
      title: 'Facturación Fiscal (SAT)',
      description: 'Configuración de timbrado digital CFDI 4.0 con Facturapi y autofactura con QR en ticket.',
      icon: <Receipt size={26} />,
      iconBg: '#f3e8ff',
      iconColor: '#7e22ce',
      badge: 'CFDI 4.0',
      path: '/invoicing',
    },
  ];

  return (
    <CategoryHubView
      title="Sucursales y Canales"
      subtitle="Gestión de puntos de venta físicos, reparto propio, plataformas de delivery y facturación fiscal."
      cards={cards}
    />
  );
};
