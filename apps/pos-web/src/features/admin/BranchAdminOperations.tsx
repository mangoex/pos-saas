import React, { useEffect, useMemo, useState } from 'react';
import { ApiError, fetchApi } from '@restaurantos/api-client';
import {
  Building2,
  ChefHat,
  ClipboardCheck,
  Plus,
  Receipt,
  Trash2,
  Truck,
  CheckCircle2,
  XCircle,
} from 'lucide-react';
import { Button, Input, Modal } from '@restaurantos/ui';
import { usePosSession } from '../../session';
import { BranchAdminPage } from './BranchAdminPage';

interface Column<T> {
  key: string;
  label: string;
  render: (row: T) => React.ReactNode;
}

interface ResourceState<T> {
  data: T[];
  loading: boolean;
  error: string;
}

function useBranchResource<T>(path: string, includeBranch = true): ResourceState<T> & { refetch: () => void } {
  const { session } = usePosSession();
  const branchId = session?.active_branch?.id || '';
  const [version, setVersion] = useState(0);
  const [state, setState] = useState<ResourceState<T>>({
    data: [],
    loading: true,
    error: '',
  });

  const refetch = () => setVersion((v) => v + 1);

  useEffect(() => {
    if (includeBranch && !branchId) {
      setState({ data: [], loading: false, error: 'No hay una sucursal activa.' });
      return;
    }

    const controller = new AbortController();
    const separator = path.includes('?') ? '&' : '?';
    const endpoint = includeBranch
      ? `${path}${separator}branch_id=${encodeURIComponent(branchId)}`
      : path;

    setState((current) => ({ ...current, loading: true, error: '' }));
    void fetchApi<T[]>(endpoint, { signal: controller.signal })
      .then((data) => {
        if (controller.signal.aborted) return;
        setState({ data: Array.isArray(data) ? data : [], loading: false, error: '' });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setState({
          data: [],
          loading: false,
          error: error instanceof ApiError ? error.message : 'No se pudo cargar la información.',
        });
      });

    return () => controller.abort();
  }, [branchId, includeBranch, path, version]);

  return { ...state, refetch };
}

function BranchTable<T>({
  columns,
  rows,
  rowKey,
  loading,
  error,
  emptyMessage,
}: {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  loading: boolean;
  error: string;
  emptyMessage: string;
}) {
  if (loading) return <p style={{ color: '#64748b' }}>Cargando información…</p>;
  if (error) return <div role="alert" style={{ color: '#b91c1c' }}>{error}</div>;
  if (rows.length === 0) {
    return (
      <div style={{ padding: 40, textAlign: 'center', color: '#64748b' }}>{emptyMessage}</div>
    );
  }

  return (
    <div style={{ overflowX: 'auto', background: '#fff', border: '1px solid #e2e8f0', borderRadius: 16 }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
        <thead>
          <tr style={{ background: '#f8fafc' }}>
            {columns.map((column) => (
              <th key={column.key} style={headerStyle}>{column.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)} style={{ borderTop: '1px solid #f1f5f9' }}>
              {columns.map((column) => (
                <td key={column.key} style={cellStyle}>{column.render(row)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const headerStyle: React.CSSProperties = {
  padding: '13px 16px',
  color: '#64748b',
  fontSize: 12,
  textTransform: 'uppercase',
  letterSpacing: '0.04em',
};

const cellStyle: React.CSSProperties = {
  padding: '14px 16px',
  color: '#334155',
  fontSize: 14,
  verticalAlign: 'top',
};

function Status({ value }: { value: string }) {
  const active = ['active', 'confirmed', 'received', 'closed'].includes(value);
  const isDraft = value === 'draft';
  const isCancelled = value === 'cancelled';
  let color = '#475569';
  let bg = '#f1f5f9';
  if (active) {
    color = '#047857';
    bg = '#d1fae5';
  } else if (isDraft) {
    color = '#b45309';
    bg = '#fef3c7';
  } else if (isCancelled) {
    color = '#dc2626';
    bg = '#fef2f2';
  }
  return (
    <span
      style={{
        display: 'inline-block',
        borderRadius: 999,
        padding: '3px 9px',
        color,
        background: bg,
        fontSize: 12,
        fontWeight: 600,
      }}
    >
      {value}
    </span>
  );
}

function money(value: number | string | null | undefined): string {
  return `$${Number(value || 0).toFixed(2)}`;
}

function dateTime(value: string | null | undefined): string {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('es-MX');
}

interface Supplier {
  id: string;
  code: string;
  commercial_name: string;
  tax_id?: string;
  credit_days: number;
  contacts?: Array<{ id: string; name: string; primary_for_orders: boolean }>;
}

interface Presentation {
  id: string;
  code: string;
  name: string;
  supplier_id: string;
  supplier_name: string;
  item_id: string;
  item_name: string;
  last_net_price: number;
  base_unit_code: string;
}

interface InventoryItem {
  id: string;
  sku: string;
  name: string;
  base_unit_id: string;
  base_unit_code?: string;
}

interface InventoryUnit {
  id: string;
  code: string;
  name: string;
}

export function BranchAdminSuppliers() {
  const suppliers = useBranchResource<Supplier>('/suppliers');
  const presentations = useBranchResource<Presentation>('/purchase-presentations');

  return (
    <BranchAdminPage
      title="Proveedores y Presentaciones"
      description="Consulta proveedores y presentaciones disponibles para la operación de tu sucursal."
      icon={Building2}
    >
      <p style={{ color: '#64748b', marginTop: 0 }}>
        El alta y modificación del catálogo central permanece en Administración corporativa.
      </p>
      <h2 style={sectionTitle}>Directorio de proveedores</h2>
      <BranchTable
        columns={[
          { key: 'code', label: 'Código', render: (row) => row.code },
          { key: 'name', label: 'Proveedor', render: (row) => row.commercial_name },
          { key: 'tax', label: 'RFC', render: (row) => row.tax_id || '—' },
          { key: 'credit', label: 'Crédito', render: (row) => `${row.credit_days} días` },
          {
            key: 'contact',
            label: 'Contacto de pedidos',
            render: (row) => row.contacts?.find((contact) => contact.primary_for_orders)?.name || '—',
          },
        ]}
        rows={suppliers.data}
        rowKey={(row) => row.id}
        loading={suppliers.loading}
        error={suppliers.error}
        emptyMessage="No hay proveedores registrados."
      />

      <h2 style={sectionTitle}>Presentaciones de compra</h2>
      <BranchTable
        columns={[
          { key: 'code', label: 'Código', render: (row) => row.code },
          { key: 'name', label: 'Presentación', render: (row) => row.name },
          { key: 'supplier', label: 'Proveedor', render: (row) => row.supplier_name },
          { key: 'item', label: 'Insumo Base', render: (row) => row.item_name },
          { key: 'price', label: 'Último precio', render: (row) => money(row.last_net_price) },
        ]}
        rows={presentations.data?.filter((p) => !p.code?.startsWith('PRES-') && !p.name?.toUpperCase().includes('KIWI')) || []}
        rowKey={(row) => row.id}
        loading={presentations.loading}
        error={presentations.error}
        emptyMessage="No hay presentaciones registradas."
      />
    </BranchAdminPage>
  );
}

interface PurchaseLine {
  id: string;
  presentation_id: string;
  presentation_snapshot?: { name?: string };
  presentation_quantity: number;
  base_quantity: number;
  unit_price: number;
  discount: number;
  tax: number;
  line_total: number;
}

interface Purchase {
  id: string;
  folio: string;
  supplier_id: string;
  document_type: string;
  total: number;
  paid_from_cash: boolean;
  status: string;
  document_date?: string;
  lines?: PurchaseLine[];
}

interface PurchaseDraftLine {
  concept: string;
  presentation_id?: string;
  quantity: string;
  unit_price: string;
  discount: string;
  tax: string;
}

export function BranchAdminPurchases() {
  const { session } = usePosSession();
  const branchId = session?.active_branch?.id || '';
  const purchases = useBranchResource<Purchase>('/purchases');
  const suppliers = useBranchResource<Supplier>('/suppliers');
  const presentations = useBranchResource<Presentation>('/purchase-presentations');

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [error, setError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const [form, setForm] = useState({
    supplier_id: '',
    document_type: 'receipt',
    folio: '',
    document_date: new Date().toISOString().slice(0, 10),
    paid_from_cash: true,
    lines: [
      { concept: '', quantity: '1', unit_price: '', discount: '0', tax: '0' },
    ] as PurchaseDraftLine[],
  });

  const addLine = () => {
    setForm((f) => ({
      ...f,
      lines: [...f.lines, { concept: '', quantity: '1', unit_price: '', discount: '0', tax: '0' }],
    }));
  };

  const removeLine = (idx: number) => {
    if (form.lines.length <= 1) return;
    setForm((f) => ({ ...f, lines: f.lines.filter((_, i) => i !== idx) }));
  };

  const updateLine = (idx: number, key: keyof PurchaseDraftLine, value: string) => {
    setForm((f) => ({
      ...f,
      lines: f.lines.map((l, i) => (i === idx ? { ...l, [key]: value } : l)),
    }));
  };

  const totals = useMemo(() => {
    let subtotal = 0;
    let discount = 0;
    let tax = 0;
    for (const line of form.lines) {
      const q = parseFloat(line.quantity) || 0;
      const p = parseFloat(line.unit_price) || 0;
      const d = parseFloat(line.discount) || 0;
      const t = parseFloat(line.tax) || 0;
      subtotal += q * p;
      discount += d;
      tax += t;
    }
    const total = Math.max(0, subtotal - discount + tax);
    return { subtotal, discount, tax, total };
  }, [form.lines]);

  const handleCreatePurchase = async () => {
    for (let i = 0; i < form.lines.length; i++) {
      const line = form.lines[i];
      if (!line.concept.trim() && !line.presentation_id) {
        setError(`Escribe el concepto o insumo en la fila ${i + 1}.`);
        return;
      }
      if (parseFloat(line.quantity) <= 0) {
        setError(`Cantidad inválida en la fila ${i + 1}.`);
        return;
      }
    }

    setError('');
    setIsSubmitting(true);
    try {
      await fetchApi('/purchases', {
        method: 'POST',
        body: JSON.stringify({
          branch_id: branchId,
          supplier_id: form.supplier_id || undefined,
          document_type: form.document_type,
          folio: form.folio.trim() || undefined,
          document_date: form.document_date,
          paid_from_cash: form.paid_from_cash,
          payment_method: form.paid_from_cash ? 'cash' : 'other',
          lines: form.lines.map((l) => ({
            concept: l.concept.trim(),
            presentation_id: l.presentation_id || undefined,
            quantity: l.quantity,
            unit_price: l.unit_price || '0',
            discount: l.discount || '0',
            tax: l.tax || '0',
          })),
        }),
      });
      setIsModalOpen(false);
      setForm({
        supplier_id: '',
        document_type: 'receipt',
        folio: '',
        document_date: new Date().toISOString().slice(0, 10),
        paid_from_cash: true,
        lines: [{ concept: '', quantity: '1', unit_price: '', discount: '0', tax: '0' }],
      });
      purchases.refetch();
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : 'No fue posible registrar la compra.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleConfirm = async (purchase: Purchase) => {
    const configuredRegisterId = (localStorage.getItem('pos_register_id') || '').trim();
    if (purchase.paid_from_cash && !configuredRegisterId) {
      alert('Configura una caja antes de confirmar una compra en efectivo.');
      return;
    }
    const storageKey = `purchase_confirmation_${purchase.id}`;
    const key = localStorage.getItem(storageKey) || `conf-${purchase.id}-${crypto.randomUUID()}`;
    localStorage.setItem(storageKey, key);
    try {
      await fetchApi(`/purchases/${purchase.id}/confirm`, {
        method: 'POST',
        headers: { 'Idempotency-Key': key },
        body: JSON.stringify({
          idempotency_key: key,
          ...(purchase.paid_from_cash ? { register_id: configuredRegisterId } : {}),
        }),
      });
      localStorage.removeItem(storageKey);
      purchases.refetch();
    } catch (e: unknown) {
      alert(e instanceof ApiError ? e.message : 'Error al confirmar la recepción.');
    }
  };

  const handleCancel = async (purchaseId: string) => {
    const reason = window.prompt('Motivo obligatorio de cancelación:');
    if (!reason || !reason.trim()) return;
    try {
      await fetchApi(`/purchases/${purchaseId}/cancel`, {
        method: 'POST',
        body: JSON.stringify({ reason: reason.trim() }),
      });
      purchases.refetch();
    } catch (e: unknown) {
      alert(e instanceof ApiError ? e.message : 'Error al cancelar la compra.');
    }
  };

  return (
    <BranchAdminPage
      title="Compras y Recepción de Insumos"
      description="Registra compras directas multilínea, afecta el inventario y concilia con caja de efectivo."
      icon={Receipt}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 12 }}>
        <h2 style={sectionTitle}>Historial de compras de sucursal</h2>
        <Button variant="primary" size="sm" onClick={() => setIsModalOpen(true)}>
          <Plus size={16} /> Nueva Compra Directa
        </Button>
      </div>

      <BranchTable
        columns={[
          { key: 'folio', label: 'Folio / Ref.', render: (row) => row.folio },
          {
            key: 'supplier',
            label: 'Proveedor',
            render: (row) => {
              const s = suppliers.data.find((sup) => sup.id === row.supplier_id);
              return s ? s.commercial_name : row.supplier_id;
            },
          },
          { key: 'document', label: 'Tipo Doc.', render: (row) => row.document_type.toUpperCase() },
          { key: 'total', label: 'Total', render: (row) => money(row.total) },
          { key: 'payment', label: 'Pago', render: (row) => (row.paid_from_cash ? 'Efectivo Caja' : 'Otro') },
          { key: 'status', label: 'Estado', render: (row) => <Status value={row.status} /> },
          {
            key: 'actions',
            label: 'Acciones',
            render: (row) => (
              <div style={{ display: 'flex', gap: 6 }}>
                {row.status === 'draft' && (
                  <Button variant="primary" size="sm" onClick={() => handleConfirm(row)}>
                    <CheckCircle2 size={14} /> Confirmar
                  </Button>
                )}
                {row.status === 'confirmed' && (
                  <Button variant="secondary" size="sm" onClick={() => handleCancel(row.id)}>
                    <XCircle size={14} /> Cancelar
                  </Button>
                )}
              </div>
            ),
          },
        ]}
        rows={purchases.data}
        rowKey={(row) => row.id}
        loading={purchases.loading}
        error={purchases.error}
        emptyMessage="No hay compras registradas para esta sucursal."
      />

      {/* Modal Nueva Compra Directa */}
      <Modal isOpen={isModalOpen} onClose={() => setIsModalOpen(false)} title="Capturar Compra Directa">
        <div style={{ display: 'grid', gap: 14 }}>
          {error && <div role="alert" style={{ color: '#b91c1c' }}>{error}</div>}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <label>
              Proveedor
              <select
                style={selectStyle}
                value={form.supplier_id}
                onChange={(e) => setForm({ ...form, supplier_id: e.target.value })}
              >
                <option value="">Proveedor General / Varios</option>
                {suppliers.data.map((s) => (
                  <option key={s.id} value={s.id}>{s.commercial_name} ({s.code})</option>
                ))}
              </select>
            </label>
            <label>
              Tipo de Documento *
              <select
                style={selectStyle}
                value={form.document_type}
                onChange={(e) => setForm({ ...form, document_type: e.target.value })}
              >
                <option value="receipt">Remisión / Nota</option>
                <option value="ticket">Ticket</option>
                <option value="invoice">Factura</option>
              </select>
            </label>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <label>
              Folio / Número Comprobante
              <Input
                placeholder="Ej. FAC-10293, Ticket # o auto-generar"
                value={form.folio}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, folio: e.target.value })}
              />
            </label>
            <label>
              Fecha del Comprobante
              <Input
                type="date"
                value={form.document_date}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, document_date: e.target.value })}
              />
            </label>
          </div>

          <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontWeight: 600 }}>
            <input
              type="checkbox"
              checked={form.paid_from_cash}
              onChange={(e) => setForm({ ...form, paid_from_cash: e.target.checked })}
            />
            Pagar de caja de efectivo (crea retiro automático en el turno activo)
          </label>

          <div style={{ borderTop: '1px solid #e2e8f0', paddingTop: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <strong style={{ fontSize: 14, color: '#0f172a' }}>Partidas de Compra</strong>
              <Button variant="secondary" size="sm" onClick={addLine}>
                <Plus size={14} /> Agregar Fila
              </Button>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '2fr 80px 100px 80px 80px 32px', gap: 8, fontSize: '0.75rem', fontWeight: 600, color: '#64748b', marginBottom: 4 }}>
              <span>Insumo o Concepto</span>
              <span>Cant.</span>
              <span>P. Unit ($)</span>
              <span>Desc.</span>
              <span>IVA</span>
              <span></span>
            </div>

            {form.lines.map((line, idx) => (
              <div
                key={idx}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '2fr 80px 100px 80px 80px 32px',
                  gap: 8,
                  alignItems: 'center',
                  marginBottom: 8,
                }}
              >
                <Input
                  placeholder="Ej. Bolsa de hielo, Verdura, Gas..."
                  value={line.concept}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => updateLine(idx, 'concept', e.target.value)}
                />
                <Input
                  type="number"
                  min="0.001"
                  step="any"
                  placeholder="Cant."
                  value={line.quantity}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => updateLine(idx, 'quantity', e.target.value)}
                />
                <Input
                  type="number"
                  min="0"
                  step="0.01"
                  placeholder="P. Unit ($)"
                  value={line.unit_price}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => updateLine(idx, 'unit_price', e.target.value)}
                />
                <Input
                  type="number"
                  min="0"
                  step="0.01"
                  placeholder="Desc."
                  value={line.discount}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => updateLine(idx, 'discount', e.target.value)}
                />
                <Input
                  type="number"
                  min="0"
                  step="0.01"
                  placeholder="IVA"
                  value={line.tax}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => updateLine(idx, 'tax', e.target.value)}
                />
                <button
                  type="button"
                  style={{
                    background: 'transparent',
                    border: 'none',
                    color: form.lines.length > 1 ? '#dc2626' : '#cbd5e1',
                    cursor: form.lines.length > 1 ? 'pointer' : 'default',
                    padding: 4,
                  }}
                  disabled={form.lines.length <= 1}
                  onClick={() => removeLine(idx)}
                >
                  <Trash2 size={16} />
                </button>
              </div>
            ))}
          </div>

          {/* Resumen de totales */}
          <div style={{ background: '#f8fafc', padding: 12, borderRadius: 8, textAlign: 'right', fontSize: 13 }}>
            <div>Subtotal: <strong>{money(totals.subtotal)}</strong></div>
            <div>Descuento: <strong>-{money(totals.discount)}</strong></div>
            <div>Impuestos: <strong>+{money(totals.tax)}</strong></div>
            <div style={{ fontSize: 16, marginTop: 4, color: '#0f172a' }}>
              Total Compra: <strong>{money(totals.total)}</strong>
            </div>
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
            <Button variant="secondary" onClick={() => setIsModalOpen(false)}>Cancelar</Button>
            <Button variant="primary" disabled={isSubmitting} onClick={handleCreatePurchase}>
              {isSubmitting ? 'Guardando…' : 'Guardar Borrador de Compra'}
            </Button>
          </div>
        </div>
      </Modal>
    </BranchAdminPage>
  );
}

const selectStyle: React.CSSProperties = {
  width: '100%',
  padding: '8px 12px',
  borderRadius: 8,
  border: '1px solid #cbd5e1',
  fontSize: 14,
  background: '#fff',
  color: '#0f172a',
};

interface ProductionBatch {
  id: string;
  recipe_id: string;
  lot_code: string;
  planned_quantity: number;
  actual_quantity: number;
  total_cost: number;
  unit_cost: number;
  status: string;
}

export function BranchAdminProduction() {
  const batches = useBranchResource<ProductionBatch>('/production-batches');
  return (
    <BranchAdminPage
      title="Producción"
      description="Lotes y elaborados producidos localmente en la sucursal activa."
      icon={ChefHat}
    >
      <BranchTable
        columns={[
          { key: 'lot', label: 'Lote', render: (row) => row.lot_code },
          { key: 'recipe', label: 'Receta', render: (row) => row.recipe_id },
          { key: 'planned', label: 'Planeado', render: (row) => Number(row.planned_quantity) },
          { key: 'actual', label: 'Real', render: (row) => Number(row.actual_quantity) },
          { key: 'cost', label: 'Costo unitario', render: (row) => money(row.unit_cost) },
          { key: 'status', label: 'Estado', render: (row) => <Status value={row.status} /> },
        ]}
        rows={batches.data}
        rowKey={(row) => row.id}
        loading={batches.loading}
        error={batches.error}
        emptyMessage="No hay lotes de producción en esta sucursal."
      />
    </BranchAdminPage>
  );
}

interface Waste {
  id: string;
  effective_at: string;
  item_name: string;
  item_sku: string;
  reason_name: string;
  stage: string;
  quantity: number;
  unit_code: string;
  total_cost: number;
  status: string;
}

export function BranchAdminWaste() {
  const wastes = useBranchResource<Waste>('/inventory/wastes');
  return (
    <BranchAdminPage
      title="Mermas"
      description="Pérdidas reales, motivos y estado de autorización de la sucursal."
      icon={Trash2}
    >
      <BranchTable
        columns={[
          { key: 'date', label: 'Fecha', render: (row) => dateTime(row.effective_at) },
          { key: 'item', label: 'Insumo', render: (row) => <><strong>{row.item_name}</strong><br /><small>{row.item_sku}</small></> },
          { key: 'reason', label: 'Motivo', render: (row) => `${row.reason_name} · ${row.stage}` },
          { key: 'quantity', label: 'Cantidad', render: (row) => `${Number(row.quantity)} ${row.unit_code}` },
          { key: 'cost', label: 'Costo', render: (row) => money(row.total_cost) },
          { key: 'status', label: 'Estado', render: (row) => <Status value={row.status} /> },
        ]}
        rows={wastes.data}
        rowKey={(row) => row.id}
        loading={wastes.loading}
        error={wastes.error}
        emptyMessage="No hay mermas registradas en esta sucursal."
      />
    </BranchAdminPage>
  );
}

interface TransferLine {
  id: string;
  item_name: string;
  requested_quantity: number;
  unit_code: string;
}

interface Transfer {
  id: string;
  folio: string;
  source_branch_name: string;
  destination_branch_name: string;
  created_at: string;
  status: string;
  lines: TransferLine[];
}

export function BranchAdminTransfers() {
  const transfers = useBranchResource<Transfer>('/inventory/transfers');
  return (
    <BranchAdminPage
      title="Traspasos"
      description="Salidas, tránsito y recepciones relacionadas con la sucursal activa."
      icon={Truck}
    >
      <BranchTable
        columns={[
          { key: 'folio', label: 'Folio', render: (row) => <><strong>{row.folio}</strong><br /><small>{dateTime(row.created_at)}</small></> },
          { key: 'source', label: 'Origen', render: (row) => row.source_branch_name },
          { key: 'destination', label: 'Destino', render: (row) => row.destination_branch_name },
          { key: 'items', label: 'Artículos', render: (row) => row.lines?.length || 0 },
          { key: 'status', label: 'Estado', render: (row) => <Status value={row.status} /> },
        ]}
        rows={transfers.data}
        rowKey={(row) => row.id}
        loading={transfers.loading}
        error={transfers.error}
        emptyMessage="No hay traspasos relacionados con esta sucursal."
      />
    </BranchAdminPage>
  );
}

interface PhysicalCount {
  id: string;
  folio: string;
  branch_name: string;
  snapshot_at: string;
  scope: string;
  blind: boolean;
  status: string;
  lines: Array<{ id: string }>;
}

export function BranchAdminCounts() {
  const counts = useBranchResource<PhysicalCount>('/inventory/physical-counts');
  return (
    <BranchAdminPage
      title="Conteos físicos"
      description="Fotografías teóricas, capturas ciegas y estados de conciliación."
      icon={ClipboardCheck}
    >
      <BranchTable
        columns={[
          { key: 'folio', label: 'Folio', render: (row) => row.folio },
          { key: 'snapshot', label: 'Fotografía', render: (row) => dateTime(row.snapshot_at) },
          { key: 'scope', label: 'Alcance', render: (row) => row.scope },
          { key: 'items', label: 'Artículos', render: (row) => row.lines?.length || 0 },
          { key: 'blind', label: 'Captura', render: (row) => row.blind ? 'Ciega' : 'Visible' },
          { key: 'status', label: 'Estado', render: (row) => <Status value={row.status} /> },
        ]}
        rows={counts.data}
        rowKey={(row) => row.id}
        loading={counts.loading}
        error={counts.error}
        emptyMessage="No hay conteos físicos registrados en esta sucursal."
      />
    </BranchAdminPage>
  );
}

const sectionTitle: React.CSSProperties = {
  color: '#0f172a',
  fontSize: 18,
  margin: '28px 0 12px',
};
