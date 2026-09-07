import React from 'react';
import { Carrot, Trash2, ClipboardCheck, Scale } from 'lucide-react';
import { CategoryHubView, HubCardItem } from './CategoryHubView';

export const InventoryHub: React.FC = () => {
  const cards: HubCardItem[] = [
    {
      title: 'Insumos',
      description: 'Ingredientes base, empaques, costos unitarios y existencias de almacén.',
      icon: <Carrot size={26} />,
      iconBg: '#fff7ed',
      iconColor: '#ea580c',
      path: '/inventory/items',
    },
    {
      title: 'Mermas',
      description: 'Registro de bajas de stock, caducidades y mermas operativas con trazabilidad.',
      icon: <Trash2 size={26} />,
      iconBg: '#fef2f2',
      iconColor: '#e11d48',
      path: '/inventory/waste',
    },
    {
      title: 'Conteos Físicos',
      description: 'Auditorías periódicas de inventario, capturas ciegas y ajustes al kardex.',
      icon: <ClipboardCheck size={26} />,
      iconBg: '#f0fdf4',
      iconColor: '#16a34a',
      path: '/inventory/counts',
    },
    {
      title: 'Unidades de Medida',
      description: 'Catálogo de unidades base (kg, litros, piezas) y factores de conversión.',
      icon: <Scale size={26} />,
      iconBg: '#faf5ff',
      iconColor: '#7c3aed',
      path: '/inventory/units',
    },
  ];

  return (
    <CategoryHubView
      title="Inventario y Almacén"
      subtitle="Insumos, mermas y conteos operativos para la sucursal activa."
      cards={cards}
    />
  );
};
