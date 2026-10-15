// Types for the simulator's API. All prices and money are integers in paise (Rs 1,179.40 is 117940).

export type Side = "BUY" | "SELL";
export type OrderType = "LIMIT" | "MARKET";
export type Product = "CNC" | "MIS"; // delivery | intraday

/** price, quantity, number of orders */
export type Level = [number, number, number];

/** [Unix seconds, price] */
export type PricePoint = [number, number];

export interface MarketState {
  symbol: string;
  ltp: number | null;
  prev_close: number;
  open: number | null;
  high: number | null;
  low: number | null;
  volume: number;
  turnover: number;
  trades: number;
  bids: Level[];
  asks: Level[];
}

export interface Instrument {
  symbol: string;
  company: string;
  prev_close: number;
  tick: number;
  band_pct: number;
  lower_band: number;
  upper_band: number;
  avg_trade_qty: number;
  day: { open: number; high: number; low: number; close: number; volume: number };
  data_date: string;
  market: MarketState;
}

export interface Trade {
  id: number;
  symbol: string;
  price: number;
  qty: number;
  /** Side of the order that caused the trade. */
  side: Side;
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
  /** Negative is a short position. */
  qty: number;
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

// ---- news ----

export interface NewsArticle {
  title: string;
  source: string;
  url: string;
  /** Unix seconds. */
  published: number;
}

export interface StockNews {
  symbol: string;
  company: string;
  articles: NewsArticle[];
  fetched_at: number;
  /** Set when the latest refresh failed; the articles may then be older. */
  error: string | null;
}

export interface NewsResponse {
  source: string;
  per_stock: number;
  stocks: Record<string, StockNews>;
}

// ---- delivery recommendation (recomendation_system) ----

export interface RecommendedStock {
  symbol: string;
  decision: "BUY" | "DONT_BUY";
  /** Share of re-runs in which the optimiser gave this stock at least 5% of the money (0 to 1). */
  confidence: number;
  /** Share of the budget in the recommended portfolio (0 to 1). */
  weight: number;
  amount: number;
  last_price: number;
  quantity: number;
  cost: number;
  max_sharpe_weight: number;
  min_vol_weight: number;
  expected_return: number;
  volatility: number;
  note: string;
}

export interface PortfolioSummary {
  expected_return: number;
  volatility: number;
  sharpe: number | null;
  weights: Record<string, number>;
}

export interface Recommendation {
  inputs: { symbols: string[]; confidence: number; budget: number };
  data: { source: string; start: string; end: string; trading_days: number; stale: boolean };
  method: { monte_carlo_portfolios: number; resamples: number; min_weight: number; risk_free_rate: number; trading_days_per_year: number };
  stocks: RecommendedStock[];
  recommended: null | {
    symbols: string[];
    expected_return: number;
    volatility: number;
    sharpe: number | null;
    value_at_risk: { confidence: number; one_day_fraction: number; one_day_amount: number };
    invested: number;
    cash_left: number;
  };
  reference_portfolios: { max_sharpe: PortfolioSummary; min_volatility: PortfolioSummary };
  /** Monte Carlo portfolios: [annual volatility, annual return, Sharpe ratio]. */
  frontier: { points: [number, number, number][] };
  runtime_ms: number;
}

// ---- intraday recommendation ----

export type IntradayAction = "BUY" | "SELL" | "NO_TRADE" | "WAIT";

/** Each between -1 (strong sell) and +1 (strong buy). */
export interface IntradaySignals {
  momentum: number;
  vwap: number;
  book: number;
  flow: number;
}

export interface IntradayStock {
  symbol: string;
  action: IntradayAction;
  confidence: number;
  score: number;
  signals: IntradaySignals | null;
  /** How many of the four signals point the same way as the score. */
  agree: number;
  ltp: number | null;
  vwap: number | null;
  best_bid: number | null;
  best_ask: number | null;
  entry: number | null;
  stop_loss: number | null;
  target: number | null;
  risk_per_share: number;
  reward_per_share: number;
  quantity: number;
  position_value: number;
  margin: number;
  max_loss: number;
  max_gain: number;
  note: string;
}

export interface IntradayRecommendation {
  inputs: { symbols: string[]; confidence: number; budget: number };
  stocks: IntradayStock[];
  totals: { trades: number; margin: number; exposure: number; max_loss: number; max_gain: number };
  method: {
    weights: IntradaySignals;
    momentum_seconds: number;
    window_seconds: number;
    hold_seconds: number;
    stop_moves: number;
    reward_to_risk: number;
    leverage: number;
  };
  as_of: number;
  /** Server time, in microseconds, from receiving the request to the answer. */
  timing: { checks_us: number; snapshot_us: number; signals_us: number; total_us: number };
}
