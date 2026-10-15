import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { TopOfBook } from "../api/types";

/** Your orders waiting in the matching engine for one stock, refreshed every two seconds and on demand. */
export function useOrderBook(symbol: string, refreshKey: unknown) {
  const [book, setBook] = useState<TopOfBook | null>(null);
  useEffect(() => {
    if (!symbol) return;
    let cancelled = false;
    const load = () => api.orderbook(symbol).then((data) => !cancelled && setBook(data)).catch(() => undefined);
    load();
    const timer = window.setInterval(load, 2000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [symbol, refreshKey]);
  return book?.symbol === symbol ? book : null;
}
