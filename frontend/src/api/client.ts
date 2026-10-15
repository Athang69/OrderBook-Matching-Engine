// Calls to the simulator's REST API.
import type {
  IntradayRecommendation, NewOrder, NewsResponse, Order, Portfolio, PricePoint, Recommendation, SimStatus, Trade,
} from "./types";

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { headers: { "Content-Type": "application/json" }, ...init });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = body?.detail;
    if (typeof detail === "string") throw new ApiError(detail, response.status);
    // Validation errors come as a list of problems.
    if (Array.isArray(detail)) {
      throw new ApiError(detail.map((d: { msg?: string }) => d.msg ?? "").filter(Boolean).join(" "), response.status);
    }
    throw new ApiError(`Request failed (${response.status})`, response.status);
  }
  return response.json() as Promise<T>;
}

const post = (body: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(body) });

export const api = {
  placeOrder: (order: NewOrder) => request<Order>("/v1/orders", post(order)),
  cancelOrder: (id: number) => request<Order>(`/v1/orders/${id}`, { method: "DELETE" }),
  orders: () => request<Order[]>("/v1/orders?limit=100"),
  portfolio: (user: string) => request<Portfolio>(`/v1/portfolio/${user}`),
  squareOff: (user: string) => request<Order[]>(`/v1/portfolio/${user}/squareoff`, { method: "POST" }),
  trades: (symbol: string) => request<Trade[]>(`/v1/market/trades/${symbol}?limit=30`),
  histories: () => request<Record<string, PricePoint[]>>("/v1/market/histories"),
  news: (symbols: string[]) =>
    request<NewsResponse>(`/v1/news?${symbols.map((s) => `symbols=${encodeURIComponent(s)}`).join("&")}`),
  recommend: (symbols: string[], confidence: number, budget: number) =>
    request<Recommendation>("/v1/recommendations", post({ symbols, confidence, budget })),
  recommendIntraday: (symbols: string[], confidence: number, budget: number) =>
    request<IntradayRecommendation>("/v1/recommendations/intraday", post({ symbols, confidence, budget })),
  setBots: (enabled: boolean) => request<SimStatus>("/v1/sim/bots", post({ enabled })),
};
