import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, Button, Input } from '@restaurantos/ui';
import { fetchApi, ApiError } from '@restaurantos/api-client';
import { Lock, Mail } from 'lucide-react';
import { setCanonicalBranchId } from '../../lib/branchContext';
import { redirectToPos } from '../../lib/posHandoff';

export const Login = () => {
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const response = await fetchApi<{ token: string; user: any }>('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      });
      
      localStorage.setItem('auth_token', response.token);
      localStorage.setItem('user', JSON.stringify(response.user));
      if (response.user.assigned_branch_id) {
        setCanonicalBranchId(response.user.assigned_branch_id);
      }
      if (!localStorage.getItem('pos_register_id')) {
        localStorage.setItem('pos_register_id', 'CAJA-01');
      }

      const roles: string[] = response.user.roles || [];
      const permissions: string[] = response.user.permissions || [];
      const isPureCashier = roles.includes('Cajero')
        && roles.length === 1
        && !roles.includes('Cajero Jefe')
        && !roles.includes('Líder')
        && !roles.includes('Supervisor')
        && !roles.includes('Administrador')
        && !roles.includes('Dueño')
        && !permissions.includes('admin.manage')
        && !permissions.includes('dashboard.read')
        && !permissions.includes('branch.admin.access')
        && !permissions.includes('purchases.read')
        && !permissions.includes('inventory.read')
        && !permissions.includes('inventory.waste');

      if (isPureCashier) {
        await redirectToPos('pos');
        return;
      }
      navigate('/');
    } catch (err: any) {
      if (err instanceof ApiError) {
        setError(err.message || 'Error de autenticación');
      } else {
        setError('Error de conexión al servidor');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', backgroundColor: 'var(--color-bg)' }}>
      <Card style={{ width: 400, padding: 32 }}>
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <h1 style={{ fontSize: '1.5rem', color: 'var(--color-blue)', marginBottom: 8 }}>RestaurantOS</h1>
          <p style={{ color: 'var(--color-text-muted)' }}>Ingresa tus credenciales para continuar</p>
        </div>

        <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {error && (
            <div style={{ padding: 12, backgroundColor: 'var(--color-red-light)', color: 'var(--color-red)', borderRadius: 8, fontSize: '0.875rem' }}>
              {error}
            </div>
          )}

          <div>
            <label style={{ display: 'block', marginBottom: 8, fontSize: '0.875rem', fontWeight: 500 }}>Correo electrónico</label>
            <div style={{ position: 'relative' }}>
              <Mail size={18} style={{ position: 'absolute', left: 12, top: 11, color: 'var(--color-text-muted)' }} />
              <Input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="admin@restaurantos.com"
                style={{ paddingLeft: 40, width: '100%' }}
                required
              />
            </div>
          </div>

          <div>
            <label style={{ display: 'block', marginBottom: 8, fontSize: '0.875rem', fontWeight: 500 }}>Contraseña</label>
            <div style={{ position: 'relative' }}>
              <Lock size={18} style={{ position: 'absolute', left: 12, top: 11, color: 'var(--color-text-muted)' }} />
              <Input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                style={{ paddingLeft: 40, width: '100%' }}
                required
              />
            </div>
          </div>

          <Button type="submit" variant="primary" style={{ width: '100%', marginTop: 8 }} disabled={loading}>
            {loading ? 'Ingresando...' : 'Iniciar Sesión'}
          </Button>

          <div style={{
            textAlign: 'center',
            marginTop: 14,
            fontSize: '0.875rem',
            color: 'var(--color-text-muted, #64748b)',
          }}>
            ¿No tienes una cuenta aún?{' '}
            <a
              href="/register"
              onClick={(e) => {
                e.preventDefault();
                navigate('/register');
              }}
              style={{
                color: 'var(--color-blue, #2563eb)',
                textDecoration: 'none',
                fontWeight: 600,
              }}
            >
              Registra tu restaurante (14 días gratis)
            </a>
          </div>
        </form>
      </Card>
    </div>
  );
};

export default Login;
