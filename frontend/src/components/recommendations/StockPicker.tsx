import type { Instrument, MarketState } from "../../api/types";
import { direction, percentChange, price } from "../../lib/format";

interface Props {
  instruments: Instrument[];
  market: Record<string, MarketState>;
  selected: string[];
  onChange: (selected: string[]) => void;
}

/** A tick-box for every stock, with its last price and change. */
export function StockPicker({ instruments, market, selected, onChange }: Props) {
  const toggle = (symbol: string) =>
    onChange(selected.includes(symbol) ? selected.filter((s) => s !== symbol) : [...selected, symbol]);
  return (
    <>
      <div className="picker-tools">
        <button type="button" className="button ghost small" onClick={() => onChange(instruments.map((i) => i.symbol))}>Select all</button>
        <button type="button" className="button ghost small" onClick={() => onChange([])}>Clear</button>
        <span className="muted small">{selected.length} selected</span>
      </div>
      <div className="picker-grid">
        {instruments.map((instrument) => {
          const ltp = market[instrument.symbol]?.ltp ?? null;
          const checked = selected.includes(instrument.symbol);
          return (
            <label key={instrument.symbol} className={checked ? "pick on" : "pick"}>
              <input type="checkbox" checked={checked} onChange={() => toggle(instrument.symbol)} />
              <span className="pick-name">
                <span className="strong">{instrument.symbol}</span>
                <span className="muted small ellipsis">{instrument.company}</span>
              </span>
              <span className="pick-price">
                <span className="num">{price(ltp ?? instrument.prev_close)}</span>
                <span className={`num small ${ltp == null ? "" : direction(ltp - instrument.prev_close)}`}>{percentChange(ltp, instrument.prev_close)}</span>
              </span>
            </label>
          );
        })}
      </div>
    </>
  );
}
