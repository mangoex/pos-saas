import React from 'react';
import { Users, Shield, Database, Contact } from 'lucide-react';
import { CategoryHubView, HubCardItem } from './CategoryHubView';

export const AdminAccessHub: React.FC = () => {
  const cards: HubCardItem[] = [
    {
      title: 'Usuarios y Cuentas',
      description: 'Directorio de colaboradores, accesos, contraseñas y asignación de sucursales.',
      icon: <Users size={26} />,
      iconBg: '#eff6ff',
      iconColor: '#1d4ed8',
      path: '/users',
    },
    {
      title: 'Roles y Permisos',
      description: 'Perfiles de acceso y seguridad operativa (Administrador, Supervisor y Cajero).',
      icon: <Shield size={26} />,
      iconBg: '#fef2f2',
      iconColor: '#dc2626',
      path: '/roles',
    },
    {
      title: 'Directorio de Clientes',
      description: 'Catálogo global de clientes, números de contacto, domicilios y datos fiscales.',
      icon: <Contact size={26} />,
      iconBg: '#fdf4ff',
      iconColor: '#a855f7',
      path: '/customers',
    },
  ];

  return (
    <CategoryHubView
      title="Administración y Accesos"
      subtitle="Control de usuarios, perfiles de acceso y directorio de clientes."
      cards={cards}
    />
  );
};
