import type { Instrument, MarketState } from "../../api/types";
import { price, qty } from "../../lib/format";

export function KeyStats({ instrument, state }: { instrument: Instrument; state: MarketState }) {
  const vwap = state.volume ? Math.round(state.turnover / state.volume) : null;
  const range = state.low == null || state.high == null ? "—" : `${price(state.low)} – ${price(state.high)}`;
  const stats: [string, string][] = [
    ["Previous close", price(instrument.prev_close)],
    ["Open", price(state.open)],
    ["Day's range", range],
    ["Volume", qty(state.volume)],
    ["Average price (VWAP)", price(vwap)],
    ["Trades", qty(state.trades)],
    [`Price band (${instrument.band_pct}%)`, `${price(instrument.lower_band)} – ${price(instrument.upper_band)}`],
    ["Tick size", price(instrument.tick)],
    ["Typical trade (previous day)", `${qty(instrument.avg_trade_qty)} shares`],
  ];
  return (
    <section className="key-stats" aria-label="Key statistics">
      <dl>
        {stats.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd className="num">{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
