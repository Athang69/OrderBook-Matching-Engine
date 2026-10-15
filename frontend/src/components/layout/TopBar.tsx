import type { Instrument, MarketState, Portfolio, SimStatus } from "../../api/types";
import { direction, longDate, money, signedMoney } from "../../lib/format";
import type { Theme } from "../../hooks/useTheme";
import { StockSearch } from "./StockSearch";

interface Props {
  instruments: Instrument[];
  market: Record<string, MarketState>;
  connected: boolean;
  sim: SimStatus | null;
  portfolio: Portfolio | null;
  theme: Theme;
  onToggleTheme: () => void;
  onToggleBots: (enabled: boolean) => void;
  onSelect: (symbol: string) => void;
}

const LINKS: [string, string][] = [
  ["#summary", "Markets"],
  ["#depth", "Order book"],
  ["#news", "News"],
  ["#recommendations", "Recommendations"],
  ["#account", "Portfolio"],
];

export function TopBar({ instruments, market, connected, sim, portfolio, theme, onToggleTheme, onToggleBots, onSelect }: Props) {
  const percent = sim ? Math.round(sim.progress * 100) : 0;
  const pnl = portfolio ? portfolio.realised_pnl + portfolio.unrealised_pnl : 0;
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
        <StockSearch instruments={instruments} market={market} onSelect={onSelect} />
        <div className="topbar-actions">
          {sim && (
            <div className="session" title={`${sim.elapsed_seconds.toFixed(0)} of ${sim.session_seconds} seconds`}>
              <span className={`status-dot ${connected ? (sim.bots_enabled ? "live" : "paused") : "off"}`} aria-hidden="true" />
              <span>
                {connected ? (sim.bots_enabled ? "Replaying" : "Paused") : "Reconnecting"} {longDate(sim.data_date)}
              </span>
              <span className="progress" role="progressbar" aria-label="Session progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}>
                <span style={{ width: `${percent}%` }} />
              </span>
            </div>
          )}
          {sim && (
            <button type="button" className="button ghost small" onClick={() => onToggleBots(!sim.bots_enabled)}>
              {sim.bots_enabled ? "Pause robot traders" : "Resume robot traders"}
            </button>
          )}
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
              <div><dt>Profit / loss</dt><dd className={`num ${direction(pnl)}`}>{signedMoney(pnl)}</dd></div>
            </dl>
          )}
        </div>
      </nav>
    </>
  );
}
