import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { fetchApi, ApiError } from '@restaurantos/api-client';

// ---------------------------------------------------------------------------
// Canonical session types (BA-002)
// ---------------------------------------------------------------------------

export interface SessionRole {
  id: string;
  name: string;
  scope: string;
  branch_id: string | null;
}

export interface SessionScope {
  level: 'organization' | 'branch';
  assigned_branch_id: string | null;
  allowed_branch_ids: string[];
}

export interface SessionBusinessUnit {
  id: string;
  name: string;
  code: string;
  unit_type: string;
}

export interface DeliveryTier {
  id: string;
  name: string;
  fee_cents: number;
  is_default_web: boolean;
}

export interface SessionActiveBranch {
  id: string;
  name: string;
  code: string;
  timezone: string;
  status: string;
  business_unit: SessionBusinessUnit;
  legal_entity: { id: string; name: string };
  warehouse: { id: string; name: string } | null;
  delivery_fee_enabled?: boolean;
  delivery_tiers?: DeliveryTier[];
  free_delivery_min_cents?: number | null;
}

export interface PosSession {
  user: {
    id: string;
    email: string;
    display_name: string;
    status: string;
  };
  roles: SessionRole[];
  permissions: string[];
  scope: SessionScope;
  active_branch: SessionActiveBranch | null;
}

// ---------------------------------------------------------------------------
// Canonical session provider (BA-002)
// ---------------------------------------------------------------------------

type SessionState =
  | { status: 'loading' }
  | { status: 'ok'; session: PosSession }
  | { status: 'error'; message: string; statusCode: number };

interface SessionContextValue {
  state: SessionState;
  session: PosSession | null;
  hasPermission: (code: string) => boolean;
  reload: () => void;
  selectBranch: (branchId: string) => Promise<void>;
}

const SessionContext = createContext<SessionContextValue | null>(null);

function redirectToLogin() {
  const isDev =
    window.location.hostname === 'localhost' ||
    window.location.hostname === '127.0.0.1' ||
    (window.location.port !== '' &&
      window.location.port !== '80' &&
      window.location.port !== '443');
  const loginUrl = isDev ? 'http://localhost:3002/admin/login' : '/admin/login';
  window.location.href = loginUrl;
}

export function setPosBranchId(branchId: string) {
  if (!branchId) return;
  localStorage.setItem('pos_branch_id', branchId);
  localStorage.setItem('admin_branch_id', branchId);
}

/**
 * Clear all POS session artifacts. Called on logout or 401.
 */
export function clearPosSession() {
  localStorage.removeItem('pos_branch_id');
  localStorage.removeItem('admin_branch_id');
  localStorage.removeItem('auth_token');
  localStorage.removeItem('user');
  sessionStorage.removeItem('auth_token');
  sessionStorage.removeItem('pos_pending_checkout_v1');
  sessionStorage.removeItem('pos_offline_cash_grant');
  sessionStorage.removeItem('pos_offline_cash_grant_expires_at');
  sessionStorage.removeItem('pos_offline_cash_grant_branch_id');
  sessionStorage.removeItem('pos_offline_cash_grant_source_device_id');
  sessionStorage.removeItem('pos_offline_cash_grant_gateway_url');
}

/**
 * Returns the branch_id previously validated and written by PosSessionProvider.
 * Does NOT read localStorage.user, assigned_branch_id, or role names.
 * If no validated branch_id exists, returns empty string.
 */
export function resolvePosBranchId(): string {
  return localStorage.getItem('pos_branch_id') || '';
}

async function fetchCanonicalSession(branchId?: string): Promise<PosSession> {
  const endpoint = branchId
    ? `/auth/session?branch_id=${encodeURIComponent(branchId)}`
    : '/auth/session';
  return fetchApi<PosSession>(endpoint);
}

export function PosSessionProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<SessionState>({ status: 'loading' });

  const applySession = useCallback((session: PosSession) => {
    // Apply the canonical active_branch before publishing the session,
    // so any stale local branch_id is replaced unconditionally.
    if (session.active_branch?.id) {
      setPosBranchId(session.active_branch.id);
    }
    setState({ status: 'ok', session });
  }, []);

  const loadSession = useCallback(async () => {
    setState({ status: 'loading' });
    try {
      applySession(await fetchCanonicalSession());
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 401) {
          clearPosSession();
          redirectToLogin();
          return;
        }
        setState({
          status: 'error',
          message:
            err.status === 403
              ? 'Tu cuenta no tiene acceso a esta operación.'
              : err.message,
          statusCode: err.status,
        });
        return;
      }
      setState({
        status: 'error',
        message: 'No se pudo conectar con el servidor.',
        statusCode: 0,
      });
    }
  }, [applySession]);

  const selectBranch = useCallback(
    async (branchId: string) => {
      if (state.status !== 'ok' || state.session.scope.level !== 'organization') {
        throw new ApiError(403, 'permission_denied', 'No puedes cambiar de sucursal.');
      }
      if (!state.session.scope.allowed_branch_ids.includes(branchId)) {
        throw new ApiError(403, 'permission_denied', 'La sucursal no está autorizada.');
      }

      // The current canonical session stays active if validation fails.
      let nextSession: PosSession;
      try {
        nextSession = await fetchCanonicalSession(branchId);
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) {
          clearPosSession();
          redirectToLogin();
        }
        throw error;
      }
      if (nextSession.active_branch?.id !== branchId) {
        throw new ApiError(
          409,
          'branch_context_mismatch',
          'El servidor no confirmó la sucursal seleccionada.',
        );
      }
      applySession(nextSession);
    },
    [applySession, state],
  );

  useEffect(() => {
    void loadSession();
  }, [loadSession]);

  const session = state.status === 'ok' ? state.session : null;

  const hasPermission = useCallback(
    (code: string) => {
      if (state.status !== 'ok') return false;
      return state.session.permissions.includes(code);
    },
    [state],
  );

  const value: SessionContextValue = {
    state,
    session,
    hasPermission,
    reload: () => void loadSession(),
    selectBranch,
  };
  return React.createElement(SessionContext.Provider, { value }, children);
}

export function usePosSession(): SessionContextValue {
  const ctx = useContext(SessionContext);
  if (!ctx) {
    throw new Error('usePosSession must be used within a PosSessionProvider');
  }
  return ctx;
}
