import { useRef } from "react";

import type { Instrument, MarketState, PricePoint } from "../../api/types";
import { direction, percentChange, price, signedPrice } from "../../lib/format";
import { Sparkline } from "../ui/Sparkline";

interface Props {
  instruments: Instrument[];
  market: Record<string, MarketState>;
  history: Record<string, PricePoint[]>;
  selected: string;
  onSelect: (symbol: string) => void;
}

const SPARK_SECONDS = 300;

/** Every stock in one row: last price, change from the previous close, and the last five minutes. */
export function MarketStrip({ instruments, market, history, selected, onSelect }: Props) {
  const scroller = useRef<HTMLDivElement>(null);
  const scroll = (by: number) => scroller.current?.scrollBy({ left: by, behavior: "smooth" });
  return (
    <section className="market-strip" aria-label="Stocks">
      <div className="container strip-row">
        <span className="strip-title">NSE stocks</span>
        <div className="strip-cards" ref={scroller}>
          {instruments.map((instrument) => {
            const state = market[instrument.symbol];
            const ltp = state?.ltp ?? null;
            const change = ltp == null ? 0 : ltp - instrument.prev_close;
            const points = (history[instrument.symbol] ?? []).filter((p, _, all) => p[0] >= all[all.length - 1][0] - SPARK_SECONDS);
            return (
              <button key={instrument.symbol} type="button" aria-pressed={instrument.symbol === selected}
                className={instrument.symbol === selected ? "strip-card selected" : "strip-card"} onClick={() => onSelect(instrument.symbol)}>
                <span className="strip-text">
                  <span className="link">{instrument.symbol}</span>
                  <span className="num strong">{price(ltp ?? instrument.prev_close)}</span>
                  <span className={`num small ${direction(change)}`}>{ltp == null ? "—" : `${signedPrice(change)} ${percentChange(ltp, instrument.prev_close)}`}</span>
                </span>
                <Sparkline points={points} base={instrument.prev_close} label={`${instrument.symbol}, last five minutes`} />
              </button>
            );
          })}
        </div>
        <div className="strip-arrows">
          <button type="button" className="icon-button" aria-label="Scroll stocks left" onClick={() => scroll(-320)}>
            <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><path d="M10 3L5 8l5 5" /></svg>
          </button>
          <button type="button" className="icon-button" aria-label="Scroll stocks right" onClick={() => scroll(320)}>
            <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><path d="M6 3l5 5-5 5" /></svg>
          </button>
        </div>
      </div>
    </section>
  );
}
