import type { Instrument, MarketState, SimStatus } from "../../api/types";
import { direction, longDate, percentChange, price, signedPrice } from "../../lib/format";

interface Props {
  instrument: Instrument;
  state: MarketState;
  sim: SimStatus | null;
  onTrade: (side: "BUY" | "SELL") => void;
}

export function QuoteHeader({ instrument, state, sim, onTrade }: Props) {
  const ltp = state.ltp;
  const change = ltp == null ? 0 : ltp - instrument.prev_close;
  const now = new Date().toLocaleTimeString("en-IN", { hour12: false });
  return (
    <header className="quote-header" id="summary">
      <p className="eyebrow">
        NSE {"·"} Equity {"·"} INR {"·"} Simulated replay of {longDate(instrument.data_date)}
      </p>
      <h1>
        {instrument.company} <span className="muted">({instrument.symbol})</span>
      </h1>
      <div className="quote-row">
        <div>
          <div className="quote-price">
            <span className="num big">{price(ltp ?? instrument.prev_close)}</span>
            <span className={`num change ${direction(change)}`}>
              {ltp == null ? "No trades yet" : `${signedPrice(change)} (${percentChange(ltp, instrument.prev_close)})`}
            </span>
          </div>
          <p className="as-of">
            As of {now} IST. {sim?.bots_enabled === false ? "Robot traders paused." : "Market open (simulation)."}
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
