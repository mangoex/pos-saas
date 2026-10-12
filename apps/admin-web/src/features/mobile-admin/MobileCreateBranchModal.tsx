import React, { useState } from 'react';
import {
  X,
  Store,
  MapPin,
  Phone,
  Tag,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Plus,
} from 'lucide-react';
import { fetchApi } from '@restaurantos/api-client';

export interface CreatedBranchInfo {
  id: string;
  name: string;
  code?: string;
  status?: string;
}

export interface MobileCreateBranchModalProps {
  isOpen: boolean;
  onClose: () => void;
  onBranchCreated: (newBranch: CreatedBranchInfo) => void;
  existingBranchesCount?: number;
}

export const MobileCreateBranchModal: React.FC<MobileCreateBranchModalProps> = ({
  isOpen,
  onClose,
  onBranchCreated,
  existingBranchesCount = 1,
}) => {
  const [name, setName] = useState('');
  const [code, setCode] = useState('');
  const [codeTouched, setCodeTouched] = useState(false);
  const [phone, setPhone] = useState('');
  const [street, setStreet] = useState('');
  const [exteriorNumber, setExteriorNumber] = useState('');
  const [neighborhood, setNeighborhood] = useState('');
  const [city, setCity] = useState('Culiacán');
  const [state, setState] = useState('Sinaloa');
  const [whatsappEnabled, setWhatsappEnabled] = useState(true);
  const [dineInEnabled, setDineInEnabled] = useState(true);

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  if (!isOpen) return null;

  // Auto-generate suggested code from name
  const handleNameChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setName(val);
    if (!codeTouched) {
      const clean = val
        .trim()
        .toUpperCase()
        .replace(/SUCURSAL\s*/gi, '')
        .replace(/[^A-Z0-9]/g, '')
        .slice(0, 8);
      const fallbackCode = `SUC0${existingBranchesCount + 1}`;
      setCode(clean.length >= 2 ? clean : fallbackCode);
    }
  };

  const handleCodeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setCodeTouched(true);
    const upper = e.target.value.toUpperCase().replace(/[^A-Z0-9-]/g, '').slice(0, 12);
    setCode(upper);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);

    const trimmedName = name.trim();
    const trimmedCode = code.trim().toUpperCase();

    if (!trimmedName) {
      setErrorMessage('Por favor ingresa el nombre de la sucursal.');
      return;
    }
    if (!trimmedCode) {
      setErrorMessage('Por favor ingresa un código identificador para la sucursal.');
      return;
    }

    setIsSubmitting(true);
    try {
      const payload: Record<string, any> = {
        name: trimmedName,
        code: trimmedCode,
        phone: phone.trim() || undefined,
        street: street.trim() || undefined,
        exterior_number: exteriorNumber.trim() || undefined,
        neighborhood: neighborhood.trim() || undefined,
        city: city.trim() || 'Culiacán',
        state: state.trim() || 'Sinaloa',
        whatsapp_ordering_enabled: whatsappEnabled,
        dine_in_enabled: dineInEnabled,
        delivery_fee_enabled: true,
      };

      const res = await fetchApi<any>('/branches', {
        method: 'POST',
        body: JSON.stringify(payload),
      });

      const created: CreatedBranchInfo = {
        id: res.id || res.branch?.id || res.data?.id,
        name: res.name || res.branch?.name || trimmedName,
        code: res.code || res.branch?.code || trimmedCode,
        status: 'active',
      };

      // Reset form
      setName('');
      setCode('');
      setCodeTouched(false);
      setPhone('');
      setStreet('');
      setExteriorNumber('');
      setNeighborhood('');
      setIsSubmitting(false);

      onBranchCreated(created);
      onClose();
    } catch (err: any) {
      setIsSubmitting(false);
      const codeError = err?.detail?.code || err?.code;
      const msg = err?.detail?.message || err?.message;

      if (codeError === 'branch_already_exists') {
        setErrorMessage('Ya existe otra sucursal registrada con este código. Elige otro identificador.');
      } else if (codeError === 'public_name_reserved') {
        setErrorMessage('El código está reservado como enlace público. Elige otro identificador.');
      } else {
        setErrorMessage(msg || 'No fue posible crear la sucursal. Verifica los datos.');
      }
    }
  };

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 250,
        backgroundColor: 'rgba(2, 6, 23, 0.75)',
        backdropFilter: 'blur(6px)',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'flex-end',
        animation: 'fadeIn 0.2s ease-out',
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget && !isSubmitting) {
          onClose();
        }
      }}
    >
      <div
        style={{
          backgroundColor: '#ffffff',
          borderTopLeftRadius: 24,
          borderTopRightRadius: 24,
          maxHeight: '92vh',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          boxShadow: '0 -8px 30px rgba(0, 0, 0, 0.4)',
        }}
      >
        {/* Grab Handle */}
        <div
          style={{
            width: 44,
            height: 4,
            borderRadius: 9999,
            backgroundColor: '#cbd5e1',
            margin: '10px auto 4px',
          }}
        />

        {/* Modal Header */}
        <div
          style={{
            padding: '12px 18px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            borderBottom: '1px solid #e2e8f0',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div
              style={{
                width: 36,
                height: 36,
                borderRadius: 10,
                backgroundColor: '#ff5722',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: '0 2px 6px rgba(255, 87, 34, 0.3)',
              }}
            >
              <Store size={20} color="#ffffff" />
            </div>
            <div>
              <div style={{ fontSize: '1.05rem', fontWeight: 800, color: '#0f172a' }}>
                Agregar Nueva Sucursal
              </div>
              <div style={{ fontSize: '0.75rem', color: '#64748b' }}>
                Registra una ubicación adicional para tu restaurante
              </div>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            disabled={isSubmitting}
            aria-label="Cerrar modal"
            style={{
              border: 'none',
              background: '#f1f5f9',
              width: 32,
              height: 32,
              borderRadius: 8,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#64748b',
              cursor: 'pointer',
            }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Modal Body / Scrollable Form */}
        <form
          onSubmit={handleSubmit}
          style={{
            overflowY: 'auto',
            padding: '16px 18px',
            display: 'flex',
            flexDirection: 'column',
            gap: 14,
          }}
        >
          {errorMessage && (
            <div
              style={{
                padding: '10px 14px',
                borderRadius: 10,
                backgroundColor: '#fef2f2',
                border: '1px solid #fecdd3',
                color: '#b91c1c',
                fontSize: '0.85rem',
                fontWeight: 600,
                display: 'flex',
                alignItems: 'center',
                gap: 8,
              }}
            >
              <AlertCircle size={18} color="#b91c1c" style={{ flexShrink: 0 }} />
              <span>{errorMessage}</span>
            </div>
          )}

          {/* Nombre de la Sucursal */}
          <div>
            <label
              htmlFor="branch-modal-name"
              style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, color: '#1e293b', marginBottom: 6 }}
            >
              Nombre de la sucursal <span style={{ color: '#ef4444' }}>*</span>
            </label>
            <input
              id="branch-modal-name"
              type="text"
              required
              value={name}
              onChange={handleNameChange}
              placeholder="ej. Sucursal Norte, Centro, Plaza Galerías"
              style={{
                width: '100%',
                padding: '11px 14px',
                borderRadius: 10,
                border: '1.5px solid #cbd5e1',
                fontSize: '0.95rem',
                color: '#0f172a',
                boxSizing: 'border-box',
                outline: 'none',
              }}
            />
          </div>

          {/* Código Identificador */}
          <div>
            <label
              htmlFor="branch-modal-code"
              style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, color: '#1e293b', marginBottom: 6 }}
            >
              Código Identificador <span style={{ color: '#ef4444' }}>*</span>
            </label>
            <input
              id="branch-modal-code"
              type="text"
              required
              value={code}
              onChange={handleCodeChange}
              placeholder="ej. NORTE, SUC02, PLAZA"
              style={{
                width: '100%',
                padding: '11px 14px',
                borderRadius: 10,
                border: '1.5px solid #cbd5e1',
                fontSize: '0.95rem',
                fontWeight: 700,
                letterSpacing: '0.05em',
                color: '#0f172a',
                boxSizing: 'border-box',
                outline: 'none',
                textTransform: 'uppercase',
              }}
            />
            <div style={{ fontSize: '0.72rem', color: '#64748b', marginTop: 4 }}>
              Código único para comandas, pedidos y corte de caja.
            </div>
          </div>

          {/* Teléfono / WhatsApp */}
          <div>
            <label
              htmlFor="branch-modal-phone"
              style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, color: '#1e293b', marginBottom: 6 }}
            >
              Teléfono / WhatsApp de pedidos
            </label>
            <div style={{ position: 'relative' }}>
              <input
                id="branch-modal-phone"
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="ej. 667 123 4567"
                style={{
                  width: '100%',
                  padding: '11px 14px 11px 38px',
                  borderRadius: 10,
                  border: '1.5px solid #cbd5e1',
                  fontSize: '0.95rem',
                  color: '#0f172a',
                  boxSizing: 'border-box',
                  outline: 'none',
                }}
              />
              <Phone
                size={16}
                color="#94a3b8"
                style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)' }}
              />
            </div>
          </div>

          {/* Ubicación / Dirección */}
          <div
            style={{
              padding: 14,
              backgroundColor: '#f8fafc',
              borderRadius: 12,
              border: '1px solid #e2e8f0',
              display: 'flex',
              flexDirection: 'column',
              gap: 10,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.825rem', fontWeight: 800, color: '#334155' }}>
              <MapPin size={16} color="#64748b" />
              <span>Dirección (opcional)</span>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 8 }}>
              <input
                type="text"
                value={street}
                onChange={(e) => setStreet(e.target.value)}
                placeholder="Calle"
                style={{
                  padding: '9px 12px',
                  borderRadius: 8,
                  border: '1px solid #cbd5e1',
                  fontSize: '0.85rem',
                  boxSizing: 'border-box',
                }}
              />
              <input
                type="text"
                value={exteriorNumber}
                onChange={(e) => setExteriorNumber(e.target.value)}
                placeholder="No. Ext"
                style={{
                  padding: '9px 12px',
                  borderRadius: 8,
                  border: '1px solid #cbd5e1',
                  fontSize: '0.85rem',
                  boxSizing: 'border-box',
                }}
              />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              <input
                type="text"
                value={neighborhood}
                onChange={(e) => setNeighborhood(e.target.value)}
                placeholder="Colonia"
                style={{
                  padding: '9px 12px',
                  borderRadius: 8,
                  border: '1px solid #cbd5e1',
                  fontSize: '0.85rem',
                  boxSizing: 'border-box',
                }}
              />
              <input
                type="text"
                value={city}
                onChange={(e) => setCity(e.target.value)}
                placeholder="Ciudad"
                style={{
                  padding: '9px 12px',
                  borderRadius: 8,
                  border: '1px solid #cbd5e1',
                  fontSize: '0.85rem',
                  boxSizing: 'border-box',
                }}
              />
            </div>
          </div>

          {/* Opciones de Operación */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 4 }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: '0.85rem', color: '#334155', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={whatsappEnabled}
                onChange={(e) => setWhatsappEnabled(e.target.checked)}
                style={{ width: 17, height: 17, accentColor: '#ff5722' }}
              />
              <span>Activar pedidos digitales y WhatsApp para esta sucursal</span>
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: '0.85rem', color: '#334155', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={dineInEnabled}
                onChange={(e) => setDineInEnabled(e.target.checked)}
                style={{ width: 17, height: 17, accentColor: '#ff5722' }}
              />
              <span>Habilitar consumo en comedor</span>
            </label>
          </div>

          {/* Submit Buttons */}
          <div style={{ display: 'flex', gap: 10, marginTop: 12, paddingBottom: 16 }}>
            <button
              type="button"
              onClick={onClose}
              disabled={isSubmitting}
              style={{
                flex: 1,
                padding: '13px',
                borderRadius: 12,
                border: '1px solid #cbd5e1',
                backgroundColor: '#f1f5f9',
                color: '#475569',
                fontSize: '0.95rem',
                fontWeight: 700,
                cursor: 'pointer',
              }}
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              style={{
                flex: 2,
                padding: '13px',
                borderRadius: 12,
                border: 'none',
                backgroundColor: '#ff5722',
                color: '#ffffff',
                fontSize: '0.95rem',
                fontWeight: 800,
                cursor: isSubmitting ? 'not-allowed' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 8,
                boxShadow: '0 4px 10px rgba(255, 87, 34, 0.3)',
              }}
            >
              {isSubmitting ? (
                <>
                  <Loader2 size={18} className="animate-spin" />
                  <span>Creando sucursal...</span>
                </>
              ) : (
                <>
                  <Plus size={18} />
                  <span>Crear Sucursal</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
