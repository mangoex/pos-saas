import React, { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Button, Modal } from '@restaurantos/ui';
import { fetchApi } from '@restaurantos/api-client';
import { Sparkles, CheckCircle2, AlertCircle, ArrowRight, BookOpen } from 'lucide-react';
import { RecipeWorkspaceItem } from './RecipeManager';

interface IngredientMatch {
  raw_name: string;
  quantity: string | number;
  unit: string;
  matched_item_id: string | null;
  matched_item_name: string | null;
  base_unit: string;
  normalized_quantity: string | number;
  unit_cost: string | number;
  line_cost: string | number;
  confidence_score: number;
  status: 'matched' | 'unmatched';
}

interface AiParseResponse {
  title: string;
  product_id?: string;
  steps: string[];
  total_cost: string | number;
  cost_per_portion: string | number;
  sale_price: string | number;
  food_cost_percentage: string | number;
  food_cost_status: 'optimal' | 'warning' | 'alert';
  ingredients: IngredientMatch[];
}

interface Props {
  isOpen: boolean;
  onClose: () => void;
  productId: string;
  productName: string;
  items: RecipeWorkspaceItem[];
  onApplyIngredients: (components: Array<{ item_id: string; unit_id: string; net_quantity: string; waste_rate: string }>) => void;
}

export const RecipeAiAssistantModal: React.FC<Props> = ({
  isOpen,
  onClose,
  productId,
  productName,
  items,
  onApplyIngredients,
}) => {
  const [recipeText, setRecipeText] = useState('');
  const [salePriceInput, setSalePriceInput] = useState('');
  const [analysis, setAnalysis] = useState<AiParseResponse | null>(null);
  const [parseError, setParseError] = useState('');

  const parseMutation = useMutation({
    mutationFn: () =>
      fetchApi<AiParseResponse>('/recipes/ai-parse', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          raw_text: recipeText,
          product_id: productId,
          sale_price: salePriceInput ? parseFloat(salePriceInput) : null,
          yield_portions: 1,
        }),
      }),
    onSuccess: (data) => {
      setAnalysis(data);
      setParseError('');
    },
    onError: (err: any) => {
      setParseError(err?.message || 'No fue posible analizar la receta con IA. Intenta con un texto más claro.');
    },
  });

  const handleApply = () => {
    if (!analysis) return;
    const componentsToApply: Array<{ item_id: string; unit_id: string; net_quantity: string; waste_rate: string }> = [];

    for (const ing of analysis.ingredients) {
      if (ing.matched_item_id) {
        const itemObj = items.find((it) => it.id === ing.matched_item_id);
        const unitId = itemObj?.unit_id || (items.find((it) => it.unit_code === ing.base_unit)?.unit_id) || items[0]?.unit_id || '';
        componentsToApply.push({
          item_id: ing.matched_item_id,
          unit_id: unitId,
          net_quantity: String(ing.normalized_quantity || '1'),
          waste_rate: '0',
        });
      }
    }

    onApplyIngredients(componentsToApply);
    onClose();
  };

  if (!isOpen) return null;

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={`✨ Asistente IA de Recetas — ${productName}`}>
      <div style={{ display: 'grid', gap: 16, maxHeight: '80vh', overflowY: 'auto', padding: '4px' }}>
        <p style={{ color: '#4b5563', fontSize: '0.9rem', margin: 0 }}>
          Pega el texto libre de la receta (ingredientes, cantidades y preparación). La IA identificará los insumos del catálogo, normalizará unidades a kg/litros/piezas y calculará el Food Cost sugerido.
        </p>

        <div style={{ display: 'grid', gap: 6 }}>
          <label style={{ fontWeight: 600, fontSize: '0.85rem', color: '#374151' }}>Texto o Ficha de la Receta</label>
          <textarea
            rows={7}
            placeholder={`Ejemplo:\n1 pan baguette fresco.\n250 g de pechuga de pollo cocida y deshebrada.\n1/4 taza de salsa BBQ.\n1/2 taza de queso mozzarella rallado.\n1/4 cebolla morada en rodajas.`}
            value={recipeText}
            onChange={(e) => setRecipeText(e.target.value)}
            style={{
              width: '100%',
              padding: '10px',
              borderRadius: '6px',
              border: '1px solid #d1d5db',
              fontFamily: 'monospace',
              fontSize: '0.85rem',
            }}
          />
        </div>

        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          <div style={{ flex: 1 }}>
            <label style={{ fontWeight: 600, fontSize: '0.85rem', color: '#374151' }}>Precio de Venta ($ MXN, opcional si ya está asignado)</label>
            <input
              type="number"
              step="0.01"
              placeholder="Ej. 135.00"
              value={salePriceInput}
              onChange={(e) => setSalePriceInput(e.target.value)}
              style={{
                width: '100%',
                padding: '8px 10px',
                borderRadius: '6px',
                border: '1px solid #d1d5db',
                marginTop: '4px',
              }}
            />
          </div>
          <Button
            variant="primary"
            disabled={parseMutation.isPending || recipeText.trim().length < 5}
            onClick={() => parseMutation.mutate()}
            style={{ marginTop: '20px', background: '#059669', borderColor: '#059669' }}
          >
            <Sparkles size={16} style={{ marginRight: 6 }} />
            {parseMutation.isPending ? 'Analizando con IA…' : '✨ Analizar y Costear'}
          </Button>
        </div>

        {parseError && (
          <div role="alert" style={{ background: '#fef2f2', color: '#b91c1c', padding: 12, borderRadius: 6, display: 'flex', gap: 8, alignItems: 'center' }}>
            <AlertCircle size={18} />
            <span>{parseError}</span>
          </div>
        )}

        {analysis && (
          <div style={{ border: '1px solid #e5e7eb', borderRadius: 8, padding: 16, background: '#f9fafb', display: 'grid', gap: 14 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h4 style={{ margin: 0, color: '#111827', fontSize: '1rem', fontWeight: 600 }}>
                {analysis.title || productName}
              </h4>
              <div
                style={{
                  padding: '4px 10px',
                  borderRadius: 9999,
                  fontWeight: 600,
                  fontSize: '0.8rem',
                  background:
                    analysis.food_cost_status === 'optimal'
                      ? '#d1fae5'
                      : analysis.food_cost_status === 'warning'
                      ? '#fef3c7'
                      : '#fee2e2',
                  color:
                    analysis.food_cost_status === 'optimal'
                      ? '#065f46'
                      : analysis.food_cost_status === 'warning'
                      ? '#92400e'
                      : '#991b1b',
                }}
              >
                Food Cost: {analysis.food_cost_percentage}% ({analysis.food_cost_status.toUpperCase()})
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10, background: '#fff', padding: 12, borderRadius: 6, border: '1px solid #e5e7eb' }}>
              <div>
                <span style={{ fontSize: '0.75rem', color: '#6b7280' }}>Costo Teórico</span>
                <div style={{ fontSize: '1.1rem', fontWeight: 700, color: '#111827' }}>${Number(analysis.total_cost).toFixed(2)} MXN</div>
              </div>
              <div>
                <span style={{ fontSize: '0.75rem', color: '#6b7280' }}>Precio Venta</span>
                <div style={{ fontSize: '1.1rem', fontWeight: 700, color: '#111827' }}>${Number(analysis.sale_price).toFixed(2)} MXN</div>
              </div>
              <div>
                <span style={{ fontSize: '0.75rem', color: '#6b7280' }}>Margen Bruto</span>
                <div style={{ fontSize: '1.1rem', fontWeight: 700, color: '#059669' }}>
                  ${(Number(analysis.sale_price) - Number(analysis.total_cost)).toFixed(2)} MXN
                </div>
              </div>
            </div>

            <h5 style={{ margin: '6px 0 0 0', fontSize: '0.85rem', color: '#374151' }}>Desglose de Insumos Reconocidos</h5>
            <div style={{ overflowX: 'auto', background: '#fff', border: '1px solid #e5e7eb', borderRadius: 6 }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.82rem' }}>
                <thead style={{ background: '#f3f4f6' }}>
                  <tr>
                    <th style={{ padding: '8px 10px', textAlign: 'left' }}>Ingrediente Detectado</th>
                    <th style={{ padding: '8px 10px', textAlign: 'left' }}>Insumo en Catálogo</th>
                    <th style={{ padding: '8px 10px', textAlign: 'right' }}>Cant. Normalizada</th>
                    <th style={{ padding: '8px 10px', textAlign: 'right' }}>Costo Línea</th>
                    <th style={{ padding: '8px 10px', textAlign: 'center' }}>Match</th>
                  </tr>
                </thead>
                <tbody>
                  {analysis.ingredients.map((ing, idx) => (
                    <tr key={idx} style={{ borderTop: '1px solid #f3f4f6' }}>
                      <td style={{ padding: '8px 10px', fontWeight: 500 }}>
                        {ing.raw_name} ({ing.quantity} {ing.unit})
                      </td>
                      <td style={{ padding: '8px 10px', color: ing.matched_item_name ? '#111827' : '#9ca3af' }}>
                        {ing.matched_item_name || '— Sin coincidencia directa —'}
                      </td>
                      <td style={{ padding: '8px 10px', textAlign: 'right', fontFamily: 'monospace' }}>
                        {ing.normalized_quantity} {ing.base_unit}
                      </td>
                      <td style={{ padding: '8px 10px', textAlign: 'right', fontWeight: 600 }}>
                        ${Number(ing.line_cost || (ing as any).item_cost || 0).toFixed(2)}
                      </td>
                      <td style={{ padding: '8px 10px', textAlign: 'center' }}>
                        {ing.status === 'matched' ? (
                          <span title={`Confianza: ${(ing.confidence_score * 100).toFixed(0)}%`} style={{ color: '#059669', display: 'inline-flex', alignItems: 'center' }}>
                            <CheckCircle2 size={15} />
                          </span>
                        ) : (
                          <span title="Insumo no encontrado en catálogo" style={{ color: '#dc2626', display: 'inline-flex', alignItems: 'center' }}>
                            <AlertCircle size={15} />
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {analysis.steps && analysis.steps.length > 0 && (
              <div style={{ marginTop: 6 }}>
                <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#4b5563', display: 'flex', alignItems: 'center', gap: 4 }}>
                  <BookOpen size={14} /> Pasos de Preparación Identificados:
                </span>
                <ol style={{ margin: '4px 0 0 0', paddingLeft: 20, fontSize: '0.8rem', color: '#4b5563' }}>
                  {analysis.steps.map((st, i) => (
                    <li key={i}>{st}</li>
                  ))}
                </ol>
              </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 10 }}>
              <Button variant="secondary" onClick={() => setAnalysis(null)}>
                Volver a editar
              </Button>
              <Button variant="primary" onClick={handleApply} style={{ background: '#2563eb' }}>
                📥 Aplicar Insumos a Ficha Técnica <ArrowRight size={14} style={{ marginLeft: 6 }} />
              </Button>
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
};
