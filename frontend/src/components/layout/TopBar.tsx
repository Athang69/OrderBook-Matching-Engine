import type { Portfolio, Quote, Status, SymbolRow } from "../../api/types";
import { direction, signedMoney } from "../../lib/format";
import { MarketStatus } from "./MarketStatus";
import { StockSearch } from "./StockSearch";

interface Props {
  symbols: SymbolRow[];
  quotes: Record<string, Quote>;
  watchlist: string[];
  connected: boolean;
  status: Status | null;
  now: number;
  portfolio: Portfolio | null;
  onSelect: (symbol: string) => void;
  onGlobalSelect?: (ticker: string) => void;
}

export function TopBar({ symbols, quotes, watchlist, connected, status, now, portfolio, onSelect, onGlobalSelect }: Props) {
  return (
    <header className="topbar">
      <div className="topbar-row container">
        <a className="brand" href="/" aria-label="OrderBook home">
          <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true">
            <rect width="24" height="24" rx="6" className="brand-mark" />
            <path d="M7 8h6M7 12h10M7 16h4" className="brand-lines" strokeWidth="2" strokeLinecap="round" />
          </svg>
          <span>OrderBook</span>
        </a>

        <StockSearch
          symbols={symbols}
          quotes={quotes}
          watchlist={watchlist}
          onSelect={onSelect}
          onGlobalSelect={onGlobalSelect}
        />

        <div className="topbar-actions">
          <MarketStatus status={status} connected={connected} now={now} />

          {portfolio && (
            <div className="topbar-pnl">
              <span className="muted" style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.05em", textTransform: "uppercase" }}>P&amp;L</span>
              <span className={`num strong ${direction(portfolio.net_pnl)}`} style={{ fontSize: 13 }}>
                {signedMoney(portfolio.net_pnl)}
              </span>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
