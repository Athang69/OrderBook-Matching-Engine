/**
 * Home dashboard — shown when no stock is selected.
 * Shows portfolio summary, watchlist, movers, and a prompt to search.
 */
import type { Portfolio, PricePoint, Quote, SymbolRow } from "../../api/types";
import { direction, money, percentChange, price, signedMoney } from "../../lib/format";
import { Sparkline } from "../ui/Sparkline";

interface Props {
  watchlist: string[];
  names: Map<string, string>;
  quotes: Record<string, Quote>;
  sparklines: Record<string, PricePoint[]>;
  portfolio: Portfolio | null;
  onSelect: (symbol: string) => void;
  symbolRows: SymbolRow[];
}

export function Dashboard({ watchlist, names, quotes, sparklines, portfolio, onSelect, symbolRows }: Props) {
  const rows = watchlist.flatMap((symbol) => {
    const q = quotes[symbol];
    if (q?.ltp == null || !q.prev_close) return [];
    return [{ symbol, q, change: (q.ltp - q.prev_close) / q.prev_close }];
  });
  const gainers = rows.filter((r) => r.change > 0).sort((a, b) => b.change - a.change).slice(0, 5);
  const losers  = rows.filter((r) => r.change < 0).sort((a, b) => a.change - b.change).slice(0, 5);

  return (
    <div className="dashboard-body">
      {/* Hero prompt */}
      <div className="dash-hero">
        <h1 className="dash-hero-title">Good{greeting()}.</h1>
        <p className="dash-hero-sub">
          Search for any NSE stock above to view its quote, chart, and place paper trades.
        </p>
      </div>

      <div className="dash-grid">
        {/* Watchlist */}
        <section className="card dash-watchlist" aria-label="Your watchlist">
          <div className="card-head">
            <h2 className="card-title">Watchlist</h2>
            <span className="muted small">{watchlist.length} stocks</span>
          </div>
          {watchlist.length === 0 ? (
            <p className="empty" style={{ minHeight: 60 }}>
              Search for a stock and star it to add it here.
            </p>
          ) : (
            <ul className="wl-list">
              {watchlist.map((symbol) => {
                const quote = quotes[symbol];
                const ltp = quote?.ltp ?? null;
                const base = quote?.prev_close ?? ltp ?? 0;
                const change = ltp != null && base ? ltp - base : 0;
                return (
                  <li key={symbol}>
                    <button type="button" className="wl-row" onClick={() => onSelect(symbol)}>
                      <div className="wl-name">
                        <span className="strong">{symbol}</span>
                        <span className="muted small ellipsis">{quote?.name ?? names.get(symbol) ?? ""}</span>
                      </div>
                      <Sparkline points={sparklines[symbol] ?? []} base={base} width={80} height={28} label={`${symbol} today`} />
                      <div className="wl-price">
                        <span className="num strong">{price(ltp)}</span>
                        <span className={`num small ${ltp == null ? "" : direction(change)}`}>
                          {percentChange(ltp, base)}
                        </span>
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        {/* Gainers & Losers */}
        <div className="dash-movers">
          <section className="card" aria-label="Top gainers">
            <div className="card-head">
              <h2 className="card-title">Gainers</h2>
            </div>
            {gainers.length === 0 ? (
              <p className="empty" style={{ minHeight: 40, fontSize: 12 }}>No data yet.</p>
            ) : (
              <ul className="mover-mini-list">
                {gainers.map((r) => (
                  <li key={r.symbol}>
                    <button type="button" className="mover-mini-row" onClick={() => onSelect(r.symbol)}>
                      <span className="strong">{r.symbol}</span>
                      <span className="num muted small">{price(r.q.ltp)}</span>
                      <span className="num up strong small">{percentChange(r.q.ltp, r.q.prev_close)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="card" aria-label="Top losers">
            <div className="card-head">
              <h2 className="card-title">Losers</h2>
            </div>
            {losers.length === 0 ? (
              <p className="empty" style={{ minHeight: 40, fontSize: 12 }}>No data yet.</p>
            ) : (
              <ul className="mover-mini-list">
                {losers.map((r) => (
                  <li key={r.symbol}>
                    <button type="button" className="mover-mini-row" onClick={() => onSelect(r.symbol)}>
                      <span className="strong">{r.symbol}</span>
                      <span className="num muted small">{price(r.q.ltp)}</span>
                      <span className="num down strong small">{percentChange(r.q.ltp, r.q.prev_close)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>

        {/* Portfolio summary */}
        {portfolio && (
          <section className="card dash-portfolio" aria-label="Portfolio summary">
            <div className="card-head">
              <h2 className="card-title">Portfolio</h2>
            </div>
            <div className="port-value">
              <span className="port-num">{money(portfolio.equity)}</span>
              <span className={`num ${direction(portfolio.net_pnl)}`} style={{ fontSize: 13, fontWeight: 600 }}>
                {signedMoney(portfolio.net_pnl)} all-time
              </span>
            </div>
            <div className="port-stats">
              <div><span className="muted small">Available</span><span className="num strong">{money(portfolio.available)}</span></div>
              <div><span className="muted small">Holdings</span><span className="num strong">{money(portfolio.holdings_value)}</span></div>
              <div><span className="muted small">Unrealised P&amp;L</span><span className={`num strong ${direction(portfolio.unrealised_pnl)}`}>{signedMoney(portfolio.unrealised_pnl)}</span></div>
              <div><span className="muted small">Positions</span><span className="num strong">{portfolio.holdings.length + portfolio.intraday.length}</span></div>
            </div>

            {(portfolio.holdings.length > 0 || portfolio.intraday.length > 0) && (
              <>
                <div style={{ height: 1, background: "var(--border)", margin: "12px 0" }} />
                <ul className="port-positions">
                  {portfolio.holdings.slice(0, 5).map((h) => (
                    <li key={h.symbol}>
                      <button type="button" className="mover-mini-row" onClick={() => onSelect(h.symbol)}>
                        <span className="strong">{h.symbol}</span>
                        <span className="num muted small">{h.qty} shares</span>
                        <span className={`num strong small ${direction(h.unrealised_pnl)}`}>
                          {signedMoney(h.unrealised_pnl)}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </section>
        )}

        {/* Market counts */}
        <section className="card dash-stats" aria-label="Market overview">
          <div className="card-head">
            <h2 className="card-title">NSE Universe</h2>
          </div>
          <div className="stat-grid">
            <div className="stat-cell">
              <span className="stat-value">{symbolRows.length.toLocaleString()}</span>
              <span className="stat-label">Tradeable stocks</span>
            </div>
            <div className="stat-cell">
              <span className="stat-value up">{rows.filter((r) => r.change > 0).length}</span>
              <span className="stat-label">Advancing in watchlist</span>
            </div>
            <div className="stat-cell">
              <span className="stat-value down">{rows.filter((r) => r.change < 0).length}</span>
              <span className="stat-label">Declining in watchlist</span>
            </div>
            <div className="stat-cell">
              <span className="stat-value">{watchlist.length}</span>
              <span className="stat-label">Watched stocks</span>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

function greeting(): string {
  const h = new Date().getHours();
  if (h < 12) return " morning";
  if (h < 17) return " afternoon";
  return " evening";
}
