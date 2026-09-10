import React, { useEffect, useReducer, useState } from 'react';
import { ApiError, fetchApi } from '@restaurantos/api-client';
import { resolvePosBranchId, usePosSession } from '../../session';
import {
  Wallet,
  ArrowDownRight,
  ArrowUpRight,
  RotateCw,
  RotateCcw,
  AlertCircle,
  CheckCircle2,
  Info,
  Coins,
  ReceiptText,
  User,
  FileText,
  Hash,
  Tag,
  ShieldAlert,
  Wifi,
  WifiOff,
  Inbox,
  Clock,
  Banknote,
  Send,
  X,
} from 'lucide-react';
import {
  buildCashCompensationPayload,
  canCompensateLedgerItem,
  cashCompensationStateLabel,
  cashMovementCapabilities,
  cashMovementTypeLabel,
  initialCashCompensationFormState,
  type CashCompensationState,
  nextCashIdempotencyKey,
  parseCashCents,
  reduceCashCompensationFormState,
} from './cashMovementForm';
import {
  configuredGatewayDeviceId,
  configuredGatewayUrl,
  enqueueOfflineCashMovement,
  listOfflineCashMovements,
  loadUsableOfflineCashGrant,
  offlineCashStatusLabel,
  refreshOfflineCashGrant,
  storeOfflineCashGrant,
  type OfflineCashMovementItem,
  type OfflineCashStatus,
} from './offlineCash';
import './CashMovements.css';

type Concept = { concept_id: string; name: string; code: string };
type CurrentShift = { cash_shift: { id: string } | null };
type CashSummary = { expected_cash_cents: number };
type LedgerItem = {
  id: string;
  movement_type: string;
  amount_cents: number;
  reason: string;
  compensation_state: CashCompensationState;
  compensated_by_movement_id: string | null;
};
type Ledger = { items: LedgerItem[]; next_cursor: string | null };
type CashMovementResponse = { current_summary: CashSummary };

export { parseCashCents } from './cashMovementForm';

function centsToMxn(cents: number) {
  return (cents / 100).toFixed(2);
}

export default function CashMovements() {
  const { hasPermission, session } = usePosSession();
  const capabilities = cashMovementCapabilities({
    canRead: hasPermission('cash.movement.read'),
    canWithdraw: hasPermission('cash.movement.withdraw'),
    canDeposit: hasPermission('cash.movement.deposit'),
    canCompensate: hasPermission('cash.movement.compensate'),
  });
  const branchId = resolvePosBranchId();
  const registerId = localStorage.getItem('pos_register_id') || '';
  const [type, setType] = useState<'withdrawal' | 'deposit'>(capabilities.initialType);
  const [conceptText, setConceptText] = useState<string>('');
  const [ledger, setLedger] = useState<LedgerItem[]>([]);
  const [amount, setAmount] = useState('');
  const [reference, setReference] = useState('');
  const [evidence, setEvidence] = useState('');
  const [key, setKey] = useState<string | null>(null);
  const [compensation, dispatchCompensation] = useReducer(
    reduceCashCompensationFormState<LedgerItem>,
    undefined,
    initialCashCompensationFormState<LedgerItem>,
  );
  const [currentSummary, setCurrentSummary] = useState<CashSummary | null>(null);
  const [shiftReady, setShiftReady] = useState(false);
  const [loading, setLoading] = useState(false);
  const [ledgerLoading, setLedgerLoading] = useState(false);
  const [status, setStatus] = useState('');
  const [offlineGrant, setOfflineGrant] = useState<string | null>(null);
  const [offlineMovements, setOfflineMovements] = useState<OfflineCashMovementItem[]>([]);
  const [offlineStatus, setOfflineStatus] = useState<OfflineCashStatus | null>(null);
  const gatewayUrl = configuredGatewayUrl();
  const gatewayDeviceId = configuredGatewayDeviceId();

  useEffect(() => {
    if (!capabilities.canWrite) return;
    if ((type === 'withdrawal' && !capabilities.canWithdraw) || (type === 'deposit' && !capabilities.canDeposit)) {
      setType(capabilities.initialType);
    }
  }, [
    capabilities.canDeposit,
    capabilities.canWithdraw,
    capabilities.canWrite,
    capabilities.initialType,
    type,
  ]);

  async function refreshLedger(): Promise<boolean> {
    if (!capabilities.canRead || !branchId) return false;
    setLedgerLoading(true);
    try {
      const data = await fetchApi<Ledger>(
        `/cash/movements?branch_id=${encodeURIComponent(branchId)}&limit=25`,
      );
      setLedger(data.items);
      return true;
    } catch {
      setStatus('No se pudo cargar el ledger de caja.');
      return false;
    } finally {
      setLedgerLoading(false);
    }
  }

  useEffect(() => {
    void refreshLedger();
  }, [branchId, capabilities.canRead]);

  useEffect(() => {
    if (!capabilities.canWrite || !branchId || !registerId) return;
    setShiftReady(false);
    void fetchApi<CurrentShift>(`/cash-shifts/current?branch_id=${encodeURIComponent(branchId)}&register_id=${encodeURIComponent(registerId)}`)
      .then(data => setShiftReady(Boolean(data.cash_shift)))
      .catch(() => setStatus('No se pudo verificar el turno actual.'));
  }, [branchId, capabilities.canWrite, registerId]);

  // Decoupled from /cash/concepts/effective: cash movements now capture concept / reason text directly

  useEffect(() => {
    setOfflineGrant(null);
    setOfflineMovements([]);
    setOfflineStatus(null);
    if (!capabilities.canWrite || !branchId || !gatewayDeviceId || !gatewayUrl) return;
    let cancelled = false;
    const current = loadUsableOfflineCashGrant(branchId, gatewayDeviceId, gatewayUrl);
    setOfflineGrant(current);
    const renew = async () => {
      try {
        const response = await refreshOfflineCashGrant(branchId, gatewayDeviceId);
        if (!cancelled) {
          const grant = storeOfflineCashGrant(
            response,
            branchId,
            gatewayDeviceId,
            gatewayUrl,
          );
          setOfflineGrant(grant);
        }
      } catch {
        if (!cancelled) setOfflineGrant(current);
      }
    };
    void renew();
    const interval = window.setInterval(() => { void renew(); }, 10 * 60 * 1000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [branchId, capabilities.canWrite, gatewayDeviceId, gatewayUrl]);

  useEffect(() => {
    if (!gatewayUrl || !offlineGrant) return;
    let cancelled = false;
    const refreshOffline = async () => {
      try {
        const items = await listOfflineCashMovements(gatewayUrl, offlineGrant);
        if (!cancelled) {
          setOfflineMovements(items);
          setOfflineStatus(items.at(-1)?.status ?? null);
        }
      } catch {
        if (!cancelled) setOfflineStatus('GATEWAY_UNAVAILABLE');
      }
    };
    void refreshOffline();
    const interval = window.setInterval(() => { void refreshOffline(); }, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [gatewayUrl, offlineGrant]);

  if (!capabilities.canUse) return null;

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const cents = parseCashCents(amount);
    const cText = conceptText.trim();
    const rText = reference.trim();
    const eText = evidence.trim() || 'Comprobante interno';

    // El concepto abierto o referencia deben contener la descripción del movimiento
    const combinedReference = cText && rText ? `${cText} — Ref: ${rText}` : (cText || rText);

    if (!cents || !cText || !shiftReady) {
      setStatus('Captura el concepto del movimiento, el importe y confirma un turno abierto.');
      return;
    }
    const commandKey = nextCashIdempotencyKey(key);
    setKey(commandKey);
    setLoading(true);
    setStatus('Registrando…');
    const payload = {
      branch_id: branchId,
      register_id: registerId,
      movement_type: type,
      concept: cText,
      amount_cents: cents,
      reference: combinedReference.slice(0, 600),
      evidence_refs: [eText.slice(0, 600)],
    };
    try {
      const result = await fetchApi<CashMovementResponse>('/cash/movements', {
        method: 'POST', headers: { 'Idempotency-Key': commandKey },
        body: JSON.stringify(payload),
      });
      setCurrentSummary(result.current_summary);
      const refreshed = await refreshLedger();
      setAmount(''); setConceptText(''); setReference(''); setEvidence(''); setKey(null);
      setStatus(refreshed ? 'Movimiento confirmado exitosamente.' : 'Movimiento confirmado; actualiza el ledger.');
    } catch (error) {
      if (error instanceof ApiError && error.code === 'idempotency_conflict') {
        setKey(null); setStatus('La solicitud cambió y fue rechazada; genera una nueva intención.');
      } else if (
        (!(error instanceof ApiError) || error.status >= 500)
        && gatewayUrl
        && gatewayDeviceId
        && offlineGrant
      ) {
        try {
          const local = await enqueueOfflineCashMovement(
            gatewayUrl,
            offlineGrant,
            commandKey,
            {
              register_id: registerId,
              movement_type: type,
              concept: cText,
              amount_cents: cents,
              reference: combinedReference.slice(0, 600),
              evidence_refs: [eText.slice(0, 600)],
            },
          );
          setOfflineMovements(current => [
            ...current.filter(item => item.idempotency_key !== local.idempotency_key),
            local,
          ]);
          setOfflineStatus(local.status);
          setAmount(''); setConceptText(''); setReference(''); setEvidence(''); setKey(null);
          setStatus(offlineCashStatusLabel(local.status));
        } catch {
          setOfflineStatus('GATEWAY_UNAVAILABLE');
          setStatus('Gateway no disponible. Reintenta con la misma intención.');
        }
      } else {
        setStatus('Operación no confirmada. Reintenta con la misma intención.');
      }
    } finally { setLoading(false); }
  }

  async function submitCompensation(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const intent = compensation.intent;
    if (!intent) return;
    const payload = buildCashCompensationPayload(intent.reason, intent.evidence);
    if (!payload.reason || !payload.evidence_refs[0]) {
      setStatus('Captura motivo y evidencia para compensar.');
      return;
    }
    const commandKey = nextCashIdempotencyKey(intent.idempotencyKey);
    dispatchCompensation({ type: 'begin_submit', idempotencyKey: commandKey });
    setStatus('Compensando…');
    try {
      const result = await fetchApi<CashMovementResponse>(
        `/cash/movements/${encodeURIComponent(intent.target.id)}/compensations`,
        {
          method: 'POST',
          headers: { 'Idempotency-Key': commandKey },
          body: JSON.stringify(payload),
        },
      );
      setCurrentSummary(result.current_summary);
      const refreshed = await refreshLedger();
      dispatchCompensation({ type: 'complete' });
      setStatus(refreshed ? 'Movimiento compensado.' : 'Movimiento compensado; actualiza el ledger.');
    } catch (error) {
      if (error instanceof ApiError && error.code === 'idempotency_conflict') {
        dispatchCompensation({ type: 'complete' });
        setStatus('La compensación cambió y fue rechazada; genera una nueva intención.');
      } else {
        dispatchCompensation({ type: 'uncertain_failure' });
        setStatus('Compensación no confirmada. Reintenta con la misma intención.');
      }
    }
  }

  return (
    <div className="cash-movements-container">
      {/* Header Principal */}
      <header className="cash-movements-header">
        <div className="cash-header-title-group">
          <div className="cash-header-icon-badge">
            <Wallet size={28} />
          </div>
          <div>
            <h1 className="cash-header-title">
              Movimientos de caja —{' '}
              <span className="cash-user-tag">
                <User size={15} />
                {session?.user?.display_name || 'Operador'}
              </span>
            </h1>
            <p className="cash-header-subtitle">
              Registro de entradas y salidas de efectivo, arqueos y control de auditoría de caja.
            </p>
          </div>
        </div>

        <div className="cash-header-kpis">
          {currentSummary && (
            <div className="cash-kpi-card" role="status">
              <div className="cash-kpi-icon">
                <Banknote size={22} />
              </div>
              <div className="cash-kpi-info">
                <span className="cash-kpi-label">Efectivo esperado:</span>
                <span className="cash-kpi-value">${centsToMxn(currentSummary.expected_cash_cents)}</span>
              </div>
            </div>
          )}
        </div>
      </header>

      {/* Grid Principal: Formulario + Ledger */}
      <div className="cash-main-grid">
        {/* Columna Izquierda: Formulario de Registro */}
        <div className="cash-card">
          <div className="cash-card-header">
            <div className="cash-card-header-left">
              <Coins size={20} style={{ color: type === 'withdrawal' ? '#dc2626' : '#059669' }} />
              <h2 className="cash-card-title">Registrar Movimiento</h2>
            </div>
            {shiftReady ? (
              <span className="cash-card-badge" style={{ background: '#ecfdf5', color: '#047857' }}>
                Turno Abierto
              </span>
            ) : (
              <span className="cash-card-badge" style={{ background: '#fffbeb', color: '#b45309' }}>
                Sin Turno
              </span>
            )}
          </div>

          {!capabilities.canWrite && (
            <div className="cash-alert cash-alert-info" role="status">
              <Info size={18} style={{ flexShrink: 0, marginTop: 2 }} />
              <span>Tu perfil sólo cuenta con permisos para consultar el ledger de caja.</span>
            </div>
          )}

          {capabilities.canWrite && <>
              {!registerId && (
                <div className="cash-alert cash-alert-warning" role="alert">
                  <AlertCircle size={18} style={{ flexShrink: 0, marginTop: 2 }} />
                  <span>Configura la caja POS antes de registrar movimientos.</span>
                </div>
              )}

              {!shiftReady && registerId && (
                <div className="cash-alert cash-alert-warning" role="status">
                  <Clock size={18} style={{ flexShrink: 0, marginTop: 2 }} />
                  <span>No hay un turno de caja abierto actualmente en esta terminal. Inicia turno en el POS para habilitar movimientos.</span>
                </div>
              )}

              {/* Selector de Tipo */}
              <div className="cash-type-toggle">
                <button
                  type="button"
                  className={`cash-type-btn ${type === 'withdrawal' ? 'is-active-withdrawal' : ''}`}
                  onClick={() => setType('withdrawal')}
                  disabled={!capabilities.canWithdraw}
                >
                  <ArrowDownRight size={18} />
                  <span>Retiro (Gasto/Salida)</span>
                </button>
                <button
                  type="button"
                  className={`cash-type-btn ${type === 'deposit' ? 'is-active-deposit' : ''}`}
                  onClick={() => setType('deposit')}
                  disabled={!capabilities.canDeposit}
                >
                  <ArrowUpRight size={18} />
                  <span>Depósito (Entrada)</span>
                </button>
              </div>

              <form onSubmit={submit} className="cash-form">
                {/* Select de tipo oculto o de respaldo para compatibilidad de formulario */}
                <input type="hidden" name="movement_type" value={type} />

                {/* Concepto / Motivo */}
                <div className="cash-form-group">
                  <label className="cash-form-label">
                    <FileText size={15} style={{ color: '#64748b' }} />
                    <span>Concepto / Motivo</span>
                    <span className="cash-form-label-required">*</span>
                  </label>
                  <input
                    value={conceptText}
                    onChange={e => setConceptText(e.target.value)}
                    maxLength={300}
                    required
                    placeholder="Ej. Compra de verdura para cocina, pago a proveedor..."
                    disabled={!shiftReady || loading}
                    className="cash-input"
                  />
                </div>

                {/* Referencia / Folio */}
                <div className="cash-form-group">
                  <label className="cash-form-label">
                    <Hash size={15} style={{ color: '#64748b' }} />
                    <span>Referencia / Folio</span>
                  </label>
                  <input
                    value={reference}
                    onChange={e => setReference(e.target.value)}
                    maxLength={200}
                    placeholder="Ej. Factura F-1029, Vale de caja #12..."
                    disabled={!shiftReady || loading}
                    className="cash-input"
                  />
                </div>

                {/* Evidencia */}
                <div className="cash-form-group">
                  <label className="cash-form-label">
                    <ReceiptText size={15} style={{ color: '#64748b' }} />
                    <span>Evidencia / Comprobante</span>
                  </label>
                  <input
                    value={evidence}
                    onChange={e => setEvidence(e.target.value)}
                    maxLength={200}
                    placeholder="Ej. Ticket firmado, Nota de remisión #48..."
                    disabled={!shiftReady || loading}
                    className="cash-input"
                  />
                </div>

                {/* Importe */}
                <div className="cash-form-group">
                  <label className="cash-form-label">
                    <Coins size={15} style={{ color: '#64748b' }} />
                    <span>Importe (MXN)</span>
                    <span className="cash-form-label-required">*</span>
                  </label>
                  <div className="cash-input-wrapper">
                    <span className="cash-input-prefix">$</span>
                    <input
                      value={amount}
                      onChange={e => setAmount(e.target.value)}
                      inputMode="decimal"
                      maxLength={18}
                      required
                      placeholder="0.00"
                      disabled={!shiftReady || loading}
                      className="cash-input cash-input-prefixed"
                    />
                  </div>
                </div>

                {/* Botón de Confirmación */}
                <button
                  type="submit"
                  disabled={loading || !shiftReady}
                  className={`cash-submit-btn ${type}`}
                >
                  {loading ? (
                    <>
                      <RotateCw size={18} className="cash-spin" />
                      <span>Registrando...</span>
                    </>
                  ) : (
                    <>
                      <Send size={18} />
                      <span>
                        Confirmar movimiento
                      </span>
                    </>
                  )}
                </button>
              </form>
            </>
          }

          {/* Feedback de Estado */}
          {status && (
            <div
              style={{ marginTop: 16 }}
              className={`cash-alert ${
                status.includes('no confirmada') || status.includes('rechazada') || status.includes('No se pudo')
                  ? 'cash-alert-danger'
                  : status.includes('confirmado') || status.includes('compensado')
                  ? 'cash-alert-success'
                  : 'cash-alert-info'
              }`}
              role={status.includes('no confirmada') || status.includes('rechazada') ? 'alert' : 'status'}
            >
              {status.includes('no confirmada') || status.includes('rechazada') ? (
                <AlertCircle size={18} style={{ flexShrink: 0, marginTop: 2 }} />
              ) : status.includes('confirmado') || status.includes('compensado') ? (
                <CheckCircle2 size={18} style={{ flexShrink: 0, marginTop: 2 }} />
              ) : (
                <Info size={18} style={{ flexShrink: 0, marginTop: 2 }} />
              )}
              <span>{status}</span>
            </div>
          )}
        </div>

        {/* Columna Derecha: Ledger de Auditoría */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          {capabilities.canRead && <section aria-label="Ledger de caja">
              <div className="cash-card-header">
                <div className="cash-card-header-left">
                  <ReceiptText size={20} style={{ color: '#475569' }} />
                  <h2 className="cash-card-title">Ledger</h2>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span className="cash-card-badge">{ledger.length} registros</span>
                  <button
                    type="button"
                    className="cash-refresh-btn"
                    onClick={() => void refreshLedger()}
                    disabled={ledgerLoading}
                    title="Actualizar ledger"
                  >
                    <RotateCw size={15} className={ledgerLoading ? 'cash-spin' : ''} />
                  </button>
                </div>
              </div>

              {ledgerLoading && (
                <div className="cash-empty-state">
                  <RotateCw size={36} className="cash-spin" style={{ color: '#10b981', marginBottom: 12 }} />
                  <p className="cash-empty-title" role="status">Cargando ledger…</p>
                </div>
              )}

              {!ledgerLoading && !ledger.length && (
                <div className="cash-empty-state">
                  <div className="cash-empty-icon">
                    <Inbox size={28} />
                  </div>
                  <p className="cash-empty-title" role="status">No hay movimientos para esta sucursal.</p>
                  <p className="cash-empty-desc">
                    Los retiros y depósitos confirmados en este turno se reflejarán aquí con su detalle contable y opción de compensación.
                  </p>
                </div>
              )}

              {!ledgerLoading && ledger.length > 0 && (
                <ul className="cash-ledger-list">
                  {ledger.map(item => {
                    const isWithdrawal = item.movement_type === 'withdrawal';
                    const isDeposit = item.movement_type === 'deposit';
                    return (
                      <li key={item.id} className="cash-ledger-item">
                        <div className="cash-ledger-left">
                          <div className={`cash-ledger-icon-badge ${isWithdrawal ? 'withdrawal' : isDeposit ? 'deposit' : 'reversal'}`}>
                            {isWithdrawal ? <ArrowDownRight size={20} /> : isDeposit ? <ArrowUpRight size={20} /> : <RotateCcw size={20} />}
                          </div>
                          <div className="cash-ledger-details">
                            <div className="cash-ledger-title-row">
                              <span style={{ fontWeight: 700, color: isWithdrawal ? '#dc2626' : isDeposit ? '#059669' : '#2563eb' }}>
                                {cashMovementTypeLabel(item.movement_type)}
                              </span>
                              <span style={{ color: '#94a3b8' }}>•</span>
                              <span className="cash-ledger-reason">{item.reason}</span>
                            </div>
                            <div className="cash-ledger-meta">
                              <span>Estado: {cashCompensationStateLabel(item.compensation_state)}</span>
                              {item.compensated_by_movement_id && (
                                <span style={{ color: '#b45309' }}>• Compensado por: {item.compensated_by_movement_id}</span>
                              )}
                            </div>
                          </div>
                        </div>

                        <div className="cash-ledger-right">
                          <span className={`cash-ledger-amount ${isWithdrawal ? 'withdrawal' : isDeposit ? 'deposit' : 'reversal'}`}>
                            {isWithdrawal ? '-' : '+'}${centsToMxn(item.amount_cents)}
                          </span>
                          {canCompensateLedgerItem(capabilities.canCompensate, item.compensation_state) && (
                            <button
                              type="button"
                              className="cash-compensate-btn"
                              onClick={() => dispatchCompensation({ type: 'open', target: item })}
                              disabled={compensation.loading}
                              title="Compensar este movimiento"
                            >
                              <RotateCcw size={13} />
                              <span>Compensar</span>
                            </button>
                          )}
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
            </section>
          }

          {/* Formulario de Compensación cuando hay intención activa */}
          {compensation.intent && (
            <div className="cash-card" style={{ border: '2px solid #fed7aa', background: '#fffaf5' }}>
              <div className="cash-card-header" style={{ borderBottomColor: '#ffedd5' }}>
                <div className="cash-card-header-left">
                  <ShieldAlert size={20} style={{ color: '#ea580c' }} />
                  <h2 className="cash-card-title" style={{ color: '#9a3412' }}>Compensar movimiento</h2>
                </div>
                <button
                  type="button"
                  onClick={() => dispatchCompensation({ type: 'cancel' })}
                  disabled={compensation.loading}
                  style={{ background: 'none', border: 'none', color: '#9a3412', cursor: 'pointer', padding: 4 }}
                >
                  <X size={18} />
                </button>
              </div>

              <p style={{ margin: '0 0 16px 0', fontSize: '0.9rem', color: '#7c2d12', lineHeight: 1.4 }}>
                Se compensará {cashMovementTypeLabel(compensation.intent.target.movement_type)}: <strong>${centsToMxn(compensation.intent.target.amount_cents)}</strong>.
              </p>

              <form aria-label="Compensar movimiento" onSubmit={submitCompensation} className="cash-form">
                <div className="cash-form-group">
                  <label className="cash-form-label">
                    <span>Motivo</span>
                    <span className="cash-form-label-required">*</span>
                  </label>
                  <input
                    value={compensation.intent.reason}
                    onChange={e => dispatchCompensation({ type: 'set_reason', reason: e.target.value })}
                    maxLength={600}
                    required
                    disabled={compensation.loading}
                    placeholder="Motivo de la compensación"
                    className="cash-input"
                  />
                </div>

                <div className="cash-form-group">
                  <label className="cash-form-label">
                    <span>Evidencia</span>
                    <span className="cash-form-label-required">*</span>
                  </label>
                  <input
                    value={compensation.intent.evidence}
                    onChange={e => dispatchCompensation({ type: 'set_evidence', evidence: e.target.value })}
                    maxLength={600}
                    required
                    disabled={compensation.loading}
                    placeholder="Referencia de comprobante o autorización"
                    className="cash-input"
                  />
                </div>

                <div style={{ display: 'flex', gap: 10, marginTop: 8 }}>
                  <button
                    type="button"
                    onClick={() => dispatchCompensation({ type: 'cancel' })}
                    disabled={compensation.loading}
                    style={{
                      flex: 1,
                      padding: '10px 16px',
                      borderRadius: 10,
                      border: '1px solid #cbd5e1',
                      background: '#ffffff',
                      color: '#475569',
                      fontWeight: 600,
                      cursor: 'pointer',
                    }}
                  >
                    Cancelar
                  </button>
                  <button
                    type="submit"
                    disabled={compensation.loading}
                    style={{
                      flex: 2,
                      padding: '10px 16px',
                      borderRadius: 10,
                      border: 'none',
                      background: '#ea580c',
                      color: '#ffffff',
                      fontWeight: 700,
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: 6,
                    }}
                  >
                    {compensation.loading ? <RotateCw size={16} className="cash-spin" /> : <CheckCircle2 size={16} />}
                    <span>Confirmar compensación</span>
                  </button>
                </div>
              </form>
            </div>
          )}

          {/* Sincronización Offline */}
          {gatewayUrl && (
            <section className="cash-offline-card" aria-label="Sincronización offline de caja">
              <div className="cash-offline-header">
                <h3 className="cash-offline-title">
                  {offlineStatus === 'GATEWAY_UNAVAILABLE' || offlineStatus === 'CONFLICT' ? (
                    <WifiOff size={18} style={{ color: '#dc2626' }} />
                  ) : (
                    <Wifi size={18} style={{ color: '#10b981' }} />
                  )}
                  <span>Sincronización offline</span>
                </h3>
                {offlineStatus && (
                  <span
                    className="cash-card-badge"
                    style={{
                      background: offlineStatus === 'CONFLICT' || offlineStatus === 'GATEWAY_UNAVAILABLE' ? '#fef2f2' : '#ecfdf5',
                      color: offlineStatus === 'CONFLICT' || offlineStatus === 'GATEWAY_UNAVAILABLE' ? '#b91c1c' : '#047857',
                    }}
                    role={offlineStatus === 'CONFLICT' || offlineStatus === 'GATEWAY_UNAVAILABLE' ? 'alert' : 'status'}
                  >
                    {offlineCashStatusLabel(offlineStatus)}
                  </span>
                )}
              </div>

              {offlineMovements.length > 0 ? (
                <ul style={{ margin: '8px 0 0', padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {offlineMovements.map(item => (
                    <li
                      key={item.command_id}
                      style={{
                        fontSize: '0.82rem',
                        padding: '8px 12px',
                        borderRadius: 8,
                        background: '#ffffff',
                        border: '1px solid #e2e8f0',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                      }}
                    >
                      <span style={{ fontWeight: 600, color: '#334155' }}>
                        {offlineCashStatusLabel(item.status)}
                      </span>
                      {item.conflict_code && (
                        <span style={{ color: '#b91c1c', fontSize: '0.78rem' }}>
                          Requiere revisión del supervisor
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              ) : (
                <p style={{ margin: 0, fontSize: '0.82rem', color: '#64748b' }}>
                  No hay movimientos pendientes de sincronización local.
                </p>
              )}
            </section>
          )}
        </div>
      </div>
    </div>
  );
}

