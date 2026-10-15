import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { PricePoint } from "../api/types";

const REFRESH_MS = 30_000;

/** Today's price in about 75 points for each stock, for the small charts. */
export function useSparklines(symbols: string[]): Record<string, PricePoint[]> {
  const [lines, setLines] = useState<Record<string, PricePoint[]>>({});
  const key = [...new Set(symbols)].sort().join(",");
  useEffect(() => {
    if (!key) return;
    let cancelled = false;
    const load = () => api.sparklines(key.split(",")).then((data) => !cancelled && setLines(data)).catch(() => undefined);
    load();
    const timer = window.setInterval(load, REFRESH_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [key]);
  return lines;
}
