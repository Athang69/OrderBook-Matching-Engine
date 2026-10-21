// Types for the API. All prices and money are integers in paise (Rs 1,179.40 is 117940).

export type Side = "BUY" | "SELL";
export type OrderType = "LIMIT" | "MARKET";
export type Product = "CNC" | "MIS"; // delivery | intraday

/** price, quantity, number of orders */
export type Level = [number, number, number];

/** [Unix seconds, price] */
export type PricePoint = [number, number];

/** [Unix seconds, open, high, low, close, volume] */
export type Bar = [number, number, number, number, number, number];

/** [symbol, NSE name, series, reference close, tick, band %, lower band, upper band] for every stock. */
export type SymbolRow = [string, string, string, number, number, number, number, number];

export interface SymbolList {
  data_date: string;
  count: number;
  watchlist: string[];
  symbols: SymbolRow[];
}

/** A stock's rules for the day, from NSE's daily files. */
export interface Instrument {
  symbol: string;
  name: string;
  series: string;
  /** Reference closing price: the price band is worked out from it. */
  close: number;
  tick: number;
  band_pct: number;
  lower_band: number;
  upper_band: number;
  volume: number;
  avg_trade_qty: number;
  data_date: string;
}

/** The live quote, from Yahoo Finance. Missing values are null. */
export interface Quote {
  symbol: string;
  name: string | null;
  ltp: number | null;
  prev_close: number | null;
  open: number | null;
  high: number | null;
  low: number | null;
  volume: number;
  vwap: number | null;
  bid: number | null;
  ask: number | null;
  /** Time of the last trade Yahoo reported, Unix seconds. */
  quote_time: number | null;
  /** When the server last fetched the quote. */
  polled_at: number | null;
  /** Time of the last price from the stream. */
  tick_time: number | null;
  week52_high: number | null;
  week52_low: number | null;
  /** Rupees, not paise. */
  market_cap: number | null;
  pe: number | null;
  eps: number | null;
  /** Percent. */
  dividend_yield: number | null;
  price_to_book: number | null;
  avg_volume: number | null;
  market_state: string | null;
  live: boolean;
}

export interface InstrumentDetail extends Instrument {
  quote: Quote;
}

export interface Trade {
  id: number;
  symbol: string;
  price: number;
  qty: number;
  /** By the tick test: a price above the previous one is a buy. Null before the first price change. */
  side: Side | null;
  ts: number;
}

export interface IndexQuote {
  name: string;
  ltp: number | null;
  prev_close: number | null;
  high: number | null;
  low: number | null;
  time: number | null;
}

export interface Session {
  state: "OPEN" | "PRE_OPEN" | "CLOSED";
  label: string;
  now: number;
  trading_day: string;
  opens_at: number;
  closes_at: number;
  intraday_open: boolean;
  square_off_at: number;
}

export interface Status {
  session: Session;
  data_date: string;
  demo_user: string;
  margin_divisor: number;
  live: boolean;
  feed: {
    stream_connected: boolean;
    last_tick: number | null;
    stream_error: string | null;
    quotes_at: number | null;
    quote_error: string | null;
  };
}

export type ChartRange = "1d" | "5d" | "1mo" | "3mo" | "6mo" | "ytd" | "1y" | "5y" | "max";
export type ChartInterval = "1m" | "2m" | "5m" | "15m" | "30m" | "1h" | "1d" | "1wk" | "1mo";

export interface Chart {
  symbol: string;
  range: ChartRange;
  interval: ChartInterval;
  bars: Bar[];
  prev_close: number | null;
}

export interface TopOfBook {
  symbol: string;
  bid: number | null;
  ask: number | null;
  ltp: number | null;
  polled_at: number | null;
  depth_available: boolean;
  your_bids: Level[];
  your_asks: Level[];
}

export interface Charges {
  brokerage: number;
  stt: number;
  exchange: number;
  sebi: number;
  stamp: number;
  gst: number;
  total: number;
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
  /** Placed while the market was closed. */
  amo: boolean;
  tag: string | null;
  charges: Charges;
  created_at: number;
  updated_at: number;
}

export interface Holding {
  symbol: string;
  qty: number;
  blocked: number;
  avg_price: number;
  ltp: number;
  prev_close: number;
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
  charges: Charges;
  net_pnl: number;
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

/** Your confidence in each stock, 0 to 100; 50 means no view. */
export type Confidences = Record<string, number>;

// ---- delivery recommendation (recomendation_system) ----

export interface RecommendedStock {
  symbol: string;
  decision: "BUY" | "DONT_BUY";
  your_confidence: number;
  /** Added to the expected annual return by your view. */
  return_shift: number;
  /** Share of re-runs with your view in which the optimiser gave this stock at least 5% of the money. */
  agreement: number;
  /** The same, on price history alone. */
  history_agreement: number;
  /** Share of the budget in the recommended portfolio (0 to 1). */
  weight: number;
  amount: number;
  last_price: number;
  quantity: number;
  cost: number;
  history_weight: number;
  max_sharpe_weight: number;
  min_vol_weight: number;
  expected_return: number;
  expected_return_with_view: number;
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
  inputs: { symbols: string[]; confidences: Confidences; budget: number };
  data: { source: string; start: string; end: string; trading_days: number; stale: boolean };
  method: {
    monte_carlo_portfolios: number;
    resamples: number;
    min_weight: number;
    buy_agreement: number;
    view_strength: number;
    risk_free_rate: number;
    trading_days_per_year: number;
  };
  stocks: RecommendedStock[];
  recommended: null | {
    symbols: string[];
    expected_return: number;
    expected_return_history: number;
    volatility: number;
    sharpe: number | null;
    value_at_risk: { confidence: number; one_day_fraction: number; one_day_amount: number };
    invested: number;
    cash_left: number;
  };
  reference_portfolios: { history_only: PortfolioSummary; max_sharpe: PortfolioSummary; min_volatility: PortfolioSummary };
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
  flow: number;
}

export interface IntradayStock {
  symbol: string;
  action: IntradayAction;
  /** Size of the final score, 0 to 1. */
  confidence: number;
  /** Final score: 60% live signals, 40% your view. */
  score: number;
  model_score: number | null;
  your_confidence: number;
  your_view: number;
  signals: IntradaySignals | null;
  /** How many of the three signals point the same way as the score. */
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
  inputs: { symbols: string[]; confidences: Confidences; budget: number };
  session: { state: Session["state"]; intraday_open: boolean; label: string };
  stocks: IntradayStock[];
  totals: { trades: number; margin: number; exposure: number; max_loss: number; max_gain: number };
  method: {
    weights: IntradaySignals;
    model_weight: number;
    view_weight: number;
    threshold: number;
    momentum_seconds: number;
    window_seconds: number;
    min_minutes: number;
    hold_minutes: number;
    stop_moves: number;
    reward_to_risk: number;
    leverage: number;
  };
  as_of: number;
  /** Server time, in microseconds, from receiving the request to the answer. */
  timing: { checks_us: number; snapshot_us: number; signals_us: number; total_us: number };
}

// ---- why a stock moved ----

export type Scope = "company" | "peers" | "industry" | "market" | "global";

export interface HeadlineSentiment {
  label: "positive" | "negative" | "neutral";
  pos: number;
  neg: number;
  neu: number;
  score: number;
}

export interface ExplainHeadline {
  title: string;
  source: string;
  url: string;
  published: number;
  scope: Scope;
  /** -1 (only negative words) to +1 (only positive words). */
  tone: number;
  reasons: string[];
  sentiment?: HeadlineSentiment;
}

export interface ReasonGroup {
  label: string;
  scope: Scope;
  score: number;
  tone: "positive" | "negative" | "mixed";
  headlines: ExplainHeadline[];
}

export interface Explanation {
  symbol: string;
  /** The day explained, YYYY-MM-DD. */
  date: string;
  previous_date: string;
  latest_date: string;
  /** Fractions: 0.0123 is +1.23%. */
  change: number;
  price: number;
  prev_close: number;
  verdict: "Market-wide move" | "Industry-wide move" | "Company-specific move" | "Ordinary day";
  summary: string[];
  market: { name: string; change: number | null };
  beta: number | null;
  market_part: number | null;
  /** The stock's typical daily move once the market is taken out. */
  typical_move: number | null;
  sector: { name: string; change: number } | null;
  peers: { symbol: string; change: number | null }[];
  profile: { sector: string | null; industry: string | null; summary: string | null; peers: string[] };
  reasons: ReasonGroup[];
  headlines: Record<Scope, ExplainHeadline[]>;
  /** The largest own moves of about the last three months, newest first. */
  big_days: { date: string; change: number; own: number }[];
  runtime_ms: number;
  /** Recent OHLC bars for candlestick rendering (last ~10 days). */
  ohlc_bars?: OHLCBar[];
  /** FinBERT sentiment totals per scope. */
  sentiment_totals?: Record<Scope, { avg_score: number; count: number; positive: number; negative: number; neutral: number }>;
  /** Candlestick patterns found on the explained day and the day before. */
  candle_patterns?: { today: CandlePattern[]; previous: CandlePattern[] };
  /** Chart CNN predictions for the explained day and the day before. */
  chart_cnn?: { today: ChartCNN | null; previous: ChartCNN | null };
}

export interface OHLCBar {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface CandlePattern {
  name: string;
  bias: "bullish" | "bearish" | "neutral";
  up_rate: number;
  note: string;
}

export interface ChartCNN {
  prob_up: number | null;
  image_b64: string;
  accuracy: number | null;
  baseline: number | null;
  auc: number | null;
}

// ---- global market data ----

export interface GlobalQuote {
  ticker: string;
  name: string | null;
  price: number | null;
  prev_close: number | null;
  open: number | null;
  high: number | null;
  low: number | null;
  volume: number;
  bid: number | null;
  ask: number | null;
  change: number | null;
  change_pct: number | null;
  market_cap: number | null;
  pe: number | null;
  eps: number | null;
  dividend_yield: number | null;
  week52_high: number | null;
  week52_low: number | null;
  avg_volume: number | null;
  market_state: string | null;
  exchange: string | null;
  currency: string | null;
  quote_type: string | null;
  quote_time: number | null;
}

export interface GlobalSearchResult {
  ticker: string;
  name: string | null;
  exchange: string | null;
  type: string | null;
  score: number;
}

export interface GlobalChart {
  ticker: string;
  range: ChartRange;
  interval: ChartInterval;
  bars: [number, number, number, number, number, number][];
  prev_close: number | null;
  currency: string | null;
  exchange: string | null;
}

export interface AllIndicesGroup {
  name: string;
  ticker: string | null;
  ltp: number | null;
  prev_close: number | null;
  high: number | null;
  low: number | null;
  time: number | null;
}

export interface AllIndicesResponse {
  groups: Record<string, AllIndicesGroup[]>;
  strip: string[];
}

export interface AnalysisDriver {
  title: string;
  explanation: string;
  impact: "major" | "moderate" | "minor";
  direction: "negative" | "positive";
  evidence: number[];
}

export interface Analysis {
  symbol: string;
  date: string;
  explanation: Explanation;
  /** The headlines Claude saw, numbered as it cites them. */
  evidence: (ExplainHeadline & { n: number })[];
  india: { name: string; change: number }[];
  world: { name: string; change: number; date: string }[];
  analysis: null | {
    headline: string;
    verdict: string;
    drivers: AnalysisDriver[];
    market_context: string;
    stock_specific: string;
    confidence: "high" | "medium" | "low";
    confidence_reason: string;
    watch: string[];
    technical_view?: string;
  };
  /** Claude's reply as text, when it could not be read as the expected shape. */
  raw: string | null;
  model: string;
  seconds: number;
}
