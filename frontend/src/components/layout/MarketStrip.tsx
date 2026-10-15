import { useRef } from "react";

import type { IndexQuote, PricePoint, Quote } from "../../api/types";
import { direction, percentChange, price, signedPrice } from "../../lib/format";
import { Sparkline } from "../ui/Sparkline";

interface Props {
  indices: Record<string, IndexQuote>;
  indexOrder: string[];
  watchlist: string[];
  quotes: Record<string, Quote>;
  sparklines: Record<string, PricePoint[]>;
  selected: string;
  onSelect: (symbol: string) => void;
}

/** The three main indices, then every stock in your watchlist with today's small chart. */
export function MarketStrip({ indices, indexOrder, watchlist, quotes, sparklines, selected, onSelect }: Props) {
  const scroller = useRef<HTMLDivElement>(null);
  const scroll = (by: number) => scroller.current?.scrollBy({ left: by, behavior: "smooth" });
  return (
    <section className="market-strip" aria-label="Indices and watchlist">
      <div className="container strip-row">
        <div className="strip-cards" ref={scroller}>
          {indexOrder.map((name) => {
            const index = indices[name];
            const change = index?.ltp != null && index.prev_close ? index.ltp - index.prev_close : 0;
            return (
              <div key={name} className="strip-card index-card">
                <span className="strip-text">
                  <span className="strong small">{name}</span>
                  <span className="num strong">{price(index?.ltp)}</span>
                  <span className={`num small ${direction(change)}`}>
                    {index?.ltp == null ? "—" : `${signedPrice(change)} ${percentChange(index.ltp, index.prev_close)}`}
                  </span>
                </span>
              </div>
            );
          })}
          <span className="strip-divider" aria-hidden="true" />
          {watchlist.map((symbol) => {
            const quote = quotes[symbol];
            const ltp = quote?.ltp ?? null;
            const base = quote?.prev_close ?? ltp ?? 0;
            const change = ltp == null ? 0 : ltp - base;
            return (
              <button key={symbol} type="button" aria-pressed={symbol === selected}
                className={symbol === selected ? "strip-card selected" : "strip-card"} onClick={() => onSelect(symbol)}>
                <span className="strip-text">
                  <span className="link">{symbol}</span>
                  <span className="num strong">{price(ltp)}</span>
                  <span className={`num small ${direction(change)}`}>{ltp == null ? "—" : `${signedPrice(change)} ${percentChange(ltp, base)}`}</span>
                </span>
                <Sparkline points={sparklines[symbol] ?? []} base={base} label={`${symbol} today`} />
              </button>
            );
          })}
        </div>
        <div className="strip-arrows">
          <button type="button" className="icon-button" aria-label="Scroll left" onClick={() => scroll(-320)}>
            <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><path d="M10 3L5 8l5 5" /></svg>
          </button>
          <button type="button" className="icon-button" aria-label="Scroll right" onClick={() => scroll(320)}>
            <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><path d="M6 3l5 5-5 5" /></svg>
          </button>
        </div>
      </div>
    </section>
  );
}
