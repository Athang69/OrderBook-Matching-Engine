import { useState, type MouseEvent } from "react";

import type { Bar, ChartRange, Quote } from "../../api/types";
import { useChart } from "../../hooks/useChart";
import { useElementWidth } from "../../hooks/useElementWidth";
import { axisDate, clock, dateTime, price, qty } from "../../lib/format";

interface Props {
  symbol: string;
  quote: Quote | undefined;
}

const RANGES: [ChartRange, string][] = [["1d", "1D"], ["5d", "5D"], ["1mo", "1M"], ["6mo", "6M"], ["1y", "1Y"], ["5y", "5Y"]];
const HEIGHT = 300;
const M = { top: 16, right: 76, bottom: 28, left: 8 };

/** Closing price of each bar over the chosen range; for one day, shaded against the previous close. */
export function PriceChart({ symbol, quote }: Props) {
  const [range, setRange] = useState<ChartRange>("1d");
  const [hover, setHover] = useState<number | null>(null);
  const [frame, width] = useElementWidth<HTMLDivElement>(700);
  const { bars, prevClose, loading, error } = useChart(symbol, range, quote);

  const base = range === "1d" ? prevClose ?? quote?.prev_close ?? null : bars[0]?.[4] ?? null;
  const innerW = Math.max(100, width - M.left - M.right);
  const innerH = HEIGHT - M.top - M.bottom;
  const chart = bars.length >= 2 ? geometry(bars, base, innerW, innerH, range) : null;
  const last = bars.length ? bars[bars.length - 1][4] : null;
  const tone = last != null && base != null && last < base ? "down" : "up";
  const hovered = hover == null ? null : bars[hover];
  const change = last != null && base ? ((last - base) / base) * 100 : null;

  const onMove = (event: MouseEvent<SVGSVGElement>) => {
    if (!chart) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const at = event.clientX - rect.left - M.left;
    let nearest = 0;
    for (let i = 1; i < bars.length; i++) if (Math.abs(chart.x(i) - at) < Math.abs(chart.x(nearest) - at)) nearest = i;
    setHover(nearest);
  };

  return (
    <section className="card chart-card" id="chart" aria-labelledby="chart-title">
      <div className="card-head">
        <h2 id="chart-title" className="sr-only">Price chart</h2>
        <div className="range-tabs" role="tablist" aria-label="Chart range">
          {RANGES.map(([value, label]) => (
            <button key={value} type="button" role="tab" aria-selected={range === value} className={range === value ? "on" : ""}
              onClick={() => { setRange(value); setHover(null); }}>
              {label}
            </button>
          ))}
        </div>
        {change != null && (
          <span className={`num small ${change < 0 ? "down" : "up"}`}>
            {change >= 0 ? "+" : "−"}{Math.abs(change).toFixed(2)}% {range === "1d" ? "today" : `over ${RANGES.find(([r]) => r === range)?.[1]}`}
          </span>
        )}
      </div>
      <div ref={frame} className="chart-frame">
        {!chart ? (
          <p className="empty" style={{ height: HEIGHT }}>{error || (loading ? "Loading the chart." : "No trades yet in this range.")}</p>
        ) : (
          <>
            <svg width={width} height={HEIGHT} onMouseMove={onMove} onMouseLeave={() => setHover(null)} role="img"
              aria-label={`${symbol} price over ${range}; now ${price(last)}`}>
              <defs>
                <linearGradient id="area-up" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" className="stop-up" stopOpacity="0.35" />
                  <stop offset="100%" className="stop-up" stopOpacity="0" />
                </linearGradient>
                <linearGradient id="area-down" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" className="stop-down" stopOpacity="0.35" />
                  <stop offset="100%" className="stop-down" stopOpacity="0" />
                </linearGradient>
              </defs>
              <g transform={`translate(${M.left},${M.top})`}>
                {chart.ticks.map((value) => (
                  <g key={value}>
                    <line className="grid" x1={0} x2={innerW} y1={chart.y(value)} y2={chart.y(value)} />
                    <text className="axis" x={innerW + 8} y={chart.y(value)} dominantBaseline="middle">{price(value)}</text>
                  </g>
                ))}
                <path className={`area ${tone}`} d={chart.area} fill={`url(#area-${tone})`} />
                <path className={`line ${tone}`} d={chart.line} />
                {chart.showBase && base != null && (
                  <>
                    <line className="baseline" x1={0} x2={innerW} y1={chart.y(base)} y2={chart.y(base)} />
                    <PriceTag x={innerW + 4} y={chart.y(base)} text={price(base)} kind="base" />
                  </>
                )}
                {last != null && <PriceTag x={innerW + 4} y={chart.y(last)} text={price(last)} kind={tone} />}
                {chart.timeTicks.map(([x, text], k) => (
                  <text key={k} className="axis" x={x} y={innerH + 20} textAnchor={k === 0 ? "start" : "middle"}>{text}</text>
                ))}
                {hovered && hover != null && (
                  <g>
                    <line className="crosshair" x1={chart.x(hover)} x2={chart.x(hover)} y1={0} y2={innerH} />
                    <circle className={`marker ${tone}`} cx={chart.x(hover)} cy={chart.y(hovered[4])} r={4} />
                  </g>
                )}
              </g>
            </svg>
            {hovered && hover != null && (
              <div className="tooltip" style={{ left: Math.min(M.left + chart.x(hover) + 12, width - 170), top: 12 }}>
                <span className="muted">{range === "1d" ? clock(hovered[0]).slice(0, 5) : range === "5d" || range === "1mo" ? dateTime(hovered[0]) : axisDate(hovered[0], true)}</span>
                <strong className="num">{price(hovered[4])}</strong>
                <span className="num muted">O {price(hovered[1])} H {price(hovered[2])} L {price(hovered[3])}</span>
                {hovered[5] > 0 && <span className="num muted">Volume {qty(hovered[5])}</span>}
              </div>
            )}
          </>
        )}
      </div>
      <p className="legend-note">
        {range === "1d" ? (
          <><span className="baseline-key" aria-hidden="true" /> Previous close {price(base)} {"·"} one-minute bars, the last one following the live price</>
        ) : (
          <>Change measured from the first bar shown {"·"} {range === "5d" ? "5-minute" : range === "1mo" ? "30-minute" : range === "5y" ? "weekly" : "daily"} bars</>
        )}
      </p>
    </section>
  );
}

function label(t: number, range: ChartRange): string {
  if (range === "1d") return clock(t).slice(0, 5);
  return axisDate(t, range === "1y" || range === "5y");
}

function PriceTag({ x, y, text, kind }: { x: number; y: number; text: string; kind: "up" | "down" | "base" }) {
  return (
    <g className={`price-tag ${kind}`} transform={`translate(${x},${y - 10})`}>
      <rect width={68} height={20} rx={4} />
      <text x={34} y={10} textAnchor="middle" dominantBaseline="central">{text}</text>
    </g>
  );
}

const SESSION_MINUTES = 375; // 9:15 am to 3:30 pm
const IST_OFFSET = 19_800; // seconds

/**
 * Bars are spaced evenly by position, as brokers' charts do, so nights and weekends leave no gaps. A one-day
 * chart is laid out over the whole session by the minute, so it fills from the left as the day goes on.
 */
function geometry(bars: Bar[], base: number | null, w: number, h: number, range: ChartRange) {
  let low = Infinity;
  let high = -Infinity;
  for (const bar of bars) {
    low = Math.min(low, bar[4]);
    high = Math.max(high, bar[4]);
  }
  const span = Math.max(high - low, 1);
  const showBase = range === "1d" && base != null && base >= low - span * 1.5 && base <= high + span * 1.5;
  if (showBase && base != null) {
    low = Math.min(low, base);
    high = Math.max(high, base);
  }
  const pad = Math.max((high - low) * 0.1, 5);
  low -= pad;
  high += pad;
  const n = bars.length;
  // 9:15 am, Indian time, on the day of the first bar.
  const open = Math.floor((bars[0][0] + IST_OFFSET) / 86_400) * 86_400 - IST_OFFSET + 555 * 60;
  const position = range === "1d"
    ? bars.map((bar) => Math.min(1, Math.max(0, (bar[0] - open) / 60 / SESSION_MINUTES)))
    : bars.map((_, i) => i / Math.max(1, n - 1));
  const x = (i: number) => position[i] * w;
  const y = (p: number) => (1 - (p - low) / (high - low)) * h;
  const line = bars.map((bar, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(bar[4]).toFixed(1)}`).join("");
  const area = `${line}L${x(n - 1).toFixed(1)},${h}L${x(0).toFixed(1)},${h}Z`;
  const ticks = niceTicks(low + pad, high - pad, 4);
  const count = Math.max(2, Math.min(6, Math.floor(w / 110)));
  const timeTicks: [number, string][] = [];
  for (let k = 0; k < count; k++) {
    const fraction = k / (count - 1);
    if (range === "1d") {
      timeTicks.push([fraction * w, clock(open + fraction * SESSION_MINUTES * 60).slice(0, 5)]);
    } else if (k < count - 1 || n > 1) {
      const i = Math.round(fraction * (n - 1));
      timeTicks.push([x(i), label(bars[i][0], range)]);
    }
  }
  return { x, y, line, area, ticks, timeTicks, showBase };
}

function niceTicks(low: number, high: number, count: number): number[] {
  const raw = Math.max(1, (high - low) / count);
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((s) => s >= raw) ?? raw;
  const out = [];
  for (let v = Math.ceil(low / step) * step; v <= high; v += step) out.push(Math.round(v));
  return out;
}
