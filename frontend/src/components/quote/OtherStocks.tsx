import type { Instrument, MarketState } from "../../api/types";
import { direction, percentChange, price } from "../../lib/format";

interface Props {
  instruments: Instrument[];
  market: Record<string, MarketState>;
  selected: string;
  onSelect: (symbol: string) => void;
}

/** Cards for the other stocks, like a "people also watch" row. */
export function OtherStocks({ instruments, market, selected, onSelect }: Props) {
  return (
    <section className="section" id="others" aria-labelledby="others-title">
      <h2 id="others-title" className="section-title">Other stocks</h2>
      <div className="other-grid">
        {instruments.filter((i) => i.symbol !== selected).map((instrument) => {
          const ltp = market[instrument.symbol]?.ltp ?? null;
          return (
            <button key={instrument.symbol} type="button" className="other-card" onClick={() => { onSelect(instrument.symbol); window.scrollTo({ top: 0, behavior: "smooth" }); }}>
              <span className="link strong">{instrument.symbol}</span>
              <span className="muted small ellipsis">{instrument.company}</span>
              <span>
                <span className="num strong">{price(ltp ?? instrument.prev_close)}</span>{" "}
                <span className={`num small ${ltp == null ? "" : direction(ltp - instrument.prev_close)}`}>{percentChange(ltp, instrument.prev_close)}</span>
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
