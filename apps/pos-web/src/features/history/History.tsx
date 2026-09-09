import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Card, Modal } from '@restaurantos/ui';
import { ApiError, fetchApi, formatOrderModifier } from '@restaurantos/api-client';
import { Calendar, ChefHat, ChevronRight, Clock, CreditCard, Pencil, Printer, ReceiptText, RefreshCcw, Search, X } from 'lucide-react';
import { usePosSession } from '../../session';
import { localDayUtcBounds } from '../reports/salesMonitorState';

type PaymentMethod = 'cash' | 'debit_card' | 'credit_card' | 'transfer';
type RequestStatus = 'REQUESTED' | 'APPROVED' | 'REJECTED' | 'EXPIRED' | 'APPLIED';

interface OrderAccount {
  id: string;
  folio: string;
  status: string;
  payment_status?: 'PENDING' | 'CONFIRMED';
  total_cents: number;
  created_at: string;
  customer_label: string | null;
  service_type: string | null;
  register_code: string | null;
  cash_shift_id: string | null;
  reopen_eligible: boolean;
  active_reopen_request_status: RequestStatus | null;
  order_notes?: string | null;
  table_number?: string | null;
  cash_amount?: string | null;
}

interface OrderDetail extends OrderAccount {
  version: number;
  editable: boolean;
  edit_block_reason?: string | null;
  payment_method_intent?: PaymentMethod | null;
  customer_phone?: string | null;
  delivery_address?: string | null;
  delivery_notes?: string | null;
  channel?: string | null;
  lines: Array<{
    id: string;
    product_id: string;
    product_name: string;
    quantity: number;
    unit_price_cents: number;
    line_total_cents: number;
    line_notes?: string | null;
    selected_modifiers?: unknown[];
  }>;
  production_tasks: Array<{ id: string; order_line_id: string; status: 'PENDING' | 'IN_PROGRESS' | 'COMPLETED' | 'CANCELLED'; quantity: number; product_name: string }>;
  payments: Array<{ id: string; method: string; status: string; amount_cents: number }>;
  sales_operation_snapshots?: Array<{ id: string; quality_status?: string; captured_at?: string }>;
  corrections: Array<{ id: string; request_id: string; folio: string; corrected_total_cents: number; settlement_delta_cents: number; currency: string; applied_at: string }>;
}

interface OrderAccountsResponse { items: OrderAccount[]; next_cursor: string | null }
interface ReopenRequest {
  id: string;
  branch_id: string;
  order_id: string;
  status: RequestStatus;
  reason: string;
  evidence_refs: string[];
  decision_reason: string | null;
  requested_at: string;
  order_version_snapshot: number;
}
interface ReopenRequestsResponse { items: ReopenRequest[]; next_cursor: string | null }
interface CorrectionProduct { id: string; name: string; price_cents: number; status: string; is_available?: boolean }
interface CorrectionDraftLine {
  key: string;
  sourceLineId?: string;
  productId?: string;
  productName: string;
  quantity: number;
  originalQuantity?: number;
}
interface ProductionDisposition {
  source_line_id: string;
  source_task_id: string;
  quantity: number;
  disposition: 'waste' | 'recovery';
}

const PAYMENT_METHODS: Array<{ value: PaymentMethod; label: string; hint: string }> = [
  { value: 'cash', label: 'Efectivo', hint: 'Pago en caja' },
  { value: 'debit_card', label: 'Débito', hint: 'Tarjeta de débito' },
  { value: 'credit_card', label: 'Crédito', hint: 'Tarjeta de crédito' },
  { value: 'transfer', label: 'Transferencia', hint: 'Transferencia bancaria' },
];

const newIdempotencyKey = () => globalThis.crypto?.randomUUID?.() ?? `pco005-${Date.now()}-${Math.random().toString(36).slice(2)}`;
const requestSignature = (orderId: string, reason: string, evidence: string[]) => JSON.stringify({ orderId, reason: reason.trim(), evidence });
const decisionSignature = (requestId: string, decision: string, decisionReason: string) => JSON.stringify({ requestId, decision, decisionReason: decisionReason.trim() });
const correctionSignature = (requestId: string, version: number, lines: CorrectionDraftLine[], dispositions: ProductionDisposition[], method: PaymentMethod, evidence: string[], registerId: string | null) => JSON.stringify({ requestId, version, lines, dispositions, method, evidence, registerId });

const getStatusConfig = (status: string) => {
  switch (status) {
    case 'PENDING': return { label: 'Por aceptar', bg: '#fef3c7', color: '#b45309', border: '#fde68a' };
    case 'PENDING_PAYMENT': return { label: 'Pendiente de pago', bg: '#fff7ed', color: '#c2410c', border: '#fed7aa' };
    case 'COMPLETED': case 'CLOSED': case 'CERRADO': return { label: 'Completado', bg: '#ecfdf5', color: '#059669', border: '#a7f3d0' };
    case 'ACCEPTED': case 'PREPARING': return { label: 'Preparando', bg: '#eff6ff', color: '#2563eb', border: '#bfdbfe' };
    case 'READY': return { label: 'Listo', bg: '#fef3c7', color: '#d97706', border: '#fde68a' };
    case 'CANCELLED': return { label: 'Cancelado', bg: '#fef2f2', color: '#dc2626', border: '#fecaca' };
    default: return { label: status, bg: '#f1f5f9', color: '#475569', border: '#e2e8f0' };
  }
};
const getRequestStatusConfig = (status: RequestStatus | string) => {
  switch (status) {
    case 'REQUESTED': return { label: 'Pendiente de autorización', bg: '#fef3c7', color: '#b45309', border: '#fde68a' };
    case 'APPROVED': return { label: 'Aprobada (Lista para corrección)', bg: '#ecfdf5', color: '#059669', border: '#a7f3d0' };
    case 'REJECTED': return { label: 'Rechazada', bg: '#fef2f2', color: '#dc2626', border: '#fecaca' };
    case 'APPLIED': return { label: 'Aplicada', bg: '#eff6ff', color: '#2563eb', border: '#bfdbfe' };
    case 'EXPIRED': return { label: 'Expirada', bg: '#f1f5f9', color: '#64748b', border: '#e2e8f0' };
    default: return { label: status, bg: '#f1f5f9', color: '#475569', border: '#e2e8f0' };
  }
};
const getTypeLabel = (type?: string | null) => ({ 'dine-in': 'En sucursal', takeout: 'Para llevar', delivery: 'A domicilio' }[type || ''] || type || 'General');
const getCorrectionDeltaLabel = (deltaCents: number) => deltaCents > 0 ? 'Cargo adicional' : deltaCents < 0 ? 'Reembolso' : 'Conciliación sin diferencia';

const History = () => {
  const navigate = useNavigate();
  const { hasPermission, session } = usePosSession();
  const canRequestReopen = hasPermission('orders.reopen.request');
  const canAuthorizeReopen = hasPermission('orders.reopen.authorize');
  const branchId = session?.active_branch?.id || '';
  const branchTimezone = session?.active_branch?.timezone || 'UTC';
  const configuredRegisterId = (localStorage.getItem('pos_register_id') || '').trim();
  const [orders, setOrders] = useState<OrderAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [day, setDay] = useState('');
  const [cashShiftId, setCashShiftId] = useState('');
  const [registerCode, setRegisterCode] = useState('');
  const [serviceType, setServiceType] = useState('');
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [selected, setSelected] = useState<OrderDetail | null>(null);
  const [activeOrderId, setActiveOrderId] = useState<string | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod>('cash');
  const [paymentPending, setPaymentPending] = useState(false);
  const [listError, setListError] = useState('');
  const [detailError, setDetailError] = useState('');
  const [reopenReason, setReopenReason] = useState('');
  const [evidenceText, setEvidenceText] = useState('');
  const [reopenPending, setReopenPending] = useState(false);
  const [reopenError, setReopenError] = useState('');
  const [reprintMessage, setReprintMessage] = useState('');

  const handleReprint = async (orderId: string) => {
    try {
      setReprintMessage('Enviando reimpresión a la cola...');
      await fetchApi('/print-jobs', {
        method: 'POST',
        body: JSON.stringify({
          order_id: orderId,
          job_type: 'receipt',
          target: 'counter-printer',
          payload: { order_id: orderId, reprint: true, requested_at: new Date().toISOString() },
        }),
      });
      setReprintMessage('✓ Ticket / Comanda enviada a la impresora.');
    } catch {
      setReprintMessage('Ticket / Comanda enviada a la terminal.');
    }
    setTimeout(() => setReprintMessage(''), 3500);
  };
  const [showReopenHistory, setShowReopenHistory] = useState(false);
  const requestKeyRef = useRef<{ signature: string; key: string } | null>(null);
  const decisionKeysRef = useRef(new Map<string, { signature: string; key: string }>());
  const [requests, setRequests] = useState<ReopenRequest[]>([]);
  const [requestsCursor, setRequestsCursor] = useState<string | null>(null);
  const [requestsLoading, setRequestsLoading] = useState(false);
  const [requestsError, setRequestsError] = useState('');
  const [decisionReasonById, setDecisionReasonById] = useState<Record<string, string>>({});
  const [decisionPendingId, setDecisionPendingId] = useState<string | null>(null);
  const [correctionRequest, setCorrectionRequest] = useState<ReopenRequest | null>(null);
  const [correctionLines, setCorrectionLines] = useState<CorrectionDraftLine[]>([]);
  const [correctionProducts, setCorrectionProducts] = useState<CorrectionProduct[]>([]);
  const [correctionProductsLoading, setCorrectionProductsLoading] = useState(false);
  const [correctionProductId, setCorrectionProductId] = useState('');
  const [correctionSettlementMethod, setCorrectionSettlementMethod] = useState<PaymentMethod>('cash');
  const [correctionEvidenceText, setCorrectionEvidenceText] = useState('');
  const [correctionDispositions, setCorrectionDispositions] = useState<Record<string, 'waste' | 'recovery'>>({});
  const [correctionState, setCorrectionState] = useState<'editing' | 'submitting' | 'applied' | 'conflict' | 'error'>('editing');
  const [correctionError, setCorrectionError] = useState('');
  const [correctionRefreshWarning, setCorrectionRefreshWarning] = useState('');
  const correctionKeyRef = useRef<{ signature: string; key: string } | null>(null);
  const accountRequestSequence = useRef(0);

  const loadAccounts = useCallback(async (cursor: string | null = null, append = false) => {
    const sequence = ++accountRequestSequence.current;
    setLoading(true); setListError('');
    const params = new URLSearchParams({ limit: '25' });
    if (branchId) params.set('branch_id', branchId);
    if (day) {
      const bounds = localDayUtcBounds(day, branchTimezone);
      params.set('from_utc', bounds.fromUtc); params.set('to_utc', bounds.toUtc);
    }
    if (cashShiftId) params.set('cash_shift_id', cashShiftId);
    if (registerCode) params.set('register_code', registerCode);
    if (serviceType) params.set('service_type', serviceType);
    const search = searchQuery.trim();
    if (search.length >= 2) params.set('q', search);
    if (cursor) params.set('cursor', cursor);
    try {
      const data = await fetchApi<OrderAccountsResponse>(`/orders/accounts?${params.toString()}`, { headers: { 'Cache-Control': 'no-cache' } });
      if (sequence !== accountRequestSequence.current) return;
      setOrders((previous) => append ? [...previous, ...data.items] : data.items);
      setNextCursor(data.next_cursor);
    } catch (reason) {
      if (sequence !== accountRequestSequence.current) return;
      setListError(reason instanceof ApiError ? reason.message : 'No fue posible cargar las cuentas.');
      if (!append) setOrders([]);
    } finally {
      if (sequence === accountRequestSequence.current) setLoading(false);
    }
  }, [branchId, branchTimezone, cashShiftId, day, registerCode, searchQuery, serviceType]);

  const loadRequests = useCallback(async (cursor: string | null = null, append = false) => {
    if (!canAuthorizeReopen) return;
    setRequestsLoading(true); setRequestsError('');
    const params = new URLSearchParams({ limit: '20' });
    if (branchId) params.set('branch_id', branchId);
    if (cursor) params.set('cursor', cursor);
    try {
      const data = await fetchApi<ReopenRequestsResponse>(`/orders/reopen-requests?${params.toString()}`);
      setRequests((previous) => append ? [...previous, ...data.items] : data.items);
      setRequestsCursor(data.next_cursor);
    } catch (reason) {
      setRequestsError(reason instanceof ApiError ? reason.message : 'No fue posible cargar solicitudes.');
      if (!append) setRequests([]);
    } finally { setRequestsLoading(false); }
  }, [branchId, canAuthorizeReopen]);

  useEffect(() => {
    const timeout = window.setTimeout(() => { void loadAccounts(); }, 250);
    return () => window.clearTimeout(timeout);
  }, [loadAccounts]);
  useEffect(() => { void loadRequests(); }, [loadRequests]);

  const openOrder = async (orderId: string) => {
    setActiveOrderId(orderId); setSelected(null); setDetailLoading(true); setDetailError('');
    try { const detail = await fetchApi<OrderDetail>(`/orders/${orderId}`); setSelected(detail); setPaymentMethod(detail.payment_method_intent || 'cash'); }
    catch (reason) { setDetailError(reason instanceof ApiError ? reason.message : 'No fue posible abrir el pedido.'); }
    finally { setDetailLoading(false); }
  };
  const closeDetail = () => { setSelected(null); setActiveOrderId(null); setDetailError(''); setReopenError(''); };
  const refreshSelected = async () => { if (selected) await openOrder(selected.id); };
  const confirmPayment = async () => {
    if (!selected) return;
    if (!configuredRegisterId) { setDetailError('Configura la caja en Configuración > Turno y Caja antes de confirmar el pago.'); return; }
    setPaymentPending(true); setDetailError('');
    try {
      const idempotencyKey = `pay-${selected.id}-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
      await fetchApi(`/orders/${selected.id}/payments`, {
        method: 'POST',
        headers: { 'Idempotency-Key': idempotencyKey },
        body: JSON.stringify({
          amount_cents: selected.total_cents,
          method: paymentMethod,
          register_id: configuredRegisterId,
          idempotency_key: idempotencyKey,
        }),
      });
      await loadAccounts();
      await refreshSelected();
    }
    catch (reason) { setDetailError(reason instanceof ApiError ? reason.message : 'No fue posible confirmar el pago.'); }
    finally { setPaymentPending(false); }
  };
  const [acceptPending, setAcceptPending] = useState(false);
  const acceptOrder = async (orderId: string) => {
    setAcceptPending(true);
    setDetailError('');
    try {
      await fetchApi(`/orders/${encodeURIComponent(orderId)}/accept`, { method: 'POST' });
      window.dispatchEvent(new Event('pos:pending-orders-changed'));
      await Promise.all([loadAccounts(), refreshSelected()]);
    } catch (reason) {
      setDetailError(reason instanceof ApiError ? reason.message : 'No fue posible aceptar el pedido.');
    } finally {
      setAcceptPending(false);
    }
  };
  const submitReopenRequest = async () => {
    if (!selected || !canRequestReopen || !selected.reopen_eligible || selected.active_reopen_request_status) return;
    const evidenceRefs = evidenceText.split('\n').map((value) => value.trim()).filter(Boolean);
    const signature = requestSignature(selected.id, reopenReason, evidenceRefs);
    if (reopenReason.trim().length < 10 || reopenReason.trim().length > 500 || evidenceRefs.length < 1 || evidenceRefs.length > 10 || evidenceRefs.some((value) => value.length > 500)) { setReopenError('El motivo requiere 10 a 500 caracteres y la evidencia 1 a 10 referencias no vacías de hasta 500 caracteres.'); return; }
    if (!requestKeyRef.current || requestKeyRef.current.signature !== signature) requestKeyRef.current = { signature, key: newIdempotencyKey() };
    setReopenPending(true); setReopenError('');
    try {
      await fetchApi(`/orders/${selected.id}/reopen-requests`, { method: 'POST', headers: { 'Idempotency-Key': requestKeyRef.current.key }, body: JSON.stringify({ reason: reopenReason.trim(), evidence_refs: evidenceRefs }) });
      requestKeyRef.current = null; setReopenReason(''); setEvidenceText(''); await Promise.all([loadAccounts(), refreshSelected(), loadRequests()]);
    } catch (reason) { setReopenError(reason instanceof ApiError ? reason.message : 'No fue posible enviar la solicitud. Conserva la misma clave para reintentar de forma segura.'); }
    finally { setReopenPending(false); }
  };
  const decideRequest = async (request: ReopenRequest, decision: 'approve' | 'reject') => {
    if (!canAuthorizeReopen) return;
    const decisionReason = decisionReasonById[request.id] || '';
    if (decisionReason.trim().length < 10 || decisionReason.trim().length > 500) { setRequestsError('El motivo de la decisión requiere 10 a 500 caracteres.'); return; }
    const mapKey = `${request.id}:${decision}`;
    const signature = decisionSignature(request.id, decision, decisionReason);
    const current = decisionKeysRef.current.get(mapKey);
    if (!current || current.signature !== signature) decisionKeysRef.current.set(mapKey, { signature, key: newIdempotencyKey() });
    setDecisionPendingId(request.id); setRequestsError('');
    try {
      await fetchApi(`/orders/reopen-requests/${request.id}/${decision}`, { method: 'POST', headers: { 'Idempotency-Key': decisionKeysRef.current.get(mapKey)?.key || '' }, body: JSON.stringify({ decision_reason: decisionReason.trim() }) });
      decisionKeysRef.current.delete(mapKey); await Promise.all([loadRequests(), loadAccounts(), refreshSelected()]);
    } catch (reason) { setRequestsError(reason instanceof ApiError ? reason.message : 'No fue posible registrar la decisión.'); }
    finally { setDecisionPendingId(null); }
  };
  const closeCorrectionEditor = () => {
    if (correctionState === 'submitting') return;
    setCorrectionRequest(null); setCorrectionLines([]); setCorrectionProducts([]); setCorrectionProductId('');
    setCorrectionEvidenceText(''); setCorrectionDispositions({}); setCorrectionState('editing'); setCorrectionError(''); setCorrectionRefreshWarning('');
    correctionKeyRef.current = null;
  };
  const invalidateCorrectionRetry = () => {
    correctionKeyRef.current = null;
    if (correctionState !== 'submitting') setCorrectionState('editing');
    setCorrectionError('');
  };
  const openCorrectionEditor = async (request: ReopenRequest) => {
    if (!canAuthorizeReopen || request.status !== 'APPROVED') return;
    setRequestsError(''); setCorrectionError(''); setCorrectionRefreshWarning(''); setCorrectionState('editing'); setCorrectionRequest(request);
    setCorrectionProductsLoading(true);
    try {
      const [detail, catalog] = await Promise.all([
        fetchApi<OrderDetail>(`/orders/${request.order_id}`),
        fetchApi<CorrectionProduct[]>(`/catalog/products?branch_id=${encodeURIComponent(branchId)}`),
      ]);
      if (detail.version !== request.order_version_snapshot) {
        setCorrectionError('La versión del pedido cambió desde la autorización. Actualiza la solicitud antes de aplicar.');
        setCorrectionState('conflict');
        return;
      }
      setSelected(detail); setActiveOrderId(detail.id);
      setCorrectionLines(detail.lines.map((line) => ({ key: `source:${line.id}`, sourceLineId: line.id, productName: line.product_name, quantity: line.quantity, originalQuantity: line.quantity })));
      setCorrectionProducts(Array.isArray(catalog) ? catalog.filter((product) => product.status === 'active' && product.is_available !== false && Number.isSafeInteger(product.price_cents) && product.price_cents > 0) : []);
      const originalMethod = detail.payments.find((payment) => payment.status === 'CONFIRMED')?.method;
      setCorrectionSettlementMethod(PAYMENT_METHODS.some((method) => method.value === originalMethod) ? originalMethod as PaymentMethod : 'cash');
      setCorrectionEvidenceText(''); setCorrectionDispositions({}); correctionKeyRef.current = null;
    } catch (reason) {
      setCorrectionError(reason instanceof ApiError ? reason.message : 'No fue posible abrir el editor de corrección.');
      setCorrectionState('error');
    } finally { setCorrectionProductsLoading(false); }
  };
  const updateCorrectionQuantity = (key: string, quantity: number) => {
    invalidateCorrectionRetry();
    setCorrectionLines((current) => current.flatMap((line) => {
      if (line.key !== key) return [line];
      const bounded = Math.max(0, Math.min(line.originalQuantity || 99, Math.trunc(quantity)));
      return bounded > 0 ? [{ ...line, quantity: bounded }] : [];
    }));
  };
  const addCorrectionProduct = () => {
    const product = correctionProducts.find((candidate) => candidate.id === correctionProductId);
    if (!product) return;
    invalidateCorrectionRetry();
    setCorrectionLines((current) => {
      const existing = current.find((line) => line.productId === product.id && !line.sourceLineId);
      if (existing) return current.map((line) => line.key === existing.key ? { ...line, quantity: line.quantity + 1 } : line);
      return [...current, { key: `product:${product.id}`, productId: product.id, productName: product.name, quantity: 1 }];
    });
    setCorrectionProductId('');
  };
  const correctionCompletedReductions = useMemo(() => {
    if (!selected) return [] as Array<{ task: OrderDetail['production_tasks'][number]; reduction: number; lineName: string }>;
    const desired = new Map(correctionLines.filter((line) => line.sourceLineId).map((line) => [line.sourceLineId!, line.quantity]));
    return selected.production_tasks.flatMap((task) => {
      if (task.status !== 'COMPLETED') return [];
      const original = selected.lines.find((line) => line.id === task.order_line_id);
      const target = desired.get(task.order_line_id) || 0;
      const reduction = (original?.quantity || 0) - target;
      return reduction > 0 ? [{ task, reduction, lineName: original?.product_name || task.product_name }] : [];
    });
  }, [correctionLines, selected]);
  const correctionHasInProgressReduction = useMemo(() => {
    if (!selected) return false;
    const desired = new Map(correctionLines.filter((line) => line.sourceLineId).map((line) => [line.sourceLineId!, line.quantity]));
    return selected.production_tasks.some((task) => task.status === 'IN_PROGRESS' && (selected.lines.find((line) => line.id === task.order_line_id)?.quantity || 0) > (desired.get(task.order_line_id) || 0));
  }, [correctionLines, selected]);
  const submitCorrection = async () => {
    if (!canAuthorizeReopen || !correctionRequest || !selected || correctionState === 'submitting') return;
    if (correctionSettlementMethod === 'cash' && !configuredRegisterId) { setCorrectionError('Configura una caja antes de liquidar una corrección en efectivo.'); return; }
    if (correctionHasInProgressReduction) { setCorrectionError('No se puede reducir una línea con producción iniciada. Ajusta la imagen o espera la resolución operativa.'); return; }
    const evidence = correctionEvidenceText.split('\n').map((value) => value.trim()).filter(Boolean);
    if (evidence.some((value) => value.length > 500)) { setCorrectionError('Cada referencia de evidencia puede tener hasta 500 caracteres.'); return; }
    if (correctionCompletedReductions.some(({ task }) => !correctionDispositions[task.id])) { setCorrectionError('Selecciona merma o recuperación para cada reducción con producción completada.'); return; }
    const production_dispositions: ProductionDisposition[] = correctionCompletedReductions.map(({ task, reduction }) => ({ source_line_id: task.order_line_id, source_task_id: task.id, quantity: reduction, disposition: correctionDispositions[task.id]! }));
    const payload = {
      expected_order_version: selected.version,
      lines: correctionLines.map((line) => line.sourceLineId ? { source_line_id: line.sourceLineId, quantity: line.quantity } : { product_id: line.productId, quantity: line.quantity }),
      production_dispositions,
      settlement_method: correctionSettlementMethod,
      settlement_evidence_refs: evidence,
      ...(correctionSettlementMethod === 'cash' ? { register_id: configuredRegisterId } : {}),
    };
    const signature = correctionSignature(correctionRequest.id, selected.version, correctionLines, production_dispositions, correctionSettlementMethod, evidence, correctionSettlementMethod === 'cash' ? configuredRegisterId : null);
    if (!correctionKeyRef.current || correctionKeyRef.current.signature !== signature) correctionKeyRef.current = { signature, key: newIdempotencyKey() };
    if (!window.confirm('Aplicar la corrección compensatoria. El pedido, pago y corte originales permanecerán inmutables.')) return;
    setCorrectionState('submitting'); setCorrectionError('');
    try {
      await fetchApi(`/orders/reopen-requests/${correctionRequest.id}/apply`, { method: 'POST', headers: { 'Idempotency-Key': correctionKeyRef.current.key }, body: JSON.stringify(payload) });
    } catch (reason) {
      const apiError = reason instanceof ApiError ? reason : null;
      setCorrectionError(apiError?.message || 'No fue posible aplicar la corrección. Reintenta con la misma clave si el plan no cambia.');
      setCorrectionState(apiError?.code === 'order_version_conflict' || apiError?.code === 'order_reopen_transition_invalid' ? 'conflict' : 'error');
      return;
    }
    correctionKeyRef.current = null;
    setCorrectionState('applied');
    try {
      await Promise.all([loadRequests(), loadAccounts(), refreshSelected()]);
    } catch (reason) {
      setCorrectionRefreshWarning('La corrección fue aplicada, pero no se pudo actualizar esta vista. Cierra y actualiza la pantalla para consultar el resultado.');
    }
  };

  const formatCurrency = (cents: number) => new Intl.NumberFormat('es-MX', { style: 'currency', currency: 'MXN' }).format(cents / 100 || 0);
  const selectedStatus = selected ? getStatusConfig(selected.status) : null;
  const selectedSnapshotQuality = selected?.sales_operation_snapshots?.map((snapshot) => snapshot.quality_status || 'sin dato').join(', ') || 'Sin snapshot operativo';
  const today = useMemo(() => new Date().toLocaleDateString('en-CA', { timeZone: branchTimezone }), [branchTimezone]);

  return <div className="orders-history-page">
    <header className="orders-history-header"><div><h1>Pedidos — <span style={{ color: '#10b981' }}>{session?.user?.display_name || ''}</span></h1><p>Consulta, edita y confirma el pago de los pedidos de la sucursal <strong style={{ color: '#0f172a' }}>{session?.active_branch?.name || 'activa'}</strong>.</p></div>
      <div className="orders-history-toolbar"><label className="orders-history-search"><Search size={18} aria-hidden="true" /><input type="search" aria-label="Buscar pedido" placeholder="Buscar folio o cliente…" value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} /></label><Button className="orders-history-refresh" variant="secondary" onClick={() => void loadAccounts()}><RefreshCcw size={18} /> Actualizar</Button></div>
    </header>
    <section className="orders-history-filters" aria-label="Filtros de cuentas">
      <label>Día<input type="date" value={day} max={today} onChange={(event) => setDay(event.target.value)} /></label>
      <label>Turno<input value={cashShiftId} onChange={(event) => setCashShiftId(event.target.value)} placeholder="ID de turno" /></label>
      <label>Caja<input value={registerCode} onChange={(event) => setRegisterCode(event.target.value)} placeholder="Código de caja" /></label>
      <label>Servicio<select value={serviceType} onChange={(event) => setServiceType(event.target.value)}><option value="">Todos</option><option value="dine-in">En sucursal</option><option value="takeout">Para llevar</option><option value="delivery">A domicilio</option></select></label>
      <Button variant="secondary" onClick={() => { setDay(''); setCashShiftId(''); setRegisterCode(''); setServiceType(''); setSearchQuery(''); }}>Limpiar filtros</Button>
    </section>
    {listError ? <p role="alert" className="orders-history-error">{listError}</p> : null}
    <div className="orders-history-layout"><Card className="orders-history-list">{loading ? <div className="orders-history-list-state"><RefreshCcw size={32} className="orders-history-spin" /><span>Cargando cuentas…</span></div> : <><div className="orders-history-table-scroll"><table><thead><tr><th>Folio</th><th>Cliente</th><th className="orders-history-type-cell">Tipo</th><th className="orders-history-date-cell">Fecha y hora</th><th>Estado</th><th>Total</th><th aria-label="Acciones" /></tr></thead><tbody>{orders.length === 0 ? <tr><td colSpan={7}><div className="orders-history-list-state"><Calendar size={42} /><span>No se encontraron cuentas.</span></div></td></tr> : orders.map((order) => { const status = getStatusConfig(order.status); const isSelected = selected?.id === order.id || activeOrderId === order.id; return <tr key={order.id} role="button" tabIndex={0} aria-selected={isSelected} className={isSelected ? 'is-selected' : ''} onClick={() => void openOrder(order.id)} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); void openOrder(order.id); } }}><td className="orders-history-folio">{order.folio}</td><td><span>{order.customer_label || 'Cliente General'}</span><small className="orders-history-compact-meta">{getTypeLabel(order.service_type)} · {new Date(order.created_at).toLocaleString('es-MX')}</small></td><td className="orders-history-type-cell">{getTypeLabel(order.service_type)}</td><td className="orders-history-date-cell"><Clock size={15} aria-hidden="true" />{new Date(order.created_at).toLocaleString('es-MX')}</td><td><span className="orders-history-status" style={{ background: status.bg, color: status.color, borderColor: status.border }}>{status.label}</span></td><td className="orders-history-total">{formatCurrency(order.total_cents)}</td><td><ChevronRight size={20} aria-hidden="true" /></td></tr>; })}</tbody></table></div>{nextCursor ? <div className="orders-history-pagination"><Button variant="secondary" onClick={() => void loadAccounts(nextCursor, true)}>Cargar más cuentas</Button></div> : null}</>}</Card>
      <aside className="orders-history-detail" aria-label="Detalle del pedido">{detailLoading ? <div className="orders-history-detail-state" role="status"><RefreshCcw size={30} className="orders-history-spin" /><strong>Abriendo pedido…</strong><span>Estamos preparando el detalle.</span></div> : !selected ? <div className="orders-history-detail-state"><span className="orders-history-empty-icon"><ReceiptText size={30} /></span><strong>Selecciona un pedido para revisar su detalle</strong><span>Podrás consultar productos, editarlo o confirmar el pago cuando corresponda.</span>{detailError ? <p role="alert" className="orders-history-inline-error">{detailError}</p> : null}</div> : <><div className="orders-history-detail-header"><div><span>Cuenta actual</span><h2>Detalle del pedido</h2></div><button type="button" onClick={closeDetail} aria-label="Cerrar detalle del pedido"><X size={20} /></button></div><div className="orders-history-detail-scroll"><section className="orders-history-order-meta"><div><span>Pedido</span><strong>{selected.folio}</strong></div><span className="orders-history-status" style={{ background: selectedStatus?.bg, color: selectedStatus?.color, borderColor: selectedStatus?.border }}>{selectedStatus?.label}</span></section><section className="orders-history-customer"><strong>{selected.customer_label || 'Cliente General'}</strong>{selected.customer_phone ? <a href={`https://wa.me/${selected.customer_phone.replace(/\D/g, '')}`} target="_blank" rel="noreferrer" style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', color: '#16a34a', textDecoration: 'none', fontWeight: 600, fontSize: '0.88rem', margin: '4px 0' }} title="Contactar por WhatsApp">💬 WhatsApp: {selected.customer_phone}</a> : null}{selected.table_number ? <div style={{ fontSize: '0.85rem', fontWeight: 700, color: '#0284c7', margin: '4px 0' }}>🍽️ Mesa: {selected.table_number}</div> : null}{selected.delivery_address ? <div style={{ fontSize: '0.82rem', color: '#334155', margin: '4px 0', background: '#f8fafc', padding: '6px 8px', borderRadius: '6px', border: '1px solid #e2e8f0' }}>📍 <strong>Dirección:</strong> {selected.delivery_address}{selected.delivery_notes ? <small style={{ display: 'block', color: '#64748b', marginTop: '2px' }}>Ref: {selected.delivery_notes}</small> : null}</div> : null}{(selected.order_notes || (!selected.delivery_address && selected.delivery_notes)) ? <div style={{ fontSize: '0.85rem', color: '#92400e', background: '#fffbeb', border: '1px solid #fde68a', padding: '8px 10px', borderRadius: '6px', margin: '6px 0', fontWeight: 600 }}>📝 <strong>Comentarios del cliente:</strong> {selected.order_notes || selected.delivery_notes}</div> : null}{selected.cash_amount ? <div style={{ fontSize: '0.82rem', color: '#059669', background: '#ecfdf5', border: '1px solid #a7f3d0', padding: '4px 8px', borderRadius: '6px', margin: '4px 0', fontWeight: 600 }}>💵 <strong>Paga en efectivo con:</strong> ${selected.cash_amount}</div> : null}<span>{getTypeLabel(selected.service_type)} {selected.channel === 'online_menu' || selected.channel === 'PUBLIC_INTENT' ? '· 📱 Pedido Web' : ''}</span><small>{new Date(selected.created_at).toLocaleString('es-MX')}</small></section><section className="orders-history-snapshot"><strong>Calidad del snapshot operativo</strong><span>{selectedSnapshotQuality}</span></section><section className="orders-history-lines"><div className="orders-history-section-title"><span>Productos</span><small>{selected.lines.length} línea(s)</small></div>{selected.lines.map((line) => <div key={line.id} className="orders-history-line"><span className="orders-history-line-quantity">{line.quantity}</span><div style={{ flex: 1 }}><strong>{line.product_name}</strong><small>{line.quantity} × {formatCurrency(line.unit_price_cents)}</small>{line.selected_modifiers && line.selected_modifiers.length > 0 && <div style={{ fontSize: '0.8rem', color: '#475569', marginTop: '2px' }}>{line.selected_modifiers.map((mod, mIdx) => { const presentation = formatOrderModifier(mod); return <span key={mIdx} style={{ display: 'inline-block', marginRight: '6px', background: '#f1f5f9', padding: '1px 5px', borderRadius: '4px' }}>+ {presentation.label}{presentation.priceLabel ? ` (${presentation.priceLabel})` : ''}</span>; })}</div>}{line.line_notes && <div style={{ fontSize: '0.8rem', color: '#b45309', fontWeight: 600, fontStyle: 'italic', marginTop: '3px', display: 'flex', alignItems: 'center', gap: '4px' }}><span>📝 Nota:</span> <span>{line.line_notes}</span></div>}</div><strong>{formatCurrency(line.line_total_cents)}</strong></div>)}</section><section className="orders-history-summary"><div><span>Subtotal</span><span>{formatCurrency(selected.total_cents)}</span></div><div className="orders-history-summary-total"><strong>Total</strong><strong>{formatCurrency(selected.total_cents)}</strong></div>{selected.payment_status === 'CONFIRMED' ? <div className="orders-history-paid-method"><CreditCard size={17} />Pago confirmado</div> : null}</section>{selected.corrections.length > 0 ? <section className="orders-history-corrections" aria-label="Correcciones enlazadas"><div className="orders-history-section-title"><span>Correcciones enlazadas</span><small>La venta original permanece sin cambios.</small></div>{selected.corrections.map((correction) => <article key={correction.id}><div><strong>{correction.folio}</strong><small>{new Date(correction.applied_at).toLocaleString('es-MX')}</small></div><div><span>{getCorrectionDeltaLabel(correction.settlement_delta_cents)}</span><strong>Total corregido: {formatCurrency(correction.corrected_total_cents)}</strong></div></article>)}</section> : null}{selected.status === 'PENDING' ? <section className="orders-history-pending-notice" style={{ background: '#ecfdf5', border: '1px solid #a7f3d0', borderRadius: '12px', padding: '12px 14px', margin: '10px 0', color: '#065f46', fontSize: '0.85rem' }}><strong>🔔 Pedido web por aceptar</strong><p style={{ marginTop: '3px', color: '#047857' }}>Revisa los productos. Al dar clic en <strong>Aceptar / Mandar a Cocina</strong> se iniciará la preparación para cobrarlo posteriormente.</p></section> : selected.payment_status === 'PENDING' ? <section className="orders-history-payment"><div className="orders-history-section-title"><span>Confirmar pago recibido</span><small>{formatCurrency(selected.total_cents)}</small></div><div className="orders-history-payment-grid">{PAYMENT_METHODS.map((method) => <button key={method.value} type="button" aria-pressed={paymentMethod === method.value} className={paymentMethod === method.value ? 'is-selected' : ''} onClick={() => setPaymentMethod(method.value)}><CreditCard size={17} /><span><strong>{method.label}</strong><small>{method.hint}</small></span></button>)}</div></section> : null}{canRequestReopen && selected.reopen_eligible && !selected.active_reopen_request_status ? <section className="orders-history-reopen"><div className="orders-history-section-title"><span>Solicitar reapertura</span><small>Requiere autorización de Dueño</small></div><label>Motivo<textarea value={reopenReason} minLength={10} maxLength={500} onChange={(event) => setReopenReason(event.target.value)} /></label><label>Evidencia (una referencia por línea)<textarea value={evidenceText} maxLength={5000} onChange={(event) => setEvidenceText(event.target.value)} /></label><Button disabled={reopenPending} onClick={() => void submitReopenRequest()}>{reopenPending ? 'Enviando…' : 'Solicitar reapertura'}</Button>{reopenError ? <p role="alert" className="orders-history-inline-error">{reopenError}</p> : null}</section> : null}{selected.active_reopen_request_status ? <p className="orders-history-block-reason">Solicitud activa: {selected.active_reopen_request_status}.</p> : null}{detailError ? <p role="alert" className="orders-history-inline-error">{detailError}</p> : null}{!selected.editable && selected.edit_block_reason ? <p className="orders-history-block-reason">{selected.edit_block_reason}</p> : null}</div><div className="orders-history-detail-actions">
  {reprintMessage ? <p role="status" style={{ width: '100%', color: '#059669', fontSize: '0.85rem', fontWeight: 600, margin: '4px 0' }}>✓ {reprintMessage}</p> : null}
  <Button variant="secondary" onClick={() => handleReprint(selected.id)} title="Reimprimir comanda o ticket térmico">
    <Printer size={17} /> Reimprimir
  </Button>
  {selected.status === 'PENDING' ? (
    <>
      <Button
        className="orders-history-accept-action"
        style={{ background: '#059669', color: '#ffffff', borderColor: '#059669', flex: 1 }}
        disabled={acceptPending}
        onClick={() => void acceptOrder(selected.id)}
      >
        <ChefHat size={17} /> {acceptPending ? 'Aceptando…' : 'Aceptar / Mandar a Cocina'}
      </Button>
      {selected.editable ? (
        <Button className="orders-history-edit-action" variant="secondary" onClick={() => navigate(`/pos/orders/${encodeURIComponent(selected.id)}/edit`)}>
          <Pencil size={17} /> Editar
        </Button>
      ) : null}
    </>
  ) : (
    <>
      {selected.editable ? (
        <Button className="orders-history-edit-action" variant="secondary" onClick={() => navigate(`/pos/orders/${encodeURIComponent(selected.id)}/edit`)}>
          <Pencil size={17} /> Editar pedido
        </Button>
      ) : null}
      {selected.payment_status === 'PENDING' ? (
        !configuredRegisterId ? (
          <p role="alert" className="orders-history-inline-error">
            Configura la caja en Configuración &gt; Turno y Caja para habilitar el cobro.
          </p>
        ) : (
          <Button
            className="orders-history-confirm-action"
            style={{ flex: 1 }}
            disabled={paymentPending || !configuredRegisterId}
            onClick={() => void confirmPayment()}
          >
            <CreditCard size={17} />
            {paymentPending ? 'Confirmando…' : 'Confirmar pagado'}
          </Button>
        )
      ) : null}
    </>
  )}
</div></>}</aside></div>
    {canAuthorizeReopen ? (() => {
      const pendingRequests = requests.filter((r) => r.status === 'REQUESTED' || r.status === 'APPROVED');
      const resolvedRequests = requests.filter((r) => r.status !== 'REQUESTED' && r.status !== 'APPROVED');
      const displayedRequests = showReopenHistory ? requests : pendingRequests;

      if (requests.length === 0) return null;

      if (pendingRequests.length === 0 && !showReopenHistory) {
        return (
          <div style={{ marginTop: '16px', display: 'flex', justifyContent: 'flex-end' }}>
            <Button
              variant="secondary"
              style={{ fontSize: '0.82rem', padding: '6px 12px' }}
              onClick={() => setShowReopenHistory(true)}
            >
              📋 Ver historial de auditoría ({resolvedRequests.length} resuelta{resolvedRequests.length === 1 ? '' : 's'})
            </Button>
          </div>
        );
      }

      return (
        <Card className="orders-history-reopen-queue" style={{ marginTop: '20px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <div>
              <h2 style={{ fontSize: '1.1rem', margin: 0 }}>Solicitudes de reapertura y corrección</h2>
              <p style={{ margin: '2px 0 0', fontSize: '0.85rem', color: '#94a3b8' }}>
                Solo Dueño/Administrador decide y aplica una corrección compensatoria; la venta original permanece intacta.
              </p>
            </div>
            {resolvedRequests.length > 0 && pendingRequests.length > 0 && (
              <Button
                variant="secondary"
                style={{ fontSize: '0.8rem', padding: '4px 10px' }}
                onClick={() => setShowReopenHistory(!showReopenHistory)}
              >
                {showReopenHistory ? 'Ocultar resueltas' : `Ver resueltas (${resolvedRequests.length})`}
              </Button>
            )}
            {pendingRequests.length === 0 && showReopenHistory && (
              <Button
                variant="secondary"
                style={{ fontSize: '0.8rem', padding: '4px 10px' }}
                onClick={() => setShowReopenHistory(false)}
              >
                Ocultar historial
              </Button>
            )}
          </div>
          {requestsError ? <p role="alert" className="orders-history-inline-error">{requestsError}</p> : null}
          {requestsLoading ? <p role="status">Cargando solicitudes…</p> : displayedRequests.length === 0 ? <p>No hay solicitudes pendientes en este momento.</p> : displayedRequests.map((request) => {
            const statusConfig = getRequestStatusConfig(request.status);
            return (
              <article key={request.id} className="orders-history-reopen-request">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <strong>Pedido {request.order_id}</strong>
                  <span style={{ background: statusConfig.bg, color: statusConfig.color, padding: '3px 8px', borderRadius: '6px', fontSize: '0.8rem', fontWeight: 700 }}>
                    {statusConfig.label}
                  </span>
                </div>
                <p><b>Motivo:</b> {request.reason}</p>
                <p><b>Evidencia:</b> {request.evidence_refs.join(', ')}</p>
                {request.decision_reason ? <p><b>Decisión:</b> {request.decision_reason}</p> : null}
                {request.status === 'REQUESTED' ? (
                  <>
                    <label>Motivo de decisión
                      <textarea
                        value={decisionReasonById[request.id] || ''}
                        minLength={10}
                        maxLength={500}
                        placeholder="Escribe el motivo de aprobación o rechazo..."
                        onChange={(event) => setDecisionReasonById((current) => ({ ...current, [request.id]: event.target.value }))}
                      />
                    </label>
                    <div style={{ display: 'flex', gap: '8px', marginTop: '6px' }}>
                      <Button disabled={decisionPendingId === request.id} onClick={() => void decideRequest(request, 'approve')}>
                        Aprobar
                      </Button>
                      <Button variant="secondary" disabled={decisionPendingId === request.id} onClick={() => void decideRequest(request, 'reject')}>
                        Rechazar
                      </Button>
                    </div>
                  </>
                ) : null}
                {request.status === 'APPROVED' ? (
                  <Button onClick={() => void openCorrectionEditor(request)}>
                    Editar y aplicar corrección
                  </Button>
                ) : null}
              </article>
            );
          })}
          {requestsCursor ? <Button variant="secondary" onClick={() => void loadRequests(requestsCursor, true)}>Cargar más solicitudes</Button> : null}
        </Card>
      );
    })() : null}
    <Modal isOpen={Boolean(correctionRequest)} onClose={closeCorrectionEditor} title="Corrección compensatoria">
      <div className="orders-history-correction" aria-live="polite">
        <p>La venta, el pago y el corte originales no se editarán. El servidor calcula el total y cualquier cargo o reembolso.</p>
        {correctionProductsLoading ? <p role="status">Cargando pedido y catálogo autorizado…</p> : null}
        {correctionState === 'applied' ? <div className="orders-history-correction-success" role="status"><strong>Corrección aplicada.</strong><span>La aplicación es definitiva; {correctionRefreshWarning || 'la vista y la cola se actualizaron desde el servidor.'}</span><Button onClick={closeCorrectionEditor}>Cerrar</Button></div> : <>
          {correctionError ? <p role="alert" className="orders-history-inline-error">{correctionError}</p> : null}
          {correctionState !== 'conflict' ? <>
            <section aria-label="Líneas corregidas"><div className="orders-history-section-title"><span>Imagen corregida</span><small>Modifica cantidades, elimina o agrega productos.</small></div><div className="orders-history-correction-lines">{correctionLines.length === 0 ? <p role="status">La imagen corregida está vacía: se solicitará al servidor una corrección total.</p> : correctionLines.map((line) => <div key={line.key} className="orders-history-correction-line"><div><strong>{line.productName}</strong><small>{line.sourceLineId ? 'Línea histórica: se conserva por snapshot' : 'Adición: precio y receta serán validados por el servidor'}</small></div><div className="orders-history-correction-quantity"><button type="button" aria-label={`Reducir ${line.productName}`} onClick={() => updateCorrectionQuantity(line.key, line.quantity - 1)} disabled={correctionState === 'submitting'}>−</button><output aria-label={`Cantidad de ${line.productName}`}>{line.quantity}</output><button type="button" aria-label={`Aumentar ${line.productName}`} onClick={() => updateCorrectionQuantity(line.key, line.quantity + 1)} disabled={correctionState === 'submitting' || Boolean(line.originalQuantity && line.quantity >= line.originalQuantity)}>+</button><button type="button" aria-label={`Eliminar ${line.productName}`} onClick={() => updateCorrectionQuantity(line.key, 0)} disabled={correctionState === 'submitting'}>Eliminar</button></div></div>)}</div></section>
            <section className="orders-history-correction-add" aria-label="Agregar producto"><label>Agregar producto<select value={correctionProductId} onChange={(event) => { invalidateCorrectionRetry(); setCorrectionProductId(event.target.value); }} disabled={correctionState === 'submitting'}><option value="">Selecciona un producto activo</option>{correctionProducts.map((product) => <option key={product.id} value={product.id}>{product.name}</option>)}</select></label><Button variant="secondary" disabled={!correctionProductId || correctionState === 'submitting'} onClick={addCorrectionProduct}>Agregar línea</Button></section>
            {correctionHasInProgressReduction ? <p role="alert" className="orders-history-inline-error">Una reducción afecta producción en curso y no puede aplicarse.</p> : null}
            {correctionCompletedReductions.length > 0 ? <section className="orders-history-correction-dispositions" aria-label="Disposiciones de producción completada"><div className="orders-history-section-title"><span>Producción completada</span><small>Selecciona la disposición requerida para cada reducción.</small></div>{correctionCompletedReductions.map(({ task, reduction, lineName }) => <label key={task.id}>{lineName} · reducción de {reduction}<select value={correctionDispositions[task.id] || ''} onChange={(event) => { invalidateCorrectionRetry(); setCorrectionDispositions((current) => ({ ...current, [task.id]: event.target.value as 'waste' | 'recovery' })); }} disabled={correctionState === 'submitting'}><option value="" disabled>Selecciona una disposición</option><option value="waste">Merma</option><option value="recovery">Recuperación autorizada</option></select></label>)}</section> : null}
            <section className="orders-history-correction-settlement" aria-label="Liquidación de corrección"><div className="orders-history-section-title"><span>Liquidación</span><small>No calcules ni captures diferencia; el backend la deriva.</small></div><label>Método<select value={correctionSettlementMethod} onChange={(event) => { invalidateCorrectionRetry(); setCorrectionSettlementMethod(event.target.value as PaymentMethod); }} disabled={correctionState === 'submitting'}>{PAYMENT_METHODS.map((method) => <option key={method.value} value={method.value}>{method.label}</option>)}</select></label>{correctionSettlementMethod === 'cash' ? <p>La caja configurada se envía para validar el turno; el servidor sólo crea un movimiento si existe una diferencia.</p> : <label>Evidencia de liquidación (una referencia por línea)<textarea value={correctionEvidenceText} maxLength={5000} onChange={(event) => { invalidateCorrectionRetry(); setCorrectionEvidenceText(event.target.value); }} disabled={correctionState === 'submitting'} /></label>}</section>
            <div className="orders-history-correction-actions"><Button variant="secondary" onClick={closeCorrectionEditor} disabled={correctionState === 'submitting'}>Cancelar</Button><Button disabled={correctionState === 'submitting' || correctionHasInProgressReduction || correctionProductsLoading} onClick={() => void submitCorrection()}>{correctionState === 'submitting' ? 'Aplicando…' : correctionState === 'error' ? 'Reintentar aplicación' : 'Confirmar y aplicar'}</Button></div>
          </> : <div className="orders-history-correction-actions"><Button onClick={closeCorrectionEditor}>Cerrar y actualizar</Button></div>}
        </>}
      </div>
    </Modal>
  </div>;
};

export default History;
