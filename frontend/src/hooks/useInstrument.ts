import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { Instrument, InstrumentDetail, SymbolRow } from "../api/types";

/** A stock's rules for the day from the stock list, so its page opens at once. */
export function instrumentOf(row: SymbolRow, dataDate: string): Instrument {
  const [symbol, name, series, close, tick, band_pct, lower_band, upper_band] = row;
  return { symbol, name, series, close, tick, band_pct, lower_band, upper_band, volume: 0, avg_trade_qty: 0, data_date: dataDate };
}

/** Asks the server for one stock when it is opened: this makes its prices live, and brings the first quote. */
export function useInstrument(symbol: string) {
  const [detail, setDetail] = useState<InstrumentDetail | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!symbol) return;
    let cancelled = false;
    setError("");
    api.instrument(symbol)
      .then((data) => !cancelled && setDetail(data))
      .catch((err) => !cancelled && setError(err instanceof Error ? err.message : "Could not load the stock."));
    return () => {
      cancelled = true;
    };
  }, [symbol]);
  return { detail: detail?.symbol === symbol ? detail : null, error };
}
