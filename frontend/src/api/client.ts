// Calls to the REST API.
import type {
  AllIndicesResponse, Analysis, Chart, ChartInterval, ChartRange, Confidences, Explanation, GlobalChart, GlobalQuote, GlobalSearchResult,
  InstrumentDetail, IntradayRecommendation, NewOrder, NewsResponse, Order, Portfolio,
  PricePoint, Quote, Recommendation, SymbolList, TopOfBook,
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
const many = (name: string, values: string[]) => values.map((v) => `${name}=${encodeURIComponent(v)}`).join("&");
const path = (symbol: string) => encodeURIComponent(symbol);

export const api = {
  symbols: () => request<SymbolList>("/v1/market/symbols"),
  instrument: (symbol: string) => request<InstrumentDetail>(`/v1/market/instrument/${path(symbol)}`),
  quotes: (symbols: string[]) => request<Record<string, Quote>>(`/v1/market/quotes?${many("symbols", symbols)}`),
  chart: (symbol: string, range: ChartRange, interval: ChartInterval) => request<Chart>(`/v1/market/chart/${path(symbol)}?range=${range}&interval=${interval}`),
  sparklines: (symbols: string[]) => request<Record<string, PricePoint[]>>(`/v1/market/sparklines?${many("symbols", symbols)}`),
  orderbook: (symbol: string) => request<TopOfBook>(`/v1/market/orderbook/${path(symbol)}`),
  placeOrder: (order: NewOrder) => request<Order>("/v1/orders", post(order)),
  cancelOrder: (id: number) => request<Order>(`/v1/orders/${id}`, { method: "DELETE" }),
  orders: () => request<Order[]>("/v1/orders?limit=100"),
  portfolio: (user: string) => request<Portfolio>(`/v1/portfolio/${user}`),
  squareOff: (user: string) => request<Order[]>(`/v1/portfolio/${user}/squareoff`, { method: "POST" }),
  news: (symbols: string[]) => request<NewsResponse>(`/v1/news?${many("symbols", symbols)}`),
  explain: (symbol: string, date: string | null) =>
    request<Explanation>(`/v1/explain/${path(symbol)}${date ? `?date=${date}` : ""}`),
  analysis: (symbol: string, date: string) => request<Analysis>(`/v1/analysis/${path(symbol)}?date=${date}`),
  recommend: (symbols: string[], confidences: Confidences, budget: number) =>
    request<Recommendation>("/v1/recommendations", post({ symbols, confidences, budget })),
  recommendIntraday: (symbols: string[], confidences: Confidences, budget: number) =>
    request<IntradayRecommendation>("/v1/recommendations/intraday", post({ symbols, confidences, budget })),

  // Global market data (any exchange, view-only)
  globalSearch: (q: string, count = 20) =>
    request<{ query: string; count: number; results: GlobalSearchResult[] }>(`/v1/global/search?q=${encodeURIComponent(q)}&count=${count}`),
  globalQuote: (tickers: string[]) =>
    request<{ count: number; quotes: Record<string, GlobalQuote> }>(`/v1/global/quote?${tickers.map((t) => `t=${encodeURIComponent(t)}`).join("&")}`),
  globalChart: (ticker: string, range: ChartRange, interval: ChartInterval) =>
    request<GlobalChart>(`/v1/global/chart/${encodeURIComponent(ticker)}?range=${range}&interval=${interval}`),
  globalProfile: (ticker: string) =>
    request<{ ticker: string; sector: string | null; industry: string | null; summary: string | null }>(`/v1/global/profile/${encodeURIComponent(ticker)}`),
  globalSimilar: (ticker: string) =>
    request<{ ticker: string; similar: string[] }>(`/v1/global/similar/${encodeURIComponent(ticker)}`),
  allIndices: () => request<AllIndicesResponse>("/v1/market/indices/all"),
  exchanges: () => request<{ exchanges: Record<string, string> }>("/v1/global/exchanges"),
};
