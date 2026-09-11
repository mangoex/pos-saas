import React from 'react';
import { Package, Tags, MessageSquareText, Plus, Image as ImageIcon } from 'lucide-react';
import { CategoryHubView, HubCardItem } from './CategoryHubView';

export const CatalogHub: React.FC = () => {

  const cards: HubCardItem[] = [
    {
      title: 'Productos',
      description: 'Alta, precios, impuestos, visibilidad y estaciones de preparación de tu menú.',
      icon: <Package size={26} />,
      iconBg: '#eff6ff',
      iconColor: '#2563eb',
      path: '/products',
    },
    {
      title: 'Categorías',
      description: 'Familias de productos y agrupación visual para terminales POS y cartas digitales.',
      icon: <Tags size={26} />,
      iconBg: '#fef3c7',
      iconColor: '#d97706',
      path: '/categories',
    },
    {
      title: 'Fotos de la Comunidad',
      description: 'Modera, aprueba y supervisa fotos reales compartidas por comensales con órdenes verificadas.',
      icon: <ImageIcon size={26} />,
      iconBg: '#fffbeb',
      iconColor: '#d97706',
      path: '/community-photos',
    },
    {
      title: 'Comentarios y Notas',
      description: 'Instrucciones especiales y especificaciones rápidas de cocina para comandas.',
      icon: <MessageSquareText size={26} />,
      iconBg: '#f3e8ff',
      iconColor: '#9333ea',
      path: '/variations',
    },
    {
      title: 'Adicionales y Modificadores',
      description: 'Extras y adiciones cobrables para enriquecer los platillos (ej. Queso extra, Tocino, Aguacate).',
      icon: <Plus size={26} />,
      iconBg: '#ecfdf5',
      iconColor: '#059669',
      path: '/ingredient-extras',
    },
  ];

  return (
    <CategoryHubView
      title="Catálogo y Menú"
      subtitle="Administra la oferta gastronómica, productos, precios y modificadores de tu restaurante."
      cards={cards}
    />
  );
};
