import React, { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, Plus, Search } from 'lucide-react';
import { Button, Input, Modal } from '@restaurantos/ui';
import { ApiError, fetchApi } from '@restaurantos/api-client';
import { centsToMxn, mxnToCentsExact } from './ingredientVariationMoney';

interface Ingredient {
  id: string;
  name: string;
  sku: string;
  unit_code?: string;
  item_type: string;
  status: string;
}

interface Extra {
  id: string;
  inventory_item_name: string;
  inventory_item_sku: string;
  unit_code: string;
  add_label: string;
  portion_quantity?: string;
  sale_price_cents?: number;
  station?: 'kitchen' | 'drinks' | 'packing' | null;
  display_order?: number;
  status: 'active' | 'archived' | 'needs_review';
  warnings: string[];
}

interface CanonicalForm {
  portion_quantity: string;
  sale_price_mxn: string;
  station: 'kitchen' | 'drinks' | 'packing';
  display_order: string;
}

const emptyCanonicalForm: CanonicalForm = {
  portion_quantity: '1',
  sale_price_mxn: '0.00',
  station: 'kitchen',
  display_order: '0',
};
const card: React.CSSProperties = {
  background: '#fff', border: '1px solid #e2e8f0', borderRadius: 12, padding: 16,
};
const errorMessage = (reason: unknown, fallback: string) => (
  reason instanceof ApiError ? reason.message : fallback
);

export default function IngredientExtras() {
  const client = useQueryClient();
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('active');
  const [createOpen, setCreateOpen] = useState(false);
  const [detailId, setDetailId] = useState('');
  const [itemSearch, setItemSearch] = useState('');
  const [itemId, setItemId] = useState('');
  const [label, setLabel] = useState('');
  const [portionQuantity, setPortionQuantity] = useState('1');
  const [salePriceMxn, setSalePriceMxn] = useState('');
  const [station, setStation] = useState<CanonicalForm['station']>('kitchen');
  const [displayOrder, setDisplayOrder] = useState('0');
  const [feedback, setFeedback] = useState('');
  const [operationalError, setOperationalError] = useState('');

  const extras = useQuery<Extra[]>({
    queryKey: ['ingredient-extras', search, status],
    queryFn: () => fetchApi(`/catalog/ingredient-variations?search=${encodeURIComponent(search)}&status=${status}`),
  });
  const items = useQuery<Ingredient[]>({
    queryKey: ['ingredient-extra-items', itemSearch],
    queryFn: () => fetchApi('/inventory/items'),
    enabled: createOpen,
  });
  const inventory = useMemo(() => (items.data || []).filter((item) => (
    item.item_type === 'ingredient'
      && item.status === 'active'
      && `${item.name} ${item.sku}`.toLowerCase().includes(itemSearch.toLowerCase()
      )
  )), [items.data, itemSearch]);
  const chosen = inventory.find((item) => item.id === itemId);
  const refresh = () => client.invalidateQueries({ queryKey: ['ingredient-extras'] });
  const resetCreate = () => {
    setCreateOpen(false);
    setItemSearch('');
    setItemId('');
    setLabel('');
    setPortionQuantity('1');
    setSalePriceMxn('');
    setStation('kitchen');
    setDisplayOrder('0');
  };
  const openCreate = () => {
    resetCreate();
    setFeedback('');
    setOperationalError('');
    setCreateOpen(true);
  };
  const create = useMutation<Extra>({
    mutationFn: () => fetchApi('/catalog/ingredient-variations', {
      method: 'POST',
      body: JSON.stringify({
        inventory_item_id: itemId || undefined,
        name: label.trim() || undefined,
        add_label: label.trim() || undefined,
        portion_quantity: portionQuantity,
        sale_price_cents: mxnToCentsExact(salePriceMxn),
        station,
        display_order: Number(displayOrder),
      }),
    }),
    onMutate: () => setOperationalError(''),
    onSuccess: (extra) => {
      resetCreate();
      setDetailId(extra.id);
      setFeedback('Ingrediente adicional corporativo creado. Está disponible para cualquier producto.');
      void refresh();
    },
    onError: (reason) => setOperationalError(errorMessage(reason, 'No fue posible crear el ingrediente adicional.')),
  });
  const statusMutation = useMutation({
    mutationFn: (extra: Extra) => fetchApi(`/catalog/ingredient-variations/${extra.id}`, {
      method: 'PUT',
      body: JSON.stringify({ status: extra.status === 'active' ? 'archived' : 'active' }),
    }),
    onMutate: () => setOperationalError(''),
    onSuccess: () => {
      setOperationalError('');
      void refresh();
    },
    onError: (reason) => setOperationalError(errorMessage(reason, 'No fue posible cambiar el estado del ingrediente adicional.')),
  });

  return <div style={{ padding: 24, maxWidth: 1120, background: '#f8fafc' }}>
    <header style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 18 }}>
      <Plus color="#10b981" />
      <div>
        <h1 style={{ margin: 0 }}>Ingredientes adicionales</h1>
        <p style={{ color: '#64748b', marginBottom: 0 }}>
          Porciones corporativas con cantidad exacta, inventario, costo interno y precio explícito.
        </p>
      </div>
    </header>
    <section style={{ ...card, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
      <div style={{ position: 'relative', flex: 1, minWidth: 220 }}>
        <Search size={16} style={{ left: 10, top: 11, position: 'absolute', color: '#64748b' }} />
        <Input
          value={search}
          onChange={(event: React.ChangeEvent<HTMLInputElement>) => setSearch(event.target.value)}
          placeholder="Buscar adicional, insumo o SKU"
          style={{ paddingLeft: 32 }}
        />
      </div>
      <select value={status} onChange={(event) => setStatus(event.target.value)} aria-label="Estado">
        <option value="active">Activos</option>
        <option value="needs_review">Requieren revisión</option>
        <option value="archived">Archivados</option>
      </select>
      <Button onClick={openCreate}>Nuevo ingrediente adicional</Button>
    </section>
    {operationalError && <p role="alert" style={{ color: '#b91c1c' }}>{operationalError}</p>}
    {extras.isLoading ? <p>Cargando ingredientes adicionales…</p> : null}
    {extras.isError ? <div role="alert">
      <p>{errorMessage(extras.error, 'No fue posible cargar ingredientes adicionales.')}</p>
      <Button onClick={() => void extras.refetch()}>Reintentar</Button>
    </div> : null}
    {!extras.isLoading && !extras.isError && (extras.data || []).length === 0 ? (
      <p style={{ color: '#64748b' }}>No hay ingredientes adicionales para este filtro.</p>
    ) : null}
    <div style={{ display: 'grid', gap: 10, marginTop: 12 }}>
      {(extras.data || []).map((extra) => <article key={extra.id} style={card}>
        <strong>{extra.inventory_item_name}</strong>
        <span style={{ color: '#64748b' }}> · {extra.inventory_item_sku} · {extra.unit_code}</span>
        <p>
          {extra.add_label} · Porción: {extra.portion_quantity || 'Sin configurar'} · Precio: {
            extra.sale_price_cents == null ? 'Sin configurar' : `$${centsToMxn(extra.sale_price_cents)}`
          } · Estación: {extra.station || 'Sin configurar'}
        </p>
        <p style={{ color: '#64748b' }}>Disponible para cualquier producto; no requiere relaciones por producto.</p>
        {extra.status === 'needs_review' || extra.warnings.length > 0 ? <p role="note" style={{ color: '#92400e' }}>
          <AlertTriangle size={14} /> Requiere configuración completa antes de volver a estar disponible en el POS.
        </p> : null}
        <div style={{ display: 'flex', gap: 8 }}>
          <Button variant="secondary" onClick={() => setDetailId(extra.id)}>Configurar</Button>
          <Button
            variant="secondary"
            disabled={statusMutation.isPending || extra.status === 'needs_review'}
            onClick={() => statusMutation.mutate(extra)}
          >
            {extra.status === 'active' ? 'Archivar' : 'Reactivar'}
          </Button>
        </div>
      </article>)}
    </div>
    <Modal isOpen={createOpen} onClose={resetCreate} title="Nuevo ingrediente adicional">
      <div style={{ display: 'grid', gap: 12 }}>
        {operationalError && <p role="alert" style={{ color: '#dc2626', margin: 0 }}>{operationalError}</p>}
        <label style={{ display: 'grid', gap: 4, fontWeight: 600 }}>Nombre del adicional (ej. Queso Extra, Tocino Extra)
          <Input
            value={label}
            onChange={(event: React.ChangeEvent<HTMLInputElement>) => setLabel(event.target.value)}
            placeholder="Ej. Queso Extra, Aguacate Extra…"
          />
        </label>
        <details style={{ fontSize: '0.875rem', color: '#64748b' }}>
          <summary style={{ cursor: 'pointer', padding: '4px 0' }}>Vincular a insumo de inventario (opcional)</summary>
          <div style={{ marginTop: 8 }}>
            <Input
              value={itemSearch}
              onChange={(event: React.ChangeEvent<HTMLInputElement>) => setItemSearch(event.target.value)}
              placeholder="Buscar insumo por nombre o SKU…"
            />
            <div style={{ maxHeight: 150, overflowY: 'auto', display: 'grid', gap: 4, marginTop: 6 }}>
              {inventory.slice(0, 15).map((item) => <button
                key={item.id}
                type="button"
                onClick={() => {
                  setItemId(item.id);
                  if (!label.trim()) setLabel(`Porción extra de ${item.name}`);
                  setOperationalError('');
                }}
                style={{ textAlign: 'left', border: itemId === item.id ? '2px solid #10b981' : '1px solid #e2e8f0', borderRadius: 8, padding: 8, background: itemId === item.id ? '#ecfdf5' : '#fff' }}
              >
                {item.name} · {item.sku} · {item.unit_code || 'unidad base'}
              </button>)}
            </div>
          </div>
        </details>
        <CanonicalFields
          form={{ portion_quantity: portionQuantity, sale_price_mxn: salePriceMxn, station, display_order: displayOrder }}
          onChange={(form) => {
            setPortionQuantity(form.portion_quantity);
            setSalePriceMxn(form.sale_price_mxn);
            setStation(form.station);
            setDisplayOrder(form.display_order);
          }}
          label={label}
          onLabelChange={setLabel}
          labelPlaceholder={chosen ? `Porción extra de ${chosen.name}` : 'Porción extra de…'}
        />
        <p style={{ color: '#64748b', fontSize: '0.8125rem', margin: 0 }}>
          La configuración corporativa aplica a cualquier producto; no existen overrides por sucursal.
        </p>
        <Button
          disabled={(!itemId && !label.trim()) || !portionQuantity.trim() || !salePriceMxn.trim() || create.isPending}
          onClick={() => create.mutate()}
        >
          Crear adicional
        </Button>
      </div>
    </Modal>
    {detailId ? <ExtraDetail key={detailId} id={detailId} onClose={() => setDetailId('')} onFeedback={setFeedback} /> : null}
    {feedback && <p role="status">{feedback}</p>}
  </div>;
}

function ExtraDetail({ id, onClose, onFeedback }: { id: string; onClose: () => void; onFeedback: (value: string) => void }) {
  const client = useQueryClient();
  const [canonicalForm, setCanonicalForm] = useState<CanonicalForm>(emptyCanonicalForm);
  const [mainError, setMainError] = useState('');
  const detail = useQuery<Extra>({
    queryKey: ['ingredient-extra', id],
    queryFn: () => fetchApi(`/catalog/ingredient-variations/${id}`),
  });
  const refresh = () => {
    void client.invalidateQueries({ queryKey: ['ingredient-extras'] });
    void client.invalidateQueries({ queryKey: ['ingredient-extra', id] });
  };
  useEffect(() => {
    if (!detail.data) return;
    setCanonicalForm({
      portion_quantity: String(detail.data.portion_quantity || '1'),
      sale_price_mxn: detail.data.sale_price_cents == null ? '0.00' : centsToMxn(detail.data.sale_price_cents),
      station: detail.data.station || 'kitchen',
      display_order: String(detail.data.display_order || 0),
    });
  }, [detail.data]);
  const canonicalUpdate = useMutation({
    mutationFn: () => fetchApi(`/catalog/ingredient-variations/${id}`, {
      method: 'PUT',
      body: JSON.stringify({
        portion_quantity: canonicalForm.portion_quantity,
        sale_price_cents: mxnToCentsExact(canonicalForm.sale_price_mxn),
        station: canonicalForm.station,
        display_order: Number(canonicalForm.display_order),
        status: detail.data?.status === 'needs_review' ? 'active' : undefined,
      }),
    }),
    onMutate: () => setMainError(''),
    onSuccess: () => {
      setMainError('');
      onFeedback('Configuración corporativa actualizada.');
      refresh();
    },
    onError: (reason) => setMainError(errorMessage(reason, 'No fue posible actualizar la configuración corporativa.')),
  });

  return <Modal isOpen onClose={onClose} title="Configurar ingrediente adicional">
    <div style={{ display: 'grid', gap: 12 }}>
      <p style={{ color: '#64748b' }}>
        Esta porción, precio y estación aplican a cualquier producto. Las relaciones heredadas se conservan sólo para el historial y no se administran aquí.
      </p>
      {mainError && <p role="alert">{mainError}</p>}
      {detail.isLoading ? <p>Cargando configuración…</p> : null}
      {detail.isError ? <p role="alert">
        {errorMessage(detail.error, 'No fue posible cargar la configuración.')} <button onClick={() => void detail.refetch()}>Reintentar</button>
      </p> : null}
      {detail.data ? <>
        {detail.data.status === 'needs_review' ? <p role="note" style={{ color: '#92400e' }}>
          <AlertTriangle size={14} /> Completa y guarda esta configuración para activar el adicional.
        </p> : null}
        <CanonicalFields form={canonicalForm} onChange={setCanonicalForm} />
        <Button
          disabled={canonicalUpdate.isPending || !canonicalForm.portion_quantity.trim() || !canonicalForm.sale_price_mxn.trim()}
          onClick={() => canonicalUpdate.mutate()}
        >
          {detail.data.status === 'needs_review' ? 'Guardar y activar' : 'Guardar configuración corporativa'}
        </Button>
      </> : null}
    </div>
  </Modal>;
}

function CanonicalFields({
  form,
  onChange,
  label,
  onLabelChange,
  labelPlaceholder,
}: {
  form: CanonicalForm;
  onChange: (value: CanonicalForm) => void;
  label?: string;
  onLabelChange?: (value: string) => void;
  labelPlaceholder?: string;
}) {
  return <div style={{ display: 'grid', gap: 8 }}>
    {onLabelChange ? <label>Etiqueta visible
      <Input value={label || ''} onChange={(event: React.ChangeEvent<HTMLInputElement>) => onLabelChange(event.target.value)} placeholder={labelPlaceholder} />
    </label> : null}
    <label>Cantidad Decimal
      <Input inputMode="decimal" value={form.portion_quantity} onChange={(event: React.ChangeEvent<HTMLInputElement>) => onChange({ ...form, portion_quantity: event.target.value })} placeholder="0.250" />
    </label>
    <label>Precio de venta (MXN)
      <Input inputMode="decimal" value={form.sale_price_mxn} onChange={(event: React.ChangeEvent<HTMLInputElement>) => onChange({ ...form, sale_price_mxn: event.target.value })} placeholder="15.00" />
    </label>
    <label>Estación
      <select value={form.station} onChange={(event) => onChange({ ...form, station: event.target.value as CanonicalForm['station'] })} style={{ width: '100%', padding: 9, border: '1px solid #cbd5e1', borderRadius: 8 }}>
        <option value="kitchen">Cocina</option>
        <option value="drinks">Bebidas</option>
        <option value="packing">Empaque</option>
      </select>
    </label>
    <label>Orden de despliegue
      <Input inputMode="numeric" value={form.display_order} onChange={(event: React.ChangeEvent<HTMLInputElement>) => onChange({ ...form, display_order: event.target.value })} />
    </label>
  </div>;
}
