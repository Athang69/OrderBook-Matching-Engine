import { useState, type MouseEvent } from "react";

import type { PricePoint } from "../../api/types";
import { clock, price } from "../../lib/format";
import { useElementWidth } from "../../hooks/useElementWidth";

interface Props {
  symbol: string;
  points: PricePoint[];
  prevClose: number;
}

const RANGES: [string, number][] = [["1M", 60], ["5M", 300], ["15M", 900], ["Session", Infinity]];
const HEIGHT = 300;
const M = { top: 16, right: 76, bottom: 28, left: 8 };

/** Last traded price over the chosen range, shaded green above the previous close and red below. */
export function PriceChart({ symbol, points: all, prevClose }: Props) {
  const [range, setRange] = useState("5M");
  const [hover, setHover] = useState<number | null>(null);
  const [frame, width] = useElementWidth<HTMLDivElement>(700);
  const seconds = RANGES.find(([r]) => r === range)?.[1] ?? Infinity;
  const end = all.length ? all[all.length - 1][0] : 0;
  const points = all.filter(([t]) => t >= end - seconds);

  const innerW = Math.max(100, width - M.left - M.right);
  const innerH = HEIGHT - M.top - M.bottom;
  const chart = points.length >= 2 ? geometry(points, prevClose, innerW, innerH) : null;
  const last = points.length ? points[points.length - 1][1] : null;
  const tone = last != null && last >= prevClose ? "up" : "down";
  const hovered = hover == null ? null : points[hover];

  const onMove = (event: MouseEvent<SVGSVGElement>) => {
    if (!chart) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const t = chart.t0 + ((event.clientX - rect.left - M.left) / innerW) * (chart.t1 - chart.t0);
    let nearest = 0;
    for (let i = 1; i < points.length; i++) if (Math.abs(points[i][0] - t) < Math.abs(points[nearest][0] - t)) nearest = i;
    setHover(nearest);
  };

  return (
    <section className="card chart-card" id="chart" aria-labelledby="chart-title">
      <div className="card-head">
        <h2 id="chart-title" className="sr-only">Price chart</h2>
        <div className="range-tabs" role="tablist" aria-label="Chart range">
          {RANGES.map(([label]) => (
            <button key={label} type="button" role="tab" aria-selected={range === label} className={range === label ? "on" : ""} onClick={() => setRange(label)}>
              {label}
            </button>
          ))}
        </div>
        <span className="muted small">One point a second</span>
      </div>
      <div ref={frame} className="chart-frame">
        {!chart ? (
          <p className="empty" style={{ height: HEIGHT }}>Waiting for trades.</p>
        ) : (
          <>
            <svg width={width} height={HEIGHT} onMouseMove={onMove} onMouseLeave={() => setHover(null)} role="img"
              aria-label={`${symbol} last traded price from ${clock(chart.t0)} to ${clock(chart.t1)}; now ${price(last)}`}>
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
                {chart.showBase && (
                  <>
                    <line className="baseline" x1={0} x2={innerW} y1={chart.y(prevClose)} y2={chart.y(prevClose)} />
                    <PriceTag x={innerW + 4} y={chart.y(prevClose)} text={price(prevClose)} kind="base" />
                  </>
                )}
                {last != null && <PriceTag x={innerW + 4} y={chart.y(last)} text={price(last)} kind={tone} />}
                {chart.timeTicks.map((t) => (
                  <text key={t} className="axis" x={chart.x(t)} y={innerH + 20} textAnchor="middle">{chart.timeStep < 60 ? clock(t) : clock(t).slice(0, 5)}</text>
                ))}
                {hovered && (
                  <g>
                    <line className="crosshair" x1={chart.x(hovered[0])} x2={chart.x(hovered[0])} y1={0} y2={innerH} />
                    <circle className={`marker ${tone}`} cx={chart.x(hovered[0])} cy={chart.y(hovered[1])} r={4} />
                  </g>
                )}
              </g>
            </svg>
            {hovered && (
              <div className="tooltip" style={{ left: Math.min(M.left + chart.x(hovered[0]) + 12, width - 150), top: 12 }}>
                <span className="muted">{clock(hovered[0])}</span>
                <strong className="num">{price(hovered[1])}</strong>
              </div>
            )}
          </>
        )}
      </div>
      <p className="legend-note">
        <span className="baseline-key" aria-hidden="true" /> Previous close {price(prevClose)}
      </p>
    </section>
  );
}

function PriceTag({ x, y, text, kind }: { x: number; y: number; text: string; kind: "up" | "down" | "base" }) {
  return (
    <g className={`price-tag ${kind}`} transform={`translate(${x},${y - 10})`}>
      <rect width={68} height={20} rx={4} />
      <text x={34} y={10} textAnchor="middle" dominantBaseline="central">{text}</text>
    </g>
  );
}

function geometry(points: PricePoint[], base: number, w: number, h: number) {
  const t0 = points[0][0];
  const t1 = points[points.length - 1][0];
  let low = Infinity;
  let high = -Infinity;
  for (const [, p] of points) {
    low = Math.min(low, p);
    high = Math.max(high, p);
  }
  // Include the previous close only when it is close to the visible prices, so a far-off close
  // does not flatten the line.
  const span = Math.max(high - low, 1);
  const showBase = base >= low - span * 1.5 && base <= high + span * 1.5;
  if (showBase) {
    low = Math.min(low, base);
    high = Math.max(high, base);
  }
  const pad = Math.max((high - low) * 0.12, 5);
  low -= pad;
  high += pad;
  const x = (t: number) => ((t - t0) / Math.max(1, t1 - t0)) * w;
  const y = (p: number) => (1 - (p - low) / (high - low)) * h;
  const line = points.map(([t, p], i) => `${i ? "L" : "M"}${x(t).toFixed(1)},${y(p).toFixed(1)}`).join("");
  const area = `${line}L${x(t1).toFixed(1)},${h}L0,${h}Z`;
  const ticks = niceTicks(low + pad, high - pad, 4);
  const timeStep = Math.max(1, Math.ceil((t1 - t0) / 5 / 15) * 15);
  const timeTicks: number[] = [];
  for (let t = Math.ceil(t0 / timeStep) * timeStep; t <= t1; t += timeStep) timeTicks.push(t);
  return { t0, t1, x, y, line, area, ticks, timeTicks, timeStep, showBase };
}

function niceTicks(low: number, high: number, count: number): number[] {
  const raw = Math.max(1, (high - low) / count);
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((s) => s >= raw) ?? raw;
  const out = [];
  for (let v = Math.ceil(low / step) * step; v <= high; v += step) out.push(Math.round(v));
  return out;
}
