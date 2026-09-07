import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { fetchApi } from '@restaurantos/api-client';
import { Button, Input, Modal } from '@restaurantos/ui';
import { CategoryImageField } from './CategoryImageField';

type MenuHome = { name: string; image_url: string | null };

export function MenuHomeEditor() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: 'Todos', image_url: '' });
  const [saved, setSaved] = useState(false);
  const home = useQuery<MenuHome>({ queryKey: ['menu-home'], queryFn: () => fetchApi('/catalog/menu-home') });
  const save = useMutation({
    mutationFn: () => fetchApi('/catalog/menu-home', { method: 'PUT', body: JSON.stringify(form) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['menu-home'] });
      setOpen(false);
      setSaved(true);
    },
  });
  return <>
    <div className="premium-card" style={{ padding: 20, marginBottom: 24 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
        <div style={{ minWidth: 0, overflowWrap: 'anywhere' }}>
          <h2 style={{ margin: '0 0 6px', fontSize: 18 }}>Portada principal del menú</h2>
          <p style={{ margin: 0, color: 'var(--color-text-muted)' }}>
            {home.data ? `«${home.data.name}» muestra todos tus productos.` : 'Cargando portada…'}
          </p>
        </div>
        <Button variant="secondary" disabled={!home.data || home.isError} onClick={() => {
          setForm({ name: home.data!.name, image_url: home.data!.image_url || '' });
          save.reset(); setSaved(false); setOpen(true);
        }}>Editar portada</Button>
      </div>
      {home.isError && <p role="alert">No fue posible cargar la portada. <button onClick={() => home.refetch()}>Reintentar</button></p>}
      {saved && <p role="status">Portada guardada. Los cambios aparecerán al volver a cargar el menú.</p>}
    </div>
    <Modal isOpen={open} onClose={() => setOpen(false)} title="Editar portada principal">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {save.isError && <p role="alert">{save.error instanceof Error ? save.error.message : 'No fue posible guardar la portada.'}</p>}
        <div>
          <label htmlFor="menu-home-name" style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>Nombre de la portada</label>
          <Input id="menu-home-name" value={form.name} maxLength={120}
            onChange={(event: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, name: event.target.value })} placeholder="Todos" />
        </div>
        <CategoryImageField value={form.image_url} onChange={image_url => setForm({ ...form, image_url })} />
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12 }}>
          <Button variant="secondary" onClick={() => setOpen(false)}>Cancelar</Button>
          <Button disabled={save.isPending || !form.name.trim()} onClick={() => save.mutate()}>
            {save.isPending ? 'Guardando…' : 'Guardar portada'}
          </Button>
        </div>
      </div>
    </Modal>
  </>;
}
