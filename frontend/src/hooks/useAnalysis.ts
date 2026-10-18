import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { Analysis } from "../api/types";

/** Claude's analysis of a stock's move on a day; asked for once the day is known. Takes 30 to 60 seconds. */
export function useAnalysis(symbol: string, date: string | null) {
  const [data, setData] = useState<Analysis | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!symbol || !date) return;
    let cancelled = false;
    setLoading(true);
    setError("");
    api.analysis(symbol, date)
      .then((answer) => !cancelled && setData(answer))
      .catch((err) => !cancelled && setError(err instanceof Error ? err.message : "Claude could not write the analysis."))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [symbol, date]);

  const current = data && data.symbol === symbol && data.date === date ? data : null;
  return { data: current, loading: loading && !current, error };
}
