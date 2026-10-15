import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { SymbolList } from "../api/types";

/** Every NSE stock that can be searched, loaded once. */
export function useSymbols() {
  const [list, setList] = useState<SymbolList | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let cancelled = false;
    const load = () =>
      api.symbols()
        .then((data) => !cancelled && setList(data))
        .catch((err) => {
          if (cancelled) return;
          setError(err instanceof Error ? err.message : "Could not load the list of stocks.");
          window.setTimeout(load, 3000);
        });
    load();
    return () => {
      cancelled = true;
    };
  }, []);
  return { list, error };
}
