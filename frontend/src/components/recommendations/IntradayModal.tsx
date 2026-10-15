import { useEffect, useState, type FormEvent } from "react";

import type { Confidences, IntradayAction, IntradayRecommendation, IntradayStock, Portfolio, Quote, SymbolRow } from "../../api/types";
import { useIntradaySignals, type IntradayQuery } from "../../hooks/useIntradaySignals";
import { clock, money, price, qty } from "../../lib/format";
import type { StockLabel } from "../news/News";
import { Modal } from "../ui/Modal";
import { SignalBar } from "../ui/SignalBar";
import { Outcomes, StatCard, Steps } from "./DeliveryModal";
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
  preselect: string;
  marginDivisor: number;
  onFollow: (symbols: string[]) => void;
  onOrdersPlaced: () => void;
}

const MAX_STOCKS = 20;
const DEFAULT_MARGIN_RUPEES = 50_000;

export const ACTION_LABEL: Record<IntradayAction, StockLabel> = {
  BUY: { text: "Buy", tone: "up" },
  SELL: { text: "Sell short", tone: "down" },
  NO_TRADE: { text: "No trade", tone: "neutral" },
  WAIT: { text: "Waiting", tone: "neutral" },
};

const SIGNALS: [keyof NonNullable<IntradayStock["signals"]>, string][] = [
  ["momentum", "Momentum"], ["vwap", "Price vs VWAP"], ["flow", "Trade flow"],
];

type Step = "choose" | "views" | "live";

/** Intraday: choose stocks and the margin to use, give your view of each after its news, then trade live signals. */
export function IntradayModal({ open, onClose, symbols, names, quotes, watchlist, portfolio, preselect, marginDivisor, onFollow, onOrdersPlaced }: Props) {
  const [step, setStep] = useState<Step>("choose");
  const [selected, setSelected] = useState<string[]>([]);
  const [confidences, setConfidences] = useState<Confidences>({});
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

  useEffect(() => {
    onFollow(open ? selected : []);
  }, [open, selected, onFollow]);

  // Validation, mirrored on the server.
  const budgetPaise = Math.round(Number(budget) * 100);
  const problems: string[] = [];
  if (selected.length < 1) problems.push("Choose at least one stock.");
  if (budget.trim() === "" || !Number.isFinite(budgetPaise) || budgetPaise <= 0) {
    problems.push("Enter the margin you want to use.");
  } else if (portfolio && budgetPaise > available) {
    problems.push(`That is more than your available cash (${money(available)}).`);
  }

  const next = (event: FormEvent) => {
    event.preventDefault();
    setTouched(true);
    if (problems.length > 0) return;
    setConfidences((current) => Object.fromEntries(selected.map((s) => [s, current[s] ?? 50])));
    setStep("views");
  };

  const start = () => {
    setQuery({ symbols: selected, confidences: Object.fromEntries(selected.map((s) => [s, confidences[s] ?? 50])), budget: budgetPaise });
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
    <Modal open={open} onClose={onClose} title="Intraday: what should I trade right now?"
      subtitle={`Choose stocks, read their news and say how confident you are that each will rise today. Live signals from today's real trading are combined with your views: buy, sell short or stay out, with an entry, a stop-loss and a target. Positions can be up to ${marginDivisor} times your margin.`}>
      <Steps step={step} labels={{ choose: "Stocks and margin", views: "News and your views", live: "Live signals" }} />

      {step === "choose" && (
        <form className="modal-body" onSubmit={next} noValidate>
          <fieldset className="field-group">
            <legend>Stocks to watch</legend>
            <StockPicker symbols={symbols} quotes={quotes} watchlist={watchlist} selected={selected} onChange={setSelected} max={MAX_STOCKS} />
          </fieldset>
          <fieldset className="field-group">
            <legend>Margin to use</legend>
            <label className="unit-input wide">
              <span>{"₹"}</span>
              <input type="number" min={1} step={1000} value={budget} aria-label="Margin to use in rupees" onChange={(e) => setBudget(e.target.value)} />
            </label>
            <p className="hint">Available cash: {money(available)}. Intraday positions need {100 / marginDivisor}% margin, so {money(Number.isFinite(budgetPaise) && budgetPaise > 0 ? budgetPaise * marginDivisor : 0)} of shares can be traded with this.</p>
          </fieldset>
          {touched && problems.length > 0 && <ul className="problems" role="alert">{problems.map((p) => <li key={p}>{p}</li>)}</ul>}
          <div className="modal-foot">
            <button type="button" className="button ghost" onClick={onClose}>Cancel</button>
            <button type="submit" className="button primary">Next: read the news</button>
          </div>
        </form>
      )}

      {step === "views" && (
        <div className="modal-body">
          <YourViews symbols={selected} names={names} quotes={quotes} confidences={confidences} onChange={setConfidences} outlook="will rise today" />
          <div className="modal-foot">
            <button type="button" className="button ghost" onClick={() => setStep("choose")}>Back</button>
            <button type="button" className="button primary" onClick={start}>Show live signals</button>
          </div>
        </div>
      )}

      {step === "live" && (
        <IntradayResult data={signals.data} error={signals.error} roundTripMs={signals.roundTripMs} updatedAt={signals.updatedAt}
          live={live} onToggleLive={() => setLive((l) => !l)} placing={placing} outcomes={outcomes} marginDivisor={marginDivisor}
          onTrade={trade} onBack={() => setStep("views")} onClose={onClose} />
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
        <div className="modal-foot"><button type="button" className="button ghost" onClick={onBack}>Change my views</button></div>
      </div>
    );
  }
  const threshold = data.method.threshold;
  const trades = data.stocks.filter((s) => (s.action === "BUY" || s.action === "SELL") && s.quantity > 0);
  const strongest = [...data.stocks].filter((s) => s.model_score != null).sort((a, b) => b.confidence - a.confidence)[0];
  const closed = !data.session.intraday_open;

  return (
    <div className="modal-body">
      <div className="live-bar">
        <span className={`status-dot ${live && !closed ? "live" : "paused"}`} aria-hidden="true" />
        <span className="strong">{closed ? data.session.label : live ? "Live, updating every second" : "Paused"}</span>
        <span className="chip" title="Time on the server from receiving the request to the answer">Server {(data.timing.total_us / 1000).toFixed(2)} ms</span>
        {roundTripMs != null && <span className="chip" title="Time measured in this browser for the whole request">Round trip {roundTripMs.toFixed(1)} ms</span>}
        {updatedAt && <span className="muted small">Updated {clock(updatedAt / 1000)}</span>}
        {error && <span className="down small">{error}</span>}
        <button type="button" className="button ghost small push-right" onClick={onToggleLive}>{live ? "Pause updates" : "Resume live updates"}</button>
      </div>

      <div className={trades.length ? "verdict up" : "verdict neutral"} role="status">
        {closed ? (
          <>
            <strong>No intraday trades now: {data.stocks[0]?.note}</strong>
            <span>The live signals below are from the last trading you can see; trades are suggested only while intraday trading is open.</span>
          </>
        ) : trades.length ? (
          <>
            <strong>{trades.length} trade{trades.length > 1 ? "s" : ""} now: {trades.map((s) => `${ACTION_LABEL[s.action].text} ${s.symbol}`).join(", ")}.</strong>
            <span>Each has a final score of at least ±{threshold.toFixed(2)}: {data.method.model_weight * 100}% live signals and {data.method.view_weight * 100}% your view.</span>
          </>
        ) : (
          <>
            <strong>No stock has a final score of ±{threshold.toFixed(2)} right now.</strong>
            <span>{strongest ? `The strongest is ${strongest.symbol} at ${strongest.score >= 0 ? "+" : ""}${strongest.score.toFixed(2)}. Signals change every second; wait, or revisit your views.` : `The signals need ${data.method.min_minutes} minutes of trading today.`}</span>
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
              <th>Stock</th><th>Signal</th><th className="num">Final score</th><th>Live signals</th><th>Your view</th>
              {SIGNALS.map(([, label]) => <th key={label}>{label}</th>)}
              <th className="num">Entry</th><th className="num">Stop-loss</th><th className="num">Target</th>
              <th className="num">Shares</th><th className="num">Margin</th><th className="num">Max loss</th><th>Why</th>
            </tr>
          </thead>
          <tbody>
            {data.stocks.map((s) => {
              const label = ACTION_LABEL[s.action];
              const trading = s.action === "BUY" || s.action === "SELL";
              return (
                <tr key={s.symbol} className={s.action === "BUY" ? "row-up" : s.action === "SELL" ? "row-down" : ""}>
                  <td className="strong">{s.symbol}</td>
                  <td><span className={`badge ${label.tone}`}>{label.text}</span></td>
                  <td className={`num ${s.score > 0 ? "up" : s.score < 0 ? "down" : ""}`}>{s.model_score == null || closed ? "—" : `${s.score >= 0 ? "+" : ""}${s.score.toFixed(2)}`}</td>
                  <td>{s.model_score == null ? <span className="muted">{"—"}</span> : <SignalBar value={s.model_score} label="Live signals" />}</td>
                  <td><span className="view-cell"><SignalBar value={s.your_view} label="Your view" /> <span className="num small muted">{s.your_confidence}%</span></span></td>
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
      <p className="hint">Bars run from strong sell (red, left) to strong buy (green, right).</p>

      <p className="method-note">
        From real NSE trading today: momentum is the last minute's price change against the stock's normal one-minute moves;
        price vs VWAP compares the live price with today's volume-weighted average; trade flow compares shares traded on up-ticks
        and down-ticks in the last five minutes. Live signals = momentum {data.method.weights.momentum * 100}%, VWAP {data.method.weights.vwap * 100}%,
        flow {data.method.weights.flow * 100}%. Your view is your confidence turned into −1 (0%) to +1 (100%). Final score
        = {data.method.model_weight * 100}% live signals + {data.method.view_weight * 100}% your view; a trade needs ±{threshold.toFixed(2)}.
        Entries are the live best offer for a buy and best bid for a short sale. Stop-losses sit {data.method.stop_moves} typical {data.method.hold_minutes}-minute
        moves away and targets {data.method.reward_to_risk} times as far. There are no stop orders here, so watch open positions; intraday positions
        are squared off at 3:20 pm. Not investment advice.
      </p>

      {outcomes && <Outcomes outcomes={outcomes} />}

      <div className="modal-foot">
        <button type="button" className="button ghost" onClick={onBack}>Change my views</button>
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
