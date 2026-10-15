import type { Instrument, MarketState, PricePoint } from "../../api/types";
import { direction, percentChange, price, qty } from "../../lib/format";
import { Sparkline } from "../ui/Sparkline";

interface Props {
  instruments: Instrument[];
  market: Record<string, MarketState>;
  history: Record<string, PricePoint[]>;
  onSelect: (symbol: string) => void;
}

const SPARK_SECONDS = 300;

/** Top gainers, top losers and most active, among the simulator's stocks. */
export function Movers({ instruments, market, history, onSelect }: Props) {
  const rows = instruments.map((i) => {
    const ltp = market[i.symbol]?.ltp ?? null;
    return { instrument: i, ltp, change: ltp == null ? 0 : (ltp - i.prev_close) / i.prev_close, volume: market[i.symbol]?.volume ?? 0 };
  });
  const gainers = rows.filter((r) => r.change > 0).sort((a, b) => b.change - a.change).slice(0, 3);
  const losers = rows.filter((r) => r.change < 0).sort((a, b) => a.change - b.change).slice(0, 3);
  const active = [...rows].sort((a, b) => b.volume - a.volume).slice(0, 3);

  const list = (title: string, items: typeof rows, extra?: (r: (typeof rows)[number]) => string) => (
    <section className="rail-card" aria-label={title}>
      <h3>{title}</h3>
      {items.length === 0 ? <p className="muted small">None right now.</p> : (
        <ul className="mover-list">
          {items.map((r) => {
            const points = (history[r.instrument.symbol] ?? []).filter((p, _, all) => p[0] >= all[all.length - 1][0] - SPARK_SECONDS);
            return (
              <li key={r.instrument.symbol}>
                <button type="button" onClick={() => onSelect(r.instrument.symbol)}>
                  <span className="mover-name">
                    <span className="link strong">{r.instrument.symbol}</span>
                    <span className="muted small ellipsis">{extra ? extra(r) : r.instrument.company}</span>
                  </span>
                  <Sparkline points={points} base={r.instrument.prev_close} width={64} height={26} label={`${r.instrument.symbol}, last five minutes`} />
                  <span className="mover-price">
                    <span className="num strong">{price(r.ltp ?? r.instrument.prev_close)}</span>
                    <span className={`num small ${direction(r.change)}`}>{percentChange(r.ltp, r.instrument.prev_close)}</span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );

  return (
    <>
      {list("Top gainers", gainers)}
      {list("Top losers", losers)}
      {list("Most active", active, (r) => `${qty(r.volume)} shares traded`)}
    </>
  );
}
