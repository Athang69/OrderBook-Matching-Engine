import { useEffect, useRef, useState } from "react";

import type { IndexQuote, Quote, Status, Trade } from "../api/types";

const MAX_TAPE = 40;

type Message =
  | { type: "hello"; status: Status; indices: IndexQuote[] }
  | { type: "snapshot"; quotes: Record<string, Quote>; trades: Record<string, Trade[]> }
  | { type: "update"; quotes: Record<string, Quote>; trades: Trade[]; indices: IndexQuote[]; status?: Status };

export interface LiveMarket {
  connected: boolean;
  status: Status | null;
  quotes: Record<string, Quote>;
  /** Most recent real trades per stock, newest first. */
  tape: Record<string, Trade[]>;
  indices: Record<string, IndexQuote>;
}

/**
 * Live quotes and trades for the stocks in `symbols`, pushed over the WebSocket. The list is sent to the
 * server whenever it changes, and again after a reconnect.
 */
export function useLiveMarket(symbols: string[]): LiveMarket {
  const [data, setData] = useState<LiveMarket>({ connected: false, status: null, quotes: {}, tape: {}, indices: {} });
  const socket = useRef<WebSocket | null>(null);
  const wanted = useRef(symbols);
  const key = [...new Set(symbols)].sort().join(",");
  wanted.current = symbols;

  useEffect(() => {
    let closed = false;
    let retry: number | undefined;

    const connect = () => {
      const scheme = window.location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${scheme}://${window.location.host}/v1/stream/marketdata`);
      socket.current = ws;
      ws.onopen = () => ws.send(JSON.stringify({ subscribe: [...new Set(wanted.current)] }));
      ws.onmessage = (event) => {
        const message = JSON.parse(event.data) as Message;
        setData((prev) => apply(prev, message));
      };
      ws.onclose = () => {
        if (closed) return;
        setData((prev) => ({ ...prev, connected: false }));
        retry = window.setTimeout(connect, 1500);
      };
    };

    connect();
    return () => {
      closed = true;
      window.clearTimeout(retry);
      socket.current?.close();
    };
  }, []);

  useEffect(() => {
    const ws = socket.current;
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ subscribe: key ? key.split(",") : [] }));
  }, [key]);

  return data;
}

function apply(prev: LiveMarket, message: Message): LiveMarket {
  if (message.type === "hello") {
    return { ...prev, connected: true, status: message.status, indices: byName(prev.indices, message.indices) };
  }
  if (message.type === "snapshot") {
    const tape = { ...prev.tape };
    for (const [symbol, trades] of Object.entries(message.trades)) {
      const known = new Set((tape[symbol] ?? []).map((t) => t.id));
      tape[symbol] = [...(tape[symbol] ?? []), ...trades.filter((t) => !known.has(t.id))]
        .sort((a, b) => b.id - a.id).slice(0, MAX_TAPE);
    }
    return { ...prev, quotes: { ...prev.quotes, ...message.quotes }, tape };
  }
  let tape = prev.tape;
  if (message.trades.length > 0) {
    tape = { ...prev.tape };
    for (const trade of message.trades) {  // oldest first, so each newer trade goes on top
      tape[trade.symbol] = [trade, ...(tape[trade.symbol] ?? [])].slice(0, MAX_TAPE);
    }
  }
  return {
    ...prev,
    connected: true,
    quotes: Object.keys(message.quotes).length ? { ...prev.quotes, ...message.quotes } : prev.quotes,
    tape,
    indices: message.indices.length ? byName(prev.indices, message.indices) : prev.indices,
    status: message.status ?? prev.status,
  };
}

function byName(current: Record<string, IndexQuote>, list: IndexQuote[]) {
  const out = { ...current };
  for (const index of list) out[index.name] = index;
  return out;
}
