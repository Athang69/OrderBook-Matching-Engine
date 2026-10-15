import { useEffect, useRef, useState, type FormEvent } from "react";

import { api } from "../../api/client";
import type { Instrument, MarketState, Portfolio, Recommendation } from "../../api/types";
import { direction, longDate, money, price, qty } from "../../lib/format";
import { NewsSection } from "../news/News";
import { ConfidenceMeter } from "../ui/ConfidenceMeter";
import { Modal } from "../ui/Modal";
import { FrontierChart, type FrontierMarker } from "./FrontierChart";
import { placeMarketOrders, type OrderOutcome } from "./placeOrders";
import { StockPicker } from "./StockPicker";

interface Props {
  open: boolean;
  onClose: () => void;
  instruments: Instrument[];
  market: Record<string, MarketState>;
  portfolio: Portfolio | null;
  /** The stock on screen, ticked when the pop-up first opens. */
  preselect: string;
  onOrdersPlaced: () => void;
  onResult: (result: Recommendation) => void;
}

type Step = "choose" | "running" | "result";

const MIN_CONFIDENCE = 50;
const MAX_CONFIDENCE = 99;
const DEFAULT_BUDGET_RUPEES = 1_00_000;

const pct = (fraction: number, digits = 1) => `${(fraction * 100).toFixed(digits)}%`;
/** Confidence comes in steps of 0.5% (200 re-runs): "72%" or "34.5%", matching the server's wording. */
const confidencePct = (fraction: number) => `${Math.round(fraction * 1000) / 10}%`;

/** Delivery: choose stocks and a confidence, ask the recommendation system, then buy. */
export function DeliveryModal({ open, onClose, instruments, market, portfolio, preselect, onOrdersPlaced, onResult }: Props) {
  const request = useRef(0); // ignores answers the user has walked away from
  const [step, setStep] = useState<Step>("choose");
  const [selected, setSelected] = useState<string[]>([]);
  const [confidence, setConfidence] = useState("60");
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

  // Validation, mirrored on the server.
  const confidenceValue = Number(confidence);
  const budgetPaise = Math.round(Number(budget) * 100);
  const problems: string[] = [];
  if (selected.length < 2) problems.push("Select at least two stocks; a portfolio needs more than one to divide money between.");
  if (confidence.trim() === "" || !Number.isFinite(confidenceValue) || confidenceValue < MIN_CONFIDENCE || confidenceValue > MAX_CONFIDENCE) {
    problems.push(`Confidence must be a number from ${MIN_CONFIDENCE} to ${MAX_CONFIDENCE}.`);
  }
  if (budget.trim() === "" || !Number.isFinite(budgetPaise) || budgetPaise <= 0) {
    problems.push("Enter the amount you want to invest.");
  } else if (portfolio && budgetPaise > available) {
    problems.push(`The amount to invest is more than your available cash (${money(available)}).`);
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setTouched(true);
    if (problems.length > 0) return;
    const id = ++request.current;
    setError("");
    setOutcomes(null);
    setStep("running");
    try {
      const answer = await api.recommend(selected, confidenceValue, budgetPaise);
      if (id !== request.current) return;
      setResult(answer);
      onResult(answer);
      setStep("result");
    } catch (err) {
      if (id !== request.current) return;
      setError(err instanceof Error ? err.message : "The recommendation system did not respond.");
      setStep("choose");
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
      subtitle="The recommendation system studies the price history of the stocks you choose and says which to buy and how much of your money each should get.">
      {step === "choose" && (
        <form className="modal-body" onSubmit={submit} noValidate>
          <fieldset className="field-group">
            <legend>1. Stocks to consider</legend>
            <StockPicker instruments={instruments} market={market} selected={selected} onChange={setSelected} />
          </fieldset>
          <fieldset className="field-group">
            <legend>2. How sure should the system be?</legend>
            <div className="slider-row">
              <input type="range" min={MIN_CONFIDENCE} max={MAX_CONFIDENCE} step={1} value={Number.isFinite(confidenceValue) ? confidenceValue : 60}
                aria-label="Confidence percentage" onChange={(e) => setConfidence(e.target.value)} />
              <label className="unit-input">
                <input type="number" min={MIN_CONFIDENCE} max={MAX_CONFIDENCE} step={1} value={confidence}
                  aria-label="Confidence percentage, typed" onChange={(e) => setConfidence(e.target.value)} />
                <span>%</span>
              </label>
            </div>
            <p className="hint">A stock is recommended only if the optimiser picks it in at least this share of its re-runs on reshuffled price history. Higher means fewer, steadier picks.</p>
          </fieldset>
          <fieldset className="field-group">
            <legend>3. Amount to invest</legend>
            <label className="unit-input wide">
              <span>{"₹"}</span>
              <input type="number" min={1} step={1000} value={budget} aria-label="Amount to invest in rupees" onChange={(e) => setBudget(e.target.value)} />
            </label>
            <p className="hint">Available cash: {money(available)}</p>
          </fieldset>
          {touched && problems.length > 0 && <ul className="problems" role="alert">{problems.map((p) => <li key={p}>{p}</li>)}</ul>}
          {error && <p className="problems" role="alert">{error}</p>}
          <div className="modal-foot">
            <button type="button" className="button ghost" onClick={close}>Cancel</button>
            <button type="submit" className="button primary">Get recommendation</button>
          </div>
        </form>
      )}

      {step === "running" && (
        <div className="modal-body running" role="status" aria-live="polite">
          <div className="spinner" aria-hidden="true" />
          <p className="strong">The recommendation system is running.</p>
          <ol className="muted">
            <li>Loading daily price history for {selected.join(", ")} (the first run of the day downloads it).</li>
            <li>Simulating 20,000 random portfolios.</li>
            <li>Finding the best mix with the SLSQP optimiser.</li>
            <li>Re-running the optimiser 200 times on reshuffled history to measure confidence.</li>
          </ol>
        </div>
      )}

      {step === "result" && result && (
        <DeliveryResult result={result} placing={placing} outcomes={outcomes} onBuy={buy} onBack={() => setStep("choose")} onClose={close} />
      )}
    </Modal>
  );
}

function DeliveryResult({ result, placing, outcomes, onBuy, onBack, onClose }: {
  result: Recommendation; placing: boolean; outcomes: OrderOutcome[] | null;
  onBuy: () => void; onBack: () => void; onClose: () => void;
}) {
  const rec = result.recommended;
  const buys = result.stocks.filter((s) => s.decision === "BUY");
  const buyable = buys.filter((s) => s.quantity > 0);
  const top = [...result.stocks].sort((a, b) => b.confidence - a.confidence)[0];
  const asked = result.inputs.confidence;
  const markers: FrontierMarker[] = [
    { kind: "best", label: "Best Sharpe ratio, all chosen stocks", volatility: result.reference_portfolios.max_sharpe.volatility, ret: result.reference_portfolios.max_sharpe.expected_return },
    { kind: "safest", label: "Lowest risk, all chosen stocks", volatility: result.reference_portfolios.min_volatility.volatility, ret: result.reference_portfolios.min_volatility.expected_return },
  ];
  if (rec) markers.push({ kind: "yours", label: "Recommended portfolio", volatility: rec.volatility, ret: rec.expected_return });
  const labels = Object.fromEntries(result.stocks.map((s) => [s.symbol, s.decision === "BUY" ? { text: "Buy", tone: "up" as const } : { text: "Do not buy", tone: "neutral" as const }]));

  return (
    <div className="modal-body">
      <div className={rec ? "verdict up" : "verdict neutral"} role="status">
        {rec ? (
          <>
            <strong>Buy {buys.length} of the {result.stocks.length} stocks you chose: {buys.map((s) => s.symbol).join(", ")}.</strong>
            <span>Each was picked in at least {asked}% of the optimiser's re-runs.</span>
          </>
        ) : (
          <>
            <strong>No stock reached {asked}% confidence, so nothing is recommended.</strong>
            <span>The highest was {top.symbol} at {confidencePct(top.confidence)}. {top.confidence * 100 >= 50 ? `Lower the confidence to ${Math.floor(top.confidence * 100 + 1e-9)}% or choose different stocks.` : "Choose different stocks; the lowest confidence allowed is 50%."}</span>
          </>
        )}
      </div>

      {rec && (
        <div className="stat-cards">
          <StatCard label="Money to invest" value={money(rec.invested)} note={`${money(rec.cash_left)} left over, because shares are bought whole`} />
          <StatCard label="Expected annual return" value={pct(rec.expected_return)} note="Average of past years; not a promise" />
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
              <th>Stock</th><th>Decision</th><th>Confidence</th><th className="num">Share of money</th><th className="num">Shares</th>
              <th className="num">Price</th><th className="num">Cost</th><th className="num">Return a year</th><th className="num">Volatility</th><th>Why</th>
            </tr>
          </thead>
          <tbody>
            {result.stocks.map((s) => (
              <tr key={s.symbol} className={s.decision === "BUY" ? "row-up" : ""}>
                <td className="strong">{s.symbol}</td>
                <td><span className={s.decision === "BUY" ? "badge up" : "badge neutral"}>{s.decision === "BUY" ? "Buy" : "Do not buy"}</span></td>
                <td><ConfidenceMeter value={s.confidence} asked={asked} text={confidencePct(s.confidence)} /></td>
                <td className="num">{s.weight > 0 ? pct(s.weight) : "—"}</td>
                <td className="num">{s.quantity > 0 ? qty(s.quantity) : "—"}</td>
                <td className="num">{price(s.last_price)}</td>
                <td className="num">{s.cost > 0 ? money(s.cost) : "—"}</td>
                <td className={`num ${direction(s.expected_return)}`}>{pct(s.expected_return)}</td>
                <td className="num">{pct(s.volatility)}</td>
                <td className="why">{s.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="hint">The tick on each bar is the confidence you asked for ({asked}%).</p>

      <NewsSection symbols={result.stocks.map((s) => s.symbol)} labels={labels} />

      <h3>Risk against return</h3>
      <FrontierChart points={result.frontier.points} markers={markers} />

      <h3>The two reference portfolios from the original method</h3>
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
            {([["Best Sharpe ratio", result.reference_portfolios.max_sharpe], ["Lowest risk", result.reference_portfolios.min_volatility]] as const).map(([label, p]) => (
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
        {" "}{result.method.resamples} re-runs, a stock counts in a re-run when it gets at least {pct(result.method.min_weight, 0)} of the money,
        risk-free rate {pct(result.method.risk_free_rate)}. Worked out in {(result.runtime_ms / 1000).toFixed(1)} seconds. For study only; not investment advice.
      </p>

      {outcomes && <Outcomes outcomes={outcomes} />}

      <div className="modal-foot">
        <button type="button" className="button ghost" onClick={onBack}>Change choices</button>
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
