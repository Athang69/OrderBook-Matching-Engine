import { useEffect, useRef, useState } from "react";

import { api } from "../api/client";
import type { MarketState, PricePoint } from "../api/types";

const MAX_POINTS = 1800; // 30 minutes at one point a second

/**
 * Price once a second for every stock: what the server has recorded so far, then one point a second
 * from the live market data. Feeds the main chart and every sparkline from one place.
 */
export function usePriceHistory(market: Record<string, MarketState>): Record<string, PricePoint[]> {
  const [history, setHistory] = useState<Record<string, PricePoint[]>>({});
  const latest = useRef(market);
  latest.current = market;
  const ready = Object.keys(market).length > 0;

  useEffect(() => {
    if (!ready) return;
    let cancelled = false;
    api.histories().then((loaded) => !cancelled && setHistory((current) => merge(loaded, current))).catch(() => undefined);
    const timer = window.setInterval(() => {
      const now = Math.floor(Date.now() / 1000);
      setHistory((current) => {
        const next = { ...current };
        for (const [symbol, state] of Object.entries(latest.current)) {
          if (state.ltp == null) continue;
          const points = next[symbol] ?? [];
          if (points.length && points[points.length - 1][0] >= now) continue;
          next[symbol] = [...points, [now, state.ltp] as PricePoint].slice(-MAX_POINTS);
        }
        return next;
      });
    }, 1000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [ready]);

  return history;
}

/** Server history first, then any points this page already recorded after it. */
function merge(loaded: Record<string, PricePoint[]>, current: Record<string, PricePoint[]>) {
  const out: Record<string, PricePoint[]> = { ...current };
  for (const [symbol, points] of Object.entries(loaded)) {
    const last = points.length ? points[points.length - 1][0] : 0;
    out[symbol] = [...points, ...(current[symbol] ?? []).filter((p) => p[0] > last)].slice(-MAX_POINTS);
  }
  return out;
}
