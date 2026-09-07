import React, { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Card, Button, Input, Select } from '@restaurantos/ui';
import { fetchApi, ApiError } from '@restaurantos/api-client';
import { Lock, Mail, User, Store, Phone, Sparkles, ArrowRight } from 'lucide-react';
import { setCanonicalBranchId } from '../../lib/branchContext';

interface SignupResponse {
  token: string;
  organization: {
    id: string;
    name: string;
    slug: string;
    plan: string;
    trial_ends_at: string;
  };
  branch: {
    id: string;
    name: string;
    slug?: string;
  };
  user: {
    id: string;
    email: string;
    display_name: string;
    roles: string[];
    permissions?: string[];
  };
}

export const Register: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [restaurantName, setRestaurantName] = useState('');
  const [ownerName, setOwnerName] = useState('');
  const [ownerEmail, setOwnerEmail] = useState('');
  const [password, setPassword] = useState('');
  const [ownerPhone, setOwnerPhone] = useState('');
  const [businessType, setBusinessType] = useState('restaurant');
  const [plan, setPlan] = useState(() => {
    const requested = searchParams.get('plan');
    return requested === 'starter' || requested === 'professional' || requested === 'trial' ? requested : 'trial';
  });
  const [branchName, setBranchName] = useState('Matriz');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSignup = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (password.length < 8) {
      setError('La contraseña debe tener al menos 8 caracteres');
      return;
    }

    setLoading(true);

    try {
      const response = await fetchApi<SignupResponse>('/auth/signup', {
        method: 'POST',
        body: JSON.stringify({
          restaurant_name: restaurantName.trim(),
          owner_name: ownerName.trim(),
          owner_email: ownerEmail.trim().toLowerCase(),
          password,
          owner_phone: ownerPhone.trim() || undefined,
          business_type: businessType,
          plan,
          branch_name: branchName.trim() || 'Matriz',
        }),
      });

      localStorage.setItem('auth_token', response.token);
      localStorage.setItem('user', JSON.stringify(response.user));
      if (response.branch?.id) {
        setCanonicalBranchId(response.branch.id);
      }
      if (!localStorage.getItem('pos_register_id')) {
        localStorage.setItem('pos_register_id', 'CAJA-01');
      }

      // Navigate to admin overview
      navigate('/');
    } catch (err: any) {
      if (err instanceof ApiError) {
        if (err.status === 409 || err.message?.includes('already registered') || err.message?.includes('email_already_exists')) {
          setError('El correo electrónico ya se encuentra registrado. Por favor inicia sesión.');
        } else {
          setError(err.message || 'Error al procesar el registro');
        }
      } else {
        setError('Error de conexión con el servidor. Intenta nuevamente.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      minHeight: '100vh',
      backgroundColor: 'var(--color-bg)',
      padding: '24px 16px',
    }}>
      <Card style={{ maxWidth: 520, width: '100%', padding: '32px 28px' }}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <div style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            background: 'rgba(16, 185, 129, 0.12)',
            color: '#10b981',
            padding: '4px 12px',
            borderRadius: 9999,
            fontSize: '0.75rem',
            fontWeight: 700,
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
            marginBottom: 12,
          }}>
            <Sparkles size={14} /> 14 Días de Prueba Gratis
          </div>
          <h1 style={{ fontSize: '1.65rem', fontWeight: 800, color: 'var(--color-text, #0f172a)', margin: '0 0 6px' }}>
            Registra tu Restaurante
          </h1>
          <p style={{ color: 'var(--color-text-muted, #64748b)', fontSize: '0.9rem', margin: 0 }}>
            Sin tarjeta de crédito requerida. Configuración instantánea en 1 minuto.
          </p>
        </div>

        <form onSubmit={handleSignup} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {error && (
            <div style={{
              padding: 12,
              backgroundColor: 'var(--color-red-light, #fee2e2)',
              color: 'var(--color-red, #b91c1c)',
              borderRadius: 8,
              fontSize: '0.875rem',
              fontWeight: 500,
            }}>
              {error}
            </div>
          )}

          <div>
            <label style={{ display: 'block', marginBottom: 6, fontSize: '0.85rem', fontWeight: 600 }}>
              Nombre del Restaurante o Marca *
            </label>
            <div style={{ position: 'relative' }}>
              <Store size={18} style={{ position: 'absolute', left: 12, top: 11, color: 'var(--color-text-muted)' }} />
              <Input
                type="text"
                value={restaurantName}
                onChange={(e) => setRestaurantName(e.target.value)}
                placeholder="Ej. Tacos El Pastor, Café Central..."
                style={{ paddingLeft: 40, width: '100%' }}
                required
              />
            </div>
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: 6, fontSize: '0.85rem', fontWeight: 600 }}>
              Plan inicial
            </label>
            <Select value={plan} onChange={(e) => setPlan(e.target.value)} style={{ width: '100%' }}>
              <option value="trial">Prueba gratuita de 14 días</option>
              <option value="starter">Starter</option>
              <option value="professional">Professional</option>
            </Select>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div>
              <label style={{ display: 'block', marginBottom: 6, fontSize: '0.85rem', fontWeight: 600 }}>
                Tipo de Negocio
              </label>
              <Select
                value={businessType}
                onChange={(e) => setBusinessType(e.target.value)}
                style={{ width: '100%' }}
              >
                <option value="restaurant">Restaurante</option>
                <option value="cafe">Cafetería</option>
                <option value="taqueria">Taquería</option>
                <option value="pizzeria">Pizzería</option>
                <option value="bar">Bar / Cantina</option>
                <option value="dark_kitchen">Dark Kitchen</option>
                <option value="bakery">Panadería / Repostería</option>
                <option value="other">Otro</option>
              </Select>
            </div>

            <div>
              <label style={{ display: 'block', marginBottom: 6, fontSize: '0.85rem', fontWeight: 600 }}>
                Sucursal Inicial
              </label>
              <Input
                type="text"
                value={branchName}
                onChange={(e) => setBranchName(e.target.value)}
                placeholder="Matriz"
                style={{ width: '100%' }}
              />
            </div>
          </div>

          <div>
            <label style={{ display: 'block', marginBottom: 6, fontSize: '0.85rem', fontWeight: 600 }}>
              Tu Nombre Completo *
            </label>
            <div style={{ position: 'relative' }}>
              <User size={18} style={{ position: 'absolute', left: 12, top: 11, color: 'var(--color-text-muted)' }} />
              <Input
                type="text"
                value={ownerName}
                onChange={(e) => setOwnerName(e.target.value)}
                placeholder="Carlos Gómez"
                style={{ paddingLeft: 40, width: '100%' }}
                required
              />
            </div>
          </div>

          <div>
            <label style={{ display: 'block', marginBottom: 6, fontSize: '0.85rem', fontWeight: 600 }}>
              Correo Electrónico (será tu usuario admin) *
            </label>
            <div style={{ position: 'relative' }}>
              <Mail size={18} style={{ position: 'absolute', left: 12, top: 11, color: 'var(--color-text-muted)' }} />
              <Input
                type="email"
                value={ownerEmail}
                onChange={(e) => setOwnerEmail(e.target.value)}
                placeholder="carlos@example.com"
                style={{ paddingLeft: 40, width: '100%' }}
                required
              />
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div>
              <label style={{ display: 'block', marginBottom: 6, fontSize: '0.85rem', fontWeight: 600 }}>
                Contraseña *
              </label>
              <div style={{ position: 'relative' }}>
                <Lock size={18} style={{ position: 'absolute', left: 12, top: 11, color: 'var(--color-text-muted)' }} />
                <Input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Mín. 8 caracteres"
                  style={{ paddingLeft: 40, width: '100%' }}
                  required
                />
              </div>
            </div>

            <div>
              <label style={{ display: 'block', marginBottom: 6, fontSize: '0.85rem', fontWeight: 600 }}>
                Teléfono / WhatsApp
              </label>
              <div style={{ position: 'relative' }}>
                <Phone size={18} style={{ position: 'absolute', left: 12, top: 11, color: 'var(--color-text-muted)' }} />
                <Input
                  type="tel"
                  value={ownerPhone}
                  onChange={(e) => setOwnerPhone(e.target.value)}
                  placeholder="+52 55 1234 5678"
                  style={{ paddingLeft: 40, width: '100%' }}
                />
              </div>
            </div>
          </div>

          <Button
            type="submit"
            variant="primary"
            style={{
              width: '100%',
              marginTop: 10,
              padding: '12px 20px',
              fontSize: '1rem',
              fontWeight: 700,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 8,
            }}
            disabled={loading}
          >
            {loading ? 'Creando tu cuenta...' : (
              <>Comenzar Prueba Gratis <ArrowRight size={18} /></>
            )}
          </Button>

          <div style={{
            textAlign: 'center',
            marginTop: 14,
            fontSize: '0.875rem',
            color: 'var(--color-text-muted, #64748b)',
          }}>
            ¿Ya tienes una cuenta registrada?{' '}
            <a
              href="/login"
              onClick={(e) => {
                e.preventDefault();
                navigate('/login');
              }}
              style={{
                color: 'var(--color-blue, #2563eb)',
                textDecoration: 'none',
                fontWeight: 600,
              }}
            >
              Iniciar Sesión
            </a>
          </div>
        </form>
      </Card>
    </div>
  );
};

export default Register;
