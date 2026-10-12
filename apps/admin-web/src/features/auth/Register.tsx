import React, { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { fetchApi, ApiError } from '@restaurantos/api-client';
import { ArrowRight, ShieldCheck } from 'lucide-react';
import { setCanonicalBranchId } from '../../lib/branchContext';
import { PrivacyPolicyModal } from '../legal/PrivacyPolicyModal';
import './Register.css';

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
    if (requested === 'esencial' || requested === 'starter') return 'starter';
    if (requested === 'conecta' || requested === 'professional' || requested === 'pro') return 'conecta';
    if (requested === 'control' || requested === 'enterprise') return 'control';
    return requested === 'trial' ? requested : 'trial';
  });
  const [branchName, setBranchName] = useState('Matriz');
  const [acceptedTerms, setAcceptedTerms] = useState(false);
  const [isLegalModalOpen, setIsLegalModalOpen] = useState(false);
  const [legalModalTab, setLegalModalTab] = useState<'privacy' | 'terms'>('privacy');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSignup = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (!acceptedTerms) {
      setError('Debes aceptar los Términos y Condiciones y el Aviso de Privacidad para continuar.');
      return;
    }

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
    <div className="register-page">
      <div className="register-mobile-aura" aria-hidden="true" />

      <header className="register-mobile-header">
        <div className="register-mobile-header__brand">
          <span>mi menú</span><span className="register-mobile-header__dot">.</span><span>onl</span>
        </div>
        <div className="register-mobile-header__tag">
          <span>TODO</span>
          <span>DESDE</span>
          <span>TU</span>
          <span>CELULAR</span>
          <span className="register-mobile-header__dash" />
        </div>
      </header>

      <div className="register-container">
        <div className="register-card">
          <div className="register-header">
            <span className="register-eyebrow">14 DÍAS DE PRUEBA GRATIS</span>
            <h1 className="register-title">Registra tu restaurante</h1>
            <p className="register-subtitle">
              Sin tarjeta de crédito requerida. Configuración instantánea en 1 minuto.
            </p>
          </div>

          <form onSubmit={handleSignup} className="register-form">
            {error && (
              <div className="register-error">
                {error}
              </div>
            )}

            <div className="register-form-group">
              <label className="register-label">
                Nombre del Restaurante o Marca *
              </label>
              <input
                type="text"
                className="register-input"
                value={restaurantName}
                onChange={(e) => setRestaurantName(e.target.value)}
                placeholder="Ej. Tacos El Pastor, Café Central..."
                required
              />
            </div>

            <div className="register-form-group">
              <label className="register-label">
                Plan inicial
              </label>
              <select
                className="register-select"
                value={plan}
                onChange={(e) => setPlan(e.target.value)}
              >
                <option value="trial">Prueba gratuita de 14 días</option>
                <option value="starter">Esencial — $349/mes</option>
                <option value="conecta">Conecta — $699/mes</option>
                <option value="control">Control — $999/mes</option>
              </select>
            </div>

            <div className="register-grid-2">
              <div className="register-form-group">
                <label className="register-label">
                  Tipo de Negocio
                </label>
                <select
                  className="register-select"
                  value={businessType}
                  onChange={(e) => setBusinessType(e.target.value)}
                >
                  <option value="restaurant">Restaurante</option>
                  <option value="cafe">Cafetería</option>
                  <option value="taqueria">Taquería</option>
                  <option value="pizzeria">Pizzería</option>
                  <option value="bar">Bar / Cantina</option>
                  <option value="dark_kitchen">Dark Kitchen</option>
                  <option value="bakery">Panadería / Repostería</option>
                  <option value="other">Otro</option>
                </select>
              </div>

              <div className="register-form-group">
                <label className="register-label">
                  Sucursal Inicial
                </label>
                <input
                  type="text"
                  className="register-input"
                  value={branchName}
                  onChange={(e) => setBranchName(e.target.value)}
                  placeholder="Matriz"
                />
              </div>
            </div>

            <div className="register-form-group">
              <label className="register-label">
                Tu Nombre Completo *
              </label>
              <input
                type="text"
                className="register-input"
                value={ownerName}
                onChange={(e) => setOwnerName(e.target.value)}
                placeholder="Carlos Gómez"
                required
              />
            </div>

            <div className="register-form-group">
              <label className="register-label">
                Correo Electrónico (será tu usuario admin) *
              </label>
              <input
                type="email"
                className="register-input"
                value={ownerEmail}
                onChange={(e) => setOwnerEmail(e.target.value)}
                placeholder="carlos@example.com"
                required
              />
            </div>

            <div className="register-grid-2">
              <div className="register-form-group">
                <label className="register-label">
                  Contraseña *
                </label>
                <input
                  type="password"
                  className="register-input"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Mín. 8 caracteres"
                  required
                />
              </div>

              <div className="register-form-group">
                <label className="register-label">
                  Teléfono / WhatsApp
                </label>
                <input
                  type="tel"
                  className="register-input"
                  value={ownerPhone}
                  onChange={(e) => setOwnerPhone(e.target.value)}
                  placeholder="+52 55 1234 5678"
                />
              </div>
            </div>

            <div style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: 10,
              marginTop: 6,
              marginBottom: 8,
              padding: '10px 12px',
              backgroundColor: '#f8fafc',
              borderRadius: 8,
              border: '1px solid #e2e8f0',
            }}>
              <input
                type="checkbox"
                id="acceptedTerms"
                checked={acceptedTerms}
                onChange={(e) => setAcceptedTerms(e.target.checked)}
                style={{
                  marginTop: 2,
                  width: 18,
                  height: 18,
                  cursor: 'pointer',
                  accentColor: '#2563eb',
                  flexShrink: 0,
                }}
                required
              />
              <label htmlFor="acceptedTerms" style={{ fontSize: '0.8125rem', color: '#475569', lineHeight: 1.45 }}>
                He leído y acepto los{' '}
                <button
                  type="button"
                  onClick={() => {
                    setLegalModalTab('terms');
                    setIsLegalModalOpen(true);
                  }}
                  style={{
                    background: 'none',
                    border: 'none',
                    padding: 0,
                    color: '#2563eb',
                    fontWeight: 600,
                    cursor: 'pointer',
                    textDecoration: 'underline',
                    fontSize: 'inherit',
                  }}
                >
                  Términos y Condiciones
                </button>{' '}
                y el{' '}
                <button
                  type="button"
                  onClick={() => {
                    setLegalModalTab('privacy');
                    setIsLegalModalOpen(true);
                  }}
                  style={{
                    background: 'none',
                    border: 'none',
                    padding: 0,
                    color: '#2563eb',
                    fontWeight: 600,
                    cursor: 'pointer',
                    textDecoration: 'underline',
                    fontSize: 'inherit',
                  }}
                >
                  Aviso de Privacidad Integral
                </button>
                . Reconozco que los precios, catálogo y calidad de los alimentos son responsabilidad de mi negocio.
              </label>
            </div>

            <button
              type="submit"
              className="register-btn-submit"
              disabled={loading}
            >
              {loading ? 'Creando tu cuenta...' : (
                <>Comenzar Prueba Gratis <ArrowRight size={18} /></>
              )}
            </button>

            <div className="register-login-row">
              ¿Ya tienes una cuenta registrada?{' '}
              <a
                href="/login"
                onClick={(e) => {
                  e.preventDefault();
                  navigate('/login');
                }}
                className="register-login-link"
              >
                Iniciar Sesión
              </a>
            </div>
          </form>
        </div>

        <footer className="register-mobile-footer">
          <span>mi menú onl · Tu operación, conectada.</span>
          <a href="https://mimenu.onl/manual/" target="_blank" rel="noopener noreferrer">
            Manual de uso
          </a>
        </footer>
      </div>

      <PrivacyPolicyModal
        isOpen={isLegalModalOpen}
        onClose={() => setIsLegalModalOpen(false)}
        defaultTab={legalModalTab}
      />
    </div>
  );
};

export default Register;
