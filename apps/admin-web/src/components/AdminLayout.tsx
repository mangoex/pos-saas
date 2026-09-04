import React, { useEffect, useState } from 'react';
import { useNavigate, useLocation, Outlet } from 'react-router-dom';
import { 
  LayoutDashboard, Users, Settings, BarChart2, Bell, Search, UserRound,
  LogOut, Package, Store, Carrot, ChevronLeft, ChevronRight, Camera,
  ShoppingCart, Receipt, Share2, Crown
} from 'lucide-react';
import { Modal, Input, Button } from '@restaurantos/ui';
import { fetchApi } from '@restaurantos/api-client';
import { canSelectAnyBranch, resolveBranchId, setCanonicalBranchId } from '../lib/branchContext';
import { redirectToPos } from '../lib/posHandoff';
import AdminAssistantPanel from '../features/admin-ai/AdminAssistantPanel';
import AdminProposalReview from '../features/admin-ai/AdminProposalReview';
import { CategorySubNav } from './CategorySubNav';
import { canManageCashConcepts } from '../features/cash/cashConceptState';
import { ImpersonationBanner } from '../features/superadmin/ImpersonationBanner';

const compressImage = (dataUrl: string, maxWidth = 128, maxHeight = 128): Promise<string> => {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.src = dataUrl;
    img.onload = () => {
      const canvas = document.createElement('canvas');
      let width = img.width;
      let height = img.height;

      if (width > height) {
        if (width > maxWidth) {
          height = Math.round((height * maxWidth) / width);
          width = maxWidth;
        }
      } else {
        if (height > maxHeight) {
          width = Math.round((width * maxHeight) / height);
          height = maxHeight;
        }
      }

      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext('2d');
      if (!ctx) {
        resolve(dataUrl);
        return;
      }
      ctx.drawImage(img, 0, 0, width, height);
      resolve(canvas.toDataURL('image/jpeg', 0.7));
    };
    img.onerror = (err) => reject(err);
  });
};

interface MainCategoryItem {
  path: string;
  label: string;
  icon: React.ReactNode;
  highlight?: boolean;
  badge?: string;
  matchingPrefixes: string[];
}

const AdminLayout = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [isProfileModalOpen, setIsProfileModalOpen] = useState(false);
  const [profileData, setProfileData] = useState({ display_name: '', email: '', password: '' });
  const [profileAvatar, setProfileAvatar] = useState('');
  const [isSavingProfile, setIsSavingProfile] = useState(false);
  const [branches, setBranches] = useState<Array<{ id: string; name: string; status: string }>>([]);
  const [branchId, setBranchId] = useState(resolveBranchId());
  const [branchReady, setBranchReady] = useState(false);
  const [isAssistantOpen, setIsAssistantOpen] = useState(false);
  const proposalId = new URLSearchParams(location.search).get('admin_ai_proposal');

  const currentUser = JSON.parse(localStorage.getItem('user') || '{}');
  const hasCatalogManage = Boolean(
    currentUser.is_superadmin || (currentUser.permissions || []).includes('catalog.manage')
  );
  const hasCashConceptManage = canManageCashConcepts(currentUser);
  const currentUserAvatar = localStorage.getItem(`user_avatar_${currentUser.id}`) || `https://i.pravatar.cc/150?u=${currentUser.id}`;
  const allowBranchSelection = canSelectAnyBranch(currentUser);

  useEffect(() => {
    fetchApi<Array<{ id: string; name: string; status: string }>>('/branches')
      .then((data) => {
        const visibleBranches = allowBranchSelection || !currentUser.assigned_branch_id
          ? data
          : data.filter((branch) => branch.id === currentUser.assigned_branch_id);
        setBranches(visibleBranches);
        const current = resolveBranchId(currentUser);
        const validCurrent = visibleBranches.some((branch) => branch.id === current);
        const nextBranchId = validCurrent
          ? current
          : currentUser.assigned_branch_id || visibleBranches.find((branch) => branch.status === 'active')?.id || visibleBranches[0]?.id || '';
        if (nextBranchId) setCanonicalBranchId(nextBranchId);
        setBranchId(nextBranchId);
      })
      .catch(() => setBranches([]))
      .finally(() => setBranchReady(true));
  }, [allowBranchSelection, currentUser.assigned_branch_id]);

  const changeBranch = (nextBranchId: string) => {
    setCanonicalBranchId(nextBranchId);
    setBranchId(nextBranchId);
    window.location.reload();
  };

  const openProfileModal = () => {
    setProfileData({
      display_name: currentUser.display_name || '',
      email: currentUser.email || '',
      password: ''
    });
    setProfileAvatar(localStorage.getItem(`user_avatar_${currentUser.id}`) || '');
    setIsProfileModalOpen(true);
  };

  const handleAvatarChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onloadend = async () => {
        try {
          const compressed = await compressImage(reader.result as string);
          setProfileAvatar(compressed);
        } catch (err) {
          console.error("Error compressing image:", err);
          setProfileAvatar(reader.result as string);
        }
      };
      reader.readAsDataURL(file);
    }
  };

  const saveProfile = async () => {
    if (!currentUser.id) return;
    setIsSavingProfile(true);
    try {
      const payload: any = {
        display_name: profileData.display_name,
        email: profileData.email,
      };
      if (profileData.password.trim()) {
        payload.password = profileData.password;
      }
      
      const response = await fetchApi(`/users/${currentUser.id}`, {
        method: 'PUT',
        body: JSON.stringify(payload)
      });
      
      if (response) {
        const updatedUser = {
          ...currentUser,
          display_name: profileData.display_name,
          email: profileData.email
        };
        localStorage.setItem('user', JSON.stringify(updatedUser));
        
        if (profileAvatar) {
          localStorage.setItem(`user_avatar_${currentUser.id}`, profileAvatar);
        } else {
          localStorage.removeItem(`user_avatar_${currentUser.id}`);
        }
        
        setIsProfileModalOpen(false);
        window.location.reload();
      }
    } catch (err) {
      console.error(err);
      alert('Error al guardar el perfil');
    } finally {
      setIsSavingProfile(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('auth_token');
    localStorage.removeItem('user');
    sessionStorage.removeItem('auth_token');
    navigate('/login');
  };

  // Main Categories in Sidebar (POS-SaaS Lean Hub)
  const mainCategories: MainCategoryItem[] = [
    {
      path: '/',
      label: 'Panel Principal',
      icon: <LayoutDashboard size={20} />,
      matchingPrefixes: ['/overview'],
    },
    {
      path: '/pos-app',
      label: 'Punto de Venta POS',
      icon: <ShoppingCart size={20} style={{ color: '#10b981' }} />,
      highlight: true,
      matchingPrefixes: [],
    },
    {
      path: '/catalog',
      label: 'Catálogo y Precios',
      icon: <Package size={20} />,
      matchingPrefixes: [
        '/catalog',
        '/products',
        '/categories',
        '/variations',
        '/ingredient-extras',
      ],
    },
    {
      path: '/branches-hub',
      label: 'Sucursales y Canales',
      icon: <Store size={20} />,
      badge: 'Uber/DiDi',
      matchingPrefixes: [
        '/branches-hub',
        '/branches',
        '/drivers',
        '/integrations',
        '/invoicing',
      ],
    },
    {
      path: '/reports-hub',
      label: 'Cajas y Reportes',
      icon: <BarChart2 size={20} />,
      matchingPrefixes: [
        '/reports-hub',
        '/reports',
        '/analytics',
        '/sales-monitor',
        '/historical-reports',
        '/orders',
        '/cash-concepts',
        '/waste',
      ],
    },
    {
      path: '/admin-access-hub',
      label: 'Equipo y Cajeros',
      icon: <Users size={20} />,
      matchingPrefixes: [
        '/admin-access-hub',
        '/users',
        '/roles',
        '/customers',
      ],
    },
    ...(currentUser.is_superadmin && !localStorage.getItem('impersonation_info')
      ? [
          {
            path: '/superadmin',
            label: 'Consola SaaS Master',
            icon: <Crown size={20} color="#f59e0b" />,
            badge: 'VIP',
            matchingPrefixes: ['/superadmin'],
          },
        ]
      : []),
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', width: '100vw' }}>
      <ImpersonationBanner />
      <div className="admin-layout" style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
      {/* Dark Admin Sidebar */}
      <div className="admin-sidebar" style={{ width: isCollapsed ? '80px' : '260px', transition: 'width 0.3s', display: 'flex', flexDirection: 'column' }}>
        <div className="admin-sidebar-logo" style={{ display: 'flex', justifyContent: isCollapsed ? 'center' : 'space-between', alignItems: 'center', padding: isCollapsed ? '24px 0' : '24px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div className="admin-sidebar-logo-icon" style={{ background: 'transparent', fontSize: '1.5rem', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              🥝
            </div>
            {!isCollapsed && <span style={{ fontWeight: 700, fontSize: '1.15rem', letterSpacing: '-0.02em' }}>RestaurantOS</span>}
          </div>
          <button 
            onClick={() => setIsCollapsed(!isCollapsed)}
            style={{ background: 'transparent', border: 'none', color: '#fff', cursor: 'pointer', padding: 0, display: isCollapsed ? 'none' : 'block' }}
          >
            <ChevronLeft size={20} />
          </button>
        </div>
        
        {isCollapsed && (
          <div style={{ textAlign: 'center', paddingBottom: '16px' }}>
            <button 
              onClick={() => setIsCollapsed(false)}
              style={{ background: 'transparent', border: 'none', color: '#fff', cursor: 'pointer', padding: 0 }}
            >
              <ChevronRight size={20} />
            </button>
          </div>
        )}

        {/* Categories List (Clean POS Style) */}
        <div style={{ flex: 1, overflowY: 'auto', paddingTop: '8px', paddingBottom: '16px', display: 'flex', flexDirection: 'column', gap: '4px', paddingLeft: isCollapsed ? '8px' : '12px', paddingRight: isCollapsed ? '8px' : '12px' }}>
          {mainCategories.map((item) => {
            const isExact = location.pathname === item.path;
            const isChildActive = item.matchingPrefixes.some((prefix) =>
              location.pathname === prefix || location.pathname.startsWith(prefix + '/')
            );
            const isActive = isExact || isChildActive;

            return (
              <button
                type="button"
                key={item.path}
                className={`admin-nav-item ${isActive ? 'active' : ''} ${item.highlight ? 'highlight' : ''}`}
                aria-current={isActive ? 'page' : undefined}
                onClick={() => {
                  if (item.path === '/pos-app') {
                    void redirectToPos('pos').catch(() => navigate('/login'));
                  } else {
                    navigate(item.path);
                  }
                }}
                style={{
                  justifyContent: isCollapsed ? 'center' : 'flex-start',
                  padding: isCollapsed ? '12px 0' : '12px 16px',
                  fontSize: '0.92rem',
                  borderRadius: '12px',
                  marginBottom: '2px',
                }}
                title={isCollapsed ? item.label : undefined}
              >
                <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minWidth: '24px' }}>
                  {item.icon}
                </span>
                {!isCollapsed && (
                  <span style={{ flex: 1, textAlign: 'left', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', fontWeight: isActive ? 600 : 500 }}>
                    {item.label}
                  </span>
                )}
                {!isCollapsed && item.badge && (
                  <span style={{ fontSize: '0.68rem', padding: '2px 7px', background: '#10b981', color: '#fff', borderRadius: '10px', fontWeight: 800 }}>
                    {item.badge}
                  </span>
                )}
              </button>
            );
          })}
        </div>
        
        {/* Configuración & Logout at the bottom */}
        <div style={{ padding: '12px 12px', borderTop: '1px solid rgba(255,255,255,0.1)' }}>
           <div 
             className={`admin-nav-item ${location.pathname === '/branches' ? 'active' : ''}`}
             onClick={() => navigate('/branches')}
             style={{ justifyContent: isCollapsed ? 'center' : 'flex-start', padding: isCollapsed ? '12px 0' : '10px 16px', borderRadius: '12px' }}
             title={isCollapsed ? 'Configuración' : undefined}
           >
             <Settings size={20} />
             {!isCollapsed && <span>Configuración</span>}
           </div>
           <div 
             className="admin-nav-item"
             onClick={handleLogout}
             style={{ justifyContent: isCollapsed ? 'center' : 'flex-start', padding: isCollapsed ? '12px 0' : '10px 16px', color: '#ef4444', borderRadius: '12px', marginTop: '2px' }}
             title={isCollapsed ? 'Cerrar sesión' : undefined}
           >
             <LogOut size={20} style={{ color: '#ef4444' }} />
             {!isCollapsed && <span style={{ color: '#ef4444' }}>Cerrar sesión</span>}
           </div>
        </div>
      </div>

      <div className="admin-main">
        {/* Topbar */}
        <header className="admin-topbar">
          <div style={{ position: 'relative' }}>
            <Search size={18} style={{ position: 'absolute', left: 16, top: '50%', transform: 'translateY(-50%)', color: 'var(--admin-text-muted)' }} />
            <input 
              type="text" 
              placeholder="Buscar insumos, productos, folios..."
              className="admin-search-input"
            />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            {!location.pathname.startsWith('/superadmin') && (
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--admin-text-muted)', fontSize: 13 }}>
                <Store size={17} />
                <select
                  aria-label="Sucursal activa"
                  value={branchId}
                  onChange={(event) => changeBranch(event.target.value)}
                  disabled={!allowBranchSelection || branches.length < 2}
                  style={{ minWidth: 180, padding: '9px 12px', border: '1px solid var(--color-border)', borderRadius: 8, background: '#fff' }}
                >
                  {branches.length === 0 && <option value="">Sin sucursal</option>}
                  {branches.map((branch) => <option key={branch.id} value={branch.id}>{branch.name}</option>)}
                </select>
              </label>
            )}
            <button style={{ background: '#fff', border: 'none', borderRadius: '50%', width: 40, height: 40, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: 'var(--admin-text-muted)', boxShadow: 'var(--admin-card-shadow)' }}><Bell size={18} /></button>
            {hasCatalogManage && <button type="button" aria-label="Abrir asistente de configuración" title="Asistente de configuración" onClick={() => setIsAssistantOpen(true)} style={{ background: '#fff', border: 'none', borderRadius: '50%', width: 40, height: 40, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: 'var(--admin-text-muted)', boxShadow: 'var(--admin-card-shadow)' }}><UserRound size={18} /></button>}
            <div 
              onClick={openProfileModal}
              style={{ width: 40, height: 40, borderRadius: '50%', backgroundColor: 'var(--admin-accent)', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 600, overflow: 'hidden', cursor: 'pointer', border: '2px solid var(--admin-accent)' }}
              title="Editar mi perfil"
            >
              <img src={currentUserAvatar} alt="Admin" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
            </div>
          </div>
        </header>

        {/* Main Content Area */}
        <div className="admin-content">
          <CategorySubNav />
          {branchReady ? <Outlet /> : <div style={{ padding: 32 }}>Cargando contexto de sucursal...</div>}
        </div>
      </div>

      <Modal isOpen={isProfileModalOpen} onClose={() => setIsProfileModalOpen(false)} title="Mi Cuenta">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Avatar Upload Preview */}
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <div style={{ position: 'relative', width: 100, height: 100, borderRadius: '50%', overflow: 'hidden', background: '#e2e8f0', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              {profileAvatar ? (
                <img src={profileAvatar} alt="Avatar" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
              ) : (
                <Users size={48} style={{ color: '#94a3b8' }} />
              )}
              <label style={{ position: 'absolute', bottom: 0, left: 0, right: 0, height: 32, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: '#fff' }}>
                <Camera size={16} />
                <input type="file" accept="image/*" onChange={handleAvatarChange} style={{ display: 'none' }} />
              </label>
            </div>
            <span style={{ fontSize: '0.875rem', color: 'var(--admin-text-muted)' }}>Sube una foto de perfil</span>
          </div>

          <div>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500, fontSize: '0.875rem' }}>Nombre a mostrar</label>
            <Input value={profileData.display_name} onChange={(e: any) => setProfileData({...profileData, display_name: e.target.value})} />
          </div>

          <div>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500, fontSize: '0.875rem' }}>Correo electrónico</label>
            <Input value={profileData.email} onChange={(e: any) => setProfileData({...profileData, email: e.target.value})} />
          </div>

          <div>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500, fontSize: '0.875rem' }}>Nueva contraseña (dejar en blanco para conservar la actual)</label>
            <Input type="password" value={profileData.password} onChange={(e: any) => setProfileData({...profileData, password: e.target.value})} />
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12, marginTop: 16 }}>
            <Button variant="secondary" onClick={() => setIsProfileModalOpen(false)}>Cancelar</Button>
            <Button variant="primary" onClick={saveProfile} disabled={isSavingProfile}>
              {isSavingProfile ? 'Guardando...' : 'Guardar Cambios'}
            </Button>
          </div>
        </div>
      </Modal>
      <AdminAssistantPanel
        open={isAssistantOpen}
        onClose={() => setIsAssistantOpen(false)}
        branchId={branchId}
        branchName={branches.find((branch) => branch.id === branchId)?.name || 'Sucursal'}
      />
      {proposalId && <AdminProposalReview proposalId={proposalId} onClose={() => navigate(`${location.pathname}${location.search.replace(/([?&])admin_ai_proposal=[^&]*&?/, '$1').replace(/[?&]$/, '')}`)} />}
      </div>
    </div>
  );
};

export default AdminLayout;
