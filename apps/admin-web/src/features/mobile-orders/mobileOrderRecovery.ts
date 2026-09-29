export type MobileCommandScope = {
  organizationId: string; branchId: string; actorId: string; orderId: string;
};
export type MobileCommandAction = 'pay' | 'pay_and_deliver' | 'deliver' | 'close' | 'start_delivery';
type PaymentBody = { amount_cents: number; method: string; register_id: string; idempotency_key: string };
type Receipt = { id: string; status: string; method: string; amount_cents: number };
type CanonicalOrder = {
  id: string; organization_id: string; branch_id: string; total_cents: number;
  status: string; payment_status?: string;
};
type Pending = {
  version: 1; scope: MobileCommandScope; action: MobileCommandAction;
  payment?: PaymentBody; receipt?: Receipt; fulfillmentKey?: string;
};
export type MobileCommandInput = {
  scope: MobileCommandScope; action: MobileCommandAction; method: string;
  registerId: string; session: string;
};
export type MobileCommandResult = { order: CanonicalOrder; payment?: Receipt };
type Dependencies = {
  storage: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;
  api: <T>(path: string, options?: RequestInit) => Promise<T>;
  currentSession: () => string | null;
  newKey: () => string;
  lock?: <T>(name: string, operation: () => Promise<T>) => Promise<T>;
};
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const METHODS = new Set(['cash', 'card', 'transfer']);
const ACTIONS = new Set(['pay', 'pay_and_deliver', 'deliver', 'close', 'start_delivery']);
const validText = (value: unknown): value is string =>
  typeof value === 'string' && value.length > 0 && value.length <= 160;
const scopeKey = (scope: MobileCommandScope) => JSON.stringify([
  scope.organizationId, scope.branchId, scope.actorId, scope.orderId,
]);

function readPending(raw: string | null, scope: MobileCommandScope): Pending | null {
  if (raw === null) return null;
  try {
    if (raw.length > 4000) throw new Error();
    const value: Pending = JSON.parse(raw);
    if (value.version !== 1 || !value.scope || scopeKey(value.scope) !== scopeKey(scope)
      || !ACTIONS.has(value.action)) throw new Error();
    if (value.payment && (!UUID.test(value.payment.idempotency_key)
      || !Number.isSafeInteger(value.payment.amount_cents) || value.payment.amount_cents <= 0
      || !METHODS.has(value.payment.method) || !validText(value.payment.register_id))) throw new Error();
    if (value.receipt && (!value.payment || !validText(value.receipt.id)
      || value.receipt.status !== 'CONFIRMED' || value.receipt.method !== value.payment.method
      || value.receipt.amount_cents !== value.payment.amount_cents)) throw new Error();
    if (value.fulfillmentKey && !UUID.test(value.fulfillmentKey)) throw new Error();
    if (!value.payment && !value.fulfillmentKey) throw new Error();
    return value;
  } catch {
    throw new Error('Los datos de recuperación no son válidos. No se realizará otro cobro.');
  }
}

export function pendingMobileOrderCommand(
  scope: MobileCommandScope, storage: Pick<Storage, 'getItem'>,
): { action: MobileCommandAction; method: string; registerId: string } | null {
  const value = readPending(storage.getItem(`restaurantos:mobile-order:v1:${scopeKey(scope)}`), scope);
  return value ? { action: value.action, method: value.payment?.method ?? 'cash',
    registerId: value.payment?.register_id ?? 'CAJA-01' } : null;
}

/** Retry durable backend commands; all monetary calculation remains on the Python server. */
export async function runMobileOrderCommand(
  input: MobileCommandInput, deps: Dependencies,
): Promise<MobileCommandResult> {
  if (!deps.lock) throw new Error('No se puede coordinar el cobro entre pestañas en este navegador.');
  if (!Object.values(input.scope).every(validText) || !validText(input.registerId)
    || !METHODS.has(input.method) || !ACTIONS.has(input.action)) {
    throw new Error('El contexto de cobro no es válido.');
  }
  const checkSession = () => {
    if (!input.session || deps.currentSession() !== input.session) {
      throw new Error('La sesión cambió. Abre nuevamente el pedido antes de continuar.');
    }
  };
  checkSession();
  const key = `restaurantos:mobile-order:v1:${scopeKey(input.scope)}`;
  return deps.lock(key, async () => {
    checkSession();
    let pending = readPending(deps.storage.getItem(key), input.scope);
    if (pending && (pending.action !== input.action || (pending.payment && !pending.receipt
      && (pending.payment.method !== input.method || pending.payment.register_id !== input.registerId)))) {
      throw new Error('Hay un intento pendiente. Recupera la operación con el método y caja originales.');
    }
    const path = `/orders/${encodeURIComponent(input.scope.orderId)}`;
    const getOrder = async () => {
      checkSession();
      const order = await deps.api<CanonicalOrder>(path);
      checkSession();
      if (order.id !== input.scope.orderId || order.organization_id !== input.scope.organizationId
        || order.branch_id !== input.scope.branchId || !Number.isSafeInteger(order.total_cents)
        || order.total_cents < 0) {
        throw new Error('El pedido no corresponde al contexto de recuperación.');
      }
      return order;
    };
    let order = await getOrder();
    const save = () => {
      checkSession();
      const serialized = JSON.stringify(pending);
      deps.storage.setItem(key, serialized);
      if (deps.storage.getItem(key) !== serialized) {
        throw new Error('No se pudo conservar el intento de cobro.');
      }
    };
    const newKey = () => {
      const value = deps.newKey();
      if (!UUID.test(value)) throw new Error('No se pudo identificar el intento de cobro.');
      return value;
    };
    if (!pending) {
      const wantsPayment = input.action === 'pay' || input.action === 'pay_and_deliver';
      pending = { version: 1, scope: input.scope, action: input.action };
      if (wantsPayment && order.payment_status !== 'CONFIRMED' && order.total_cents > 0) {
        pending.payment = { amount_cents: order.total_cents, method: input.method,
          register_id: input.registerId, idempotency_key: newKey() };
      }
      if (input.action !== 'pay') pending.fulfillmentKey = newKey();
      if (!pending.payment && !pending.fulfillmentKey) return { order };
      save();
    }
    if (pending.payment && !pending.receipt) {
      checkSession();
      const receipt = await deps.api<Receipt>(`${path}/payments`, {
        method: 'POST', headers: { 'Idempotency-Key': pending.payment.idempotency_key },
        body: JSON.stringify(pending.payment),
      });
      checkSession();
      if (!validText(receipt.id) || receipt.status !== 'CONFIRMED'
        || receipt.method !== pending.payment.method || receipt.amount_cents !== pending.payment.amount_cents) {
        throw new Error('No se pudo verificar el recibo. Conservamos el intento para recuperación.');
      }
      pending.receipt = { id: receipt.id, status: receipt.status, method: receipt.method,
        amount_cents: receipt.amount_cents };
      save();
    }
    if (pending.fulfillmentKey) {
      checkSession();
      const command = pending.action === 'pay_and_deliver' ? 'deliver' : pending.action;
      const response = await deps.api<{ id: string; status: string }>(`${path}/fulfillment/${command}`, {
        method: 'POST', headers: { 'Idempotency-Key': pending.fulfillmentKey },
      });
      checkSession();
      const target = command === 'close' ? 'CLOSED' : command === 'start_delivery' ? 'IN_DELIVERY' : 'DELIVERED';
      if (response.id !== input.scope.orderId || response.status !== target) {
        throw new Error('No se pudo confirmar la entrega. Conservamos el intento para recuperación.');
      }
    }
    order = await getOrder();
    checkSession();
    deps.storage.removeItem(key);
    if (deps.storage.getItem(key) !== null) throw new Error('No se pudo cerrar el intento de recuperación.');
    return { order, payment: pending.receipt };
  });
}
