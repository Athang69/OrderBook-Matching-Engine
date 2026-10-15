import type { Confidences, Quote } from "../../api/types";
import { useNews } from "../../hooks/useNews";
import { direction, percentChange, price, signedPrice } from "../../lib/format";
import { NewsList } from "../news/News";

interface Props {
  symbols: string[];
  names: Map<string, string>;
  quotes: Record<string, Quote>;
  confidences: Confidences;
  onChange: (confidences: Confidences) => void;
  /** e.g. "will do well over the coming year" */
  outlook: string;
}

const LABELS: [number, string][] = [[0, "Sure it falls"], [25, "Doubtful"], [50, "No view"], [75, "Fairly sure"], [100, "Sure it rises"]];

/** For each stock: its live price, its latest news, and a slider for how confident you are. */
export function YourViews({ symbols, names, quotes, confidences, onChange, outlook }: Props) {
  const { stocks, loading, error, refresh } = useNews(symbols);
  const set = (symbol: string, value: number) => onChange({ ...confidences, [symbol]: Math.max(0, Math.min(100, Math.round(value))) });
  return (
    <div className="views">
      <div className="section-head">
        <p className="muted">Read each stock's latest news, then set how confident you are that it {outlook}. Leave it at 50% if you have no view.</p>
        <button type="button" className="button ghost small" onClick={refresh} disabled={loading}>{loading ? "Loading news" : "Refresh news"}</button>
      </div>
      {error && <p className="news-warning">{error}</p>}
      <div className="view-grid">
        {symbols.map((symbol) => {
          const q = quotes[symbol];
          const value = confidences[symbol] ?? 50;
          const change = q?.ltp != null && q.prev_close ? q.ltp - q.prev_close : 0;
          const label = LABELS.reduce((best, item) => (Math.abs(item[0] - value) < Math.abs(best[0] - value) ? item : best))[1];
          const tone = value > 55 ? "up" : value < 45 ? "down" : "neutral";
          const mood = value > 55 ? "bullish" : value < 45 ? "bearish" : "";
          return (
            <article key={symbol} className={`view-card ${mood}`}>
              <header>
                <span className="view-name">
                  <strong>{symbol}</strong>
                  <span className="muted small ellipsis">{q?.name ?? stocks[symbol]?.company ?? names.get(symbol) ?? ""}</span>
                </span>
                <span className="view-price">
                  <span className="num strong">{price(q?.ltp)}</span>
                  <span className={`num small ${direction(change)}`}>{q?.ltp == null ? "" : `${signedPrice(change)} (${percentChange(q.ltp, q.prev_close)})`}</span>
                </span>
              </header>
              <NewsList news={stocks[symbol]} loading={loading} />
              <div className="view-input">
                <label htmlFor={`view-${symbol}`} className="small">Your confidence that {symbol} {outlook}</label>
                <div className="slider-row">
                  <input id={`view-${symbol}`} type="range" min={0} max={100} step={1} value={value} onChange={(e) => set(symbol, Number(e.target.value))} />
                  <label className="unit-input">
                    <input type="number" min={0} max={100} step={1} value={value} aria-label={`Your confidence in ${symbol}, typed`}
                      onChange={(e) => set(symbol, Number(e.target.value))} />
                    <span>%</span>
                  </label>
                </div>
                <span className={`badge ${tone}`}>{label}</span>
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}
