import { useMemo } from "react";

import type { Portfolio, Recommendation } from "../../api/types";
import { useIntradaySignals } from "../../hooks/useIntradaySignals";
import { SignalBar } from "../ui/SignalBar";
import { ACTION_LABEL } from "./IntradayModal";

interface Props {
  watchlist: string[];
  portfolio: Portfolio | null;
  lastDelivery: Recommendation | null;
  onOpenDelivery: () => void;
  onOpenIntraday: () => void;
}

const PREVIEW_MARGIN = 50_000 * 100;

/** The two recommendation tools side by side, with a live preview of the strongest signals in your watchlist. */
export function RecommendationsPanel({ watchlist, portfolio, lastDelivery, onOpenDelivery, onOpenIntraday }: Props) {
  const available = portfolio?.available ?? 0;
  const key = watchlist.slice(0, 20).join(",");
  const query = useMemo(
    () => (key && available > 0 ? { symbols: key.split(","), confidences: {}, budget: Math.min(PREVIEW_MARGIN, available) } : null),
    // Re-ask only when the watchlist changes or cash crosses the preview amount, not on every cash update.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [key, available >= PREVIEW_MARGIN, available > 0],
  );
  const signals = useIntradaySignals(query, true, 2000);
  const top = signals.data
    ? [...signals.data.stocks].filter((s) => s.model_score != null).sort((a, b) => Math.abs(b.model_score ?? 0) - Math.abs(a.model_score ?? 0)).slice(0, 4)
    : [];
  const buys = lastDelivery?.stocks.filter((s) => s.decision === "BUY") ?? [];

  return (
    <section className="section" id="recommendations" aria-labelledby="rec-title">
      <h2 id="rec-title" className="section-title">Recommendations</h2>
      <div className="rec-grid">
        <article className="card rec-card">
          <div className="rec-card-head">
            <h3>Delivery</h3>
            <span className="chip">Your views + portfolio optimisation</span>
          </div>
          <p className="muted">
            Which stocks to buy and hold, and how much money each should get. You read each stock's latest news and say how
            confident you are in it; the optimiser (20,000 random portfolios and SLSQP on prices since 2015) combines your views
            with the history, then re-runs 200 times to check how stable each pick is.
          </p>
          {lastDelivery && (
            <p className="rec-last">
              Last result: {buys.length ? `buy ${buys.map((s) => s.symbol).join(", ")}` : "no stock was picked often enough"}.
            </p>
          )}
          <button type="button" className="button primary" onClick={onOpenDelivery}>Get delivery ideas</button>
        </article>

        <article className="card rec-card">
          <div className="rec-card-head">
            <h3>Intraday</h3>
            <span className="chip">Your views + live signals</span>
            {signals.data && <span className="chip quiet" title="Server time for the last update">{(signals.data.timing.total_us / 1000).toFixed(2)} ms</span>}
          </div>
          <p className="muted">
            Buy, sell short or stay out, from today's real trading (momentum, VWAP, trade flow) and your own view of each stock.
            Strongest live signals in your watchlist, before your views:
          </p>
          {!query && <p className="muted small">Add stocks to your watchlist and keep some cash available.</p>}
          {query && top.length === 0 && <p className="muted small">{signals.error || signals.data?.stocks[0]?.note || "Reading the market."}</p>}
          {top.length > 0 && (
            <ul className="signal-preview">
              {top.map((s) => {
                const direction = (s.model_score ?? 0) >= 0 ? "Up" : "Down";
                const label = signals.data?.session.intraday_open ? ACTION_LABEL[s.action] : { text: direction, tone: direction === "Up" ? "up" as const : "down" as const };
                return (
                  <li key={s.symbol}>
                    <span className="strong">{s.symbol}</span>
                    <span className={`badge ${label.tone}`}>{label.text}</span>
                    <span className="view-cell"><SignalBar value={s.model_score ?? 0} label="Live signals" /> <span className="num small muted">{(s.model_score ?? 0) >= 0 ? "+" : ""}{(s.model_score ?? 0).toFixed(2)}</span></span>
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
