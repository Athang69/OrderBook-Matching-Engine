import type { Portfolio, SimStatus } from "../api";
import { direction, longDate, money, signedMoney } from "../format";

interface Props {
  connected: boolean;
  sim: SimStatus | null;
  portfolio: Portfolio | null;
  onToggleBots: (enabled: boolean) => void;
}

export function Header({ connected, sim, portfolio, onToggleBots }: Props) {
  const percent = sim ? Math.round(sim.progress * 100) : 0;
  const pnl = portfolio ? portfolio.realised_pnl + portfolio.unrealised_pnl : 0;

  return (
    <header className="topbar">
      <div className="brand">
        <strong>Order Book Simulator</strong>
        <span className="muted">NSE cash market, virtual money</span>
      </div>

      {sim && (
        <div className="session">
          <div className="session-text">
            <span>Replaying {longDate(sim.data_date)}</span>
            <span className="muted">
              {sim.bots_enabled ? `${percent}% of the session` : "robot traders paused"}
            </span>
          </div>
          <div className="progress" role="progressbar" aria-label="Session progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}>
            <div style={{ width: `${percent}%` }} />
          </div>
          <button className="ghost" onClick={() => onToggleBots(!sim.bots_enabled)}>
            {sim.bots_enabled ? "Pause robot traders" : "Resume robot traders"}
          </button>
        </div>
      )}

      <div className="funds">
        <Stat label="Available cash" value={portfolio ? money(portfolio.available) : "—"} />
        <Stat label="Account value" value={portfolio ? money(portfolio.equity) : "—"} />
        <Stat label="Profit / loss" value={portfolio ? signedMoney(pnl) : "—"} tone={direction(pnl)} />
        <span className={`pill ${connected ? "ok" : "bad"}`}>{connected ? "Live" : "Reconnecting"}</span>
      </div>
    </header>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="stat">
      <span className="muted">{label}</span>
      <span className={`num ${tone ?? ""}`}>{value}</span>
    </div>
  );
}
