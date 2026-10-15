import { useId, useState, type KeyboardEvent } from "react";

import type { Instrument, MarketState } from "../../api/types";
import { direction, percentChange, price } from "../../lib/format";

interface Props {
  instruments: Instrument[];
  market: Record<string, MarketState>;
  onSelect: (symbol: string) => void;
}

/** Search by symbol or company name; arrow keys move, Enter opens, Escape closes. */
export function StockSearch({ instruments, market, onSelect }: Props) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const listId = useId();
  const q = query.trim().toLowerCase();
  const matches = instruments.filter((i) => !q || i.symbol.toLowerCase().includes(q) || i.company.toLowerCase().includes(q));

  const choose = (symbol: string) => {
    onSelect(symbol);
    setQuery("");
    setOpen(false);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setOpen(true);
      setActive((a) => Math.min(a + 1, matches.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (event.key === "Enter" && matches[active]) {
      choose(matches[active].symbol);
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
        aria-activedescendant={open && matches[active] ? `${listId}-${matches[active].symbol}` : undefined}
        aria-autocomplete="list" placeholder="Search stocks by symbol or company" value={query}
        onChange={(e) => { setQuery(e.target.value); setOpen(true); setActive(0); }}
        onFocus={() => setOpen(true)} onBlur={() => window.setTimeout(() => setOpen(false), 120)} onKeyDown={onKeyDown} />
      {open && matches.length > 0 && (
        <ul id={listId} role="listbox" className="search-results">
          {matches.map((instrument, i) => {
            const ltp = market[instrument.symbol]?.ltp ?? null;
            return (
              <li key={instrument.symbol} id={`${listId}-${instrument.symbol}`} role="option" aria-selected={i === active}
                className={i === active ? "active" : ""} onMouseDown={(e) => e.preventDefault()}
                onMouseEnter={() => setActive(i)} onClick={() => choose(instrument.symbol)}>
                <span className="symbol">{instrument.symbol}</span>
                <span className="company">{instrument.company}</span>
                <span className="num">{price(ltp ?? instrument.prev_close)}</span>
                <span className={`num ${ltp == null ? "" : direction(ltp - instrument.prev_close)}`}>{percentChange(ltp, instrument.prev_close)}</span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
