export interface PublicModifierOption {
  id: string;
  name: string;
  price_delta_cents: number;
  selection_kind: string;
}

export interface PublicModifierGroup {
  id: string;
  name: string;
  is_required: boolean;
  minimum_selections: number;
  maximum_selections: number;
  options: PublicModifierOption[];
}

export interface SelectedModifier {
  option_id: string;
  name: string;
  price_delta_cents: number;
  selection_kind: string;
  text?: string;
}

export interface Product {
  id: string;
  name: string;
  sku: string;
  category_name?: string;
  category_id?: string;
  price_cents: number;
  description?: string;
  station?: string;
  image_url?: string;
  calories?: string;
  prep_time?: string;
  tags?: string[];
  is_available?: boolean;
  modifier_groups?: PublicModifierGroup[];
}

export interface Category {
  id: string;
  name: string;
  icon?: string;
  display_order?: number;
}

export interface BranchInfo {
  id: string;
  name: string;
  code: string;
  street?: string;
  exterior_number?: string;
  interior_number?: string;
  neighborhood?: string;
  postal_code?: string;
  city?: string;
  state?: string;
  cross_streets?: string;
  latitude?: number | null;
  longitude?: number | null;
  phone?: string;
  status: string;
  distance_km?: number | null;
  public_key?: string | null;
  google_review_url?: string | null;
}

export interface CartItem {
  cart_id: string;
  product: Product;
  quantity: number;
  notes?: string;
  modifiers: SelectedModifier[];
  line_total_cents: number;
}

export type OrderType = 'takeaway' | 'delivery' | 'dine-in';
export type PaymentMethod = 'cash' | 'card' | 'transfer';

export interface CustomerOrderInfo {
  name: string;
  phone: string;
  order_type: OrderType;
  address_street: string;
  address_number: string;
  address_neighborhood: string;
  address_notes: string;
  payment_method: PaymentMethod;
  cash_amount?: string;
  order_notes?: string;
}

interface PersistedOrderResultBase {
  customer_info: CustomerOrderInfo;
  items: CartItem[];
  total_cents: number;
  whatsapp_url?: string;
}

/** A canonical operational order returned by the legacy public-order endpoint. */
export interface OperationalOrderResult extends PersistedOrderResultBase {
  kind: 'operational_order';
  folio: string;
  id: string;
  created_at: string;
  whatsapp_url?: string;
}

/**
 * A persisted public request is not an Order.  Keep it structurally separate so
 * no UI consumer can accidentally present its reference as an operational folio.
 */
export interface PublicOrderIntentResult extends PersistedOrderResultBase {
  kind: 'public_order_intent';
  public_reference: string;
  status: 'PENDING_REVIEW';
  version: number;
}

export type CreatedOrderResult = OperationalOrderResult | PublicOrderIntentResult;
