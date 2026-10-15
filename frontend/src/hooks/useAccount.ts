import { useCallback, useEffect, useState } from "react";

import { api } from "../api/client";
import type { Order, Portfolio } from "../api/types";

const REFRESH_MS = 1500;

/** The user's balances and orders, fetched over REST every 1.5 seconds and after each action. */
export function useAccount(user: string | undefined) {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [orders, setOrders] = useState<Order[]>([]);

  const refresh = useCallback(async () => {
    if (!user) return;
    try {
      const [nextPortfolio, nextOrders] = await Promise.all([api.portfolio(user), api.orders()]);
      setPortfolio(nextPortfolio);
      setOrders(nextOrders);
    } catch {
      // The header shows the connection state; keep the last known values.
    }
  }, [user]);

  useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [refresh]);

  return { portfolio, orders, refresh };
}
