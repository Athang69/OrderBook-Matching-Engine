import type { Quote, SymbolRow } from "../../api/types";
import { direction, percentChange, price } from "../../lib/format";
import { StockSearch } from "../layout/StockSearch";

interface Props {
  symbols: SymbolRow[];
  quotes: Record<string, Quote>;
  watchlist: string[];
  selected: string[];
  onChange: (selected: string[]) => void;
  max: number;
}

/** Search any NSE stock to add it; your watchlist is one click away. */
export function StockPicker({ symbols, quotes, watchlist, selected, onChange, max }: Props) {
  const add = (symbol: string) => {
    if (!selected.includes(symbol) && selected.length < max) onChange([...selected, symbol]);
  };
  const remove = (symbol: string) => onChange(selected.filter((s) => s !== symbol));
  const names = new Map(symbols.map(([s, n]) => [s, n]));
  const quick = watchlist.filter((s) => !selected.includes(s));
  return (
    <div className="picker">
      <div className="picker-search">
        <StockSearch symbols={symbols} quotes={quotes} watchlist={quick} onSelect={add} keepOpen
          placeholder={selected.length >= max ? `At most ${max} stocks` : "Add a stock: search by symbol or company"} />
        <span className="muted small">{selected.length} of {max} chosen</span>
      </div>
      {selected.length > 0 && (
        <ul className="picked">
          {selected.map((symbol) => {
            const q = quotes[symbol];
            return (
              <li key={symbol}>
                <span className="pick-name">
                  <span className="strong">{symbol}</span>
                  <span className="muted small ellipsis">{q?.name ?? names.get(symbol) ?? ""}</span>
                </span>
                <span className="pick-price">
                  <span className="num">{price(q?.ltp)}</span>
                  <span className={`num small ${q?.ltp == null || !q.prev_close ? "" : direction(q.ltp - q.prev_close)}`}>{percentChange(q?.ltp, q?.prev_close)}</span>
                </span>
                <button type="button" className="icon-button small" aria-label={`Remove ${symbol}`} onClick={() => remove(symbol)}>
                  <svg width="12" height="12" viewBox="0 0 16 16" aria-hidden="true"><path d="M3 3l10 10M13 3L3 13" /></svg>
                </button>
              </li>
            );
          })}
        </ul>
      )}
      {quick.length > 0 && selected.length < max && (
        <div className="quick-add">
          <span className="muted small">From your watchlist:</span>
          {quick.slice(0, 12).map((symbol) => (
            <button key={symbol} type="button" className="chip-button" onClick={() => add(symbol)}>+ {symbol}</button>
          ))}
          {quick.length > 1 && (
            <button type="button" className="chip-button" onClick={() => onChange([...selected, ...quick].slice(0, max))}>Add all</button>
          )}
        </div>
      )}
    </div>
  );
}
