import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { Bar, Chart, ChartRange, Quote } from "../api/types";

const REFRESH_MS: Record<ChartRange, number> = { "1d": 60_000, "5d": 300_000, "1mo": 900_000, "6mo": 3_600_000, "1y": 3_600_000, "5y": 3_600_000 };

/**
 * Price bars for the chosen range. Today's chart is refreshed every minute and its last bar follows the
 * live price in between, so the line moves as the stock trades.
 */
export function useChart(symbol: string, range: ChartRange, quote: Quote | undefined) {
  const [chart, setChart] = useState<Chart | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!symbol) return;
    let cancelled = false;
    const load = (first: boolean) => {
      if (first) setLoading(true);
      api.chart(symbol, range)
        .then((data) => {
          if (cancelled) return;
          setChart(data);
          setError("");
        })
        .catch((err) => !cancelled && setError(err instanceof Error ? err.message : "Could not load the chart."))
        .finally(() => !cancelled && setLoading(false));
    };
    setChart(null);
    load(true);
    const timer = window.setInterval(() => load(false), REFRESH_MS[range]);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [symbol, range]);

  let bars: Bar[] = chart && chart.symbol === symbol && chart.range === range ? chart.bars : [];
  const ltp = quote?.ltp;
  const at = quote?.tick_time ?? quote?.polled_at;
  if (range === "1d" && bars.length && ltp != null && at != null) {
    const minute = Math.floor(at / 60) * 60;
    const last = bars[bars.length - 1];
    if (minute === last[0]) {
      bars = [...bars.slice(0, -1), [last[0], last[1], Math.max(last[2], ltp), Math.min(last[3], ltp), ltp, last[5]]];
    } else if (minute > last[0] && minute - last[0] < 3600) {
      bars = [...bars, [minute, ltp, ltp, ltp, ltp, 0]];
    }
  }
  return { bars, prevClose: chart?.prev_close ?? null, loading, error };
}
