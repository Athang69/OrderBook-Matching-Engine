import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { Explanation } from "../api/types";

const REFRESH_MS = 120_000;

/**
 * Why a stock moved on a day (`date` null means its latest trading day, refreshed every two minutes).
 * The first answer for a stock takes a second or two: the server downloads its history and searches the news.
 */
export function useExplanation(symbol: string, date: string | null) {
  const [data, setData] = useState<Explanation | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!symbol) return;
    let cancelled = false;
    const load = (first: boolean) => {
      if (first) {
        setLoading(true);
        setError("");
      }
      api.explain(symbol, date)
        .then((answer) => !cancelled && setData(answer))
        .catch((err) => !cancelled && first && setError(err instanceof Error ? err.message : "Could not explain the move."))
        .finally(() => !cancelled && first && setLoading(false));
    };
    load(true);
    const timer = date ? undefined : window.setInterval(() => load(false), REFRESH_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [symbol, date]);

  const current = data && data.symbol === symbol && (date === null || data.date === date) ? data : null;
  return { data: current, loading, error };
}
