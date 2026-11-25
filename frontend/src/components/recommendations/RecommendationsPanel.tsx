import { useMemo } from "react";

import type { Portfolio, Recommendation } from "../../api/types";
import { useIntradaySignals } from "../../hooks/useIntradaySignals";

interface Props {
  watchlist: string[];
  portfolio: Portfolio | null;
  lastDelivery: Recommendation | null;
  onOpenDelivery: () => void;
  onOpenIntraday: () => void;
}

const PREVIEW_MARGIN = 50_000 * 100;

export function RecommendationsPanel({ watchlist, portfolio, lastDelivery, onOpenDelivery, onOpenIntraday }: Props) {
  const available = portfolio?.available ?? 0;
  const key = watchlist.slice(0, 20).join(",");
  const query = useMemo(
    () => (key && available > 0 ? { symbols: key.split(","), confidences: {}, budget: Math.min(PREVIEW_MARGIN, available) } : null),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [key, available >= PREVIEW_MARGIN, available > 0],
  );
  const signals = useIntradaySignals(query, true, 2000);
  // Only show actual BUY/SELL signals, sorted by absolute score
  const actionSignals = signals.data
    ? [...signals.data.stocks]
        .filter((s) => s.action === "BUY" || s.action === "SELL")
        .sort((a, b) => Math.abs(b.model_score ?? 0) - Math.abs(a.model_score ?? 0))
        .slice(0, 4)
    : [];
  // Fallback: show top scored stocks when market closed
  const topScored = signals.data && actionSignals.length === 0
    ? [...signals.data.stocks]
        .filter((s) => s.model_score != null)
        .sort((a, b) => Math.abs(b.model_score ?? 0) - Math.abs(a.model_score ?? 0))
        .slice(0, 4)
    : [];
  const displaySignals = actionSignals.length > 0 ? actionSignals : topScored;
  const buys = lastDelivery?.stocks.filter((s) => s.decision === "BUY") ?? [];

  return (
    <section className="section" id="recommendations" aria-labelledby="rec-title">
      <div className="section-head">
        <h2 id="rec-title" className="section-title">AI Ideas</h2>
      </div>
      <div className="rec-grid">

        {/* Delivery card */}
        <article className="rec-card">
          <div className="rec-card-label">Portfolio optimisation</div>
          <h3 className="rec-card-title">Delivery</h3>
          <p className="rec-card-desc">Allocate capital across your watchlist based on confidence views and risk-adjusted returns.</p>
          {lastDelivery && buys.length > 0 && (
            <div className="rec-last-result">
              <span className="muted small">Last picks</span>
              <span className="small strong">{buys.map((s) => s.symbol).join(" · ")}</span>
            </div>
          )}
          <button type="button" className="button primary small" onClick={onOpenDelivery} style={{ marginTop: "auto" }}>
            Get ideas
          </button>
        </article>

        {/* Intraday card */}
        <article className="rec-card">
          <div className="rec-card-label">
            Live signals
            {signals.data && (
              <span className="rec-latency">{(signals.data.timing.total_us / 1000).toFixed(1)} ms</span>
            )}
          </div>
          <h3 className="rec-card-title">Intraday</h3>

          {signals.data && !signals.data.session.intraday_open ? (
            // Closed: momentum and trade flow need live trades, so the scores would all look alike.
            <p className="muted small" style={{ minHeight: 60, flex: 1 }}>
              {signals.data.session.state === "OPEN"
                ? "Intraday trading closed at 3:20 pm. Live signals start again at 9:15 am."
                : `${signals.data.session.label}. Live signals come from real trades and start at 9:15 am.`}
            </p>
          ) : displaySignals.length > 0 ? (
            <ul className="signal-preview">
              {displaySignals.map((s) => {
                const score = s.model_score ?? 0;
                const pill = s.action === "BUY" ? "up" : s.action === "SELL" ? "down" : "";
                return (
                  <li key={s.symbol}>
                    <span className="sig-sym">{s.symbol}</span>
                    <span className={`sig-pill ${pill}`}>
                      {s.action === "BUY" ? "Buy" : s.action === "SELL" ? "Sell" : "Wait"}
                    </span>
                    <span className={`sig-score num ${score >= 0 ? "up" : "down"}`}>
                      {score >= 0 ? "+" : ""}{score.toFixed(2)}
                    </span>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="muted small" style={{ minHeight: 60, flex: 1 }}>
              {!query
                ? "Add stocks to your watchlist to see signals."
                : signals.error || "Reading the market…"}
            </p>
          )}

          <button type="button" className="button primary small" onClick={onOpenIntraday} style={{ marginTop: "auto" }}>
            Get ideas
          </button>
        </article>
      </div>
    </section>
  );
}
