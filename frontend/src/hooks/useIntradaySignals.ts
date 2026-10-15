import { useEffect, useRef, useState } from "react";

import { api } from "../api/client";
import type { Confidences, IntradayRecommendation } from "../api/types";

export interface IntradayQuery {
  symbols: string[];
  confidences: Confidences;
  budget: number;
}

export interface IntradayState {
  data: IntradayRecommendation | null;
  error: string;
  /** Browser-measured time for the last request, in milliseconds. */
  roundTripMs: number | null;
  updatedAt: number | null;
}

/**
 * Asks for intraday signals every `intervalMs` while `live` is on. A request is skipped if the previous
 * one has not answered yet, so a slow moment never piles up requests.
 */
export function useIntradaySignals(query: IntradayQuery | null, live: boolean, intervalMs = 1000): IntradayState {
  const [state, setState] = useState<IntradayState>({ data: null, error: "", roundTripMs: null, updatedAt: null });
  const inFlight = useRef(false);
  const key = query ? `${query.symbols.join(",")}|${JSON.stringify(query.confidences)}|${query.budget}` : "";

  useEffect(() => {
    if (!query) return;
    let cancelled = false;
    const run = async () => {
      if (inFlight.current) return;
      inFlight.current = true;
      const started = performance.now();
      try {
        const data = await api.recommendIntraday(query.symbols, query.confidences, query.budget);
        if (!cancelled) setState({ data, error: "", roundTripMs: performance.now() - started, updatedAt: Date.now() });
      } catch (err) {
        if (!cancelled) setState((prev) => ({ ...prev, error: err instanceof Error ? err.message : "No answer from the server." }));
      } finally {
        inFlight.current = false;
      }
    };
    run();
    if (!live) return () => { cancelled = true; };
    const timer = window.setInterval(run, intervalMs);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, live, intervalMs]);

  return state;
}
