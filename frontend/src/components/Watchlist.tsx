import type { Instrument, MarketState } from "../api";
import { direction, percentChange, price } from "../format";

interface Props {
  instruments: Instrument[];
  market: Record<string, MarketState>;
  selected: string;
  onSelect: (symbol: string) => void;
}

export function Watchlist({ instruments, market, selected, onSelect }: Props) {
  return (
    <section className="panel watchlist">
      <h2>Stocks</h2>
      <div className="watch-head muted">
        <span>Symbol</span>
        <span>Last price</span>
        <span>Change</span>
      </div>
      <ul>
        {instruments.map((instrument) => {
          const state = market[instrument.symbol];
          const ltp = state?.ltp ?? null;
          const tone = ltp == null ? "flat" : direction(ltp - instrument.prev_close);
          return (
            <li key={instrument.symbol}>
              <button
                className={instrument.symbol === selected ? "watch-row selected" : "watch-row"}
                aria-pressed={instrument.symbol === selected}
                onClick={() => onSelect(instrument.symbol)}
              >
                <span className="symbol">{instrument.symbol}</span>
                <span className="num">{price(ltp ?? instrument.prev_close)}</span>
                <span className={`num ${tone}`}>{percentChange(ltp, instrument.prev_close)}</span>
              </button>
            </li>
          );
        })}
      </ul>
      <p className="hint">Change is measured from the previous close.</p>
    </section>
  );
}
