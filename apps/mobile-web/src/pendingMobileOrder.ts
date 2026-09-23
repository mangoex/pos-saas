import type { CartItem, CustomerOrderInfo } from './types';

const PENDING_PREFIX = 'restaurantos_pending_mobile_order:';
const COMPLETED_PREFIX = 'restaurantos_completed_mobile_order:';
const CURRENT_KEY_PREFIX = 'restaurantos_public_order_key:';
const LEGACY_KEY_PREFIX = 'kiwi_public_order_key:';
const LOCK_PREFIX = 'restaurantos:public-order:';

interface MobileOrderLockManager {
  request(name: string, callback: () => Promise<unknown>): Promise<unknown>;
}

export interface PendingMobileOrder {
  version: 1;
  idempotencyKey: string;
  requestBody: string;
  customerInfo: CustomerOrderInfo;
  items: CartItem[];
  branchName?: string;
  branchPhone?: string;
  whatsappOrderingEnabled?: boolean;
}

export type PendingMobileOrderState =
  | { kind: 'none' }
  | { kind: 'record'; attempt: PendingMobileOrder }
  | { kind: 'legacy' }
  | { kind: 'unavailable' };

const pendingKey = (effectiveKey: string) => `${PENDING_PREFIX}${effectiveKey}`;
const completedKey = (effectiveKey: string) => `${COMPLETED_PREFIX}${effectiveKey}`;
const oldKeys = (effectiveKey: string) => [
  `${CURRENT_KEY_PREFIX}${effectiveKey}`,
  `${LEGACY_KEY_PREFIX}${effectiveKey}`,
];

function isPendingMobileOrder(value: unknown): value is PendingMobileOrder {
  if (!value || typeof value !== 'object') return false;
  const attempt = value as Partial<PendingMobileOrder>;
  return attempt.version === 1
    && typeof attempt.idempotencyKey === 'string'
    && attempt.idempotencyKey.length > 0
    && typeof attempt.requestBody === 'string'
    && Boolean(attempt.customerInfo && typeof attempt.customerInfo === 'object')
    && Array.isArray(attempt.items);
}

/** Read a recoverable order attempt, or fail closed when old data cannot be replayed safely. */
export function readPendingMobileOrder(effectiveKey: string | null | undefined): PendingMobileOrderState {
  if (!effectiveKey) return { kind: 'none' };
  try {
    const stored = globalThis.localStorage.getItem(pendingKey(effectiveKey));
    if (stored !== null) {
      try {
        const parsed: unknown = JSON.parse(stored);
        return isPendingMobileOrder(parsed) ? { kind: 'record', attempt: parsed } : { kind: 'legacy' };
      } catch {
        return { kind: 'legacy' };
      }
    }
    if (oldKeys(effectiveKey).some((key) => globalThis.localStorage.getItem(key) !== null)) {
      return { kind: 'legacy' };
    }
    return { kind: 'none' };
  } catch {
    return { kind: 'unavailable' };
  }
}

/** True for replayable, legacy-ambiguous, malformed, or inaccessible pending state. */
export function hasPendingMobileOrder(effectiveKey: string | null | undefined): boolean {
  if (!effectiveKey) return false;
  return readPendingMobileOrder(effectiveKey).kind !== 'none';
}

/** Persist before sending so a reload can replay the exact body and idempotency key. */
export function savePendingMobileOrder(
  effectiveKey: string,
  attempt: PendingMobileOrder,
): boolean {
  try {
    const serialized = JSON.stringify(attempt);
    if (!serialized) return false;
    globalThis.localStorage.setItem(pendingKey(effectiveKey), serialized);
    return true;
  } catch {
    return false;
  }
}

/** Clear the current record and old key-only formats after a definitive outcome. */
export function clearPendingMobileOrder(effectiveKey: string): boolean {
  try {
    globalThis.localStorage.removeItem(pendingKey(effectiveKey));
    for (const key of oldKeys(effectiveKey)) globalThis.localStorage.removeItem(key);
    return true;
  } catch {
    return false;
  }
}

/** Serialize keyed submits across tabs; unsupported browsers fail closed. */
export function withMobileOrderSubmissionLock<T>(
  effectiveKey: string,
  callback: () => Promise<T>,
): Promise<T> {
  try {
    const locks = (globalThis.navigator as Navigator & { locks?: MobileOrderLockManager } | undefined)?.locks;
    if (!locks || typeof locks.request !== 'function') {
      const error = new Error('Este navegador no puede proteger el envío de pedidos entre pestañas. Actualízalo para continuar.');
      (error as Error & { code?: string }).code = 'mobile_order_lock_unavailable';
      return Promise.reject(error);
    }
    return locks.request(`${LOCK_PREFIX}${effectiveKey}`, callback) as Promise<T>;
  } catch {
    const error = new Error('No se pudo proteger el envío del pedido entre pestañas. No se envió.');
    (error as Error & { code?: string }).code = 'mobile_order_lock_unavailable';
    return Promise.reject(error);
  }
}

/** Returns true when this call began before a prior locked call completed. */
export function hasMobileOrderCompletedSince(
  effectiveKey: string,
  invocationStartedAt: number,
): boolean | null {
  try {
    const stored = globalThis.localStorage.getItem(completedKey(effectiveKey));
    if (stored === null) return false;
    const completedAt = Number(stored);
    return Number.isFinite(completedAt) ? completedAt >= invocationStartedAt : null;
  } catch {
    return null;
  }
}

/** Store a PII-free fence so callers queued before success cannot start a second order. */
export function markMobileOrderCompleted(effectiveKey: string, completedAt: number): boolean {
  try {
    globalThis.localStorage.setItem(completedKey(effectiveKey), String(completedAt));
    return true;
  } catch {
    return false;
  }
}

export function mobileOrderTimestamp(): number {
  const performanceApi = globalThis.performance;
  return performanceApi && Number.isFinite(performanceApi.timeOrigin)
    ? performanceApi.timeOrigin + performanceApi.now()
    : Date.now();
}
