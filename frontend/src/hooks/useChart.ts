import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { Bar, Chart, ChartInterval, ChartRange, Quote } from "../api/types";

function refreshMs(interval: ChartInterval): number {
  if (interval === "1m" || interval === "2m") return 60_000;
  if (interval === "5m") return 300_000;
  if (interval === "15m" || interval === "30m") return 900_000;
  return 3_600_000;
}

export function useChart(symbol: string, range: ChartRange, interval: ChartInterval, quote: Quote | undefined) {
  const [chart, setChart] = useState<Chart | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!symbol) return;
    let cancelled = false;
    const load = (first: boolean) => {
      if (first) setLoading(true);
      api.chart(symbol, range, interval)
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
    const timer = window.setInterval(() => load(false), refreshMs(interval));
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [symbol, range, interval]);

  let bars: Bar[] = chart && chart.symbol === symbol && chart.range === range ? chart.bars : [];
  const ltp = quote?.ltp;
  const at = quote?.tick_time ?? quote?.polled_at;
  if (range === "1d" && interval === "1m" && bars.length && ltp != null && at != null) {
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
