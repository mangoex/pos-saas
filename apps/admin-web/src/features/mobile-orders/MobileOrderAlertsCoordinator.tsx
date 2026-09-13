import React, { useCallback, useEffect, useRef, useState } from 'react';
import { fetchApi } from '@restaurantos/api-client';
import { Bell, BellRing } from 'lucide-react';
import {
  reconcileMobileOrderAlerts,
  type MobileOrderAlertCandidate,
  type MobileOrderAlertState,
} from './mobileOrderAlerts';

interface MobileOrderAlertsCoordinatorProps {
  branchId: string;
}

type SoundState = 'inactive' | 'activating' | 'ready' | 'suspended' | 'unsupported' | 'error';

type BrowserAudioContext = AudioContext & { close: () => Promise<void> };

type AlertSignal = {
  result: 'reconciled' | 'poll_error' | 'audio_unavailable';
  detected?: number;
  deduplicated?: number;
  reason?: string;
};

const emitAlertSignal = (detail: AlertSignal): void => {
  window.dispatchEvent(new CustomEvent<AlertSignal>('restaurantos:mobile-order-alert', { detail }));
};

const getAudioContextConstructor = (): typeof AudioContext | null => {
  const browserWindow = window as typeof window & { webkitAudioContext?: typeof AudioContext };
  return window.AudioContext || browserWindow.webkitAudioContext || null;
};

export const MobileOrderAlertsCoordinator: React.FC<MobileOrderAlertsCoordinatorProps> = ({
  branchId,
}) => {
  const audioContextRef = useRef<BrowserAudioContext | null>(null);
  const alertStateRef = useRef<MobileOrderAlertState | null>(null);
  const requestSequenceRef = useRef(0);
  const requestInFlightRef = useRef(false);
  const requestAbortRef = useRef<AbortController | null>(null);
  const [soundState, setSoundState] = useState<SoundState>('inactive');
  const [pendingVisualAlertIds, setPendingVisualAlertIds] = useState<string[]>([]);
  const [pollDegraded, setPollDegraded] = useState(false);

  const ensureAudioReady = useCallback(async (): Promise<BrowserAudioContext | null> => {
    const AudioContextConstructor = getAudioContextConstructor();
    if (!AudioContextConstructor) {
      setSoundState('unsupported');
      emitAlertSignal({ result: 'audio_unavailable', reason: 'unsupported' });
      return null;
    }
    setSoundState('activating');
    try {
      const ctx = audioContextRef.current || new AudioContextConstructor();
      audioContextRef.current = ctx as BrowserAudioContext;
      ctx.onstatechange = () => {
        setSoundState(ctx.state === 'running' ? 'ready' : 'suspended');
      };
      if (ctx.state !== 'running') {
        await ctx.resume();
      }
      if (ctx.state === 'running') {
        setSoundState('ready');
        return ctx as BrowserAudioContext;
      }
      setSoundState('suspended');
      emitAlertSignal({ result: 'audio_unavailable', reason: ctx.state });
      return null;
    } catch {
      setSoundState('error');
      emitAlertSignal({ result: 'audio_unavailable', reason: 'resume_error' });
      return null;
    }
  }, []);

  const playNewOrderSound = useCallback(async (): Promise<boolean> => {
    const ctx = await ensureAudioReady();
    if (!ctx || ctx.state !== 'running') return false;
    try {
      const now = ctx.currentTime;
      [659.25, 830.61, 987.77].forEach((frequency, index) => {
        const startsAt = now + index * 0.16;
        const oscillator = ctx.createOscillator();
        const gain = ctx.createGain();
        oscillator.type = 'triangle';
        oscillator.frequency.setValueAtTime(frequency, startsAt);
        gain.gain.setValueAtTime(0.001, startsAt);
        gain.gain.linearRampToValueAtTime(0.7, startsAt + 0.03);
        gain.gain.exponentialRampToValueAtTime(0.001, startsAt + 0.5);
        oscillator.connect(gain);
        gain.connect(ctx.destination);
        oscillator.start(startsAt);
        oscillator.stop(startsAt + 0.55);
      });
      setSoundState('ready');
      return true;
    } catch {
      setSoundState('error');
      return false;
    }
  }, [ensureAudioReady]);

  const poll = useCallback(async () => {
    if (!branchId || requestInFlightRef.current) return;
    requestInFlightRef.current = true;
    const sequence = ++requestSequenceRef.current;
    const controller = new AbortController();
    requestAbortRef.current = controller;
    const timeout = window.setTimeout(() => controller.abort(), 6_500);
    try {
      const currentState = alertStateRef.current;
      const since = currentState?.branchId === branchId && currentState.cursorCreatedAt
        ? `&since_utc=${encodeURIComponent(currentState.cursorCreatedAt)}`
        : '';
      const result = await fetchApi<{ items: MobileOrderAlertCandidate[] }>(
        `/orders/public-intent-alerts?branch_id=${encodeURIComponent(branchId)}${since}`,
        { signal: controller.signal, cache: 'no-store' },
      );
      if (sequence !== requestSequenceRef.current) return;
      const reconciliation = reconcileMobileOrderAlerts(
        alertStateRef.current,
        branchId,
        Array.isArray(result?.items) ? result.items : [],
      );
      alertStateRef.current = reconciliation.state;
      setPollDegraded(false);
      emitAlertSignal({
        result: 'reconciled',
        detected: reconciliation.newOrderIds.length,
        deduplicated: Math.max(0, (result?.items?.length ?? 0) - reconciliation.newOrderIds.length),
      });
      if (reconciliation.newOrderIds.length > 0) {
        setPendingVisualAlertIds((current) => [
          ...new Set([...current, ...reconciliation.newOrderIds]),
        ]);
        void playNewOrderSound();
      }
    } catch {
      if (sequence === requestSequenceRef.current) {
        setPollDegraded(true);
        emitAlertSignal({
          result: 'poll_error',
          reason: controller.signal.aborted ? 'timeout' : 'request_error',
        });
      }
    } finally {
      window.clearTimeout(timeout);
      if (sequence === requestSequenceRef.current) {
        requestInFlightRef.current = false;
        requestAbortRef.current = null;
      }
    }
  }, [branchId, playNewOrderSound]);

  useEffect(() => {
    requestAbortRef.current?.abort();
    requestSequenceRef.current += 1;
    requestInFlightRef.current = false;
    alertStateRef.current = null;
    setPendingVisualAlertIds([]);
    void poll();
    const interval = window.setInterval(() => void poll(), 8_000);
    return () => {
      window.clearInterval(interval);
      requestAbortRef.current?.abort();
    };
  }, [branchId, poll]);

  useEffect(() => {
    const onVisibilityChange = () => {
      if (document.visibilityState !== 'visible') return;
      if (audioContextRef.current?.state !== 'running' && soundState === 'ready') {
        setSoundState('suspended');
      }
      void poll();
    };
    document.addEventListener('visibilitychange', onVisibilityChange);
    return () => document.removeEventListener('visibilitychange', onVisibilityChange);
  }, [poll, soundState]);

  useEffect(() => () => {
    requestSequenceRef.current += 1;
    requestAbortRef.current?.abort();
    const ctx = audioContextRef.current;
    audioContextRef.current = null;
    if (ctx) {
      ctx.onstatechange = null;
      void ctx.close().catch(() => undefined);
    }
  }, []);

  const handleSoundButton = async () => {
    const played = await playNewOrderSound();
    if (played) setPendingVisualAlertIds([]);
  };

  const pendingVisualAlerts = pendingVisualAlertIds.length;
  const needsAttention = pendingVisualAlerts > 0 || soundState !== 'ready' || pollDegraded;
  const label = pollDegraded
    ? 'Alertas de pedidos sin conexión. Reintentando.'
    : pendingVisualAlerts > 0
    ? `${pendingVisualAlerts} alerta${pendingVisualAlerts === 1 ? '' : 's'} de pedido web pendiente${pendingVisualAlerts === 1 ? '' : 's'} de confirmar.`
    : soundState === 'ready'
      ? 'Alarma de pedidos lista'
      : 'Toca para activar la alarma de pedidos';

  return (
    <button
      type="button"
      onClick={() => void handleSoundButton()}
      aria-live="polite"
      aria-label={label}
      title={label}
      style={{
        position: 'fixed',
        right: 14,
        bottom: 88,
        zIndex: 55,
        border: needsAttention ? '1px solid #fb923c' : '1px solid #34d399',
        backgroundColor: needsAttention ? '#fff7ed' : '#ecfdf5',
        color: needsAttention ? '#9a3412' : '#065f46',
        borderRadius: 999,
        padding: '9px 12px',
        display: 'flex',
        alignItems: 'center',
        gap: 7,
        fontSize: '0.75rem',
        fontWeight: 800,
        boxShadow: '0 4px 14px rgba(15, 23, 42, 0.18)',
        cursor: 'pointer',
      }}
    >
      {pendingVisualAlerts > 0 ? <BellRing size={17} /> : <Bell size={17} />}
      <span>{pollDegraded ? 'Alertas sin conexión' : pendingVisualAlerts > 0 ? `Nuevo pedido (${pendingVisualAlerts})` : soundState === 'ready' ? 'Alarma lista' : 'Activar alarma'}</span>
    </button>
  );
};
