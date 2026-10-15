import { useCallback, useEffect, useState } from "react";

import { api } from "../api/client";
import type { StockNews } from "../api/types";

const REFRESH_MS = 5 * 60 * 1000;

export interface NewsState {
  stocks: Record<string, StockNews>;
  loading: boolean;
  error: string;
  refresh: () => void;
}

/** Latest headlines for the given stocks, refreshed every five minutes. */
export function useNews(symbols: string[]): NewsState {
  const key = symbols.join(",");
  const [stocks, setStocks] = useState<Record<string, StockNews>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!key) return;
    let cancelled = false;
    setLoading(true);
    setError("");
    api.news(key.split(","))
      .then((response) => !cancelled && setStocks(response.stocks))
      .catch((err) => !cancelled && setError(err instanceof Error ? err.message : "Could not load the news."))
      .finally(() => !cancelled && setLoading(false));
    const timer = window.setTimeout(() => setTick((t) => t + 1), REFRESH_MS);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [key, tick]);

  const refresh = useCallback(() => setTick((t) => t + 1), []);
  return { stocks, loading, error, refresh };
}
