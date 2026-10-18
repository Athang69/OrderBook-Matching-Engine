import type { Instrument, Quote, Session } from "../../api/types";
import { clock, companyName, dateTime, direction, percentChange, price, signedPrice } from "../../lib/format";

interface Props {
  instrument: Instrument;
  quote: Quote | undefined;
  session: Session | null;
  watched: boolean;
  onToggleWatch: () => void;
  onTrade: (side: "BUY" | "SELL") => void;
  onWhy: () => void;
}

export function QuoteHeader({ instrument, quote, session, watched, onToggleWatch, onTrade, onWhy }: Props) {
  const ltp = quote?.ltp ?? null;
  const base = quote?.prev_close ?? instrument.close;
  const change = ltp == null ? 0 : ltp - base;
  const updated = quote ? Math.max(quote.tick_time ?? 0, quote.quote_time ?? 0) : 0;
  const open = session?.state === "OPEN";
  return (
    <header className="quote-header" id="summary">
      <p className="eyebrow">
        NSE {"·"} {instrument.series === "BE" ? "Trade for trade (BE), delivery only" : "Equity"} {"·"} INR {"·"} Live prices, paper trading
      </p>
      <div className="quote-title">
        <h1>
          {quote?.name ?? companyName(instrument.name)} <span className="muted">({instrument.symbol})</span>
        </h1>
        <button type="button" className={watched ? "watch on" : "watch"} aria-pressed={watched} onClick={onToggleWatch}>
          <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><path d="M8 1.8l1.9 3.9 4.3.6-3.1 3 .7 4.3L8 11.6l-3.8 2 .7-4.3-3.1-3 4.3-.6z" /></svg>
          {watched ? "In watchlist" : "Add to watchlist"}
        </button>
      </div>
      <div className="quote-row">
        <div>
          <div className="quote-price">
            <span className="num big">{price(ltp)}</span>
            <span className={`num change ${direction(change)}`}>
              {ltp == null ? "Waiting for the first price" : `${signedPrice(change)} (${percentChange(ltp, base)})`}
            </span>
            {ltp != null && (
              <button type="button" className="why-button" onClick={onWhy}>
                Why {change < 0 ? "down" : "up"}? <span aria-hidden="true">→</span>
              </button>
            )}
          </div>
          <p className="as-of">
            {!updated ? "No price yet." : open ? `Live · last trade at ${clock(updated)} IST.` : `At close · ${dateTime(updated)} IST. ${session?.label ?? ""}.`}
          </p>
        </div>
        <div className="quote-actions">
          <button type="button" className="button buy" onClick={() => onTrade("BUY")}>Buy</button>
          <button type="button" className="button sell" onClick={() => onTrade("SELL")}>Sell</button>
        </div>
      </div>
    </header>
  );
}
