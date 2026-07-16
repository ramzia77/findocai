import { useCallback, useEffect, useState } from "react";
import { getHealth } from "../api/client";
import { useSettings } from "../context/SettingsContext";
import type { HealthResponse } from "../api/types";

const POLL_INTERVAL_MS = 20_000;

interface HealthState {
  health: HealthResponse | null;
  error: string | null;
  loading: boolean;
  refresh: () => void;
}

export function useHealth(): HealthState {
  const { apiBaseUrl, apiKey } = useSettings();
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);

  const refresh = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    getHealth({ baseUrl: apiBaseUrl, apiKey })
      .then((result) => {
        if (cancelled) return;
        setHealth(result);
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setHealth(null);
        setError(err instanceof Error ? err.message : "Could not reach the API");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    const interval = setInterval(refresh, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [apiBaseUrl, apiKey, nonce, refresh]);

  return { health, error, loading, refresh };
}
