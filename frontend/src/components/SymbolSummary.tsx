import type { Instrument, MarketState } from "../api";
import { direction, percentChange, price, qty } from "../format";

interface Props {
  instrument: Instrument;
  state: MarketState;
}

export function SymbolSummary({ instrument, state }: Props) {
  const ltp = state.ltp;
  const change = ltp == null ? 0 : ltp - instrument.prev_close;
  const tone = direction(change);

  return (
    <section className="panel summary">
      <div className="summary-main">
        <h1>{instrument.symbol}</h1>
        <span className="ltp num">{price(ltp ?? instrument.prev_close)}</span>
        <span className={`num ${tone}`}>
          {ltp == null ? "no trades yet" : `${change > 0 ? "+" : change < 0 ? "−" : ""}${price(Math.abs(change))} (${percentChange(ltp, instrument.prev_close)})`}
        </span>
      </div>
      <dl className="facts">
        <Fact label="Open" value={price(state.open)} />
        <Fact label="High" value={price(state.high)} />
        <Fact label="Low" value={price(state.low)} />
        <Fact label="Volume" value={qty(state.volume)} />
        <Fact label="Previous close" value={price(instrument.prev_close)} />
        <Fact label={`Price band (${instrument.band_pct}%)`} value={`${price(instrument.lower_band)} to ${price(instrument.upper_band)}`} />
        <Fact label="Tick size" value={price(instrument.tick)} />
      </dl>
    </section>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="muted">{label}</dt>
      <dd className="num">{value}</dd>
    </div>
  );
}
