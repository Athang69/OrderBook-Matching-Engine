import { useEffect, useRef, useState } from "react";

import type { Instrument, MarketState, SimStatus, Trade } from "./api";

const MAX_TAPE = 40;

interface HelloMessage {
  type: "hello";
  instruments: Instrument[];
  sim: SimStatus;
}

interface UpdateMessage {
  type: "update";
  symbols: Record<string, MarketState>;
  trades: Trade[];
  sim: SimStatus;
}

export interface MarketData {
  connected: boolean;
  instruments: Instrument[];
  market: Record<string, MarketState>;
  /** Most recent trades per symbol, newest first. */
  tape: Record<string, Trade[]>;
  sim: SimStatus | null;
}

/** Keeps a live copy of every order book and the recent trades, fed by the WebSocket stream. */
export function useMarketData(): MarketData {
  const [data, setData] = useState<MarketData>({ connected: false, instruments: [], market: {}, tape: {}, sim: null });
  const retry = useRef<number>();

  useEffect(() => {
    let socket: WebSocket | null = null;
    let closed = false;

    const connect = () => {
      const scheme = window.location.protocol === "https:" ? "wss" : "ws";
      socket = new WebSocket(`${scheme}://${window.location.host}/v1/stream/marketdata`);

      socket.onmessage = (event) => {
        const message = JSON.parse(event.data) as HelloMessage | UpdateMessage;
        if (message.type === "hello") {
          const market: Record<string, MarketState> = {};
          for (const instrument of message.instruments) market[instrument.symbol] = instrument.market;
          setData((prev) => ({ ...prev, connected: true, instruments: message.instruments, market, sim: message.sim }));
          return;
        }
        setData((prev) => {
          let tape = prev.tape;
          if (message.trades.length > 0) {
            tape = { ...prev.tape };
            for (const trade of message.trades) {
              tape[trade.symbol] = [trade, ...(tape[trade.symbol] ?? [])].slice(0, MAX_TAPE);
            }
          }
          return { ...prev, market: { ...prev.market, ...message.symbols }, tape, sim: message.sim };
        });
      };

      socket.onclose = () => {
        if (closed) return;
        setData((prev) => ({ ...prev, connected: false }));
        retry.current = window.setTimeout(connect, 1000);
      };
    };

    connect();
    return () => {
      closed = true;
      window.clearTimeout(retry.current);
      socket?.close();
    };
  }, []);

  return data;
}
