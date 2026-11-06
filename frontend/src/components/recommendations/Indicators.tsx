import type {
  BetaData,
  FibLevel,
  FibonacciData,
  IndicatorData,
  IndicatorResult,
  MACDData,
  RSIData,
} from "../../api/types";
import { price } from "../../lib/format";

interface Props {
  indicators: IndicatorData | null | undefined;
  ltp: number | null | undefined;
  loading?: boolean;
}

// ── helpers ──────────────────────────────────────────────────────────────────

function hasError(r: IndicatorResult<unknown>): r is { error: string } {
  return r != null && typeof (r as { error?: unknown }).error === "string";
}

function isData<T>(r: IndicatorResult<T>): r is T {
  return r != null && !hasError(r);
}

function verdictTone(verdict: string): string {
  const v = verdict.toLowerCase();
  if (v.includes("overbought") || v.includes("bearish") || v.includes("inverse") || v.includes("highly volatile"))
    return "ind-down";
  if (v.includes("oversold") || v.includes("bullish"))
    return "ind-up";
  return "ind-neutral";
}

function macdHistArrow(histogram: number): string {
  if (histogram > 0) return " ▲";
  if (histogram < 0) return " ▼";
  return "";
}

// ── RSI gauge ────────────────────────────────────────────────────────────────

function RSIGauge({ value }: { value: number }) {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div className="ind-gauge" role="img" aria-label={`RSI gauge ${pct.toFixed(0)}`}>
      <div className="ind-gauge-track">
        <div className="ind-gauge-zone ind-zone-down"  style={{ left: "0%",   width: "30%" }} aria-hidden="true" />
        <div className="ind-gauge-zone ind-zone-up"    style={{ left: "70%",  width: "30%" }} aria-hidden="true" />
        <div className="ind-gauge-needle" style={{ left: `${pct}%` }} aria-hidden="true" />
      </div>
      <div className="ind-gauge-labels" aria-hidden="true">
        <span>0</span><span>30</span><span>70</span><span>100</span>
      </div>
    </div>
  );
}

// ── Fibonacci panel ───────────────────────────────────────────────────────────

function FibPanel({ fib, ltp }: { fib: FibonacciData; ltp: number | null | undefined }) {
  const levels: FibLevel[] = [...fib.levels].sort((a, b) => b.price - a.price);
  const isLtpNear = (p: number) =>
    ltp != null && Math.abs(ltp - p) / ltp <= 0.005;

  return (
    <div className="ind-fib-panel">
      <div className="ind-fib-header">
        <span className="ind-fib-trend">{fib.trend === "uptrend" ? "↑ Uptrend" : "↓ Downtrend"}</span>
        <span className="ind-fib-anchors muted small">
          Swing: {fib.swing_low.toFixed(2)} – {fib.swing_high.toFixed(2)}
        </span>
      </div>
      <ul className="ind-fib-levels" role="list" aria-label="Fibonacci levels">
        {levels.map((lv) => {
          const near     = isLtpNear(lv.price);
          const isAbove  = lv.price === fib.nearest_above;
          const isBelow  = lv.price === fib.nearest_below;
          return (
            <li key={lv.ratio}
              className={`ind-fib-row${near ? " ind-fib-near" : ""}${isAbove ? " ind-fib-resist" : ""}${isBelow ? " ind-fib-support" : ""}`}>
              <span className="ind-fib-label">{(lv.ratio * 100).toFixed(1)}%</span>
              <span className="ind-fib-price num">{lv.price.toFixed(2)}</span>
              {near && ltp != null && (
                <span className="ind-fib-pill" aria-label={`Current price ${price(Math.round(ltp * 100))}`}>
                  PRICE
                </span>
              )}
            </li>
          );
        })}
      </ul>
      <p className="ind-fib-verdict hint">{fib.verdict}</p>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function IndicatorsPanel({ indicators, ltp, loading }: Props) {
  if (loading) {
    return (
      <div className="ind-panel">
        <div className="ind-header">
          <span className="strong">Indicators</span>
          <InfoTip text="RSI, MACD and Beta are computed from 1-year daily history. Fibonacci uses the 50-day swing high and low. All are for context only — not financial advice." />
        </div>
        <div className="ind-skeleton">
          {[0, 1, 2].map((i) => <div key={i} className="ind-skeleton-row" />)}
        </div>
      </div>
    );
  }

  if (!indicators) {
    return (
      <div className="ind-panel">
        <div className="ind-header">
          <span className="strong">Indicators</span>
        </div>
        <div className="ind-empty">
          <span className="muted small">Not enough data yet</span>
        </div>
      </div>
    );
  }

  const { rsi, macd, fibonacci, beta } = indicators;
  const rsiData  = isData<RSIData>(rsi)        ? rsi        : null;
  const macdData = isData<MACDData>(macd)      ? macd       : null;
  const fibData  = isData<FibonacciData>(fibonacci) ? fibonacci : null;
  const betaData = isData<BetaData>(beta)      ? beta       : null;

  const rsiError  = hasError(rsi)  ? rsi.error  : null;
  const macdError = hasError(macd) ? macd.error : null;
  const fibError  = hasError(fibonacci) ? fibonacci.error : null;
  const betaError = hasError(beta) ? beta.error : null;

  return (
    <div className="ind-panel">
      <div className="ind-header">
        <span className="strong">Indicators</span>
        <InfoTip text="RSI, MACD and Beta are computed from 1-year daily history. Fibonacci uses the 50-day swing high and low. All are for context only — not financial advice." />
      </div>

      <table className="ind-table" aria-label="Technical indicators">
        <thead>
          <tr>
            <th>Indicator</th>
            <th className="num">Value</th>
            <th>Verdict</th>
          </tr>
        </thead>
        <tbody>
          {/* RSI */}
          <tr>
            <td>
              <span className="ind-name">RSI (14)</span>
              <InfoTip text="Relative Strength Index: 70+ is overbought (recent gains are very strong), 30− is oversold (recent losses are heavy). Computed with Wilder's smoothing on daily closes." />
            </td>
            <td className="num">
              {rsiData ? (
                <span>{rsiData.value >= 0 ? "+" : ""}{rsiData.value.toFixed(2)}</span>
              ) : (
                <span className="muted">—</span>
              )}
            </td>
            <td>
              {rsiData ? (
                <span className={`ind-verdict ${verdictTone(rsiData.verdict)}`}
                      title={rsiData.reason} aria-label={`${rsiData.verdict}: ${rsiData.reason}`}>
                  {rsiData.verdict}
                </span>
              ) : (
                <span className="muted small">{rsiError ? _errorLabel(rsiError) : "—"}</span>
              )}
            </td>
          </tr>

          {/* MACD */}
          <tr>
            <td>
              <span className="ind-name">MACD (12, 26, 9)</span>
              <InfoTip text="Moving Average Convergence Divergence: the gap between a 12-day and 26-day EMA. When MACD crosses above its 9-day signal line the trend is turning bullish; below is bearish." />
            </td>
            <td className="num">
              {macdData ? (
                <span>{macdData.macd >= 0 ? "+" : ""}{macdData.macd.toFixed(2)}{macdHistArrow(macdData.histogram)}</span>
              ) : (
                <span className="muted">—</span>
              )}
            </td>
            <td>
              {macdData ? (
                <span className={`ind-verdict ${verdictTone(macdData.verdict)}`}
                      title={macdData.reason} aria-label={`${macdData.verdict}: ${macdData.reason}`}>
                  {macdData.verdict}
                </span>
              ) : (
                <span className="muted small">{macdError ? _errorLabel(macdError) : "—"}</span>
              )}
            </td>
          </tr>

          {/* Beta */}
          <tr>
            <td>
              <span className="ind-name">Beta</span>
              <InfoTip text="Sensitivity to NIFTY 50 moves over the past year of daily returns. Above 1.5 amplifies the market; near 1 tracks it; below 0.8 is defensive; negative means it moves opposite the market." />
            </td>
            <td className="num">
              {betaData ? (
                <span>{betaData.value >= 0 ? "+" : ""}{betaData.value.toFixed(2)}</span>
              ) : (
                <span className="muted">—</span>
              )}
            </td>
            <td>
              {betaData ? (
                <span className={`ind-verdict ${verdictTone(betaData.verdict)}`}
                      title={betaData.reason} aria-label={`${betaData.verdict}: ${betaData.reason}`}>
                  {betaData.verdict}
                </span>
              ) : (
                <span className="muted small">{betaError ? _errorLabel(betaError) : "—"}</span>
              )}
            </td>
          </tr>
        </tbody>
      </table>

      {/* RSI gauge */}
      {rsiData && <RSIGauge value={rsiData.value} />}

      {/* Fibonacci panel */}
      {fibData ? (
        <div className="ind-fib-section">
          <div className="ind-fib-title">
            <span className="strong small">Fibonacci (50-day)</span>
            <InfoTip text="Retracement levels from the 50-day swing high and low. Price near a 61.8% or 38.2% level often acts as support or resistance. Trend direction is from the order of the swing points." />
          </div>
          <FibPanel fib={fibData} ltp={ltp} />
        </div>
      ) : fibError ? (
        <p className="muted small ind-fib-error">{_errorLabel(fibError)}</p>
      ) : null}

      <p className="ind-disclaimer hint">
        Algorithmic indicators for reference only — not financial advice.
      </p>
    </div>
  );
}

function InfoTip({ text }: { text: string }) {
  return (
    <span className="ind-info" title={text} aria-label={`Info: ${text}`}>ⓘ</span>
  );
}

function _errorLabel(error: string): string {
  if (error === "insufficient_data") return "Not enough history yet";
  if (error === "data_unavailable")  return "Data unavailable";
  if (error === "market_flat")       return "Market returns are flat";
  if (error === "no_clear_swing")    return "No clear swing";
  if (error === "benchmark_unavailable") return "Benchmark data unavailable";
  return "Unavailable";
}
