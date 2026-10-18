import type { Portfolio, Quote, Status, SymbolRow } from "../../api/types";
import type { Theme } from "../../hooks/useTheme";
import { direction, money, signedMoney } from "../../lib/format";
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
  theme: Theme;
  onToggleTheme: () => void;
  onSelect: (symbol: string) => void;
}

const LINKS: [string, string][] = [
  ["#summary", "Markets"],
  ["#why", "Why it moved"],
  ["#depth", "Order book"],
  ["#news", "News"],
  ["#recommendations", "Recommendations"],
  ["#account", "Portfolio"],
  ["#watchlist", "Watchlist"],
];

export function TopBar({ symbols, quotes, watchlist, connected, status, now, portfolio, theme, onToggleTheme, onSelect }: Props) {
  return (
    <>
      <header className="topbar">
        <div className="topbar-row container">
          <a className="brand" href="#summary" aria-label="OrderBook, back to the top">
            <svg width="26" height="26" viewBox="0 0 26 26" aria-hidden="true">
              <rect width="26" height="26" rx="7" className="brand-mark" />
              <path d="M7 9h8M7 13h12M7 17h6" className="brand-lines" />
            </svg>
            <span>OrderBook</span>
          </a>
          <StockSearch symbols={symbols} quotes={quotes} watchlist={watchlist} onSelect={onSelect} />
          <div className="topbar-actions">
            <MarketStatus status={status} connected={connected} now={now} />
            <button type="button" className="icon-button" onClick={onToggleTheme} aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}>
              {theme === "dark" ? (
                <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true"><circle cx="9" cy="9" r="3.5" /><path d="M9 1.5v2M9 14.5v2M1.5 9h2M14.5 9h2M3.7 3.7l1.4 1.4M12.9 12.9l1.4 1.4M3.7 14.3l1.4-1.4M12.9 5.1l1.4-1.4" /></svg>
              ) : (
                <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true"><path d="M14.5 11.5A6.5 6.5 0 016.5 3.5a6.5 6.5 0 108 8z" /></svg>
              )}
            </button>
          </div>
        </div>
      </header>
      <nav className="subnav" aria-label="Main">
        <div className="container subnav-row">
          <ul>
            {LINKS.map(([href, text]) => <li key={href}><a href={href}>{text}</a></li>)}
          </ul>
          {portfolio && (
            <dl className="account-chips">
              <div><dt>Available</dt><dd className="num">{money(portfolio.available)}</dd></div>
              <div><dt>Account value</dt><dd className="num">{money(portfolio.equity)}</dd></div>
              <div><dt>Profit / loss after charges</dt><dd className={`num ${direction(portfolio.net_pnl)}`}>{signedMoney(portfolio.net_pnl)}</dd></div>
            </dl>
          )}
        </div>
      </nav>
    </>
  );
}
