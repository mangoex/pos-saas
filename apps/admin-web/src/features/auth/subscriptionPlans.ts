export interface SubscriptionPlanItem {
  code: string;
  name: string;
  priceMxn: number;
  amountDecimal: string;
  priceFormatted: string;
  features: string;
  checkoutUrl?: string;
  inAppCheckoutSupported?: boolean;
}

export const SUBSCRIPTION_PLANS: SubscriptionPlanItem[] = [
  {
    code: 'starter_349',
    name: 'Esencial',
    priceMxn: 349,
    amountDecimal: '349.00',
    priceFormatted: '$349/mes',
    features: 'Menú digital, pedidos, caja, QR/enlace, promociones, disponibilidad y administración desde celular.',
    inAppCheckoutSupported: true,
  },
  {
    code: 'conecta_699',
    name: 'Conecta',
    priceMxn: 699,
    amountDecimal: '699.00',
    priceFormatted: '$699/mes',
    features: 'Todo Esencial + integraciones con Uber Eats/DiDi/Rappi cuando estén disponibles + pedidos centralizados + sincronización de catálogo/disponibilidad.',
    checkoutUrl: 'https://mpago.la/2b3VRu1',
    inAppCheckoutSupported: true,
  },
  {
    code: 'control_999',
    name: 'Control',
    priceMxn: 999,
    amountDecimal: '999.00',
    priceFormatted: '$999/mes',
    features: 'Todo Conecta + inventarios, recetas, subrecetas, costos, mermas, consumo de insumos, márgenes y reportes operativos.',
    checkoutUrl: 'https://mpago.la/1yS6YdX',
    inAppCheckoutSupported: true,
  },
];

export const PLAN_NAMES: Record<string, string> = {
  starter_349: 'Esencial',
  starter: 'Esencial',
  esencial: 'Esencial',
  lite: 'Esencial',
  conecta_699: 'Conecta',
  conecta: 'Conecta',
  pro_599: 'Conecta',
  pro: 'Conecta',
  professional: 'Conecta',
  control_999: 'Control',
  control: 'Control',
  enterprise: 'Control',
};

export function findPlanCatalogItem(code: string): SubscriptionPlanItem | undefined {
  return SUBSCRIPTION_PLANS.find(p => p.code === code)
    || (code === 'pro_599' ? SUBSCRIPTION_PLANS.find(p => p.code === 'conecta_699') : undefined)
    || (code === 'starter' || code === 'esencial' || code === 'lite' ? SUBSCRIPTION_PLANS.find(p => p.code === 'starter_349') : undefined);
}
