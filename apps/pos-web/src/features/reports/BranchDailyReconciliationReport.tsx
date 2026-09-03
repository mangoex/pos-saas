import React, { useEffect, useState } from 'react';
import { fetchApi } from '@restaurantos/api-client';
import { Button } from '@restaurantos/ui';
import { usePosSession } from '../../session';

interface BalanceSummary {
  initial_cash: number;
  total_sales_with_tax: number;
  card_payments: number;
  transfer_payments: number;
  credit_sales: number;
  cash_sales: number;
  supplier_expenses: number;
  fixed_expenses: number;
  cash_withdrawals: number;
  cash_deposits: number;
  expected_cash_in_register: number;
  physical_cash_count: number;
  difference: number;
}

interface SupplierRow {
  no: number;
  provider_name: string;
  amount: number;
  observations: string;
}

interface FixedExpenseRow {
  no: number;
  expense_type: string;
  amount: number;
  observations: string;
}

interface TransferRow {
  ticket_folio: string;
  customer_name: string;
  customer_phone: string;
  amount: number;
}

interface WithdrawalRow {
  no: number;
  folio: string;
  amount: number;
  recipient_name: string;
}

interface DailyReconciliationData {
  branch_id: string;
  branch_name: string;
  date: string;
  balance: BalanceSummary;
  suppliers_breakdown: SupplierRow[];
  fixed_expenses_breakdown: FixedExpenseRow[];
  transfers_breakdown: TransferRow[];
  credit_clients_breakdown: TransferRow[];
  withdrawals_breakdown: WithdrawalRow[];
  audit: {
    reviewed: boolean;
    audited_by_user_id?: string;
    audited_at?: string;
    notes?: string;
  };
}

const money = (val: number) =>
  new Intl.NumberFormat('es-MX', { style: 'currency', currency: 'MXN' }).format(val);

export default function BranchDailyReconciliationReport() {
  const { session, hasPermission } = usePosSession();
  const branchId = session?.active_branch?.id || '';
  const branchName = session?.active_branch?.name || 'Sucursal';
  const canAudit = hasPermission('branch.admin.access') || hasPermission('cash.shift.close');

  const [date, setDate] = useState(() => new Date().toISOString().split('T')[0]);
  const [data, setData] = useState<DailyReconciliationData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [auditNotes, setAuditNotes] = useState('');
  const [auditing, setAuditing] = useState(false);

  const loadReport = async () => {
    if (!branchId) return;
    setLoading(true);
    setError('');
    try {
      const res = await fetchApi<DailyReconciliationData>(
        `/reports/branch-reconciliation/daily?branch_id=${encodeURIComponent(branchId)}&date=${encodeURIComponent(date)}`
      );
      setData(res);
      setAuditNotes(res.audit?.notes || '');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al cargar el reporte de conciliación.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadReport();
  }, [branchId, date]);

  const handleToggleAudit = async () => {
    if (!branchId || !data) return;
    setAuditing(true);
    try {
      const nextReviewed = !data.audit.reviewed;
      await fetchApi('/reports/branch-reconciliation/audit', {
        method: 'POST',
        body: JSON.stringify({
          branch_id: branchId,
          date,
          reviewed: nextReviewed,
          notes: auditNotes,
        }),
      });
      await loadReport();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'No se pudo actualizar el estado de auditoría.');
    } finally {
      setAuditing(false);
    }
  };

  const handleExportExcel = () => {
    const d = new Date(date);
    const month = d.getUTCMonth() + 1;
    const year = d.getUTCFullYear();
    const url = `/api/v1/reports/branch-reconciliation/export?branch_id=${encodeURIComponent(branchId)}&month=${month}&year=${year}`;
    window.open(url, '_blank');
  };

  const balance = data?.balance;

  return (
    <div style={{ padding: 24, maxWidth: 1200, margin: '0 auto', fontFamily: 'system-ui, sans-serif' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 16, marginBottom: 20 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: '1.6rem', color: '#0f172a' }}>
            Conciliación y Corte Diario de Caja
          </h1>
          <p style={{ margin: '4px 0 0', color: '#64748b', fontSize: '0.9rem' }}>
            Sucursal: <strong>{branchName}</strong> · Libro Mayor y Conciliación Multicanal (Oficial)
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            style={{ padding: '8px 12px', borderRadius: 8, border: '1px solid #cbd5e1', fontSize: '0.9rem' }}
          />
          <Button variant="secondary" onClick={handleExportExcel}>
            📥 Descargar Excel (.xlsx)
          </Button>
        </div>
      </div>

      {loading && <p style={{ color: '#64748b' }}>Generando conciliación contable de sucursal…</p>}
      {error && <div role="alert" style={{ padding: 12, borderRadius: 8, background: '#fee2e2', color: '#b91c1c', marginBottom: 16 }}>{error}</div>}

      {data && balance && (
        <div style={{ display: 'grid', gap: 24 }}>
          {/* Audit Badge & Actions */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 16px', background: data.audit.reviewed ? '#ecfdf5' : '#fffbeb', border: `1px solid ${data.audit.reviewed ? '#10b981' : '#f59e0b'}`, borderRadius: 8 }}>
            <div>
              <span style={{ fontWeight: 700, color: data.audit.reviewed ? '#065f46' : '#92400e' }}>
                {data.audit.reviewed ? '✓ CORTE REVISADO Y APROBADO' : '⏳ PENDIENTE DE REVISIÓN'}
              </span>
              {data.audit.notes && (
                <span style={{ marginLeft: 12, color: '#475569', fontSize: '0.85rem' }}>
                  Nota: {data.audit.notes}
                </span>
              )}
            </div>
            {canAudit && (
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <input
                  type="text"
                  placeholder="Nota de revisión / folio..."
                  value={auditNotes}
                  onChange={(e) => setAuditNotes(e.target.value)}
                  style={{ padding: '6px 10px', borderRadius: 6, border: '1px solid #cbd5e1', fontSize: '0.85rem' }}
                />
                <Button variant={data.audit.reviewed ? 'secondary' : 'primary'} size="sm" onClick={handleToggleAudit} disabled={auditing}>
                  {data.audit.reviewed ? 'Desmarcar revisión' : 'Marcar como Revisado'}
                </Button>
              </div>
            )}
          </div>

          {/* 4 Summary Cards */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 16 }}>
            <div style={{ background: '#f8fafc', padding: 16, borderRadius: 10, border: '1px solid #e2e8f0' }}>
              <div style={{ color: '#64748b', fontSize: '0.85rem', fontWeight: 600 }}>VENTA TOTAL CON IMPUESTOS</div>
              <div style={{ fontSize: '1.4rem', fontWeight: 800, color: '#0f172a', marginTop: 4 }}>
                {money(balance.total_sales_with_tax)}
              </div>
              <div style={{ fontSize: '0.78rem', color: '#64748b', marginTop: 4 }}>
                Efectivo: {money(balance.cash_sales)} · Tarjetas: {money(balance.card_payments)}
              </div>
            </div>

            <div style={{ background: '#f8fafc', padding: 16, borderRadius: 10, border: '1px solid #e2e8f0' }}>
              <div style={{ color: '#64748b', fontSize: '0.85rem', fontWeight: 600 }}>EGRESOS EN EFECTIVO</div>
              <div style={{ fontSize: '1.4rem', fontWeight: 800, color: '#dc2626', marginTop: 4 }}>
                -{money(balance.supplier_expenses + balance.fixed_expenses + balance.cash_withdrawals)}
              </div>
              <div style={{ fontSize: '0.78rem', color: '#64748b', marginTop: 4 }}>
                Proveedores: {money(balance.supplier_expenses)} · Gastos: {money(balance.fixed_expenses)}
              </div>
            </div>

            <div style={{ background: '#f8fafc', padding: 16, borderRadius: 10, border: '1px solid #e2e8f0' }}>
              <div style={{ color: '#64748b', fontSize: '0.85rem', fontWeight: 600 }}>EFECTIVO TEÓRICO EN CAJA</div>
              <div style={{ fontSize: '1.4rem', fontWeight: 800, color: '#059669', marginTop: 4 }}>
                {money(balance.expected_cash_in_register)}
              </div>
              <div style={{ fontSize: '0.78rem', color: '#64748b', marginTop: 4 }}>
                Fondo Inicial: {money(balance.initial_cash)}
              </div>
            </div>

            <div style={{ background: balance.difference === 0 ? '#ecfdf5' : balance.difference > 0 ? '#eff6ff' : '#fef2f2', padding: 16, borderRadius: 10, border: `1px solid ${balance.difference === 0 ? '#10b981' : '#f87171'}` }}>
              <div style={{ color: balance.difference >= 0 ? '#065f46' : '#991b1b', fontSize: '0.85rem', fontWeight: 600 }}>
                {balance.difference === 0 ? 'CAJA CUADRADA AL CENTAVO' : balance.difference > 0 ? 'SOBRANTE (+)' : 'FALTANTE (-)'}
              </div>
              <div style={{ fontSize: '1.4rem', fontWeight: 800, color: balance.difference >= 0 ? '#059669' : '#dc2626', marginTop: 4 }}>
                {money(balance.difference)}
              </div>
              <div style={{ fontSize: '0.78rem', color: '#64748b', marginTop: 4 }}>
                Arqueo físico: {money(balance.physical_cash_count)}
              </div>
            </div>
          </div>

          {/* 2-Column Tabular Details */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
            {/* Left Col: Proveedores & Gastos Fijos */}
            <div style={{ display: 'grid', gap: 20 }}>
              {/* Proveedores */}
              <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 8, overflow: 'hidden' }}>
                <div style={{ padding: '10px 14px', background: '#f1f5f9', fontWeight: 700, fontSize: '0.9rem' }}>
                  📦 Pago a Proveedores de Insumos ({money(balance.supplier_expenses)})
                </div>
                {data.suppliers_breakdown.length === 0 ? (
                  <p style={{ padding: 14, margin: 0, color: '#94a3b8', fontSize: '0.85rem' }}>No hubo pagos a proveedores en efectivo.</p>
                ) : (
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                    <thead>
                      <tr style={{ borderBottom: '1px solid #e2e8f0', color: '#64748b', textAlign: 'left' }}>
                        <th style={{ padding: 8 }}>No.</th>
                        <th style={{ padding: 8 }}>Proveedor</th>
                        <th style={{ padding: 8, textAlign: 'right' }}>Monto</th>
                        <th style={{ padding: 8 }}>Observaciones</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.suppliers_breakdown.map((s) => (
                        <tr key={s.no} style={{ borderBottom: '1px solid #f1f5f9' }}>
                          <td style={{ padding: 8 }}>{s.no}</td>
                          <td style={{ padding: 8, fontWeight: 600 }}>{s.provider_name}</td>
                          <td style={{ padding: 8, textAlign: 'right', fontWeight: 700 }}>{money(s.amount)}</td>
                          <td style={{ padding: 8, color: '#64748b' }}>{s.observations}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>

              {/* Gastos Fijos */}
              <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 8, overflow: 'hidden' }}>
                <div style={{ padding: '10px 14px', background: '#f1f5f9', fontWeight: 700, fontSize: '0.9rem' }}>
                  🏢 Gastos Fijos y Operativos ({money(balance.fixed_expenses)})
                </div>
                {data.fixed_expenses_breakdown.length === 0 ? (
                  <p style={{ padding: 14, margin: 0, color: '#94a3b8', fontSize: '0.85rem' }}>No se registraron gastos fijos.</p>
                ) : (
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                    <thead>
                      <tr style={{ borderBottom: '1px solid #e2e8f0', color: '#64748b', textAlign: 'left' }}>
                        <th style={{ padding: 8 }}>No.</th>
                        <th style={{ padding: 8 }}>Tipo de Gasto</th>
                        <th style={{ padding: 8, textAlign: 'right' }}>Monto</th>
                        <th style={{ padding: 8 }}>Observaciones</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.fixed_expenses_breakdown.map((g) => (
                        <tr key={g.no} style={{ borderBottom: '1px solid #f1f5f9' }}>
                          <td style={{ padding: 8 }}>{g.no}</td>
                          <td style={{ padding: 8, fontWeight: 600 }}>{g.expense_type}</td>
                          <td style={{ padding: 8, textAlign: 'right', fontWeight: 700 }}>{money(g.amount)}</td>
                          <td style={{ padding: 8, color: '#64748b' }}>{g.observations}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>

            {/* Right Col: Transferencias, Crédito & Retiros */}
            <div style={{ display: 'grid', gap: 20 }}>
              {/* Transferencias */}
              <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 8, overflow: 'hidden' }}>
                <div style={{ padding: '10px 14px', background: '#f1f5f9', fontWeight: 700, fontSize: '0.9rem' }}>
                  📲 Ingresos por Transferencias ({money(balance.transfer_payments)})
                </div>
                {data.transfers_breakdown.length === 0 ? (
                  <p style={{ padding: 14, margin: 0, color: '#94a3b8', fontSize: '0.85rem' }}>No hubo cobros por transferencia.</p>
                ) : (
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                    <thead>
                      <tr style={{ borderBottom: '1px solid #e2e8f0', color: '#64748b', textAlign: 'left' }}>
                        <th style={{ padding: 8 }}>Ticket</th>
                        <th style={{ padding: 8 }}>Cliente</th>
                        <th style={{ padding: 8, textAlign: 'right' }}>Monto</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.transfers_breakdown.map((t, idx) => (
                        <tr key={idx} style={{ borderBottom: '1px solid #f1f5f9' }}>
                          <td style={{ padding: 8, fontWeight: 600 }}>{t.ticket_folio}</td>
                          <td style={{ padding: 8 }}>{t.customer_name} ({t.customer_phone})</td>
                          <td style={{ padding: 8, textAlign: 'right', fontWeight: 700 }}>{money(t.amount)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>

              {/* Retiros a Bóveda */}
              <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 8, overflow: 'hidden' }}>
                <div style={{ padding: '10px 14px', background: '#f1f5f9', fontWeight: 700, fontSize: '0.9rem' }}>
                  🔒 Retiros en Efectivo / Bóveda ({money(balance.cash_withdrawals)})
                </div>
                {data.withdrawals_breakdown.length === 0 ? (
                  <p style={{ padding: 14, margin: 0, color: '#94a3b8', fontSize: '0.85rem' }}>No hubo retiros de seguridad.</p>
                ) : (
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                    <thead>
                      <tr style={{ borderBottom: '1px solid #e2e8f0', color: '#64748b', textAlign: 'left' }}>
                        <th style={{ padding: 8 }}>Folio</th>
                        <th style={{ padding: 8 }}>Recibe</th>
                        <th style={{ padding: 8, textAlign: 'right' }}>Monto</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.withdrawals_breakdown.map((w) => (
                        <tr key={w.no} style={{ borderBottom: '1px solid #f1f5f9' }}>
                          <td style={{ padding: 8, fontWeight: 600 }}>{w.folio}</td>
                          <td style={{ padding: 8 }}>{w.recipient_name}</td>
                          <td style={{ padding: 8, textAlign: 'right', fontWeight: 700 }}>{money(w.amount)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
