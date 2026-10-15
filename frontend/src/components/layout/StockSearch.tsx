import { useId, useMemo, useState, type KeyboardEvent } from "react";

import type { Quote, SymbolRow } from "../../api/types";
import { direction, percentChange, price } from "../../lib/format";

interface Props {
  symbols: SymbolRow[];
  quotes: Record<string, Quote>;
  watchlist: string[];
  onSelect: (symbol: string) => void;
  placeholder?: string;
  /** Leaves the text in the box after a choice (used inside forms). */
  keepOpen?: boolean;
}

const MAX_RESULTS = 12;

/** Search every NSE stock by symbol or company name; arrow keys move, Enter opens, Escape closes. */
export function StockSearch({ symbols, quotes, watchlist, onSelect, placeholder, keepOpen }: Props) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const listId = useId();
  const index = useMemo(() => symbols.map(([s, n]) => [s.toLowerCase(), n.toLowerCase()] as const), [symbols]);
  const bySymbol = useMemo(() => new Map(symbols.map((row) => [row[0], row])), [symbols]);

  const q = query.trim().toLowerCase();
  const matches: SymbolRow[] = useMemo(() => {
    if (!q) return watchlist.map((s) => bySymbol.get(s)).filter((row): row is SymbolRow => !!row).slice(0, MAX_RESULTS);
    const ranked: [number, number][] = [];
    for (let i = 0; i < index.length; i++) {
      const [s, n] = index[i];
      let rank = -1;
      if (s === q) rank = 0;
      else if (s.startsWith(q)) rank = 1;
      else if (n.startsWith(q) || n.includes(` ${q}`)) rank = 2;
      else if (s.includes(q)) rank = 3;
      else if (n.includes(q)) rank = 4;
      if (rank >= 0) ranked.push([rank, i]);
    }
    ranked.sort((a, b) => a[0] - b[0] || index[a[1]][0].length - index[b[1]][0].length);
    return ranked.slice(0, MAX_RESULTS).map(([, i]) => symbols[i]);
  }, [q, index, symbols, watchlist, bySymbol]);

  const choose = (symbol: string) => {
    onSelect(symbol);
    setQuery("");
    if (!keepOpen) setOpen(false);
    setActive(0);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setOpen(true);
      setActive((a) => Math.min(a + 1, matches.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      if (matches[active]) choose(matches[active][0]);
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  };

  return (
    <div className="search">
      <svg className="search-icon" width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
        <circle cx="7" cy="7" r="5" /><path d="M11 11l3.5 3.5" />
      </svg>
      <input type="search" role="combobox" aria-expanded={open && matches.length > 0} aria-controls={listId}
        aria-activedescendant={open && matches[active] ? `${listId}-${active}` : undefined}
        aria-autocomplete="list" placeholder={placeholder ?? `Search ${symbols.length ? symbols.length.toLocaleString("en-IN") : ""} NSE stocks by symbol or company`}
        value={query} onChange={(e) => { setQuery(e.target.value); setOpen(true); setActive(0); }}
        onFocus={() => setOpen(true)} onBlur={() => window.setTimeout(() => setOpen(false), 120)} onKeyDown={onKeyDown} />
      {open && matches.length > 0 && (
        <ul id={listId} role="listbox" className="search-results">
          {!q && <li className="search-heading" role="presentation">Your watchlist</li>}
          {matches.map(([symbol, name, series], i) => {
            const quote = quotes[symbol];
            const ltp = quote?.ltp ?? null;
            return (
              <li key={symbol} id={`${listId}-${i}`} role="option" aria-selected={i === active}
                className={i === active ? "active" : ""} onMouseDown={(e) => e.preventDefault()}
                onMouseEnter={() => setActive(i)} onClick={() => choose(symbol)}>
                <span className="symbol">{symbol}{series !== "EQ" && <span className="series-tag">{series}</span>}</span>
                <span className="company">{name}</span>
                <span className="num">{ltp == null ? "" : price(ltp)}</span>
                <span className={`num ${ltp == null || !quote?.prev_close ? "" : direction(ltp - quote.prev_close)}`}>
                  {ltp == null ? "NSE" : percentChange(ltp, quote?.prev_close)}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
