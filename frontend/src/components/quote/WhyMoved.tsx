import { Fragment, useState, type ReactNode } from "react";

import type { Analysis, CandlePattern, ExplainHeadline, Explanation, OHLCBar, Scope } from "../../api/types";
import { useAnalysis } from "../../hooks/useAnalysis";
import { useExplanation } from "../../hooks/useExplanation";
import { dateTime, price } from "../../lib/format";
import { SupportResistance } from "../recommendations/SupportResistance";

interface Props {
  symbol: string;
  /** The day to explain, YYYY-MM-DD; null for the latest trading day. */
  date: string | null;
  onDate: (date: string | null) => void;
  onOpenStock: (symbol: string) => void;
}

const SCOPE_LABEL: Record<Scope, string> = {
  company: "This company", peers: "Similar companies", industry: "Its industry", market: "Indian market", global: "World markets",
};

const pct = (x: number | null | undefined, digits = 2) =>
  x == null ? "—" : `${x > 0 ? "+" : x < 0 ? "−" : ""}${Math.abs(x * 100).toFixed(digits)}%`;
const tone = (x: number | null | undefined) => (x == null || x === 0 ? "" : x > 0 ? "up" : "down");
const longDay = (iso: string) =>
  new Date(`${iso}T12:00:00+05:30`).toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short", timeZone: "Asia/Kolkata" });

/** Why the stock moved on a day: Claude's analysis of the market data and that day's news, with every source shown. */
export function WhyMoved({ symbol, date, onDate, onOpenStock }: Props) {
  const explained = useExplanation(symbol, date);
  const e = explained.data;
  const ai = useAnalysis(symbol, e?.date ?? null);
  const [highlight, setHighlight] = useState<number | null>(null);

  const showEvidence = (n: number) => {
    setHighlight(n);
    document.getElementById(`ev-${n}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  const fell = e ? e.change < 0 : false;
  const title = !e ? `Why is ${symbol} moving?`
    : e.date === e.latest_date && date === null
      ? `Why did ${symbol} ${fell ? "fall" : "rise"} ${isToday(e.date) ? "today" : `on ${longDay(e.date)}`}?`
      : `Why did ${symbol} ${fell ? "fall" : "rise"} on ${longDay(e.date)}?`;

  return (
    <section className="section why" id="why" aria-labelledby="why-title">
      <div className="section-head">
        <h2 id="why-title" className="section-title">{title}</h2>
        {e && <span className={`badge ${fell ? "down" : "up"}`}>{pct(e.change)}</span>}
      </div>

      {e && (
        <div className="why-days" role="group" aria-label="Choose a day to explain">
          <span className="muted small">Explain:</span>
          <button type="button" className={date === null ? "day-chip on" : "day-chip"} onClick={() => onDate(null)}>
            Latest ({longDay(e.latest_date)})
          </button>
          {e.big_days.filter((b) => b.date !== e.latest_date).map((b) => (
            <button key={b.date} type="button" className={date === b.date ? "day-chip on" : "day-chip"} onClick={() => onDate(b.date)}>
              {longDay(b.date)} <span className={tone(b.change)}>{pct(b.change, 1)}</span>
            </button>
          ))}
          <span className="muted small">or click any day on the chart</span>
        </div>
      )}

      {explained.loading && !e && <Loading text={`Gathering ${symbol}'s prices, similar companies and the news for that day.`} />}
      {explained.error && <p className="problems" role="alert">{explained.error}</p>}

      {e && (
        <>
          <ClaudeCard analysis={ai.data} loading={ai.loading} error={ai.error} explanation={e} onCite={showEvidence} />
          <TechnicalCard explanation={e} />
          <Facts e={e} analysis={ai.data} onOpenStock={onOpenStock} />
          <Evidence items={ai.data?.evidence ?? numberLocally(e)} highlight={highlight} cited={citedNumbers(ai.data)} sentimentTotals={e.sentiment_totals} />
          <p className="method-note">
            How this is worked out: the move is split into the part the whole market explains ({symbol}'s beta of{" "}
            {e.beta ?? "—"} times the NIFTY 50's move, from a year of daily prices) and {symbol}'s own part, which is compared
            with a typical day. Similar companies, the sector index, the Indian and world markets that day, and the headlines
            published between the previous close and the end of that day are then given to an AI model, which writes the analysis
            and cites the headlines it relies on. Prices and indices from Yahoo Finance; headlines from Google News. Not investment advice.
          </p>
        </>
      )}
    </section>
  );
}

function ClaudeCard({ analysis, loading, error, explanation, onCite }: {
  analysis: Analysis | null; loading: boolean; error: string; explanation: Explanation; onCite: (n: number) => void;
}) {
  const a = analysis?.analysis;
  return (
    <article className="card why-ai" aria-live="polite">
      <header className="why-ai-head">
        <span className="ai-mark" aria-hidden="true">✦</span>
        <span className="strong">AI analysis</span>
        {analysis && <span className="chip quiet">{modelName(analysis.model)} · {Math.round(analysis.seconds)} s</span>}
        {a && <span className={`badge ${a.confidence === "high" ? "up" : a.confidence === "low" ? "down" : "neutral"}`}>{a.confidence} confidence</span>}
        {a && <span className="chip">{a.verdict}</span>}
      </header>

      {loading && (
        <>
          <Loading text={`The AI model is reading ${countHeadlines(explanation)} headlines and the Indian and world markets for ${longDay(explanation.date)}. This takes about 30 to 60 seconds.`} />
          <QuickReading explanation={explanation} />
        </>
      )}
      {error && !loading && (
        <>
          <p className="problems" role="alert">{error}</p>
          <QuickReading explanation={explanation} />
        </>
      )}
      {analysis && !a && analysis.raw && <p className="why-raw">{analysis.raw}</p>}

      {a && (
        <>
          <p className="why-headline">{cite(a.headline, onCite)}</p>
          <div className="why-drivers">
            {a.drivers.map((d, i) => (
              <div key={i} className={`why-driver ${d.direction === "negative" ? "neg" : "pos"}`}>
                <div className="why-driver-head">
                  <span className={`badge ${d.impact === "major" ? (d.direction === "negative" ? "down" : "up") : "neutral"}`}>{d.impact}</span>
                  <strong>{d.title}</strong>
                </div>
                <p>{cite(d.explanation, onCite)}</p>
                {d.evidence.length > 0 && (
                  <p className="why-cites">
                    Sources: {d.evidence.map((n) => (
                      <button key={n} type="button" className="cite" onClick={() => onCite(n)}>[{n}]</button>
                    ))}
                  </p>
                )}
              </div>
            ))}
          </div>
          <div className="why-columns">
            <div>
              <h3>Market that day</h3>
              <p>{cite(a.market_context, onCite)}</p>
            </div>
            <div>
              <h3>Specific to this stock</h3>
              <p>{cite(a.stock_specific, onCite)}</p>
            </div>
          </div>
          {a.technical_view && (
            <div className="why-columns">
              <div style={{ gridColumn: "1 / -1" }}>
                <h3>📊 Technical view</h3>
                <p>{cite(a.technical_view, onCite)}</p>
              </div>
            </div>
          )}
          {(analysis?.sr_levels || analysis?.sr_entry) && (
            <div className="why-columns">
              <div style={{ gridColumn: "1 / -1" }}>
                <SupportResistance
                  levels={analysis.sr_levels}
                  ltp={explanation.price}
                  entry={analysis.sr_entry}
                />
                {a.sr_view && <p className="hint" style={{ marginTop: 8 }}>{cite(a.sr_view, onCite)}</p>}
              </div>
            </div>
          )}
          <div className="why-columns">
            <div>
              <h3>What to watch</h3>
              <ul className="why-watch">{a.watch.map((w, i) => <li key={i}>{cite(w, onCite)}</li>)}</ul>
            </div>
            <div>
              <h3>How sure</h3>
              <p>{cite(a.confidence_reason, onCite)}</p>
            </div>
          </div>
        </>
      )}
    </article>
  );
}

/** The rule-based reading, shown at once while Claude works. */
function QuickReading({ explanation }: { explanation: Explanation }) {
  return (
    <div className="why-quick">
      <span className="muted small">Quick reading from the numbers and headlines ({explanation.verdict.toLowerCase()}):</span>
      <ul>{explanation.summary.map((s, i) => <li key={i}>{s}</li>)}</ul>
    </div>
  );
}

function Facts({ e, analysis, onOpenStock }: { e: Explanation; analysis: Analysis | null; onOpenStock: (s: string) => void }) {
  const own = e.change - (e.market_part ?? 0);
  const times = e.typical_move ? Math.abs(own) / e.typical_move : null;
  return (
    <div className="why-facts">
      <div className="stat-cards">
        <Fact label={`${e.symbol} on ${longDay(e.date)}`} value={pct(e.change)} tone={tone(e.change)}
          note={`₹${price(e.prev_close)} to ₹${price(e.price)}`} />
        <Fact label="NIFTY 50 that day" value={pct(e.market.change)} tone={tone(e.market.change)} />
        <Fact label="Part explained by the market" value={pct(e.market_part)} tone={tone(e.market_part)}
          note={e.beta != null ? `Beta ${e.beta}: it usually moves ${e.beta} times the market` : undefined} />
        <Fact label={`${e.symbol}'s own move`} value={pct(own)} tone={tone(own)}
          note={times != null ? `${times.toFixed(1)} times a typical day (${pct(e.typical_move)})` : undefined} />
        {e.sector && <Fact label={e.sector.name} value={pct(e.sector.change)} tone={tone(e.sector.change)} note="Its sector index" />}
      </div>
      {e.peers.length > 0 && (
        <div className="why-chips">
          <span className="muted small">Similar companies that day:</span>
          {e.peers.map((p) => (
            <button key={p.symbol} type="button" className="day-chip" onClick={() => onOpenStock(p.symbol)}>
              {p.symbol} <span className={tone(p.change)}>{pct(p.change)}</span>
            </button>
          ))}
        </div>
      )}
      {analysis && (
        <>
          <div className="why-chips">
            <span className="muted small">Indian market:</span>
            {analysis.india.map((m) => <span key={m.name} className="market-chip">{m.name} <span className={tone(m.change)}>{pct(m.change)}</span></span>)}
          </div>
          <div className="why-chips">
            <span className="muted small">World markets:</span>
            {analysis.world.map((m) => (
              <span key={m.name} className="market-chip" title={`Session of ${longDay(m.date)}`}>
                {m.name} <span className={tone(m.change)}>{pct(m.change)}</span>
              </span>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function Fact({ label, value, tone: t, note }: { label: string; value: string; tone: string; note?: string }) {
  return (
    <div className="stat-card">
      <span className="stat-label">{label}</span>
      <strong className={`num ${t}`}>{value}</strong>
      {note && <span className="stat-note">{note}</span>}
    </div>
  );
}

function Evidence({ items, highlight, cited, sentimentTotals }: {
  items: (ExplainHeadline & { n: number })[]; highlight: number | null; cited: Set<number>;
  sentimentTotals?: Explanation["sentiment_totals"];
}) {
  const scopes = (Object.keys(SCOPE_LABEL) as Scope[]).filter((s) => items.some((h) => h.scope === s));
  return (
    <details className="card why-evidence" open>
      <summary>
        <strong>Evidence: {items.length} headlines</strong>
        <span className="muted small"> from the previous close to the end of that day{cited.size ? `; ${cited.size} cited by Claude` : ""}</span>
      </summary>
      {sentimentTotals && Object.keys(sentimentTotals).length > 0 && (
        <div className="why-chips" style={{ marginTop: 8 }}>
          <span className="muted small">FinBERT sentiment:</span>
          {(Object.keys(SCOPE_LABEL) as Scope[]).filter((s) => sentimentTotals[s]).map((s) => {
            const t = sentimentTotals[s]!;
            return (
              <span key={s} className="market-chip" title={`${t.positive} positive, ${t.negative} negative, ${t.neutral} neutral`}>
                {SCOPE_LABEL[s]}: <span className={t.avg_score > 0.05 ? "up" : t.avg_score < -0.05 ? "down" : ""}>{t.avg_score > 0 ? "+" : ""}{(t.avg_score * 100).toFixed(0)}</span>
                <span className="muted small"> ({t.count})</span>
              </span>
            );
          })}
        </div>
      )}
      {items.length === 0 && <p className="muted">No headlines were found for that day.</p>}
      {scopes.map((scope) => (
        <div key={scope} className="ev-group">
          <h4>{SCOPE_LABEL[scope]}</h4>
          <ol>
            {items.filter((h) => h.scope === scope).map((h) => (
              <li key={h.n} id={`ev-${h.n}`} className={[h.n === highlight ? "hit" : "", cited.has(h.n) ? "cited" : ""].join(" ").trim()}>
                <span className="ev-n">[{h.n}]</span>
                <span className={`ev-dot ${h.tone > 0 ? "up" : h.tone < 0 ? "down" : ""}`} aria-hidden="true" />
                <span className="ev-text">
                  <a href={h.url} target="_blank" rel="noopener noreferrer">{h.title}</a>
                  {h.sentiment && (
                    <span className={`finbert-badge ${h.sentiment.label}`} title={`FinBERT: P(pos)=${h.sentiment.pos} P(neg)=${h.sentiment.neg} P(neu)=${h.sentiment.neu}`}>
                      {h.sentiment.label === "positive" ? "▲" : h.sentiment.label === "negative" ? "▼" : "●"} {h.sentiment.label} {(h.sentiment.score * 100).toFixed(0)}
                    </span>
                  )}
                  <span className="muted small"> {h.source} · {dateTime(h.published)}{h.reasons.length ? ` · ${h.reasons.join(", ")}` : ""}</span>
                </span>
              </li>
            ))}
          </ol>
        </div>
      ))}
    </details>
  );
}

/** The chart CNN image, its prediction, candlestick patterns and their historical up rates. */
function TechnicalCard({ explanation }: { explanation: Explanation }) {
  const cnn = explanation.chart_cnn;
  const patterns = explanation.candle_patterns;
  const ohlcBars = explanation.ohlc_bars;
  const hasPatterns = patterns && (patterns.today.length > 0 || patterns.previous.length > 0);
  const hasCnn = cnn && (cnn.today || cnn.previous);
  const hasBars = ohlcBars && ohlcBars.length > 0;
  if (!hasPatterns && !hasCnn && !hasBars) return null;

  return (
    <article className="card why-tech">
      <header className="why-ai-head">
        <span className="ai-mark" aria-hidden="true">📊</span>
        <strong>Chart model &amp; patterns</strong>
      </header>

      <div className="tech-grid">
        {hasCnn && cnn.today && (
          <div className="tech-cnn">
            <img
              src={`data:image/png;base64,${cnn.today.image_b64}`}
              alt="20-day candlestick chart"
              className="cnn-image"
              style={{ imageRendering: "pixelated" }}
            />
            <div className="cnn-info">
              <div className="cnn-prob">
                <span className="stat-label">P(up next 5 days)</span>
                <strong className={`num ${cnn.today.prob_up != null && cnn.today.prob_up > 0.5 ? "up" : "down"}`}>
                  {cnn.today.prob_up != null ? `${(cnn.today.prob_up * 100).toFixed(1)}%` : "—"}
                </strong>
              </div>
              {cnn.today.accuracy != null && (
                <span className="muted small">
                  Test accuracy: {(cnn.today.accuracy * 100).toFixed(1)}% (baseline: {(cnn.today.baseline! * 100).toFixed(1)}%)
                  {cnn.today.auc != null && ` · AUC: ${cnn.today.auc.toFixed(3)}`}
                </span>
              )}
              {cnn.previous && cnn.previous.prob_up != null && (
                <span className="muted small">
                  Day before: P(up) = {(cnn.previous.prob_up * 100).toFixed(1)}%
                  {cnn.today.prob_up != null && (
                    cnn.previous.prob_up < cnn.today.prob_up
                      ? " → chart turned more bullish"
                      : cnn.previous.prob_up > cnn.today.prob_up
                        ? " → chart turned more bearish"
                        : ""
                  )}
                </span>
              )}
              <span className="muted small" style={{ fontStyle: "italic" }}>
                Method: Jiang, Kelly &amp; Xiu (2023). 20-day chart as a 64×60 image → CNN. Honest accuracy — not a trading signal.
              </span>
            </div>
          </div>
        )}

        <div className="tech-patterns">
          {hasBars && (
            <>
              <h4>Recent candles</h4>
              <CandlestickChart bars={ohlcBars!} date={explanation.date} />
            </>
          )}
          {hasPatterns && (
            <>
              <h4>Patterns detected</h4>
              {patterns!.today.map((p) => <PatternBadge key={p.name} pattern={p} when="today" />)}
              {patterns!.previous.map((p) => <PatternBadge key={`prev-${p.name}`} pattern={p} when="previous day" />)}
            </>
          )}
        </div>
      </div>
    </article>
  );
}

/** Inline SVG candlestick chart from OHLC bars. */
function CandlestickChart({ bars, date }: { bars: OHLCBar[]; date: string }) {
  if (!bars || bars.length === 0) return null;
  const W = 280, H = 140, PAD = 16;
  const cw = Math.floor((W - PAD * 2) / bars.length);  // candle width
  const allPrices = bars.flatMap((b) => [b.high, b.low]);
  const pMin = Math.min(...allPrices);
  const pMax = Math.max(...allPrices);
  const range = pMax - pMin || 1;
  const y = (p: number) => PAD + (1 - (p - pMin) / range) * (H - PAD * 2);

  return (
    <svg className="candle-chart" viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-label="Candlestick chart">
      {bars.map((b, i) => {
        const x = PAD + i * cw + cw / 2;
        const isUp = b.close >= b.open;
        const color = isUp ? "var(--up)" : "var(--down)";
        const bodyTop = y(Math.max(b.open, b.close));
        const bodyBot = y(Math.min(b.open, b.close));
        const bodyH = Math.max(bodyBot - bodyTop, 1);
        const isExplained = b.date === date;
        return (
          <g key={b.date}>
            {/* Wick */}
            <line x1={x} y1={y(b.high)} x2={x} y2={y(b.low)} stroke={color} strokeWidth={1} />
            {/* Body */}
            <rect x={x - cw * 0.35} y={bodyTop} width={cw * 0.7} height={bodyH}
              fill={isUp ? "transparent" : color} stroke={color} strokeWidth={1} />
            {/* Highlight explained day */}
            {isExplained && (
              <line x1={x} y1={H - 4} x2={x} y2={H - 1} stroke="var(--accent)" strokeWidth={3} />
            )}
          </g>
        );
      })}
    </svg>
  );
}

function PatternBadge({ pattern, when }: { pattern: CandlePattern; when: string }) {
  return (
    <div className={`pattern-row ${pattern.bias}`}>
      <span className={`badge ${pattern.bias === "bullish" ? "up" : pattern.bias === "bearish" ? "down" : "neutral"}`}>
        {pattern.name}
      </span>
      <span className="muted small">
        {when} · {pattern.bias} · hist. up rate {(pattern.up_rate * 100).toFixed(0)}% · {pattern.note}
      </span>
    </div>
  );
}

function Loading({ text }: { text: string }) {
  return (
    <div className="why-loading" role="status">
      <div className="spinner" aria-hidden="true" />
      <span>{text}</span>
    </div>
  );
}

/** Turns "[3]" and "[3][5]" in Claude's text into buttons that jump to the headline. */
function cite(text: string, onCite: (n: number) => void): ReactNode {
  const parts = text.split(/(\[\d+\])/g);
  return parts.map((part, i) => {
    const m = /^\[(\d+)\]$/.exec(part);
    return m
      ? <button key={i} type="button" className="cite" onClick={() => onCite(Number(m[1]))}>{part}</button>
      : <Fragment key={i}>{part}</Fragment>;
  });
}

function citedNumbers(analysis: Analysis | null): Set<number> {
  const out = new Set<number>();
  const a = analysis?.analysis;
  if (!a) return out;
  a.drivers.forEach((d) => d.evidence.forEach((n) => out.add(n)));
  const text = [a.headline, a.market_context, a.stock_specific, a.confidence_reason, ...a.watch, ...a.drivers.map((d) => d.explanation)].join(" ");
  for (const m of text.matchAll(/\[(\d+)\]/g)) out.add(Number(m[1]));
  return out;
}

/** The same numbering the server gives Claude, so headlines can be shown before the analysis arrives. */
function numberLocally(e: Explanation): (ExplainHeadline & { n: number })[] {
  const out: (ExplainHeadline & { n: number })[] = [];
  for (const scope of Object.keys(SCOPE_LABEL) as Scope[]) {
    for (const h of (e.headlines[scope] ?? []).slice(0, 10)) out.push({ ...h, n: out.length + 1 });
  }
  return out;
}

function countHeadlines(e: Explanation): number {
  return numberLocally(e).length;
}

function modelName(id: string): string {
  const m = /claude-(\w+)-(\d+)-(\d+)/.exec(id);
  if (m) return `Claude ${m[1][0].toUpperCase()}${m[1].slice(1)} ${m[2]}.${m[3]}`;
  return `${id.split("/").pop()?.replace(":free", "") ?? id} (free, via OpenRouter)`;
}

function isToday(iso: string): boolean {
  return iso === new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });
}
