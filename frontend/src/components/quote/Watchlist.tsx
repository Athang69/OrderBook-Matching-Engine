import type { PricePoint, Quote } from "../../api/types";
import { direction, percentChange, price } from "../../lib/format";
import { Sparkline } from "../ui/Sparkline";

interface Props {
  watchlist: string[];
  names: Map<string, string>;
  quotes: Record<string, Quote>;
  sparklines: Record<string, PricePoint[]>;
  selected: string;
  onSelect: (symbol: string) => void;
  onRemove: (symbol: string) => void;
}

/** Your watchlist as cards; search for any NSE stock and star it to add it here. */
export function Watchlist({ watchlist, names, quotes, sparklines, selected, onSelect, onRemove }: Props) {
  return (
    <section className="section" id="watchlist" aria-labelledby="watchlist-title">
      <h2 id="watchlist-title" className="section-title">Your watchlist</h2>
      {watchlist.length === 0 ? (
        <p className="muted">Empty. Search for a stock and click "Add to watchlist".</p>
      ) : (
        <div className="other-grid">
          {watchlist.map((symbol) => {
            const quote = quotes[symbol];
            const ltp = quote?.ltp ?? null;
            const base = quote?.prev_close ?? ltp ?? 0;
            return (
              <div key={symbol} className={symbol === selected ? "other-card selected" : "other-card"}>
                <button type="button" className="other-open" onClick={() => { onSelect(symbol); window.scrollTo({ top: 0, behavior: "smooth" }); }}>
                  <span className="link strong">{symbol}</span>
                  <span className="muted small ellipsis">{quote?.name ?? names.get(symbol) ?? ""}</span>
                  <span>
                    <span className="num strong">{price(ltp)}</span>{" "}
                    <span className={`num small ${ltp == null ? "" : direction(ltp - base)}`}>{percentChange(ltp, base)}</span>
                  </span>
                  <Sparkline points={sparklines[symbol] ?? []} base={base} width={140} height={32} label={`${symbol} today`} />
                </button>
                <button type="button" className="other-remove" aria-label={`Remove ${symbol} from the watchlist`} onClick={() => onRemove(symbol)}>
                  <svg width="12" height="12" viewBox="0 0 16 16" aria-hidden="true"><path d="M3 3l10 10M13 3L3 13" /></svg>
                </button>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
