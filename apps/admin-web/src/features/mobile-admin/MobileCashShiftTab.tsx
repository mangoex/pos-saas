import React, { useEffect, useRef, useState, useCallback } from 'react';
import { fetchApi, ApiError } from '@restaurantos/api-client';
import { commandKeyStore } from '../cash/cashConceptState';
import {
  CircleDollarSign,
  Lock,
  Unlock,
  PlusCircle,
  MinusCircle,
  Clock,
  AlertCircle,
  RefreshCw,
  CheckCircle2,
  X,
} from 'lucide-react';

interface MobileCashShiftTabProps {
  branchId: string;
  branchName?: string;
}

interface CashShift {
  id: string;
  register_code: string;
  status: string;
  opening_cash_cents: number;
  opened_at: string;
  closed_at?: string | null;
}

interface CurrentShiftResponse {
  cash_shift: CashShift | null;
  closure?: any;
}

interface CashConcept {
  concept_id: string;
  code: string;
  name: string;
  allowed_movement_type: string;
}

const PRESET_AMOUNTS = [200, 500, 1000, 1500, 2000];

export const MobileCashShiftTab: React.FC<MobileCashShiftTabProps> = ({
  branchId,
  branchName,
}) => {
  const registerId = 'CAJA-01';
  const [shift, setShift] = useState<CashShift | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Opening form
  const [openingAmount, setOpeningAmount] = useState('500');
  const [openingSubmitting, setOpeningSubmitting] = useState(false);

  // Movement modal
  const [isMovementModalOpen, setIsMovementModalOpen] = useState(false);
  const [movementType, setMovementType] = useState<'deposit' | 'withdrawal'>('deposit');
  const [movementAmount, setMovementAmount] = useState('');
  const [movementConcept, setMovementConcept] = useState('Aportación de cambio');
  const [movementEvidence, setMovementEvidence] = useState('');
  const [movementSubmitting, setMovementSubmitting] = useState(false);
  const [concepts, setConcepts] = useState<CashConcept[]>([]);
  const commandKeys = useRef(commandKeyStore());

  // Close shift modal
  const [isCloseModalOpen, setIsCloseModalOpen] = useState(false);
  const [closeSubmitting, setCloseSubmitting] = useState(false);

  const loadShift = useCallback(async (silent = false) => {
    if (!branchId) return;
    if (!silent) setRefreshing(true);
    setError(null);
    try {
      const res = await fetchApi<CurrentShiftResponse>(
        `/cash/shifts/current?branch_id=${encodeURIComponent(branchId)}&register_id=${encodeURIComponent(registerId)}`
      );
      setShift(res?.cash_shift || null);
    } catch (err) {
      if (!silent) {
        setError(err instanceof ApiError ? err.message : 'Error al consultar estado de caja.');
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [branchId]);

  const loadConcepts = useCallback(async () => {
    if (!branchId) return;
    try {
      const res = await fetchApi<CashConcept[]>(
        `/cash/concepts/effective?branch_id=${encodeURIComponent(branchId)}&movement_type=${movementType}`
      );
      setConcepts(Array.isArray(res) ? res : []);
    } catch {
      // ignore
    }
  }, [branchId, movementType]);

  useEffect(() => {
    void loadShift();
  }, [loadShift]);

  useEffect(() => {
    if (shift) {
      void loadConcepts();
    }
  }, [shift, loadConcepts]);

  const handleOpenShift = async (e: React.FormEvent) => {
    e.preventDefault();
    const amountNum = parseFloat(openingAmount);
    if (isNaN(amountNum) || amountNum < 0) {
      setError('Por favor ingresa un monto válido de apertura.');
      return;
    }
    const cents = Math.round(amountNum * 100);
    const operation = `mobile-open:${branchId}:${registerId}:${cents}`;
    setOpeningSubmitting(true);
    setError(null);
    setNotice(null);
    try {
      const newShift = await fetchApi<CashShift>('/cash/shifts/open', {
        method: 'POST',
        headers: {
          'Idempotency-Key': commandKeys.current.get(operation, () => crypto.randomUUID()),
        },
        body: JSON.stringify({
          branch_id: branchId,
          register_id: registerId,
          opening_cash_cents: cents,
        }),
      });
      commandKeys.current.clear(operation);
      setShift(newShift);
      setNotice('¡Turno de caja abierto correctamente!');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo abrir el turno.');
    } finally {
      setOpeningSubmitting(false);
    }
  };

  const handleCreateMovement = async (e: React.FormEvent) => {
    e.preventDefault();
    const amountNum = parseFloat(movementAmount);
    if (isNaN(amountNum) || amountNum <= 0) {
      setError('Por favor ingresa un monto mayor a cero.');
      return;
    }
    const cents = Math.round(amountNum * 100);
    const conceptId = concepts.length > 0 ? concepts[0].concept_id : '';
    const cleanReference = movementConcept.trim();
    const cleanEvidence = movementEvidence.trim();
    if (!conceptId) {
      setError('No existe un concepto de caja disponible para este movimiento.');
      return;
    }
    if (!cleanReference || !cleanEvidence) {
      setError('Captura el motivo y una referencia de evidencia real.');
      return;
    }
    const operation = [
      'mobile-movement',
      branchId,
      registerId,
      movementType,
      conceptId,
      String(cents),
      cleanReference,
      cleanEvidence,
    ].join(':');
    setMovementSubmitting(true);
    setError(null);
    try {
      await fetchApi('/cash/movements', {
        method: 'POST',
        headers: {
          'Idempotency-Key': commandKeys.current.get(operation, () => crypto.randomUUID()),
        },
        body: JSON.stringify({
          branch_id: branchId,
          register_id: registerId,
          movement_type: movementType,
          concept_id: conceptId,
          amount_cents: cents,
          reference: cleanReference,
          evidence_refs: [movementEvidence.trim()],
        }),
      });
      commandKeys.current.clear(operation);
      setIsMovementModalOpen(false);
      setMovementAmount('');
      setMovementEvidence('');
      setNotice(`Movimiento de ${movementType === 'deposit' ? 'entrada' : 'retiro'} registrado con éxito.`);
      void loadShift(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo registrar el movimiento.');
    } finally {
      setMovementSubmitting(false);
    }
  };

  const handleCloseShift = async () => {
    if (!shift) return;
    const operation = `mobile-close:${branchId}:${registerId}:${shift.id}`;
    setCloseSubmitting(true);
    setError(null);
    try {
      await fetchApi(`/cash/shifts/${encodeURIComponent(shift.id)}/close-operationally`, {
        method: 'POST',
        headers: {
          'Idempotency-Key': commandKeys.current.get(operation, () => crypto.randomUUID()),
        },
        body: JSON.stringify({}),
      });
      commandKeys.current.clear(operation);
      setIsCloseModalOpen(false);
      setShift(null);
      setNotice('Turno de caja cerrado exitosamente.');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo cerrar el turno.');
    } finally {
      setCloseSubmitting(false);
    }
  };

  const formatOpenedDate = (isoStr: string) => {
    try {
      const d = new Date(isoStr);
      return d.toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' });
    } catch {
      return isoStr;
    }
  };

  return (
    <div style={{ minHeight: '100vh', backgroundColor: '#f8fafc', paddingBottom: 84 }}>
      {/* Header */}
      <header
        style={{
          position: 'sticky',
          top: 0,
          zIndex: 40,
          backgroundColor: '#0f172a',
          color: '#ffffff',
          padding: '12px 16px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          borderBottom: '1px solid #1e293b',
          boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div
            style={{
              width: 38,
              height: 38,
              borderRadius: 10,
              backgroundColor: shift ? '#16a34a' : '#475569',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <CircleDollarSign size={22} color="#ffffff" />
          </div>
          <div>
            <div style={{ fontSize: '1rem', fontWeight: 800, lineHeight: 1.1 }}>
              Control de Caja
            </div>
            <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
              {branchName || 'Sucursal Principal'} • {registerId}
            </div>
          </div>
        </div>

        <button
          onClick={() => void loadShift()}
          disabled={refreshing}
          aria-label="Refrescar caja"
          style={{
            border: 'none',
            background: '#1e293b',
            color: '#ffffff',
            borderRadius: 8,
            padding: '8px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
          }}
        >
          <RefreshCw size={16} className={refreshing ? 'animate-spin' : ''} />
        </button>
      </header>

      {/* Main content */}
      <main style={{ padding: '16px 14px', maxWidth: 640, margin: '0 auto' }}>
        {notice && (
          <div
            style={{
              backgroundColor: '#dcfce7',
              border: '1px solid #bbf7d0',
              borderRadius: 12,
              padding: '10px 14px',
              color: '#15803d',
              fontSize: '0.875rem',
              fontWeight: 600,
              marginBottom: 14,
              display: 'flex',
              alignItems: 'center',
              gap: 8,
            }}
          >
            <CheckCircle2 size={18} />
            <span>{notice}</span>
          </div>
        )}

        {error && (
          <div
            style={{
              backgroundColor: '#fee2e2',
              border: '1px solid #fecaca',
              borderRadius: 12,
              padding: '10px 14px',
              color: '#b91c1c',
              fontSize: '0.875rem',
              fontWeight: 600,
              marginBottom: 14,
              display: 'flex',
              alignItems: 'center',
              gap: 8,
            }}
          >
            <AlertCircle size={18} />
            <span>{error}</span>
          </div>
        )}

        {loading ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#64748b' }}>
            <RefreshCw size={24} className="animate-spin" style={{ margin: '0 auto 8px' }} />
            <div>Consultando estado de turno...</div>
          </div>
        ) : !shift ? (
          /* Caja Cerrada: Abrir Turno */
          <div
            style={{
              backgroundColor: '#ffffff',
              borderRadius: 16,
              padding: 20,
              boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.05)',
              border: '1px solid #e2e8f0',
            }}
          >
            <div style={{ textAlign: 'center', marginBottom: 20 }}>
              <div
                style={{
                  width: 56,
                  height: 56,
                  borderRadius: 28,
                  backgroundColor: '#f1f5f9',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  margin: '0 auto 12px',
                  color: '#64748b',
                }}
              >
                <Lock size={28} />
              </div>
              <h2 style={{ fontSize: '1.25rem', fontWeight: 800, color: '#0f172a', margin: '0 0 6px' }}>
                Caja Cerrada
              </h2>
              <p style={{ fontSize: '0.875rem', color: '#64748b', margin: 0 }}>
                Para comenzar a registrar cobros y ventas, abre un turno con el fondo de caja inicial para dar cambio.
              </p>
            </div>

            <form onSubmit={handleOpenShift}>
              <label
                style={{
                  display: 'block',
                  fontSize: '0.875rem',
                  fontWeight: 700,
                  color: '#334155',
                  marginBottom: 8,
                }}
              >
                Fondo inicial en efectivo (MXN)
              </label>

              <div style={{ position: 'relative', marginBottom: 14 }}>
                <span
                  style={{
                    position: 'absolute',
                    left: 14,
                    top: '50%',
                    transform: 'translateY(-50%)',
                    fontSize: '1.25rem',
                    fontWeight: 700,
                    color: '#64748b',
                  }}
                >
                  $
                </span>
                <input
                  type="number"
                  step="0.50"
                  min="0"
                  value={openingAmount}
                  onChange={(e) => setOpeningAmount(e.target.value)}
                  required
                  placeholder="0.00"
                  style={{
                    width: '100%',
                    boxSizing: 'border-box',
                    padding: '14px 14px 14px 34px',
                    fontSize: '1.25rem',
                    fontWeight: 800,
                    borderRadius: 12,
                    border: '2px solid #cbd5e1',
                    color: '#0f172a',
                    outline: 'none',
                  }}
                />
              </div>

              {/* Preset Chips */}
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 20 }}>
                {PRESET_AMOUNTS.map((amt) => (
                  <button
                    key={amt}
                    type="button"
                    onClick={() => setOpeningAmount(amt.toString())}
                    style={{
                      padding: '6px 12px',
                      borderRadius: 8,
                      border: openingAmount === amt.toString() ? '2px solid #3b82f6' : '1px solid #e2e8f0',
                      backgroundColor: openingAmount === amt.toString() ? '#eff6ff' : '#f8fafc',
                      color: openingAmount === amt.toString() ? '#1d4ed8' : '#475569',
                      fontWeight: 700,
                      fontSize: '0.875rem',
                      cursor: 'pointer',
                    }}
                  >
                    ${amt}
                  </button>
                ))}
              </div>

              <button
                type="submit"
                disabled={openingSubmitting}
                style={{
                  width: '100%',
                  padding: '16px',
                  backgroundColor: '#16a34a',
                  color: '#ffffff',
                  border: 'none',
                  borderRadius: 12,
                  fontSize: '1rem',
                  fontWeight: 800,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 8,
                  cursor: 'pointer',
                  boxShadow: '0 4px 6px -1px rgba(22, 163, 74, 0.3)',
                }}
              >
                <Unlock size={20} />
                {openingSubmitting ? 'Abriendo turno...' : 'Abrir Turno de Caja'}
              </button>
            </form>
          </div>
        ) : (
          /* Caja Abierta: Resumen y Operaciones */
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {/* Status Card */}
            <div
              style={{
                backgroundColor: '#ffffff',
                borderRadius: 16,
                padding: 18,
                border: '1px solid #e2e8f0',
                boxShadow: '0 2px 4px rgba(0,0,0,0.04)',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
                <span
                  style={{
                    backgroundColor: '#dcfce7',
                    color: '#15803d',
                    padding: '4px 10px',
                    borderRadius: 8,
                    fontSize: '0.75rem',
                    fontWeight: 800,
                    textTransform: 'uppercase',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 6,
                  }}
                >
                  <span
                    style={{
                      width: 8,
                      height: 8,
                      borderRadius: 4,
                      backgroundColor: '#22c55e',
                    }}
                  />
                  Turno Activo
                </span>
                <span style={{ fontSize: '0.8rem', color: '#64748b', display: 'flex', alignItems: 'center', gap: 4 }}>
                  <Clock size={14} /> Abierto a las {formatOpenedDate(shift.opened_at)}
                </span>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 10 }}>
                <div
                  style={{
                    backgroundColor: '#f8fafc',
                    padding: '12px 14px',
                    borderRadius: 10,
                    border: '1px solid #f1f5f9',
                  }}
                >
                  <div style={{ fontSize: '0.8rem', color: '#64748b', fontWeight: 600 }}>
                    Fondo inicial en efectivo
                  </div>
                  <div style={{ fontSize: '1.4rem', fontWeight: 800, color: '#0f172a' }}>
                    ${(shift.opening_cash_cents / 100).toFixed(2)}{' '}
                    <span style={{ fontSize: '0.8rem', fontWeight: 500, color: '#64748b' }}>MXN</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Quick Actions Grid */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              <button
                type="button"
                onClick={() => {
                  setMovementType('deposit');
                  setMovementConcept('Entrada de efectivo');
                  setIsMovementModalOpen(true);
                }}
                style={{
                  padding: '14px 12px',
                  backgroundColor: '#ffffff',
                  border: '1px solid #e2e8f0',
                  borderRadius: 14,
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: 6,
                  cursor: 'pointer',
                  boxShadow: '0 2px 4px rgba(0,0,0,0.03)',
                }}
              >
                <div
                  style={{
                    width: 40,
                    height: 40,
                    borderRadius: 10,
                    backgroundColor: '#eff6ff',
                    color: '#2563eb',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  <PlusCircle size={22} />
                </div>
                <span style={{ fontSize: '0.875rem', fontWeight: 700, color: '#0f172a' }}>
                  Entrada Dinero
                </span>
                <span style={{ fontSize: '0.75rem', color: '#64748b' }}>Aportar cambio</span>
              </button>

              <button
                type="button"
                onClick={() => {
                  setMovementType('withdrawal');
                  setMovementConcept('Gasto / Retiro');
                  setIsMovementModalOpen(true);
                }}
                style={{
                  padding: '14px 12px',
                  backgroundColor: '#ffffff',
                  border: '1px solid #e2e8f0',
                  borderRadius: 14,
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: 6,
                  cursor: 'pointer',
                  boxShadow: '0 2px 4px rgba(0,0,0,0.03)',
                }}
              >
                <div
                  style={{
                    width: 40,
                    height: 40,
                    borderRadius: 10,
                    backgroundColor: '#fff1f2',
                    color: '#e11d48',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  <MinusCircle size={22} />
                </div>
                <span style={{ fontSize: '0.875rem', fontWeight: 700, color: '#0f172a' }}>
                  Retiro / Gasto
                </span>
                <span style={{ fontSize: '0.75rem', color: '#64748b' }}>Pago a proveedor</span>
              </button>
            </div>

            {/* Close Shift Button */}
            <div style={{ marginTop: 8 }}>
              <button
                type="button"
                onClick={() => setIsCloseModalOpen(true)}
                style={{
                  width: '100%',
                  padding: '15px',
                  backgroundColor: '#ffffff',
                  border: '2px solid #fee2e2',
                  borderRadius: 12,
                  color: '#dc2626',
                  fontSize: '0.95rem',
                  fontWeight: 800,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 8,
                  cursor: 'pointer',
                }}
              >
                <Lock size={18} />
                Cerrar Turno de Caja
              </button>
            </div>
          </div>
        )}
      </main>

      {/* Movement Modal */}
      {isMovementModalOpen && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(15, 23, 42, 0.6)',
            zIndex: 60,
            display: 'flex',
            alignItems: 'flex-end',
            justifyContent: 'center',
          }}
        >
          <div
            style={{
              backgroundColor: '#ffffff',
              width: '100%',
              maxWidth: 500,
              borderTopLeftRadius: 20,
              borderTopRightRadius: 20,
              padding: '20px 18px 28px',
              boxShadow: '0 -4px 10px rgba(0, 0, 0, 0.15)',
              maxHeight: '85vh',
              overflowY: 'auto',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <h3 style={{ margin: 0, fontSize: '1.15rem', fontWeight: 800, color: '#0f172a' }}>
                {movementType === 'deposit' ? 'Entrada de Efectivo' : 'Retiro de Efectivo'}
              </h3>
              <button
                onClick={() => setIsMovementModalOpen(false)}
                style={{ background: 'none', border: 'none', color: '#64748b', cursor: 'pointer', padding: 4 }}
              >
                <X size={20} />
              </button>
            </div>

            <form onSubmit={handleCreateMovement}>
              <div style={{ marginBottom: 14 }}>
                <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, color: '#334155', marginBottom: 6 }}>
                  Monto ($ MXN)
                </label>
                <input
                  type="number"
                  step="0.50"
                  min="0.50"
                  value={movementAmount}
                  onChange={(e) => setMovementAmount(e.target.value)}
                  required
                  placeholder="0.00"
                  autoFocus
                  style={{
                    width: '100%',
                    boxSizing: 'border-box',
                    padding: '12px 14px',
                    fontSize: '1.1rem',
                    fontWeight: 700,
                    borderRadius: 10,
                    border: '1px solid #cbd5e1',
                    outline: 'none',
                  }}
                />
              </div>

              <div style={{ marginBottom: 20 }}>
                <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, color: '#334155', marginBottom: 6 }}>
                  Motivo / Concepto
                </label>
                <input
                  type="text"
                  value={movementConcept}
                  onChange={(e) => setMovementConcept(e.target.value)}
                  required
                  placeholder="Ej. Pago de hielo, cambio, etc."
                  style={{
                    width: '100%',
                    boxSizing: 'border-box',
                    padding: '12px 14px',
                    fontSize: '0.95rem',
                    borderRadius: 10,
                    border: '1px solid #cbd5e1',
                    outline: 'none',
                  }}
                />
              </div>

              <div style={{ marginBottom: 20 }}>
                <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, color: '#334155', marginBottom: 6 }}>
                  Referencia de evidencia
                </label>
                <input
                  type="text"
                  value={movementEvidence}
                  onChange={(e) => setMovementEvidence(e.target.value)}
                  required
                  maxLength={600}
                  placeholder="Ej. ticket:ABC-123 o foto:corte-2026-09-09"
                  style={{
                    width: '100%',
                    boxSizing: 'border-box',
                    padding: '12px 14px',
                    fontSize: '0.95rem',
                    borderRadius: 10,
                    border: '1px solid #cbd5e1',
                    outline: 'none',
                  }}
                />
              </div>

              <button
                type="submit"
                disabled={movementSubmitting}
                style={{
                  width: '100%',
                  padding: '14px',
                  backgroundColor: movementType === 'deposit' ? '#2563eb' : '#dc2626',
                  color: '#ffffff',
                  border: 'none',
                  borderRadius: 10,
                  fontSize: '1rem',
                  fontWeight: 800,
                  cursor: 'pointer',
                }}
              >
                {movementSubmitting ? 'Guardando...' : 'Confirmar Movimiento'}
              </button>
            </form>
          </div>
        </div>
      )}

      {/* Close Shift Modal */}
      {isCloseModalOpen && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(15, 23, 42, 0.6)',
            zIndex: 60,
            display: 'flex',
            alignItems: 'flex-end',
            justifyContent: 'center',
          }}
        >
          <div
            style={{
              backgroundColor: '#ffffff',
              width: '100%',
              maxWidth: 500,
              borderTopLeftRadius: 20,
              borderTopRightRadius: 20,
              padding: '22px 18px 28px',
              boxShadow: '0 -4px 10px rgba(0, 0, 0, 0.15)',
            }}
          >
            <div style={{ textAlign: 'center', marginBottom: 18 }}>
              <div
                style={{
                  width: 50,
                  height: 50,
                  borderRadius: 25,
                  backgroundColor: '#fee2e2',
                  color: '#dc2626',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  margin: '0 auto 12px',
                }}
              >
                <Lock size={24} />
              </div>
              <h3 style={{ margin: '0 0 6px', fontSize: '1.2rem', fontWeight: 800, color: '#0f172a' }}>
                ¿Cerrar Turno de Caja?
              </h3>
              <p style={{ margin: 0, fontSize: '0.875rem', color: '#64748b' }}>
                Al cerrar el turno, la caja quedará bloqueada hasta que se abra un nuevo turno.
              </p>
            </div>

            <div style={{ display: 'flex', gap: 10 }}>
              <button
                type="button"
                onClick={() => setIsCloseModalOpen(false)}
                disabled={closeSubmitting}
                style={{
                  flex: 1,
                  padding: '14px',
                  backgroundColor: '#f1f5f9',
                  border: 'none',
                  borderRadius: 10,
                  fontWeight: 700,
                  color: '#475569',
                  cursor: 'pointer',
                }}
              >
                Cancelar
              </button>
              <button
                type="button"
                onClick={handleCloseShift}
                disabled={closeSubmitting}
                style={{
                  flex: 1,
                  padding: '14px',
                  backgroundColor: '#dc2626',
                  border: 'none',
                  borderRadius: 10,
                  fontWeight: 800,
                  color: '#ffffff',
                  cursor: 'pointer',
                }}
              >
                {closeSubmitting ? 'Cerrando...' : 'Sí, Cerrar Caja'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
