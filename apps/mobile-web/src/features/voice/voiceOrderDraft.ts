export interface VoiceDraftOption {
  id: string;
  name: string;
  price_delta_cents: number;
  kind: 'modifier' | 'comment';
}

export interface VoiceDraftSelection {
  group_id: string;
  option_id: string;
  option_name: string;
  price_delta_cents: number;
  kind: 'modifier' | 'comment';
}

export interface VoiceDraftQuestion {
  line_index: number;
  group_id: string;
  prompt: string;
  minimum_selections: number;
  maximum_selections: number;
  options: VoiceDraftOption[];
}

export interface VoiceOrderDraft {
  customer_name: string;
  phone: string;
  order_type: 'takeout' | 'delivery' | null;
  lines: Array<{
    product_id: string;
    product_name: string;
    quantity: number;
    selected_options: VoiceDraftSelection[];
  }>;
  questions: VoiceDraftQuestion[];
  option_groups?: VoiceDraftQuestion[];
  status: 'ready' | 'needs_input';
  model: string;
}

interface CatalogModifierOption {
  id: string;
  name: string;
  price_delta_cents: number;
  selection_kind: string;
}

interface CatalogModifierGroup {
  id: string;
  name: string;
  minimum_selections: number;
  maximum_selections: number;
  options: CatalogModifierOption[];
}

interface VoiceCatalogProduct {
  id: string;
  name: string;
  price_cents: number;
  is_available?: boolean;
  modifier_groups?: CatalogModifierGroup[];
}

export interface VoiceCartItem<TProduct extends VoiceCatalogProduct = VoiceCatalogProduct> {
  cart_id: string;
  product: TProduct;
  quantity: number;
  modifiers: Array<{
    option_id: string;
    name: string;
    price_delta_cents: number;
    selection_kind: string;
  }>;
  line_total_cents: number;
}

export const appendVoiceTranscript = (base: string, recognized: string): string => {
  const current = base.trim();
  const addition = recognized.trim();
  if (!addition) return current;
  if (!current) return addition.slice(0, 1_000);
  const normalizedCurrent = current.toLocaleLowerCase('es-MX');
  const normalizedAddition = addition.toLocaleLowerCase('es-MX');
  if (normalizedCurrent === normalizedAddition || normalizedCurrent.endsWith(normalizedAddition)) {
    return current;
  }
  return `${current} ${addition}`.slice(0, 1_000);
};

const selectionsForQuestion = (
  draft: VoiceOrderDraft,
  question: VoiceDraftQuestion,
): VoiceDraftSelection[] => draft.lines[question.line_index]?.selected_options.filter(
  (selection) => selection.group_id === question.group_id,
) ?? [];

const editableGroups = (draft: VoiceOrderDraft): VoiceDraftQuestion[] => (
  draft.option_groups ?? draft.questions
);

export const isVoiceDraftComplete = (draft: VoiceOrderDraft): boolean => (
  draft.lines.length > 0
  && editableGroups(draft).every((question) => {
    const count = selectionsForQuestion(draft, question).length;
    return count >= question.minimum_selections && count <= question.maximum_selections;
  })
);

export const toggleVoiceDraftOption = (
  draft: VoiceOrderDraft,
  question: VoiceDraftQuestion,
  option: VoiceDraftOption,
): VoiceOrderDraft => {
  const line = draft.lines[question.line_index];
  if (!line || !question.options.some((candidate) => candidate.id === option.id)) return draft;
  const selected = selectionsForQuestion(draft, question);
  const alreadySelected = selected.some((candidate) => candidate.option_id === option.id);
  let nextForGroup: VoiceDraftSelection[];
  if (alreadySelected) {
    nextForGroup = selected.filter((candidate) => candidate.option_id !== option.id);
  } else if (selected.length >= question.maximum_selections && question.maximum_selections !== 1) {
    return draft;
  } else {
    nextForGroup = [
      ...(question.maximum_selections === 1 ? [] : selected),
      {
      group_id: question.group_id,
      option_id: option.id,
      option_name: option.name,
      price_delta_cents: option.price_delta_cents,
      kind: option.kind,
      },
    ];
  }
  const selectedOptions = line.selected_options.filter(
    (selection) => selection.group_id !== question.group_id,
  ).concat(nextForGroup);
  const lines = draft.lines.map((candidate, index) => (
    index === question.line_index ? { ...candidate, selected_options: selectedOptions } : candidate
  ));
  const next = { ...draft, lines };
  return { ...next, status: isVoiceDraftComplete(next) ? 'ready' : 'needs_input' };
};

const defaultCartId = (): string => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `voice-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
};

export const voiceDraftToCartItems = <TProduct extends VoiceCatalogProduct>(
  draft: VoiceOrderDraft,
  products: TProduct[],
  idFactory: () => string = defaultCartId,
): VoiceCartItem<TProduct>[] => {
  if (!isVoiceDraftComplete(draft)) {
    throw new Error('Completa las opciones requeridas antes de agregar el pedido.');
  }
  const byId = new Map(products.map((product) => [product.id, product]));
  return draft.lines.map((line) => {
    const product = byId.get(line.product_id);
    if (!product || product.is_available === false) {
      throw new Error('Un producto del borrador ya no está disponible.');
    }
    if (!Number.isInteger(line.quantity) || line.quantity < 1 || line.quantity > 99) {
      throw new Error('La cantidad propuesta no es válida.');
    }
    const groups = new Map((product.modifier_groups ?? []).map((group) => [group.id, group]));
    const uniqueOptions = new Set<string>();
    const modifiers = line.selected_options.map((selection) => {
      const group = groups.get(selection.group_id);
      const option = group?.options.find((candidate) => candidate.id === selection.option_id);
      if (!group || !option || uniqueOptions.has(option.id)) {
        throw new Error('Una opción del borrador ya no pertenece al catálogo.');
      }
      uniqueOptions.add(option.id);
      return {
        option_id: option.id,
        name: option.name,
        price_delta_cents: option.price_delta_cents,
        selection_kind: option.selection_kind,
      };
    });
    for (const group of product.modifier_groups ?? []) {
      const count = group.options.filter((option) => uniqueOptions.has(option.id)).length;
      if (count < group.minimum_selections || count > group.maximum_selections) {
        throw new Error(`${group.name} requiere una selección válida.`);
      }
    }
    const unitTotal = product.price_cents + modifiers.reduce(
      (sum, modifier) => sum + modifier.price_delta_cents,
      0,
    );
    return {
      cart_id: idFactory(),
      product,
      quantity: line.quantity,
      modifiers,
      line_total_cents: line.quantity * unitTotal,
    };
  });
};
