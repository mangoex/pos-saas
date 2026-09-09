import React, { useState, useEffect } from 'react';
import {
  Store,
  Phone,
  Sparkles,
  Utensils,
  QrCode,
  CheckCircle2,
  ArrowRight,
  ArrowLeft,
  X,
  Smartphone,
  ExternalLink,
  Laptop,
  Check,
} from 'lucide-react';
import { Card, Button, Input, Select } from '@restaurantos/ui';
import { fetchApi } from '@restaurantos/api-client';
import { QRCodeCard } from './QRCodeCard';
import { redirectToPos } from '../../lib/posHandoff';

interface OrganizationProfile {
  id: string;
  name: string;
  slug: string;
  business_type: string;
  owner_name: string;
  owner_email: string;
  owner_phone: string;
  plan: string;
  subscription_status: string;
  trial_ends_at: string | null;
  trial_days_remaining: number;
  mobile_theme: string;
  products_count: number;
  branches: Array<{
    id: string;
    name: string;
    slug: string;
    code: string;
    phone: string;
    public_key: string | null;
  }>;
}

interface OnboardingWizardModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCompleted?: () => void;
}

type OnboardingStatus = { step: 'business' | 'menu' | 'register' | 'complete'; branch: { name: string }; register_name: string | null };
const onboardingTemplate = (businessType: string) => ({
  cafe: 'cafeteria', restaurant: 'general', bar: 'general', dark_kitchen: 'general', bakery: 'general', other: 'general',
}[businessType] || businessType);

export const OnboardingWizardModal: React.FC<OnboardingWizardModalProps> = ({
  isOpen,
  onClose,
  onCompleted,
}) => {
  const [step, setStep] = useState<1 | 2 | 3 | 4>(1);
  const [loading, setLoading] = useState(false);
  const [profile, setProfile] = useState<OrganizationProfile | null>(null);

  // Form State Step 1
  const [restaurantName, setRestaurantName] = useState('');
  const [businessType, setBusinessType] = useState('restaurant');
  const [whatsappPhone, setWhatsappPhone] = useState('');
  const [mobileTheme, setMobileTheme] = useState('light');
  const [registerName, setRegisterName] = useState('CAJA-01');
  const [savingStep1, setSavingStep1] = useState(false);

  // Step 2 Seed State
  const [seedingMenu, setSeedingMenu] = useState(false);
  const [menuSeeded, setMenuSeeded] = useState(false);
  const [seedSuccessMsg, setSeedSuccessMsg] = useState('');
  const [setupError, setSetupError] = useState('');

  // Load organization profile on mount
  useEffect(() => {
    if (isOpen) {
      fetchApi<OnboardingStatus>('/saas/onboarding').then((setup) => {
        setStep(({ business: 1, menu: 2, register: 3, complete: 4 }[setup.step] ?? 1) as 1 | 2 | 3 | 4);
        setRegisterName(setup.register_name || 'CAJA-01');
      }).catch(() => undefined);
      fetchApi<OrganizationProfile>('/organization/profile')
        .then((data) => {
          setProfile(data);
          setRestaurantName(data.name || '');
          setBusinessType(data.business_type || 'restaurant');
          setWhatsappPhone(data.owner_phone || '');
          setMobileTheme(data.mobile_theme || 'light');
          if (data.products_count > 0) {
            setMenuSeeded(true);
          }
        })
        .catch((err) => {
          console.warn('Could not load organization profile:', err);
        });
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSaveStep1 = async (e: React.FormEvent) => {
    e.preventDefault();
    setSavingStep1(true);
    try {
      const updated = await fetchApi<OrganizationProfile>('/organization/profile', {
        method: 'PATCH',
        body: JSON.stringify({
          name: restaurantName.trim(),
          business_type: businessType,
          owner_phone: whatsappPhone.trim() || undefined,
          mobile_theme: mobileTheme,
        }),
      });
      setProfile(updated);
      await fetchApi<OnboardingStatus>('/saas/onboarding', {
        method: 'PUT',
        body: JSON.stringify({
          step: 'business', business_name: restaurantName.trim(), branch_name: updated.branches?.[0]?.name || 'Matriz',
          phone: whatsappPhone.trim() || undefined, timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        }),
      });
      setStep(2);
    } catch (err) {
      console.error('Error saving profile step 1:', err);
    } finally {
      setSavingStep1(false);
    }
  };

  const handleSeedStarterMenu = async () => {
    setSeedingMenu(true);
    setSeedSuccessMsg('');
    setSetupError('');
    try {
      await fetchApi<OnboardingStatus>('/saas/onboarding', {
        method: 'PUT',
        body: JSON.stringify({ step: 'menu', business_type: onboardingTemplate(businessType) }),
      });
      setMenuSeeded(true);
      setSeedSuccessMsg('¡Menú inicial importado exitosamente con platillos y precios!');
      // Refresh profile to reflect new product count
      const updated = await fetchApi<OrganizationProfile>('/organization/profile');
      setProfile(updated);
    } catch (err: any) {
      console.warn('Could not seed menu automatically:', err);
      setSeedSuccessMsg('No pudimos guardar el menú. Inténtalo de nuevo.');
    } finally {
      setSeedingMenu(false);
    }
  };

  const handleContinueToQr = async () => {
    setSeedingMenu(true);
    setSetupError('');
    try {
      await fetchApi<OnboardingStatus>('/saas/onboarding', {
        method: 'PUT',
        body: JSON.stringify({ step: 'menu', business_type: 'blank' }),
      });
      setStep(3);
    } catch {
      setSetupError('No pudimos guardar el estado del menú. Inténtalo de nuevo.');
    } finally {
      setSeedingMenu(false);
    }
  };

  const persistRegisterStep = async (): Promise<boolean> => {
    setSetupError('');
    try {
      await fetchApi<OnboardingStatus>('/saas/onboarding', {
        method: 'PUT', body: JSON.stringify({ step: 'register', register_name: registerName.trim() || 'CAJA-01' }),
      });
      return true;
    } catch {
      setSetupError('No pudimos guardar el identificador de caja. Inténtalo de nuevo.');
      return false;
    }
  };

  const handleAdvanceToFinish = async () => {
    if (await persistRegisterStep()) setStep(4);
  };

  const handleFinishOnboarding = async () => {
    if (await persistRegisterStep()) {
      if (onCompleted) onCompleted();
      onClose();
    }
  };

  const handleOpenPos = async () => {
    if (await persistRegisterStep()) {
      if (onCompleted) onCompleted();
      onClose();
      await redirectToPos('pos');
    }
  };

  const currentSlug = profile?.slug || 'matriz';

  return (
    <div style={{
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      backgroundColor: 'rgba(15, 23, 42, 0.75)',
      backdropFilter: 'blur(6px)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 9999,
      padding: 16,
    }}>
      <div style={{
        maxWidth: 680,
        width: '100%',
        maxHeight: '90vh',
        overflowY: 'auto',
        backgroundColor: '#fff',
        borderRadius: 20,
        boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
        display: 'flex',
        flexDirection: 'column',
      }}>
        {/* Modal Header */}
        <div style={{
          padding: '24px 28px 16px',
          borderBottom: '1px solid #f1f5f9',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}>
          <div>
            <div style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              background: 'rgba(37, 99, 235, 0.1)',
              color: '#2563eb',
              padding: '3px 10px',
              borderRadius: 9999,
              fontSize: '0.75rem',
              fontWeight: 700,
              textTransform: 'uppercase',
              letterSpacing: '0.04em',
              marginBottom: 6,
            }}>
              <Sparkles size={14} /> Configuración Inicial en 3 Minutos
            </div>
            <h2 style={{ margin: 0, fontSize: '1.4rem', fontWeight: 800, color: '#0f172a' }}>
              Bienvenido a tu Restaurante en Omnipos
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            style={{
              background: '#f8fafc',
              border: 'none',
              borderRadius: '50%',
              width: 36,
              height: 36,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: 'pointer',
              color: '#64748b',
            }}
          >
            <X size={18} />
          </button>
        </div>

        {setupError && <p role="alert" style={{ margin: '12px 28px 0', color: '#b91c1c', fontSize: '0.9rem' }}>{setupError}</p>}

        {/* Stepper Progress Indicator */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '14px 28px',
          background: '#f8fafc',
          borderBottom: '1px solid #e2e8f0',
        }}>
          {[
            { num: 1, label: 'Identidad' },
            { num: 2, label: 'Menú' },
            { num: 3, label: 'Código QR' },
            { num: 4, label: 'Listo' },
          ].map((s) => {
            const isCompleted = s.num < step;
            const isCurrent = s.num === step;
            return (
              <div
                key={s.num}
                onClick={() => isCompleted && setStep(s.num as any)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  cursor: isCompleted ? 'pointer' : 'default',
                  opacity: isCurrent || isCompleted ? 1 : 0.5,
                }}
              >
                <div style={{
                  width: 28,
                  height: 28,
                  borderRadius: '50%',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '0.8rem',
                  fontWeight: 700,
                  backgroundColor: isCompleted ? '#10b981' : isCurrent ? '#2563eb' : '#cbd5e1',
                  color: '#fff',
                }}>
                  {isCompleted ? <Check size={16} /> : s.num}
                </div>
                <span style={{ fontSize: '0.85rem', fontWeight: isCurrent ? 700 : 500, color: '#1e293b' }}>
                  {s.label}
                </span>
              </div>
            );
          })}
        </div>

        {/* Modal Body */}
        <div style={{ padding: '24px 28px', flex: 1 }}>
          {/* STEP 1: Identidad y WhatsApp */}
          {step === 1 && (
            <form onSubmit={handleSaveStep1} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <p style={{ color: '#64748b', fontSize: '0.9rem', margin: '0 0 8px' }}>
                Personaliza el nombre de tu restaurante y el número de WhatsApp donde quieres recibir las notificaciones y comandas de tus clientes.
              </p>

              <div>
                <label style={{ display: 'block', marginBottom: 6, fontSize: '0.85rem', fontWeight: 600 }}>
                  Nombre del Restaurante / Marca *
                </label>
                <div style={{ position: 'relative' }}>
                  <Store size={18} style={{ position: 'absolute', left: 12, top: 11, color: '#94a3b8' }} />
                  <Input
                    type="text"
                    value={restaurantName}
                    onChange={(e) => setRestaurantName(e.target.value)}
                    placeholder="Ej. Tacos Don Pancho"
                    style={{ paddingLeft: 40, width: '100%' }}
                    required
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div>
                  <label style={{ display: 'block', marginBottom: 6, fontSize: '0.85rem', fontWeight: 600 }}>
                    Giro Comercial
                  </label>
                  <Select
                    value={businessType}
                    onChange={(e) => setBusinessType(e.target.value)}
                    style={{ width: '100%' }}
                  >
                    <option value="restaurant">Restaurante General</option>
                    <option value="taqueria">Taquería</option>
                    <option value="cafe">Cafetería</option>
                    <option value="pizzeria">Pizzería</option>
                    <option value="bar">Bar / Snacks</option>
                    <option value="dark_kitchen">Dark Kitchen</option>
                    <option value="bakery">Panadería</option>
                  </Select>
                </div>

                <div>
                  <label style={{ display: 'block', marginBottom: 6, fontSize: '0.85rem', fontWeight: 600 }}>
                    Tema del Menú Digital
                  </label>
                  <Select
                    value={mobileTheme}
                    onChange={(e) => setMobileTheme(e.target.value)}
                    style={{ width: '100%' }}
                  >
                    <option value="light">Claro Elegante (Día)</option>
                    <option value="dark">Oscuro Cálido (Nocturno)</option>
                  </Select>
                </div>
              </div>

              <div>
                <label style={{ display: 'block', marginBottom: 6, fontSize: '0.85rem', fontWeight: 600 }}>
                  Número de WhatsApp para Comandas
                </label>
                <div style={{ position: 'relative' }}>
                  <Phone size={18} style={{ position: 'absolute', left: 12, top: 11, color: '#94a3b8' }} />
                  <Input
                    type="tel"
                    value={whatsappPhone}
                    onChange={(e) => setWhatsappPhone(e.target.value)}
                    placeholder="+52 55 1234 5678"
                    style={{ paddingLeft: 40, width: '100%' }}
                  />
                </div>
                <span style={{ fontSize: '0.75rem', color: '#64748b', display: 'block', marginTop: 4 }}>
                  Los clientes que hagan pedidos en tu menú web podrán confirmar directo a este número con su folio.
                </span>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 12 }}>
                <Button
                  type="submit"
                  variant="primary"
                  disabled={savingStep1}
                  style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 24px', fontWeight: 700 }}
                >
                  {savingStep1 ? 'Guardando...' : <>Siguiente: Cargar Menú <ArrowRight size={18} /></>}
                </Button>
              </div>
            </form>
          )}

          {/* STEP 2: Carga Rápida de Menú */}
          {step === 2 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <p style={{ color: '#64748b', fontSize: '0.9rem', margin: '0 0 4px' }}>
                Tu menú es el corazón de tu negocio. Puedes cargar una plantilla de platillos de muestra para empezar de inmediato o continuar con tu propio menú.
              </p>

              {seedSuccessMsg && (
                <div style={{
                  padding: 12,
                  backgroundColor: 'rgba(16, 185, 129, 0.12)',
                  color: '#065f46',
                  borderRadius: 10,
                  fontSize: '0.875rem',
                  fontWeight: 600,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                }}>
                  <CheckCircle2 size={18} color="#10b981" />
                  {seedSuccessMsg}
                </div>
              )}

              <div style={{
                background: '#f8fafc',
                border: '1.5px dashed #cbd5e1',
                borderRadius: 16,
                padding: '28px 20px',
                textAlign: 'center',
              }}>
                <div style={{
                  width: 52,
                  height: 52,
                  borderRadius: '50%',
                  background: 'rgba(37, 99, 235, 0.1)',
                  color: '#2563eb',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  margin: '0 auto 12px',
                }}>
                  <Utensils size={26} />
                </div>
                <h3 style={{ margin: '0 0 6px', fontSize: '1.15rem', fontWeight: 800, color: '#0f172a' }}>
                  {profile && profile.products_count > 0 ? 'Menú Activo' : '¿Quieres cargar un menú de inicio en 1 clic?'}
                </h3>
                <p style={{ margin: '0 0 16px', color: '#64748b', fontSize: '0.85rem', maxWidth: 460, marginInline: 'auto' }}>
                  {profile && profile.products_count > 0
                    ? `Actualmente tienes ${profile.products_count} platillos registrados en tu catálogo listos para la venta.`
                    : `Podemos crear un catálogo inicial con 8-10 platillos populares para ${businessType.toUpperCase()} con precios y fotos listos para editar.`}
                </p>

                <div style={{ display: 'flex', justifyContent: 'center', gap: 12 }}>
                  <Button
                    type="button"
                    variant="primary"
                    disabled={seedingMenu}
                    onClick={handleSeedStarterMenu}
                    style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 700 }}
                  >
                    <Sparkles size={16} />
                    {seedingMenu ? 'Cargando catálogo...' : (profile && profile.products_count > 0 ? 'Recargar Menú de Muestra' : 'Cargar Menú de Muestra')}
                  </Button>
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 16 }}>
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => setStep(1)}
                  style={{ display: 'flex', alignItems: 'center', gap: 6 }}
                >
                  <ArrowLeft size={16} /> Atrás
                </Button>

                <Button
                  type="button"
                  variant="primary"
                  disabled={seedingMenu}
                  onClick={handleContinueToQr}
                  style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 24px', fontWeight: 700 }}
                >
                  {seedingMenu ? 'Guardando menú...' : <>Siguiente: Código QR <ArrowRight size={18} /></>}
                </Button>
              </div>
            </div>
          )}

          {/* STEP 3: Código QR y Menú Digital */}
          {step === 3 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <p style={{ color: '#64748b', fontSize: '0.9rem', margin: 0 }}>
                Este es el código QR oficial de tu restaurante. Puedes imprimirlo para colocarlo en mesas o compartir el enlace en redes sociales.
              </p>

              <QRCodeCard
                restaurantName={restaurantName || profile?.name || 'Tu Restaurante'}
                restaurantSlug={currentSlug}
                whatsappPhone={whatsappPhone}
              />

              <div style={{ textAlign: 'left' }}>
                <label style={{ display: 'block', marginBottom: 6, fontSize: '0.85rem', fontWeight: 600 }}>
                  Identificador de tu primera caja
                </label>
                <Input value={registerName} onChange={(event) => setRegisterName(event.target.value)} placeholder="CAJA-01" style={{ width: '100%' }} />
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 12 }}>
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => setStep(2)}
                  style={{ display: 'flex', alignItems: 'center', gap: 6 }}
                >
                  <ArrowLeft size={16} /> Atrás
                </Button>

                <Button
                  type="button"
                  variant="primary"
                  onClick={handleAdvanceToFinish}
                  style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 24px', fontWeight: 700 }}
                >
                  Siguiente: Finalizar <ArrowRight size={18} />
                </Button>
              </div>
            </div>
          )}

          {/* STEP 4: ¡Todo Listo para Vender! */}
          {step === 4 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 20, textAlign: 'center', padding: '10px 0' }}>
              <div style={{
                width: 68,
                height: 68,
                borderRadius: '50%',
                background: 'rgba(16, 185, 129, 0.12)',
                color: '#10b981',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                margin: '0 auto',
              }}>
                <CheckCircle2 size={40} />
              </div>

              <div>
                <h3 style={{ margin: '0 0 8px', fontSize: '1.5rem', fontWeight: 800, color: '#0f172a' }}>
                  ¡Tu Restaurante está listo para operar!
                </h3>
                <p style={{ margin: 0, color: '#64748b', fontSize: '0.95rem' }}>
                  Tienes <strong>14 días de prueba completa</strong> sin ningún compromiso.
                </p>
              </div>

              {/* Checklist summary */}
              <div style={{
                background: '#f8fafc',
                borderRadius: 14,
                padding: '16px 20px',
                textAlign: 'left',
                display: 'flex',
                flexDirection: 'column',
                gap: 10,
                fontSize: '0.9rem',
                color: '#334155',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Check size={18} color="#10b981" /> Cuenta de Administrador y Empresa Creada
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Check size={18} color="#10b981" /> Menú Digital QR activo con enlace público verificado
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Check size={18} color="#10b981" /> Pedidos directos a WhatsApp conectados
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Check size={18} color="#10b981" /> Terminal Punto de Venta (POS) y Cocina (KDS) listos
                </div>
              </div>

              {/* Action Buttons */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 10 }}>
                <Button
                  type="button"
                  variant="primary"
                  onClick={handleOpenPos}
                  style={{
                    padding: '14px 20px',
                    fontSize: '1rem',
                    fontWeight: 700,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: 8,
                    background: '#10b981',
                    borderColor: '#10b981',
                  }}
                >
                  <Laptop size={18} /> Abrir Punto de Venta (POS)
                </Button>

                <Button
                  type="button"
                  variant="secondary"
                  onClick={handleFinishOnboarding}
                  style={{ padding: '12px 20px', fontSize: '0.95rem', fontWeight: 600 }}
                >
                  Explorar Panel de Administración
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default OnboardingWizardModal;
