import type { Portfolio } from "../../api/types";
import { direction, money, signedMoney } from "../../lib/format";

/** The account at a glance, in the right-hand rail. */
export function AccountSummary({ portfolio }: { portfolio: Portfolio | null }) {
  if (!portfolio) return null;
  const positions = portfolio.holdings.length + portfolio.intraday.length;
  const rows: [string, string, string?][] = [
    ["Available cash", money(portfolio.available)],
    ["Holdings value", money(portfolio.holdings_value)],
    ["Intraday margin", money(portfolio.intraday_margin)],
    ["Realised profit / loss", signedMoney(portfolio.realised_pnl), direction(portfolio.realised_pnl)],
    ["Unrealised profit / loss", signedMoney(portfolio.unrealised_pnl), direction(portfolio.unrealised_pnl)],
    ["Charges paid", money(portfolio.charges.total)],
  ];
  return (
    <section className="rail-card" aria-labelledby="summary-title">
      <h3 id="summary-title">Your account</h3>
      <p className="account-value num">{money(portfolio.equity)}</p>
      <p className={`num small ${direction(portfolio.net_pnl)}`}>
        {signedMoney(portfolio.net_pnl)} after charges {"·"} {positions} open position{positions === 1 ? "" : "s"}
      </p>
      <dl className="mini-stats">
        {rows.map(([label, value, tone]) => (
          <div key={label}><dt>{label}</dt><dd className={`num ${tone ?? ""}`}>{value}</dd></div>
        ))}
      </dl>
      <a className="link small" href="#account">See positions and orders</a>
    </section>
  );
}
