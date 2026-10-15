import { useMemo } from "react";

import type { Instrument, Portfolio, Recommendation } from "../../api/types";
import { useIntradaySignals } from "../../hooks/useIntradaySignals";
import { ConfidenceMeter } from "../ui/ConfidenceMeter";
import { ACTION_LABEL } from "./IntradayModal";

interface Props {
  instruments: Instrument[];
  portfolio: Portfolio | null;
  lastDelivery: Recommendation | null;
  onOpenDelivery: () => void;
  onOpenIntraday: () => void;
}

const PREVIEW_CONFIDENCE = 40;
const PREVIEW_MARGIN = 50_000 * 100;

/** The two recommendation tools side by side, with a live preview of the strongest intraday signals. */
export function RecommendationsPanel({ instruments, portfolio, lastDelivery, onOpenDelivery, onOpenIntraday }: Props) {
  const available = portfolio?.available ?? 0;
  const query = useMemo(
    () => (instruments.length && available > 0
      ? { symbols: instruments.map((i) => i.symbol), confidence: PREVIEW_CONFIDENCE, budget: Math.min(PREVIEW_MARGIN, available) }
      : null),
    // Re-ask only when the stock list changes or cash crosses the preview amount, not on every cash update.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [instruments.length, available >= PREVIEW_MARGIN, available > 0],
  );
  const signals = useIntradaySignals(query, true, 2000);
  const top = signals.data ? [...signals.data.stocks].filter((s) => s.signals).sort((a, b) => b.confidence - a.confidence).slice(0, 4) : [];
  const buys = lastDelivery?.stocks.filter((s) => s.decision === "BUY") ?? [];

  return (
    <section className="section" id="recommendations" aria-labelledby="rec-title">
      <h2 id="rec-title" className="section-title">Recommendations</h2>
      <div className="rec-grid">
        <article className="card rec-card">
          <div className="rec-card-head">
            <h3>Delivery</h3>
            <span className="chip">Portfolio optimisation</span>
          </div>
          <p className="muted">
            Which stocks to buy and hold, and how much money each should get. Studies daily prices since 2015 with
            20,000 random portfolios and the SLSQP optimiser, then re-runs it 200 times to measure confidence.
          </p>
          {lastDelivery && (
            <p className="rec-last">
              Last result: {buys.length ? `buy ${buys.map((s) => s.symbol).join(", ")}` : "nothing reached the confidence asked for"}
              {" "}at {lastDelivery.inputs.confidence}% confidence.
            </p>
          )}
          <button type="button" className="button primary" onClick={onOpenDelivery}>Get delivery ideas</button>
        </article>

        <article className="card rec-card">
          <div className="rec-card-head">
            <h3>Intraday</h3>
            <span className="chip">Live signals</span>
            {signals.data && <span className="chip quiet" title="Server time for the last update">{(signals.data.timing.total_us / 1000).toFixed(2)} ms</span>}
          </div>
          <p className="muted">
            Buy, sell short or stay out, from momentum, VWAP, order book and trade flow over the last few minutes. Strongest right now:
          </p>
          {!query && <p className="muted small">No available cash for intraday trades.</p>}
          {query && top.length === 0 && <p className="muted small">{signals.error || "Waiting for enough trading to read the market."}</p>}
          {top.length > 0 && (
            <ul className="signal-preview">
              {top.map((s) => {
                const label = ACTION_LABEL[s.action];
                return (
                  <li key={s.symbol}>
                    <span className="strong">{s.symbol}</span>
                    <span className={`badge ${label.tone}`}>{label.text}</span>
                    <ConfidenceMeter value={s.confidence} asked={PREVIEW_CONFIDENCE} text={`${(s.confidence * 100).toFixed(0)}%`} />
                  </li>
                );
              })}
            </ul>
          )}
          <button type="button" className="button primary" onClick={onOpenIntraday}>Get intraday ideas</button>
        </article>
      </div>
    </section>
  );
}
