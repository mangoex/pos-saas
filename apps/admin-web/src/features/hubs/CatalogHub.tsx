import React from 'react';
import { Package, Tags, MessageSquareText, Plus, ListTree } from 'lucide-react';
import { CategoryHubView, HubCardItem } from './CategoryHubView';

export const CatalogHub: React.FC = () => {
  const currentUser = JSON.parse(localStorage.getItem('user') || '{}');
  const hasCatalogManage = Boolean(
    currentUser.is_superadmin || (currentUser.permissions || []).includes('catalog.manage')
  );

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
      title: 'Comentarios y Notas',
      description: 'Instrucciones especiales y especificaciones rápidas de cocina para comandas.',
      icon: <MessageSquareText size={26} />,
      iconBg: '#f3e8ff',
      iconColor: '#9333ea',
      path: '/variations',
    },
    {
      title: 'Ingredientes Extra',
      description: 'Extras y adiciones cobrables personalizadas para enriquecer los platillos.',
      icon: <Plus size={26} />,
      iconBg: '#ecfdf5',
      iconColor: '#059669',
      path: '/ingredient-extras',
    },
    ...(hasCatalogManage
      ? [
          {
            title: 'Selector previo',
            description: 'Preguntas obligatorias al ordenar (ej. términos de cocción o tipos de base).',
            icon: <ListTree size={26} />,
            iconBg: '#fdf2f8',
            iconColor: '#db2777',
            path: '/category-options',
          },
        ]
      : []),
  ];

  return (
    <CategoryHubView
      title="Catálogo y Menú"
      subtitle="Administra la oferta gastronómica, productos, precios y modificadores de tu restaurante."
      cards={cards}
    />
  );
};
