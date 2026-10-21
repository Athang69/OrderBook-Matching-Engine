import { useId, useMemo, useState, useEffect, useRef, type KeyboardEvent } from "react";

import { api } from "../../api/client";
import type { GlobalSearchResult, Quote, SymbolRow } from "../../api/types";
import { direction, percentChange, price } from "../../lib/format";

interface Props {
  symbols: SymbolRow[];
  quotes: Record<string, Quote>;
  watchlist: string[];
  onSelect: (symbol: string) => void;
  onGlobalSelect?: (ticker: string) => void;
  placeholder?: string;
  keepOpen?: boolean;
}

const MAX_NSE = 8;
const MAX_GLOBAL = 5;

export function StockSearch({ symbols, quotes, watchlist, onSelect, onGlobalSelect, placeholder, keepOpen }: Props) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [globalResults, setGlobalResults] = useState<GlobalSearchResult[]>([]);
  const [globalLoading, setGlobalLoading] = useState(false);
  const listId = useId();
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const index = useMemo(() => symbols.map(([s, n]) => [s.toLowerCase(), n.toLowerCase()] as const), [symbols]);
  const bySymbol = useMemo(() => new Map(symbols.map((row) => [row[0], row])), [symbols]);

  const q = query.trim().toLowerCase();

  const nseMatches: SymbolRow[] = useMemo(() => {
    if (!q) return watchlist.map((s) => bySymbol.get(s)).filter((row): row is SymbolRow => !!row).slice(0, MAX_NSE);
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
    return ranked.slice(0, MAX_NSE).map(([, i]) => symbols[i]);
  }, [q, index, symbols, watchlist, bySymbol]);

  // Global search: fire after 400 ms when query is non-empty
  useEffect(() => {
    if (!q || q.length < 2) { setGlobalResults([]); return; }
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      setGlobalLoading(true);
      try {
        const data = await api.globalSearch(q);
        setGlobalResults(data.results.slice(0, MAX_GLOBAL));
      } catch {
        setGlobalResults([]);
      } finally {
        setGlobalLoading(false);
      }
    }, 400);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [q]);

  const totalItems = nseMatches.length + globalResults.length;

  const choose = (symbol: string) => {
    onSelect(symbol);
    setQuery("");
    setGlobalResults([]);
    if (!keepOpen) setOpen(false);
    setActive(0);
  };

  const chooseGlobal = (ticker: string) => {
    if (onGlobalSelect) onGlobalSelect(ticker);
    setQuery("");
    setGlobalResults([]);
    if (!keepOpen) setOpen(false);
    setActive(0);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setOpen(true);
      setActive((a) => Math.min(a + 1, totalItems - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      if (active < nseMatches.length) {
        if (nseMatches[active]) choose(nseMatches[active][0]);
      } else {
        const g = globalResults[active - nseMatches.length];
        if (g) chooseGlobal(g.ticker);
      }
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  };

  const showDropdown = open && (nseMatches.length > 0 || (q.length >= 2 && (globalLoading || globalResults.length > 0)));

  return (
    <div className="search">
      <svg className="search-icon" width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
        <circle cx="7" cy="7" r="5" /><path d="M11 11l3.5 3.5" />
      </svg>
      <input
        type="search"
        role="combobox"
        aria-expanded={showDropdown}
        aria-controls={listId}
        aria-activedescendant={showDropdown && active >= 0 ? `${listId}-${active}` : undefined}
        aria-autocomplete="list"
        placeholder={placeholder ?? `Search ${symbols.length ? symbols.length.toLocaleString("en-IN") : ""} NSE stocks or any global ticker`}
        value={query}
        onChange={(e) => { setQuery(e.target.value); setOpen(true); setActive(0); }}
        onFocus={() => setOpen(true)}
        onBlur={() => window.setTimeout(() => setOpen(false), 150)}
        onKeyDown={onKeyDown}
      />
      {showDropdown && (
        <ul id={listId} role="listbox" className="search-results">
          {/* NSE stocks */}
          {nseMatches.length > 0 && (
            <>
              {!q && <li className="search-heading" role="presentation">Your watchlist</li>}
              {q && <li className="search-heading" role="presentation">NSE</li>}
              {nseMatches.map(([symbol, name, series], i) => {
                const quote = quotes[symbol];
                const ltp = quote?.ltp ?? null;
                return (
                  <li key={symbol} id={`${listId}-${i}`} role="option" aria-selected={i === active}
                    className={i === active ? "active" : ""}
                    onMouseDown={(e) => e.preventDefault()}
                    onMouseEnter={() => setActive(i)}
                    onClick={() => choose(symbol)}>
                    <span className="symbol">{symbol}{series !== "EQ" && <span className="series-tag">{series}</span>}</span>
                    <span className="company">{name}</span>
                    <span className="num">{ltp == null ? "" : price(ltp)}</span>
                    <span className={`num ${ltp == null || !quote?.prev_close ? "" : direction(ltp - quote.prev_close)}`}>
                      {ltp == null ? "NSE" : percentChange(ltp, quote?.prev_close)}
                    </span>
                  </li>
                );
              })}
            </>
          )}

          {/* Global stocks */}
          {q.length >= 2 && (
            <>
              <li className="search-heading" role="presentation">
                {globalLoading ? "Searching global markets…" : globalResults.length > 0 ? "Global markets" : nseMatches.length === 0 ? "No NSE match — global markets" : "Also globally"}
              </li>
              {globalResults.map((r, gi) => {
                const i = nseMatches.length + gi;
                return (
                  <li key={r.ticker} id={`${listId}-${i}`} role="option" aria-selected={i === active}
                    className={i === active ? "active" : ""}
                    onMouseDown={(e) => e.preventDefault()}
                    onMouseEnter={() => setActive(i)}
                    onClick={() => chooseGlobal(r.ticker)}>
                    <span className="symbol">{r.ticker}</span>
                    <span className="company">{r.name}</span>
                    <span className="num" style={{ color: "var(--faint)", fontSize: 11 }}>{r.exchange}</span>
                    <span className="num" style={{ color: "var(--faint)", fontSize: 11 }}>{r.type}</span>
                  </li>
                );
              })}
            </>
          )}
        </ul>
      )}
    </div>
  );
}
