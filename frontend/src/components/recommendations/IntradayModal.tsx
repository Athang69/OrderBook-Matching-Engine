import { useEffect, useState, type FormEvent } from "react";

import type { Instrument, IntradayAction, IntradayRecommendation, IntradayStock, MarketState, Portfolio } from "../../api/types";
import { clock, money, price, qty } from "../../lib/format";
import { useIntradaySignals, type IntradayQuery } from "../../hooks/useIntradaySignals";
import { NewsSection, type StockLabel } from "../news/News";
import { ConfidenceMeter } from "../ui/ConfidenceMeter";
import { Modal } from "../ui/Modal";
import { SignalBar } from "../ui/SignalBar";
import { Outcomes, StatCard } from "./DeliveryModal";
import { placeMarketOrders, type OrderOutcome } from "./placeOrders";
import { StockPicker } from "./StockPicker";

interface Props {
  open: boolean;
  onClose: () => void;
  instruments: Instrument[];
  market: Record<string, MarketState>;
  portfolio: Portfolio | null;
  preselect: string;
  marginDivisor: number;
  onOrdersPlaced: () => void;
}

const MIN_CONFIDENCE = 10;
const MAX_CONFIDENCE = 95;
const DEFAULT_MARGIN_RUPEES = 50_000;

export const ACTION_LABEL: Record<IntradayAction, StockLabel> = {
  BUY: { text: "Buy", tone: "up" },
  SELL: { text: "Sell short", tone: "down" },
  NO_TRADE: { text: "No trade", tone: "neutral" },
  WAIT: { text: "Waiting", tone: "neutral" },
};

const SIGNALS: [keyof NonNullable<IntradayStock["signals"]>, string][] = [
  ["momentum", "Momentum"], ["vwap", "Price vs VWAP"], ["book", "Order book"], ["flow", "Trade flow"],
];

/** Intraday: choose stocks, a confidence and the margin to use; then watch live signals and trade them. */
export function IntradayModal({ open, onClose, instruments, market, portfolio, preselect, marginDivisor, onOrdersPlaced }: Props) {
  const [step, setStep] = useState<"choose" | "live">("choose");
  const [selected, setSelected] = useState<string[]>([]);
  const [confidence, setConfidence] = useState("40");
  const [budget, setBudget] = useState("");
  const [touched, setTouched] = useState(false);
  const [query, setQuery] = useState<IntradayQuery | null>(null);
  const [live, setLive] = useState(true);
  const [placing, setPlacing] = useState(false);
  const [outcomes, setOutcomes] = useState<OrderOutcome[] | null>(null);
  const available = portfolio?.available ?? 0;
  const signals = useIntradaySignals(open && step === "live" ? query : null, live);

  useEffect(() => {
    if (!open) return;
    setStep("choose");
    setTouched(false);
    setOutcomes(null);
    setLive(true);
    setSelected((current) => (current.length > 0 ? current : preselect ? [preselect] : []));
    setBudget((current) => current || String(Math.min(DEFAULT_MARGIN_RUPEES, Math.floor(available / 100))));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // Validation, mirrored on the server.
  const confidenceValue = Number(confidence);
  const budgetPaise = Math.round(Number(budget) * 100);
  const problems: string[] = [];
  if (selected.length < 1) problems.push("Select at least one stock.");
  if (confidence.trim() === "" || !Number.isFinite(confidenceValue) || confidenceValue < MIN_CONFIDENCE || confidenceValue > MAX_CONFIDENCE) {
    problems.push(`Confidence must be a number from ${MIN_CONFIDENCE} to ${MAX_CONFIDENCE}.`);
  }
  if (budget.trim() === "" || !Number.isFinite(budgetPaise) || budgetPaise <= 0) {
    problems.push("Enter the margin you want to use.");
  } else if (portfolio && budgetPaise > available) {
    problems.push(`That is more than your available cash (${money(available)}).`);
  }

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setTouched(true);
    if (problems.length > 0) return;
    setQuery({ symbols: selected, confidence: confidenceValue, budget: budgetPaise });
    setOutcomes(null);
    setLive(true);
    setStep("live");
  };

  const trade = async (data: IntradayRecommendation) => {
    setLive(false); // freeze the numbers being traded
    setPlacing(true);
    const items = data.stocks
      .filter((s) => (s.action === "BUY" || s.action === "SELL") && s.quantity > 0)
      .map((s) => ({ symbol: s.symbol, side: s.action as "BUY" | "SELL", qty: s.quantity }));
    await placeMarketOrders(items, "MIS", setOutcomes);
    setPlacing(false);
    onOrdersPlaced();
  };

  return (
    <Modal open={open} onClose={onClose} title="Intraday: what to trade right now?"
      subtitle={`Live signals from the last few minutes of trading: buy, sell short or stay out, with an entry, a stop-loss and a target. Positions can be up to ${marginDivisor} times your margin.`}>
      {step === "choose" && (
        <form className="modal-body" onSubmit={submit} noValidate>
          <fieldset className="field-group">
            <legend>1. Stocks to watch</legend>
            <StockPicker instruments={instruments} market={market} selected={selected} onChange={setSelected} />
          </fieldset>
          <fieldset className="field-group">
            <legend>2. How strong must the signal be?</legend>
            <div className="slider-row">
              <input type="range" min={MIN_CONFIDENCE} max={MAX_CONFIDENCE} step={1} value={Number.isFinite(confidenceValue) ? confidenceValue : 40}
                aria-label="Confidence percentage" onChange={(e) => setConfidence(e.target.value)} />
              <label className="unit-input">
                <input type="number" min={MIN_CONFIDENCE} max={MAX_CONFIDENCE} step={1} value={confidence}
                  aria-label="Confidence percentage, typed" onChange={(e) => setConfidence(e.target.value)} />
                <span>%</span>
              </label>
            </div>
            <p className="hint">Four signals each vote from strong sell to strong buy. A stock is a trade when their weighted average is at least this strong. Most of the time only the strongest one or two reach 40%.</p>
          </fieldset>
          <fieldset className="field-group">
            <legend>3. Margin to use</legend>
            <label className="unit-input wide">
              <span>{"₹"}</span>
              <input type="number" min={1} step={1000} value={budget} aria-label="Margin to use in rupees" onChange={(e) => setBudget(e.target.value)} />
            </label>
            <p className="hint">Available cash: {money(available)}. Intraday positions need {100 / marginDivisor}% margin, so {money(Number.isFinite(budgetPaise) && budgetPaise > 0 ? budgetPaise * marginDivisor : 0)} of shares can be traded with this.</p>
          </fieldset>
          {touched && problems.length > 0 && <ul className="problems" role="alert">{problems.map((p) => <li key={p}>{p}</li>)}</ul>}
          <div className="modal-foot">
            <button type="button" className="button ghost" onClick={onClose}>Cancel</button>
            <button type="submit" className="button primary">Show live signals</button>
          </div>
        </form>
      )}

      {step === "live" && (
        <IntradayResult data={signals.data} error={signals.error} roundTripMs={signals.roundTripMs} updatedAt={signals.updatedAt}
          live={live} onToggleLive={() => setLive((l) => !l)} placing={placing} outcomes={outcomes} marginDivisor={marginDivisor}
          onTrade={trade} onBack={() => setStep("choose")} onClose={onClose} />
      )}
    </Modal>
  );
}

function IntradayResult({ data, error, roundTripMs, updatedAt, live, onToggleLive, placing, outcomes, marginDivisor, onTrade, onBack, onClose }: {
  data: IntradayRecommendation | null; error: string; roundTripMs: number | null; updatedAt: number | null;
  live: boolean; onToggleLive: () => void; placing: boolean; outcomes: OrderOutcome[] | null; marginDivisor: number;
  onTrade: (data: IntradayRecommendation) => void; onBack: () => void; onClose: () => void;
}) {
  if (!data) {
    return (
      <div className="modal-body running" role="status">
        {error ? <p className="problems">{error}</p> : <><div className="spinner" aria-hidden="true" /><p>Reading the market.</p></>}
        <div className="modal-foot"><button type="button" className="button ghost" onClick={onBack}>Change choices</button></div>
      </div>
    );
  }
  const asked = data.inputs.confidence;
  const trades = data.stocks.filter((s) => (s.action === "BUY" || s.action === "SELL") && s.quantity > 0);
  const strongest = [...data.stocks].filter((s) => s.signals).sort((a, b) => b.confidence - a.confidence)[0];
  const labels = Object.fromEntries(data.stocks.map((s) => [s.symbol, ACTION_LABEL[s.action]]));

  return (
    <div className="modal-body">
      <div className="live-bar">
        <span className={`status-dot ${live ? "live" : "paused"}`} aria-hidden="true" />
        <span className="strong">{live ? "Live, updating every second" : "Paused"}</span>
        <span className="chip" title="Time on the server from receiving the request to the answer">Server {(data.timing.total_us / 1000).toFixed(2)} ms</span>
        {roundTripMs != null && <span className="chip" title="Time measured in this browser for the whole request">Round trip {roundTripMs.toFixed(1)} ms</span>}
        {updatedAt && <span className="muted small">Updated {clock(updatedAt / 1000)}</span>}
        {error && <span className="down small">{error}</span>}
        <button type="button" className="button ghost small push-right" onClick={onToggleLive}>{live ? "Pause updates" : "Resume live updates"}</button>
      </div>

      <div className={trades.length ? "verdict up" : "verdict neutral"} role="status">
        {trades.length ? (
          <>
            <strong>{trades.length} trade{trades.length > 1 ? "s" : ""} now: {trades.map((s) => `${ACTION_LABEL[s.action].text} ${s.symbol}`).join(", ")}.</strong>
            <span>Each has signals at least {asked}% strong.</span>
          </>
        ) : (
          <>
            <strong>No stock has signals {asked}% strong right now.</strong>
            <span>{strongest ? `The strongest is ${strongest.symbol} at ${(strongest.confidence * 100).toFixed(0)}% (${strongest.score > 0 ? "up" : "down"}). Signals change every second; wait, or lower the confidence.` : "Waiting for enough trading to read the market."}</span>
          </>
        )}
      </div>

      <div className="stat-cards">
        <StatCard label="Trades" value={String(data.totals.trades)} />
        <StatCard label="Margin used" value={money(data.totals.margin)} note={`of ${money(data.inputs.budget)}`} />
        <StatCard label="Position value" value={money(data.totals.exposure)} note={`Up to ${marginDivisor} times the margin`} />
        <StatCard label="Loss if every stop-loss hits" value={money(data.totals.max_loss)} tone={data.totals.max_loss ? "down" : ""} />
        <StatCard label="Gain if every target hits" value={money(data.totals.max_gain)} tone={data.totals.max_gain ? "up" : ""} />
      </div>

      <h3>Signal for each stock</h3>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Stock</th><th>Signal</th><th>Confidence</th>
              {SIGNALS.map(([, label]) => <th key={label}>{label}</th>)}
              <th className="num">Entry</th><th className="num">Stop-loss</th><th className="num">Target</th>
              <th className="num">Shares</th><th className="num">Margin</th><th className="num">Max loss</th><th>Why</th>
            </tr>
          </thead>
          <tbody>
            {data.stocks.map((s) => {
              const label = ACTION_LABEL[s.action];
              const trading = (s.action === "BUY" || s.action === "SELL");
              return (
                <tr key={s.symbol} className={s.action === "BUY" ? "row-up" : s.action === "SELL" ? "row-down" : ""}>
                  <td className="strong">{s.symbol}</td>
                  <td><span className={`badge ${label.tone}`}>{label.text}</span></td>
                  <td><ConfidenceMeter value={s.confidence} asked={asked} text={`${(s.confidence * 100).toFixed(0)}%`} /></td>
                  {SIGNALS.map(([key, labelText]) => (
                    <td key={key}>{s.signals ? <SignalBar value={s.signals[key]} label={labelText} /> : <span className="muted">{"—"}</span>}</td>
                  ))}
                  <td className="num">{trading ? price(s.entry) : "—"}</td>
                  <td className="num down">{trading ? price(s.stop_loss) : "—"}</td>
                  <td className="num up">{trading ? price(s.target) : "—"}</td>
                  <td className="num">{s.quantity ? qty(s.quantity) : "—"}</td>
                  <td className="num">{s.margin ? money(s.margin) : "—"}</td>
                  <td className="num">{s.max_loss ? money(s.max_loss) : "—"}</td>
                  <td className="why">{s.note}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="hint">
        Bars run from strong sell (red, left) to strong buy (green, right). The tick on each confidence bar is the {asked}% you asked for.
      </p>

      <NewsSection symbols={data.stocks.map((s) => s.symbol)} labels={labels} />

      <p className="method-note">
        Momentum is the last minute's price change against the stock's normal one-second swings; price vs VWAP compares the last
        price with the session's volume-weighted average; order book compares quantity waiting to buy and to sell in the best five
        levels; trade flow compares shares bought and sold by orders that crossed the spread in the last five minutes. Weights:
        momentum {data.method.weights.momentum * 100}%, VWAP {data.method.weights.vwap * 100}%, book {data.method.weights.book * 100}%,
        flow {data.method.weights.flow * 100}%. Stop-losses sit {data.method.stop_moves} typical {data.method.hold_seconds / 60}-minute moves away and
        targets {data.method.reward_to_risk} times as far. The simulator has no stop orders, so watch open positions or square off. Not investment advice.
      </p>

      {outcomes && <Outcomes outcomes={outcomes} />}

      <div className="modal-foot">
        <button type="button" className="button ghost" onClick={onBack}>Change choices</button>
        <button type="button" className="button ghost" onClick={onClose}>Close</button>
        {trades.length > 0 && !outcomes && (
          <button type="button" className="button primary" onClick={() => onTrade(data)} disabled={placing}>
            {placing ? "Placing orders" : `Place ${trades.length} intraday order${trades.length > 1 ? "s" : ""} (margin ${money(data.totals.margin)})`}
          </button>
        )}
      </div>
    </div>
  );
}
