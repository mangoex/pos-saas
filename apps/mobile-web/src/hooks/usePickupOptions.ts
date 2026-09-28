import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { fetchPickupOptions } from '../api';
import type { PickupOptions } from '../types';
import { createPickupOptionsLoader } from '../utils/pickupSchedule';

export function usePickupOptions(branchKey: string, enabled: boolean) {
  const [result, setResult] = useState<{ key: string; data: PickupOptions } | null>(null);
  const [status, setStatus] = useState({ key: '', loading: false, error: '' });
  const revision = useRef(0);
  const loader = useMemo(() => createPickupOptionsLoader(fetchPickupOptions,
    (key, data) => setResult({ key, data })), [branchKey]);
  const refresh = useCallback(async () => {
    const request = ++revision.current;
    setStatus({ key: branchKey, loading: true, error: '' });
    try {
      const data = await loader.load(branchKey);
      if (request === revision.current) setStatus({ key: branchKey, loading: false, error: '' });
      return data;
    } catch (error) {
      if (request === revision.current) setStatus({ key: branchKey, loading: false,
        error: 'No pudimos verificar los horarios. Vuelve a intentarlo.' });
      throw error;
    }
  }, [branchKey, loader]);

  useEffect(() => {
    if (!enabled) return;
    const refreshVisible = () => {
      if (document.visibilityState !== 'hidden') void refresh().catch(() => {});
    };
    refreshVisible();
    const interval = window.setInterval(refreshVisible, 60_000);
    window.addEventListener('focus', refreshVisible);
    document.addEventListener('visibilitychange', refreshVisible);
    return () => {
      ++revision.current;
      loader.dispose();
      window.clearInterval(interval);
      window.removeEventListener('focus', refreshVisible);
      document.removeEventListener('visibilitychange', refreshVisible);
    };
  }, [enabled, loader, refresh]);

  return {
    options: result?.key === branchKey ? result.data : null,
    loading: status.key !== branchKey || status.loading,
    error: status.key === branchKey ? status.error : '',
    refresh,
  };
}
