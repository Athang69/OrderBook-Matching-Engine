import { useCallback, useEffect, useState } from "react";

import { api } from "../../api/client";
import type { AllIndicesResponse, ChartRange, GlobalChart, GlobalQuote, GlobalSearchResult } from "../../api/types";

interface Props {
  onClose: () => void;
  initialTicker?: string;
}

const CURRENCY_SYMBOLS: Record<string, string> = {
  INR: "₹", USD: "$", EUR: "€", GBP: "£", JPY: "¥", CNY: "¥", KRW: "₩", HKD: "HK$",
  AUD: "A$", SGD: "S$", TWD: "NT$", IDR: "Rp", ZAR: "R", CHF: "CHF",
};

function cur(currency: string | null) {
  return currency ? CURRENCY_SYMBOLS[currency] ?? currency + " " : "";
}

function fmtPrice(value: number | null, currency?: string | null): string {
  if (value == null) return "—";
  const abs = Math.abs(value);
  const decimals = abs < 1 ? 4 : abs < 100 ? 2 : abs >= 10000 ? 0 : 2;
  return (currency ? cur(currency) : "") + value.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

function fmtChange(change: number | null, pct: number | null): string {
  if (change == null || pct == null) return "—";
  const sign = change > 0 ? "+" : change < 0 ? "" : "";
  return `${sign}${change.toFixed(2)} (${sign}${pct.toFixed(2)}%)`;
}

function dir(value: number | null): string {
  if (value == null || value === 0) return "";
  return value > 0 ? "up" : "down";
}

function fmtVol(value: number | null): string {
  if (value == null || value === 0) return "—";
  if (value >= 1e9) return (value / 1e9).toFixed(1) + "B";
  if (value >= 1e6) return (value / 1e6).toFixed(1) + "M";
  if (value >= 1e3) return (value / 1e3).toFixed(1) + "K";
  return value.toString();
}

function fmtCap(value: number | null, currency?: string | null): string {
  if (value == null) return "—";
  const c = cur(currency ?? null);
  if (value >= 1e12) return c + (value / 1e12).toFixed(2) + "T";
  if (value >= 1e9) return c + (value / 1e9).toFixed(2) + "B";
  if (value >= 1e6) return c + (value / 1e6).toFixed(2) + "M";
  return c + value.toLocaleString();
}

type Tab = "indices" | "search";

const RANGES: { label: string; range: ChartRange; interval: "1d" | "1wk" }[] = [
  { label: "1D",  range: "1d",  interval: "1d" },
  { label: "1M",  range: "1mo", interval: "1d" },
  { label: "6M",  range: "6mo", interval: "1d" },
  { label: "1Y",  range: "1y",  interval: "1wk" },
  { label: "5Y",  range: "5y",  interval: "1wk" },
];

function MiniLineChart({ bars, currency }: { bars: GlobalChart["bars"]; currency: string | null }) {
  if (!bars.length) return <p className="muted small">No chart data.</p>;
  const closes = bars.map((b) => b[4]);
  const times  = bars.map((b) => b[0]);
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const range = max - min || 1;
  const W = 600, H = 160, PAD = 8;
  const x = (i: number) => PAD + (i / (closes.length - 1)) * (W - PAD * 2);
  const y = (v: number) => H - PAD - ((v - min) / range) * (H - PAD * 2);
  const first = closes[0], last = closes[closes.length - 1];
  const up = last >= first;
  const color = up ? "var(--up)" : "var(--down)";
  const pts   = closes.map((v, i) => `${x(i)},${y(v)}`).join(" ");
  const area  = `M${x(0)},${H - PAD} ` + closes.map((v, i) => `L${x(i)},${y(v)}`).join(" ") + ` L${x(closes.length-1)},${H - PAD} Z`;

  // Format x-axis labels
  const labelCount = 5;
  const step = Math.max(1, Math.floor((closes.length - 1) / (labelCount - 1)));
  const labelIdxs = Array.from({ length: labelCount }, (_, i) => Math.min(i * step, closes.length - 1));

  return (
    <div className="global-chart">
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ width: "100%", height: H }}>
        <defs>
          <linearGradient id="gcfill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.18" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>
        {/* area fill */}
        <path d={area} fill="url(#gcfill)" />
        {/* line */}
        <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" />
        {/* x-axis labels */}
        {labelIdxs.map((idx) => (
          <text key={idx} x={x(idx)} y={H - 2} textAnchor="middle" fontSize="10" fill="var(--faint)">
            {new Date(times[idx] * 1000).toLocaleDateString("en-IN", { month: "short", day: "numeric" })}
          </text>
        ))}
      </svg>
      <div className="global-chart-axis">
        <span className="num small faint">{cur(currency)}{min.toLocaleString("en-US", { maximumFractionDigits: 2 })}</span>
        <span className={`num small ${up ? "up" : "down"}`}>{cur(currency)}{last.toLocaleString("en-US", { maximumFractionDigits: 2 })}</span>
        <span className="num small faint">{cur(currency)}{max.toLocaleString("en-US", { maximumFractionDigits: 2 })}</span>
      </div>
    </div>
  );
}

export function GlobalMarkets({ onClose, initialTicker }: Props) {
  const [tab, setTab] = useState<Tab>("indices");
  const [allIndices, setAllIndices] = useState<AllIndicesResponse | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<GlobalSearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);
  const [tickerQuote, setTickerQuote] = useState<GlobalQuote | null>(null);
  const [loadingQuote, setLoadingQuote] = useState(false);
  const [chartData, setChartData] = useState<GlobalChart | null>(null);
  const [chartRange, setChartRange] = useState<typeof RANGES[number]>(RANGES[2]);
  const [loadingChart, setLoadingChart] = useState(false);
  const [error, setError] = useState("");
  const [expandedGroup, setExpandedGroup] = useState<string | null>("India");

  useEffect(() => {
    api.allIndices().then(setAllIndices).catch(() => {});
    const iv = setInterval(() => { api.allIndices().then(setAllIndices).catch(() => {}); }, 10000);
    return () => clearInterval(iv);
  }, []);

  useEffect(() => {
    if (initialTicker) loadQuote(initialTicker);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialTicker]);

  const doSearch = useCallback(async () => {
    if (!searchQuery.trim()) return;
    setSearching(true);
    setError("");
    try {
      const res = await api.globalSearch(searchQuery.trim());
      setSearchResults(res.results);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed.");
    } finally {
      setSearching(false);
    }
  }, [searchQuery]);

  const loadChart = useCallback(async (ticker: string, r: typeof RANGES[number]) => {
    setLoadingChart(true);
    setChartData(null);
    try {
      const data = await api.globalChart(ticker, r.range, r.interval);
      setChartData(data);
    } catch {
      setChartData(null);
    } finally {
      setLoadingChart(false);
    }
  }, []);

  const loadQuote = useCallback(async (ticker: string) => {
    setSelectedTicker(ticker);
    setLoadingQuote(true);
    setTickerQuote(null);
    setChartData(null);
    const r = RANGES[2]; // default 6M
    setChartRange(r);
    try {
      const [quoteRes] = await Promise.all([
        api.globalQuote([ticker]),
        loadChart(ticker, r),
      ]);
      setTickerQuote(quoteRes.quotes[ticker] ?? null);
    } catch {
      setTickerQuote(null);
    } finally {
      setLoadingQuote(false);
    }
  }, [loadChart]);

  return (
    <div className="global-overlay" role="dialog" aria-label="Global Markets">
      <div className="global-panel">
        <header className="global-header">
          <h2>Global Markets</h2>
          <div className="global-tabs">
            <button type="button" className={tab === "indices" ? "active" : ""} onClick={() => setTab("indices")}>
              All Indices
            </button>
            <button type="button" className={tab === "search" ? "active" : ""} onClick={() => setTab("search")}>
              Search Any Stock
            </button>
          </div>
          <button type="button" className="global-close" onClick={onClose} aria-label="Close">
            <svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true">
              <path d="M5 5l10 10M15 5L5 15" stroke="currentColor" strokeWidth="2" />
            </svg>
          </button>
        </header>

        {tab === "indices" && (
          <div className="global-body">
            {allIndices ? (
              Object.entries(allIndices.groups).map(([group, items]) => (
                <div key={group} className="index-group">
                  <button type="button" className="group-toggle" onClick={() => setExpandedGroup(expandedGroup === group ? null : group)}>
                    <span className="group-name">{group}</span>
                    <span className="group-count">{items.length}</span>
                    <svg className={expandedGroup === group ? "chevron open" : "chevron"} width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
                      <path d="M4 5.5l3 3 3-3" />
                    </svg>
                  </button>
                  {expandedGroup === group && (
                    <table className="index-table">
                      <thead>
                        <tr><th>Index</th><th>Last</th><th>Change</th><th>High</th><th>Low</th></tr>
                      </thead>
                      <tbody>
                        {items.map((idx) => {
                          // The backend sends index levels in hundredths, like prices in paise.
                          const chg = idx.ltp != null && idx.prev_close ? (idx.ltp - idx.prev_close) / 100 : null;
                          const pct = chg != null && idx.prev_close ? (chg / (idx.prev_close / 100)) * 100 : null;
                          return (
                            <tr key={idx.name} className={idx.ticker ? "clickable" : ""} onClick={() => idx.ticker && loadQuote(idx.ticker)}>
                              <td className="idx-name">{idx.name}</td>
                              <td className="num">{idx.ltp != null ? (idx.ltp / 100).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "—"}</td>
                              <td className={`num ${dir(chg)}`}>{fmtChange(chg, pct)}</td>
                              <td className="num muted">{idx.high != null ? (idx.high / 100).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "—"}</td>
                              <td className="num muted">{idx.low != null ? (idx.low / 100).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "—"}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  )}
                </div>
              ))
            ) : (
              <p className="muted">Loading indices...</p>
            )}
          </div>
        )}

        {tab === "search" && (
          <div className="global-body">
            <form className="global-search-form" onSubmit={(e) => { e.preventDefault(); doSearch(); }}>
              <input type="text" value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search: AAPL, TSLA, ^GSPC, BTC-USD, RELIANCE.NS ..."
                className="global-search-input" autoFocus />
              <button type="submit" disabled={searching || !searchQuery.trim()} className="btn btn-accent">
                {searching ? "Searching..." : "Search"}
              </button>
            </form>
            {error && <p className="notice">{error}</p>}
            {searchResults.length > 0 && (
              <table className="search-results-table">
                <thead>
                  <tr><th>Ticker</th><th>Name</th><th>Exchange</th><th>Type</th></tr>
                </thead>
                <tbody>
                  {searchResults.map((r) => (
                    <tr key={r.ticker} className="clickable" onClick={() => loadQuote(r.ticker)}>
                      <td className="strong">{r.ticker}</td>
                      <td>{r.name ?? "—"}</td>
                      <td className="muted">{r.exchange ?? "—"}</td>
                      <td className="muted">{r.type ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}

        {selectedTicker && (
          <div className="quote-detail-panel">
            <div className="qd-header-row">
              <h3 className="qd-ticker">{selectedTicker}</h3>
              <button type="button" className="global-close qd-close" onClick={() => { setSelectedTicker(null); setTickerQuote(null); setChartData(null); }} aria-label="Close detail">
                <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><path d="M4 4l8 8M12 4L4 12" stroke="currentColor" strokeWidth="1.8" /></svg>
              </button>
            </div>

            {loadingQuote ? (
              <p className="muted small">Loading…</p>
            ) : tickerQuote ? (
              <>
                <div className="qd-main">
                  <span className="qd-name">{tickerQuote.name}</span>
                  <span className="qd-price">{fmtPrice(tickerQuote.price, tickerQuote.currency)}</span>
                  <span className={`qd-change ${dir(tickerQuote.change)}`}>
                    {fmtChange(tickerQuote.change, tickerQuote.change_pct)}
                  </span>
                  <span className="qd-meta muted small">
                    {tickerQuote.exchange} · {tickerQuote.currency} · {tickerQuote.market_state}
                  </span>
                </div>

                {/* Chart */}
                <div className="qd-chart-section">
                  <div className="qd-range-row">
                    {RANGES.map((r) => (
                      <button
                        key={r.label}
                        type="button"
                        className={`range-btn${chartRange.label === r.label ? " active" : ""}`}
                        onClick={() => { setChartRange(r); loadChart(selectedTicker, r); }}
                      >{r.label}</button>
                    ))}
                  </div>
                  {loadingChart
                    ? <div className="global-chart-loading muted small">Loading chart…</div>
                    : chartData
                      ? <MiniLineChart bars={chartData.bars} currency={tickerQuote.currency} />
                      : <div className="global-chart-loading muted small">No chart data.</div>
                  }
                </div>

                {/* Key stats */}
                <div className="qd-stats">
                  <div><span className="label">Open</span><span className="num">{fmtPrice(tickerQuote.open)}</span></div>
                  <div><span className="label">High</span><span className="num">{fmtPrice(tickerQuote.high)}</span></div>
                  <div><span className="label">Low</span><span className="num">{fmtPrice(tickerQuote.low)}</span></div>
                  <div><span className="label">Prev Close</span><span className="num">{fmtPrice(tickerQuote.prev_close)}</span></div>
                  <div><span className="label">Volume</span><span className="num">{fmtVol(tickerQuote.volume)}</span></div>
                  <div><span className="label">Avg Vol</span><span className="num">{fmtVol(tickerQuote.avg_volume)}</span></div>
                  <div><span className="label">Mkt Cap</span><span className="num">{fmtCap(tickerQuote.market_cap, tickerQuote.currency)}</span></div>
                  <div><span className="label">P/E</span><span className="num">{tickerQuote.pe?.toFixed(2) ?? "—"}</span></div>
                  <div><span className="label">EPS</span><span className="num">{tickerQuote.eps?.toFixed(2) ?? "—"}</span></div>
                  <div><span className="label">52W High</span><span className="num">{fmtPrice(tickerQuote.week52_high)}</span></div>
                  <div><span className="label">52W Low</span><span className="num">{fmtPrice(tickerQuote.week52_low)}</span></div>
                  <div><span className="label">Div Yield</span><span className="num">{tickerQuote.dividend_yield != null ? tickerQuote.dividend_yield.toFixed(2) + "%" : "—"}</span></div>
                </div>
              </>
            ) : (
              <p className="muted small">No data available for {selectedTicker}.</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
