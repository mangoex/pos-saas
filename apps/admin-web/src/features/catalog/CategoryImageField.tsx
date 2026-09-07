import React, { useState } from 'react';
import { Input } from '@restaurantos/ui';

export function CategoryImageField({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  const trimmed = value.trim();
  const preview = /^https?:\/\//i.test(trimmed) && failedUrl !== trimmed;
  return <div>
    <label htmlFor="category-image-url" style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>Liga de la imagen</label>
    <Input id="category-image-url" type="url" maxLength={512} value={value}
      onChange={(event: React.ChangeEvent<HTMLInputElement>) => onChange(event.target.value)}
      placeholder="https://ejemplo.com/imagen.jpg" />
    <p style={{ margin: '8px 0', color: 'var(--color-text-muted)', fontSize: 13 }}>
      Pega una liga pública HTTP o HTTPS. Usa una imagen horizontal para la portada. Deja vacío para usar la ilustración predeterminada.
    </p>
    {preview && <img src={trimmed} alt="Vista previa de la imagen" referrerPolicy="no-referrer"
      onError={() => setFailedUrl(trimmed)} style={{ width: '100%', maxHeight: 140, objectFit: 'cover', borderRadius: 10 }} />}
    {trimmed && failedUrl === trimmed && <p role="status" style={{ fontSize: 13 }}>No se pudo cargar la vista previa. Comprueba que la liga sea pública y apunte a una imagen.</p>}
  </div>;
}
