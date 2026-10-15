import { useEffect, useRef, useState, type FormEvent } from "react";

import { api } from "../../api/client";
import type { Confidences, Portfolio, Quote, Recommendation, SymbolRow } from "../../api/types";
import { direction, longDate, money, price, qty } from "../../lib/format";
import { ConfidenceMeter } from "../ui/ConfidenceMeter";
import { Modal } from "../ui/Modal";
import { FrontierChart, type FrontierMarker } from "./FrontierChart";
import { placeMarketOrders, type OrderOutcome } from "./placeOrders";
import { StockPicker } from "./StockPicker";
import { YourViews } from "./YourViews";

interface Props {
  open: boolean;
  onClose: () => void;
  symbols: SymbolRow[];
  names: Map<string, string>;
  quotes: Record<string, Quote>;
  watchlist: string[];
  portfolio: Portfolio | null;
  /** The stock on screen, chosen when the pop-up first opens. */
  preselect: string;
  /** Asks for live prices of the chosen stocks. */
  onFollow: (symbols: string[]) => void;
  onOrdersPlaced: () => void;
  onResult: (result: Recommendation) => void;
}

type Step = "choose" | "views" | "running" | "result";

const MAX_STOCKS = 10;
const DEFAULT_BUDGET_RUPEES = 1_00_000;

const pct = (fraction: number, digits = 1) => `${(fraction * 100).toFixed(digits)}%`;
/** Agreement comes in steps of 0.5% (200 re-runs): "72%" or "34.5%". */
const share = (fraction: number) => `${Math.round(fraction * 1000) / 10}%`;

/** Delivery: choose stocks, read their news and give your view of each, then see what to buy. */
export function DeliveryModal({ open, onClose, symbols, names, quotes, watchlist, portfolio, preselect, onFollow, onOrdersPlaced, onResult }: Props) {
  const request = useRef(0); // ignores answers the user has walked away from
  const [step, setStep] = useState<Step>("choose");
  const [selected, setSelected] = useState<string[]>([]);
  const [confidences, setConfidences] = useState<Confidences>({});
  const [budget, setBudget] = useState("");
  const [touched, setTouched] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<Recommendation | null>(null);
  const [placing, setPlacing] = useState(false);
  const [outcomes, setOutcomes] = useState<OrderOutcome[] | null>(null);
  const available = portfolio?.available ?? 0;

  useEffect(() => {
    if (!open) return;
    setStep("choose");
    setError("");
    setTouched(false);
    setOutcomes(null);
    setSelected((current) => (current.length > 0 ? current : preselect ? [preselect] : []));
    setBudget((current) => current || String(Math.min(DEFAULT_BUDGET_RUPEES, Math.floor(available / 100))));
    // Only when the pop-up opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useEffect(() => {
    onFollow(open ? selected : []);
  }, [open, selected, onFollow]);

  // Validation, mirrored on the server.
  const budgetPaise = Math.round(Number(budget) * 100);
  const problems: string[] = [];
  if (selected.length < 2) problems.push("Choose at least two stocks; a portfolio needs more than one to divide money between.");
  if (budget.trim() === "" || !Number.isFinite(budgetPaise) || budgetPaise <= 0) {
    problems.push("Enter the amount you want to invest.");
  } else if (portfolio && budgetPaise > available) {
    problems.push(`The amount to invest is more than your available cash (${money(available)}).`);
  }

  const next = (event: FormEvent) => {
    event.preventDefault();
    setTouched(true);
    if (problems.length > 0) return;
    setConfidences((current) => Object.fromEntries(selected.map((s) => [s, current[s] ?? 50])));
    setStep("views");
  };

  const run = async () => {
    const id = ++request.current;
    setError("");
    setOutcomes(null);
    setStep("running");
    try {
      const views = Object.fromEntries(selected.map((s) => [s, confidences[s] ?? 50]));
      const answer = await api.recommend(selected, views, budgetPaise);
      if (id !== request.current) return;
      setResult(answer);
      onResult(answer);
      setStep("result");
    } catch (err) {
      if (id !== request.current) return;
      setError(err instanceof Error ? err.message : "The recommendation system did not respond.");
      setStep("views");
    }
  };

  const close = () => {
    request.current += 1;
    onClose();
  };

  const buy = async () => {
    if (!result) return;
    setPlacing(true);
    const items = result.stocks.filter((s) => s.decision === "BUY" && s.quantity > 0).map((s) => ({ symbol: s.symbol, side: "BUY" as const, qty: s.quantity }));
    await placeMarketOrders(items, "CNC", setOutcomes);
    setPlacing(false);
    onOrdersPlaced();
  };

  return (
    <Modal open={open} onClose={close} title="Delivery: which stocks should I buy?"
      subtitle="Choose stocks, read each one's latest news and say how confident you are in it. The recommendation system combines your views with the price history since 2015 and says which to buy and how much money each should get.">
      <Steps step={step === "running" ? "result" : step} labels={{ choose: "Stocks and amount", views: "News and your views", result: "Recommendation" }} />

      {step === "choose" && (
        <form className="modal-body" onSubmit={next} noValidate>
          <fieldset className="field-group">
            <legend>Stocks to consider</legend>
            <StockPicker symbols={symbols} quotes={quotes} watchlist={watchlist} selected={selected} onChange={setSelected} max={MAX_STOCKS} />
          </fieldset>
          <fieldset className="field-group">
            <legend>Amount to invest</legend>
            <label className="unit-input wide">
              <span>{"₹"}</span>
              <input type="number" min={1} step={1000} value={budget} aria-label="Amount to invest in rupees" onChange={(e) => setBudget(e.target.value)} />
            </label>
            <p className="hint">Available cash: {money(available)}</p>
          </fieldset>
          {touched && problems.length > 0 && <ul className="problems" role="alert">{problems.map((p) => <li key={p}>{p}</li>)}</ul>}
          <div className="modal-foot">
            <button type="button" className="button ghost" onClick={close}>Cancel</button>
            <button type="submit" className="button primary">Next: read the news</button>
          </div>
        </form>
      )}

      {step === "views" && (
        <div className="modal-body">
          <YourViews symbols={selected} names={names} quotes={quotes} confidences={confidences} onChange={setConfidences}
            outlook="will do well over the coming year" />
          {error && <p className="problems" role="alert">{error}</p>}
          <div className="modal-foot">
            <button type="button" className="button ghost" onClick={() => setStep("choose")}>Back</button>
            <button type="button" className="button primary" onClick={run}>Get recommendation</button>
          </div>
        </div>
      )}

      {step === "running" && (
        <div className="modal-body running" role="status" aria-live="polite">
          <div className="spinner" aria-hidden="true" />
          <p className="strong">The recommendation system is running.</p>
          <ol className="muted">
            <li>Loading daily prices since 2015 for {selected.join(", ")} (the first run of the day downloads them).</li>
            <li>Moving each stock's expected return up or down by your view.</li>
            <li>Simulating 20,000 random portfolios and finding the best mix with the SLSQP optimiser.</li>
            <li>Re-running the optimiser 200 times on resampled history, with and without your views.</li>
          </ol>
        </div>
      )}

      {step === "result" && result && (
        <DeliveryResult result={result} placing={placing} outcomes={outcomes} onBuy={buy} onBack={() => setStep("views")} onClose={close} />
      )}
    </Modal>
  );
}

export function Steps<T extends string>({ step, labels }: { step: T; labels: Record<T, string> }) {
  const keys = Object.keys(labels) as T[];
  return (
    <ol className="steps" aria-label="Steps">
      {keys.map((key, i) => (
        <li key={key} className={key === step ? "on" : keys.indexOf(step) > i ? "done" : ""} aria-current={key === step ? "step" : undefined}>
          <span className="step-number">{i + 1}</span> {labels[key]}
        </li>
      ))}
    </ol>
  );
}

function DeliveryResult({ result, placing, outcomes, onBuy, onBack, onClose }: {
  result: Recommendation; placing: boolean; outcomes: OrderOutcome[] | null;
  onBuy: () => void; onBack: () => void; onClose: () => void;
}) {
  const rec = result.recommended;
  const buys = result.stocks.filter((s) => s.decision === "BUY");
  const buyable = buys.filter((s) => s.quantity > 0);
  const top = [...result.stocks].sort((a, b) => b.agreement - a.agreement)[0];
  const needed = result.method.buy_agreement * 100;
  const refs = result.reference_portfolios;
  const markers: FrontierMarker[] = [
    { kind: "best", label: "Best Sharpe ratio with your views", volatility: refs.max_sharpe.volatility, ret: refs.max_sharpe.expected_return },
    { kind: "safest", label: "Lowest risk", volatility: refs.min_volatility.volatility, ret: refs.min_volatility.expected_return },
  ];
  if (rec) markers.push({ kind: "yours", label: "Recommended portfolio", volatility: rec.volatility, ret: rec.expected_return });

  return (
    <div className="modal-body">
      <div className={rec ? "verdict up" : "verdict neutral"} role="status">
        {rec ? (
          <>
            <strong>Buy {buys.length} of the {result.stocks.length} stocks: {buys.map((s) => s.symbol).join(", ")}.</strong>
            <span>Each was picked in at least {needed}% of the optimiser's {result.method.resamples} re-runs with your views.</span>
          </>
        ) : (
          <>
            <strong>No stock was picked in at least {needed}% of the re-runs, so nothing is recommended.</strong>
            <span>The highest was {top.symbol} at {share(top.agreement)}. Choose other stocks, or revisit your views.</span>
          </>
        )}
      </div>

      {rec && (
        <div className="stat-cards">
          <StatCard label="Money to invest" value={money(rec.invested)} note={`${money(rec.cash_left)} left over, because shares are bought whole`} />
          <StatCard label="Expected annual return" value={pct(rec.expected_return)} note={`With your views; ${pct(rec.expected_return_history)} on price history alone. Not a promise`} />
          <StatCard label="Annual volatility" value={pct(rec.volatility)} note="How much the value usually swings in a year" />
          <StatCard label="Sharpe ratio" value={rec.sharpe == null ? "—" : rec.sharpe.toFixed(2)} note={`Return above ${pct(result.method.risk_free_rate)} risk-free, per unit of risk`} />
          <StatCard label={`One-day loss at ${rec.value_at_risk.confidence}% confidence`} value={money(rec.value_at_risk.one_day_amount)}
            note={`On ${rec.value_at_risk.confidence}% of past days the loss was smaller than ${pct(rec.value_at_risk.one_day_fraction, 2)}`} />
        </div>
      )}

      <h3>Decision for each stock</h3>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Stock</th><th className="num">Your view</th><th>Decision</th><th>Picked, with your view</th><th className="num">On history alone</th>
              <th className="num">Share of money</th><th className="num">Shares</th><th className="num">Live price</th><th className="num">Cost</th>
              <th className="num">Return a year</th><th className="num">Volatility</th><th>Why</th>
            </tr>
          </thead>
          <tbody>
            {result.stocks.map((s) => (
              <tr key={s.symbol} className={s.decision === "BUY" ? "row-up" : ""}>
                <td className="strong">{s.symbol}</td>
                <td className={`num ${s.your_confidence > 50 ? "up" : s.your_confidence < 50 ? "down" : "muted"}`}>{s.your_confidence}%</td>
                <td><span className={s.decision === "BUY" ? "badge up" : "badge neutral"}>{s.decision === "BUY" ? "Buy" : "Do not buy"}</span></td>
                <td><ConfidenceMeter value={s.agreement} asked={needed} text={share(s.agreement)} /></td>
                <td className="num muted">{share(s.history_agreement)}</td>
                <td className="num">{s.weight > 0 ? pct(s.weight) : "—"}</td>
                <td className="num">{s.quantity > 0 ? qty(s.quantity) : "—"}</td>
                <td className="num">{price(s.last_price)}</td>
                <td className="num">{s.cost > 0 ? money(s.cost) : "—"}</td>
                <td className={`num ${direction(s.expected_return_with_view)}`} title={`History ${pct(s.expected_return)}, your view ${s.return_shift >= 0 ? "+" : ""}${pct(s.return_shift)}`}>
                  {pct(s.expected_return_with_view)}{s.return_shift !== 0 && <span className="muted small"> ({pct(s.expected_return)})</span>}
                </td>
                <td className="num">{pct(s.volatility)}</td>
                <td className="why">{s.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="hint">
        The tick on each bar is the {needed}% needed for a buy. A view above 50% raised the stock's expected return and one below 50%
        lowered it, by up to half of its yearly volatility; the figure in brackets is the return on price history alone.
      </p>

      <h3>Risk against return, with your views</h3>
      <FrontierChart points={result.frontier.points} markers={markers} />

      <h3>Reference portfolios</h3>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Portfolio</th>
              {result.stocks.map((s) => <th key={s.symbol} className="num">{s.symbol}</th>)}
              <th className="num">Return</th><th className="num">Volatility</th><th className="num">Sharpe</th>
            </tr>
          </thead>
          <tbody>
            {([["Best Sharpe ratio, price history alone", refs.history_only], ["Best Sharpe ratio, with your views", refs.max_sharpe], ["Lowest risk", refs.min_volatility]] as const).map(([label, p]) => (
              <tr key={label}>
                <td>{label}</td>
                {result.stocks.map((s) => <td key={s.symbol} className="num">{pct(p.weights[s.symbol] ?? 0)}</td>)}
                <td className="num">{pct(p.expected_return)}</td>
                <td className="num">{pct(p.volatility)}</td>
                <td className="num">{p.sharpe == null ? "—" : p.sharpe.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="method-note">
        Price history from {longDate(result.data.start)} to {longDate(result.data.end)} ({qty(result.data.trading_days)} trading days), {result.data.source}
        {result.data.stale ? ", from the saved copy because the download failed" : ""}. {qty(result.method.monte_carlo_portfolios)} random portfolios,
        {" "}{result.method.resamples} re-runs; a stock counts in a re-run when it gets at least {pct(result.method.min_weight, 0)} of the money;
        risk-free rate {pct(result.method.risk_free_rate)}. Shares are priced at the live price. Worked out in {(result.runtime_ms / 1000).toFixed(1)} seconds.
        For study only; not investment advice.
      </p>

      {outcomes && <Outcomes outcomes={outcomes} />}

      <div className="modal-foot">
        <button type="button" className="button ghost" onClick={onBack}>Change my views</button>
        <button type="button" className="button ghost" onClick={onClose}>Close</button>
        {buyable.length > 0 && !outcomes && (
          <button type="button" className="button primary" onClick={onBuy} disabled={placing}>
            {placing ? "Placing orders" : `Buy ${buyable.length} recommended stock${buyable.length > 1 ? "s" : ""} for delivery (${money(buyable.reduce((sum, s) => sum + s.cost, 0))})`}
          </button>
        )}
      </div>
    </div>
  );
}

export function StatCard({ label, value, note, tone }: { label: string; value: string; note?: string; tone?: string }) {
  return (
    <div className="stat-card">
      <span className="stat-label">{label}</span>
      <strong className={`num ${tone ?? ""}`}>{value}</strong>
      {note && <span className="stat-note">{note}</span>}
    </div>
  );
}

export function Outcomes({ outcomes }: { outcomes: OrderOutcome[] }) {
  return (
    <ul className="outcomes" role="status">
      {outcomes.map((o) => <li key={o.symbol} className={o.ok ? "up" : "down"}><strong>{o.symbol}</strong> {o.text}</li>)}
    </ul>
  );
}
