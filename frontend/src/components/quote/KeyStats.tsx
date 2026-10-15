import type { Instrument, Quote } from "../../api/types";
import { compact, crores, price } from "../../lib/format";

/** The figures a broker's stock page shows, all from the live quote except the day's rules from NSE. */
export function KeyStats({ instrument, quote }: { instrument: Instrument; quote: Quote | undefined }) {
  const q = quote;
  const range = (low: number | null | undefined, high: number | null | undefined) =>
    low == null || high == null ? "—" : `${price(low)} – ${price(high)}`;
  const stats: [string, string][] = [
    ["Previous close", price(q?.prev_close ?? instrument.close)],
    ["Open", price(q?.open)],
    ["Day's range", range(q?.low, q?.high)],
    ["52-week range", range(q?.week52_low, q?.week52_high)],
    ["Volume", compact(q?.volume || null)],
    ["Average volume (3 months)", compact(q?.avg_volume)],
    ["Average price today (VWAP)", price(q?.vwap)],
    ["Market value", crores(q?.market_cap)],
    ["P/E ratio (12 months)", q?.pe == null ? "—" : q.pe.toFixed(2)],
    ["Earnings per share", q?.eps == null ? "—" : `₹${q.eps.toFixed(2)}`],
    ["Dividend yield", q?.dividend_yield == null ? "—" : `${q.dividend_yield.toFixed(2)}%`],
    ["Price to book", q?.price_to_book == null ? "—" : q.price_to_book.toFixed(2)],
    [`Price band (${instrument.band_pct}%)`, range(instrument.lower_band, instrument.upper_band)],
    ["Tick size", price(instrument.tick)],
    ["Series", instrument.series === "BE" ? "BE (trade for trade)" : "EQ (normal market)"],
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
