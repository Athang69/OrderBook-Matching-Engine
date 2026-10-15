import type { PricePoint, Quote } from "../../api/types";
import { compact, direction, percentChange, price } from "../../lib/format";
import { Sparkline } from "../ui/Sparkline";

interface Props {
  symbols: string[];
  names: Map<string, string>;
  quotes: Record<string, Quote>;
  sparklines: Record<string, PricePoint[]>;
  onSelect: (symbol: string) => void;
}

/** Top gainers, top losers and most active among the stocks in your watchlist. */
export function Movers({ symbols, names, quotes, sparklines, onSelect }: Props) {
  const rows = symbols.flatMap((symbol) => {
    const q = quotes[symbol];
    if (q?.ltp == null || !q.prev_close) return [];
    return [{ symbol, q, change: (q.ltp - q.prev_close) / q.prev_close, turnover: q.volume * q.ltp }];
  });
  const gainers = rows.filter((r) => r.change > 0).sort((a, b) => b.change - a.change).slice(0, 3);
  const losers = rows.filter((r) => r.change < 0).sort((a, b) => a.change - b.change).slice(0, 3);
  const active = [...rows].sort((a, b) => b.turnover - a.turnover).slice(0, 3);

  const list = (title: string, items: typeof rows, extra?: (r: (typeof rows)[number]) => string) => (
    <section className="rail-card" aria-label={title}>
      <h3>{title}</h3>
      {items.length === 0 ? <p className="muted small">None right now.</p> : (
        <ul className="mover-list">
          {items.map((r) => (
            <li key={r.symbol}>
              <button type="button" onClick={() => onSelect(r.symbol)}>
                <span className="mover-name">
                  <span className="link strong">{r.symbol}</span>
                  <span className="muted small ellipsis">{extra ? extra(r) : r.q.name ?? names.get(r.symbol) ?? ""}</span>
                </span>
                <Sparkline points={sparklines[r.symbol] ?? []} base={r.q.prev_close ?? 0} width={64} height={26} label={`${r.symbol} today`} />
                <span className="mover-price">
                  <span className="num strong">{price(r.q.ltp)}</span>
                  <span className={`num small ${direction(r.change)}`}>{percentChange(r.q.ltp, r.q.prev_close)}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );

  return (
    <>
      {list("Watchlist gainers", gainers)}
      {list("Watchlist losers", losers)}
      {list("Most traded in your watchlist", active, (r) => `${compact(r.q.volume)} shares today`)}
    </>
  );
}
