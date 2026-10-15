import { useCallback, useEffect, useState } from "react";

const KEY = "orderbook-watchlist";
const MAX = 30;

/** Your watchlist, remembered in this browser when storage is available. */
export function useWatchlist(defaults: string[] | undefined) {
  const [list, setList] = useState<string[] | null>(() => {
    try {
      const saved = localStorage.getItem(KEY);
      return saved ? (JSON.parse(saved) as string[]) : null;
    } catch {
      return null;
    }
  });

  useEffect(() => {
    if (list === null && defaults) setList(defaults);
  }, [list, defaults]);

  useEffect(() => {
    if (list === null) return;
    try {
      localStorage.setItem(KEY, JSON.stringify(list));
    } catch {
      // Storage can be blocked; the watchlist still works for this visit.
    }
  }, [list]);

  const toggle = useCallback((symbol: string) => {
    setList((current) => {
      const now = current ?? [];
      return now.includes(symbol) ? now.filter((s) => s !== symbol) : [...now, symbol].slice(-MAX);
    });
  }, []);

  return { watchlist: list ?? defaults ?? [], toggle };
}
