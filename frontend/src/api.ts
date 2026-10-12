// Types and calls for the simulator's REST API. All prices are integers in paise.

export type Side = "BUY" | "SELL";
export type OrderType = "LIMIT" | "MARKET";
export type Product = "CNC" | "MIS"; // delivery | intraday

/** price, quantity, number of orders */
export type Level = [number, number, number];

export interface MarketState {
  symbol: string;
  ltp: number | null;
  prev_close: number;
  open: number | null;
  high: number | null;
  low: number | null;
  volume: number;
  trades: number;
  bids: Level[];
  asks: Level[];
}

export interface Instrument {
  symbol: string;
  prev_close: number;
  tick: number;
  band_pct: number;
  lower_band: number;
  upper_band: number;
  day: { open: number; high: number; low: number; close: number; volume: number };
  data_date: string;
  market: MarketState;
}

export interface Trade {
  id: number;
  symbol: string;
  price: number;
  qty: number;
  side: Side; // side of the order that caused the trade
  ts: number;
}

export interface SimStatus {
  data_date: string;
  demo_user: string;
  margin_divisor: number;
  bots_enabled: boolean;
  session_seconds: number;
  elapsed_seconds: number;
  progress: number;
}

export interface Order {
  id: number;
  user_id: string;
  symbol: string;
  side: Side;
  type: OrderType;
  product: Product;
  qty: number;
  price: number | null;
  status: "PENDING" | "OPEN" | "PARTIALLY_FILLED" | "FILLED" | "CANCELLED" | "REJECTED";
  filled: number;
  remaining: number;
  avg_price: number | null;
  reason: string | null;
  created_at: number;
  updated_at: number;
}

export interface Holding {
  symbol: string;
  qty: number;
  blocked: number;
  avg_price: number;
  ltp: number;
  value: number;
  unrealised_pnl: number;
}

export interface IntradayPosition {
  symbol: string;
  qty: number; // negative is a short position
  avg_price: number;
  ltp: number;
  margin: number;
  unrealised_pnl: number;
}

export interface Portfolio {
  user_id: string;
  cash: number;
  blocked_for_orders: number;
  intraday_margin: number;
  available: number;
  holdings_value: number;
  realised_pnl: number;
  unrealised_pnl: number;
  equity: number;
  holdings: Holding[];
  intraday: IntradayPosition[];
}

export interface NewOrder {
  symbol: string;
  side: Side;
  type: OrderType;
  product: Product;
  qty: number;
  price?: number;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { headers: { "Content-Type": "application/json" }, ...init });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = body?.detail;
    throw new Error(typeof detail === "string" ? detail : `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  placeOrder: (order: NewOrder) => request<Order>("/v1/orders", { method: "POST", body: JSON.stringify(order) }),
  cancelOrder: (id: number) => request<Order>(`/v1/orders/${id}`, { method: "DELETE" }),
  orders: () => request<Order[]>("/v1/orders?limit=100"),
  portfolio: (user: string) => request<Portfolio>(`/v1/portfolio/${user}`),
  squareOff: (user: string) => request<Order[]>(`/v1/portfolio/${user}/squareoff`, { method: "POST" }),
  trades: (symbol: string) => request<Trade[]>(`/v1/market/trades/${symbol}?limit=30`),
  history: (symbol: string) => request<[number, number][]>(`/v1/market/history/${symbol}`),
  setBots: (enabled: boolean) => request<SimStatus>("/v1/sim/bots", { method: "POST", body: JSON.stringify({ enabled }) }),
};
