import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Button } from '@restaurantos/ui';
import { fetchApi } from '@restaurantos/api-client';

interface BranchSummary {
  branch_id: string;
  branch_name: string;
  total_sales: number;
  total_expenses: number;
}

interface ConsolidatedReport {
  date_from: string;
  date_to: string;
  branches: BranchSummary[];
  supplier_totals: Record<string, number>;
  fixed_expense_totals: Record<string, number>;
  summary: {
    total_sales: number;
    total_cards: number;
    total_transfers: number;
    total_credits: number;
    total_suppliers: number;
    total_fixed: number;
    total_withdrawals: number;
    total_expected_cash: number;
  };
}

interface Branch {
  id: string;
  name: string;
}

const money = (val: number) =>
  new Intl.NumberFormat('es-MX', { style: 'currency', currency: 'MXN' }).format(val);

export default function CorporateReconciliationDashboard() {
  const today = new Date().toISOString().split('T')[0];
  const firstDay = `${today.substring(0, 7)}-01`;

  const [dateFrom, setDateFrom] = useState(firstDay);
  const [dateTo, setDateTo] = useState(today);
  const [selectedBranchId, setSelectedBranchId] = useState('');

  const { data: branches = [] } = useQuery<Branch[]>({
    queryKey: ['branches'],
    queryFn: () => fetchApi('/branches'),
  });

  const { data, isLoading, error, refetch } = useQuery<ConsolidatedReport>({
    queryKey: ['consolidated-reconciliation', dateFrom, dateTo, selectedBranchId],
    queryFn: () => {
      const params = new URLSearchParams({
        date_from: dateFrom,
        date_to: dateTo,
      });
      if (selectedBranchId) params.set('branch_id', selectedBranchId);
      return fetchApi(`/reports/branch-reconciliation/consolidated?${params.toString()}`);
    },
  });

  const handleExportExcel = () => {
    const d = new Date(dateTo);
    const month = d.getUTCMonth() + 1;
    const year = d.getUTCFullYear();
    const branchParam = selectedBranchId || (branches[0]?.id || '');
    const url = `/api/v1/reports/branch-reconciliation/export?branch_id=${encodeURIComponent(branchParam)}&month=${month}&year=${year}`;
    window.open(url, '_blank');
  };

  const summary = data?.summary;

  return (
    <div style={{ padding: 24, maxWidth: 1200, margin: '0 auto', fontFamily: 'system-ui, sans-serif' }}>
      {/* Header & Controls */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 16, marginBottom: 24 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: '1.75rem', fontWeight: 800, color: '#0f172a' }}>
            Consolidado Multi-Sucursal y Cortes
          </h1>
          <p style={{ margin: '4px 0 0', color: '#64748b', fontSize: '0.9rem' }}>
            Informe General Acumulado Diaria y Mensualmente (Formato Oficial)
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <select
            value={selectedBranchId}
            onChange={(e) => setSelectedBranchId(e.target.value)}
            style={{ padding: '8px 12px', borderRadius: 8, border: '1px solid #cbd5e1', fontSize: '0.9rem' }}
          >
            <option value="">🏢 Todas las Sucursales</option>
            {branches.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </select>

          <label style={{ fontSize: '0.85rem', color: '#475569', display: 'flex', alignItems: 'center', gap: 6 }}>
            Desde:
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              style={{ padding: '6px 10px', borderRadius: 6, border: '1px solid #cbd5e1' }}
            />
          </label>

          <label style={{ fontSize: '0.85rem', color: '#475569', display: 'flex', alignItems: 'center', gap: 6 }}>
            Hasta:
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              style={{ padding: '6px 10px', borderRadius: 6, border: '1px solid #cbd5e1' }}
            />
          </label>

          <Button variant="secondary" onClick={handleExportExcel}>
            📥 Exportar Excel (.xlsx)
          </Button>
        </div>
      </div>

      {isLoading && <p style={{ color: '#64748b' }}>Consolidando reportes de sucursales…</p>}
      {error && <div role="alert" style={{ padding: 12, borderRadius: 8, background: '#fee2e2', color: '#b91c1c' }}>Error al cargar el consolidado.</div>}

      {summary && data && (
        <div style={{ display: 'grid', gap: 24 }}>
          {/* Summary KPIs */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16 }}>
            <div style={{ background: '#fff', padding: 16, borderRadius: 10, border: '1px solid #e2e8f0' }}>
              <div style={{ color: '#64748b', fontSize: '0.8rem', fontWeight: 600 }}>VENTAS TOTALES</div>
              <div style={{ fontSize: '1.3rem', fontWeight: 800, color: '#0f172a', marginTop: 4 }}>
                {money(summary.total_sales)}
              </div>
            </div>

            <div style={{ background: '#fff', padding: 16, borderRadius: 10, border: '1px solid #e2e8f0' }}>
              <div style={{ color: '#64748b', fontSize: '0.8rem', fontWeight: 600 }}>COBROS CON TARJETA</div>
              <div style={{ fontSize: '1.3rem', fontWeight: 800, color: '#2563eb', marginTop: 4 }}>
                {money(summary.total_cards)}
              </div>
            </div>

            <div style={{ background: '#fff', padding: 16, borderRadius: 10, border: '1px solid #e2e8f0' }}>
              <div style={{ color: '#64748b', fontSize: '0.8rem', fontWeight: 600 }}>PAGO A PROVEEDORES</div>
              <div style={{ fontSize: '1.3rem', fontWeight: 800, color: '#dc2626', marginTop: 4 }}>
                {money(summary.total_suppliers)}
              </div>
            </div>

            <div style={{ background: '#fff', padding: 16, borderRadius: 10, border: '1px solid #e2e8f0' }}>
              <div style={{ color: '#64748b', fontSize: '0.8rem', fontWeight: 600 }}>GASTOS FIJOS / SUELDOS</div>
              <div style={{ fontSize: '1.3rem', fontWeight: 800, color: '#dc2626', marginTop: 4 }}>
                {money(summary.total_fixed)}
              </div>
            </div>

            <div style={{ background: '#ecfdf5', padding: 16, borderRadius: 10, border: '1px solid #10b981' }}>
              <div style={{ color: '#065f46', fontSize: '0.8rem', fontWeight: 600 }}>EFECTIVO ESPERADO TOTAL</div>
              <div style={{ fontSize: '1.3rem', fontWeight: 800, color: '#059669', marginTop: 4 }}>
                {money(summary.total_expected_cash)}
              </div>
            </div>
          </div>

          {/* 3 Tables Layout: Sucursales, Proveedores, Gastos Fijos */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: 20 }}>
            {/* Sucursales */}
            <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 8, overflow: 'hidden' }}>
              <div style={{ padding: '12px 16px', background: '#f8fafc', fontWeight: 700, borderBottom: '1px solid #e2e8f0' }}>
                🏪 Resumen por Sucursal
              </div>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid #e2e8f0', color: '#64748b', textAlign: 'left' }}>
                    <th style={{ padding: 10 }}>Sucursal</th>
                    <th style={{ padding: 10, textAlign: 'right' }}>Ventas</th>
                    <th style={{ padding: 10, textAlign: 'right' }}>Egresos</th>
                  </tr>
                </thead>
                <tbody>
                  {data.branches.map((b) => (
                    <tr key={b.branch_id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                      <td style={{ padding: 10, fontWeight: 600 }}>{b.branch_name}</td>
                      <td style={{ padding: 10, textAlign: 'right', fontWeight: 700, color: '#059669' }}>{money(b.total_sales)}</td>
                      <td style={{ padding: 10, textAlign: 'right', fontWeight: 700, color: '#dc2626' }}>{money(b.total_expenses)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Proveedores */}
            <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 8, overflow: 'hidden' }}>
              <div style={{ padding: '12px 16px', background: '#f8fafc', fontWeight: 700, borderBottom: '1px solid #e2e8f0' }}>
                📦 Acumulado por Proveedor de Insumos
              </div>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid #e2e8f0', color: '#64748b', textAlign: 'left' }}>
                    <th style={{ padding: 10 }}>Proveedor</th>
                    <th style={{ padding: 10, textAlign: 'right' }}>Total Pagado</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(data.supplier_totals).length === 0 ? (
                    <tr><td colSpan={2} style={{ padding: 12, color: '#94a3b8' }}>Sin pagos a proveedores en el periodo.</td></tr>
                  ) : (
                    Object.entries(data.supplier_totals).map(([name, total]) => (
                      <tr key={name} style={{ borderBottom: '1px solid #f1f5f9' }}>
                        <td style={{ padding: 10, fontWeight: 600 }}>{name}</td>
                        <td style={{ padding: 10, textAlign: 'right', fontWeight: 700 }}>{money(total)}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            {/* Gastos Fijos */}
            <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 8, overflow: 'hidden' }}>
              <div style={{ padding: '12px 16px', background: '#f8fafc', fontWeight: 700, borderBottom: '1px solid #e2e8f0' }}>
                🏢 Acumulado por Tipo de Gasto Fijo
              </div>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid #e2e8f0', color: '#64748b', textAlign: 'left' }}>
                    <th style={{ padding: 10 }}>Tipo de Gasto</th>
                    <th style={{ padding: 10, textAlign: 'right' }}>Total Pagado</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(data.fixed_expense_totals).length === 0 ? (
                    <tr><td colSpan={2} style={{ padding: 12, color: '#94a3b8' }}>Sin gastos fijos registrados en el periodo.</td></tr>
                  ) : (
                    Object.entries(data.fixed_expense_totals).map(([name, total]) => (
                      <tr key={name} style={{ borderBottom: '1px solid #f1f5f9' }}>
                        <td style={{ padding: 10, fontWeight: 600 }}>{name}</td>
                        <td style={{ padding: 10, textAlign: 'right', fontWeight: 700 }}>{money(total)}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
