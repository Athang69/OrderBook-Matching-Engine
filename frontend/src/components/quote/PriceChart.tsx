import { useCallback, useEffect, useRef, useState, type MouseEvent, type WheelEvent } from "react";

import type { Bar, ChartRange, Quote } from "../../api/types";
import { useChart } from "../../hooks/useChart";
import { useElementWidth } from "../../hooks/useElementWidth";
import { axisDate, clock, dateTime, price, qty } from "../../lib/format";

interface Props {
  symbol: string;
  quote: Quote | undefined;
  onPickDay?: (date: string) => void;
}

const RANGES: [ChartRange, string][] = [["1d", "1D"], ["5d", "5D"], ["1mo", "1M"], ["6mo", "6M"], ["1y", "1Y"], ["5y", "5Y"]];
const HEIGHT = 340;
const VOL_H = 50;
const M = { top: 16, right: 76, bottom: 28, left: 8 };
const MIN_VISIBLE = 10;

export function PriceChart({ symbol, quote, onPickDay }: Props) {
  const [range, setRange] = useState<ChartRange>("1d");
  const [mode, setMode] = useState<"candle" | "line">("candle");
  const [hover, setHover] = useState<number | null>(null);
  const [frame, width] = useElementWidth<HTMLDivElement>(700);
  const { bars, prevClose, loading, error } = useChart(symbol, range, quote);

  // Zoom/pan state: visibleEnd is the rightmost bar index, visibleCount is how many bars are shown
  const [visibleEnd, setVisibleEnd] = useState<number | null>(null);
  const [visibleCount, setVisibleCount] = useState<number | null>(null);
  const [dragging, setDragging] = useState(false);
  const dragStart = useRef<{ x: number; end: number } | null>(null);

  // Reset zoom when range or symbol changes
  useEffect(() => { setVisibleEnd(null); setVisibleCount(null); setHover(null); }, [range, symbol]);

  const n = bars.length;
  const vCount = Math.min(n, visibleCount ?? n);
  const vEnd = Math.min(n, visibleEnd ?? n);
  const vStart = Math.max(0, vEnd - vCount);
  const visible = bars.slice(vStart, vEnd);

  const base = range === "1d" ? prevClose ?? quote?.prev_close ?? null : bars[0]?.[4] ?? null;
  const innerW = Math.max(100, width - M.left - M.right);
  const priceH = HEIGHT - M.top - M.bottom - VOL_H;
  const chart = visible.length >= 2 ? geometry(visible, base, innerW, priceH, range) : null;
  const last = visible.length ? visible[visible.length - 1][4] : null;
  const tone = last != null && base != null && last < base ? "down" : "up";
  const hovered = hover == null ? null : visible[hover];
  const change = last != null && base ? ((last - base) / base) * 100 : null;
  const isZoomed = vCount < n;

  const onWheel = useCallback((e: WheelEvent<SVGSVGElement>) => {
    if (n < MIN_VISIBLE) return;
    e.preventDefault();
    const curCount = visibleCount ?? n;
    const curEnd = visibleEnd ?? n;
    // Zoom: delta > 0 = scroll down = zoom out, delta < 0 = zoom in
    const factor = e.deltaY > 0 ? 1.15 : 1 / 1.15;
    let newCount = Math.round(curCount * factor);
    newCount = Math.max(MIN_VISIBLE, Math.min(n, newCount));
    // Keep the mouse position anchored
    const rect = e.currentTarget.getBoundingClientRect();
    const mouseX = e.clientX - rect.left - M.left;
    const frac = Math.max(0, Math.min(1, mouseX / innerW));
    const mouseIdx = Math.round(curEnd - curCount + frac * curCount);
    const newStart = Math.max(0, mouseIdx - Math.round(frac * newCount));
    const newEnd = Math.min(n, newStart + newCount);
    setVisibleCount(newCount);
    setVisibleEnd(newEnd);
    setHover(null);
  }, [n, visibleCount, visibleEnd, innerW]);

  const onMouseDown = useCallback((e: MouseEvent<SVGSVGElement>) => {
    if (!isZoomed) return;
    setDragging(true);
    dragStart.current = { x: e.clientX, end: visibleEnd ?? n };
  }, [isZoomed, visibleEnd, n]);

  const onMouseUp = useCallback(() => { setDragging(false); dragStart.current = null; }, []);

  const onMove = useCallback((e: MouseEvent<SVGSVGElement>) => {
    if (!chart) return;
    if (dragging && dragStart.current) {
      const dx = e.clientX - dragStart.current.x;
      const barsPerPx = vCount / innerW;
      const shift = Math.round(-dx * barsPerPx);
      let newEnd = dragStart.current.end + shift;
      newEnd = Math.max(vCount, Math.min(n, newEnd));
      setVisibleEnd(newEnd);
      setHover(null);
      return;
    }
    const rect = e.currentTarget.getBoundingClientRect();
    const at = e.clientX - rect.left - M.left;
    let nearest = 0;
    for (let i = 1; i < visible.length; i++) if (Math.abs(chart.x(i) - at) < Math.abs(chart.x(nearest) - at)) nearest = i;
    setHover(nearest);
  }, [chart, dragging, vCount, innerW, n, visible.length]);

  // Prevent default scroll on wheel over chart
  const svgRef = useRef<SVGSVGElement>(null);
  useEffect(() => {
    const el = svgRef.current;
    if (!el) return;
    const prevent = (e: globalThis.WheelEvent) => { if (n >= MIN_VISIBLE) e.preventDefault(); };
    el.addEventListener("wheel", prevent, { passive: false });
    return () => el.removeEventListener("wheel", prevent);
  }, [n]);

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
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <div className="range-tabs" role="radiogroup" aria-label="Chart style">
            <button type="button" className={mode === "candle" ? "on" : ""} onClick={() => setMode("candle")} title="Candlestick">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5"><line x1="7" y1="1" x2="7" y2="13"/><rect x="4" y="4" width="6" height="6" rx="0.5"/></svg>
            </button>
            <button type="button" className={mode === "line" ? "on" : ""} onClick={() => setMode("line")} title="Line">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5"><polyline points="1,10 4,6 7,8 10,3 13,5"/></svg>
            </button>
          </div>
          {isZoomed && (
            <button type="button" className="zoom-reset" onClick={() => { setVisibleCount(null); setVisibleEnd(null); }}>
              Reset zoom
            </button>
          )}
          {change != null && (
            <span className={`num small ${change < 0 ? "down" : "up"}`}>
              {change >= 0 ? "+" : "−"}{Math.abs(change).toFixed(2)}% {range === "1d" ? "today" : `over ${RANGES.find(([r]) => r === range)?.[1]}`}
            </span>
          )}
        </div>
      </div>
      <div ref={frame} className="chart-frame">
        {!chart ? (
          <p className="empty" style={{ height: HEIGHT }}>{error || (loading ? "Loading the chart." : "No trades yet in this range.")}</p>
        ) : (
          <>
            <svg ref={svgRef} width={width} height={HEIGHT}
              onMouseMove={onMove} onMouseLeave={() => { setHover(null); setDragging(false); }}
              onMouseDown={onMouseDown} onMouseUp={onMouseUp}
              onWheel={onWheel}
              role="img"
              className={`${onPickDay ? "pickable" : ""} ${isZoomed ? "pannable" : ""}`}
              onClick={() => !dragging && hovered && onPickDay?.(new Date(hovered[0] * 1000).toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" }))}
              aria-label={`${symbol} price over ${range}; now ${price(last)}`}>
              <defs>
                <clipPath id="chart-clip"><rect width={innerW} height={priceH + VOL_H} /></clipPath>
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
                {/* Grid lines + Y axis */}
                {chart.ticks.map((value) => (
                  <g key={value}>
                    <line className="grid" x1={0} x2={innerW} y1={chart.y(value)} y2={chart.y(value)} />
                    <text className="axis" x={innerW + 8} y={chart.y(value)} dominantBaseline="middle">{price(value)}</text>
                  </g>
                ))}
                {/* Price bars */}
                <g clipPath="url(#chart-clip)">
                  {mode === "candle" ? visible.map((bar, i) => {
                    const [, o, h, l, c, v] = bar;
                    const isUp = c >= o;
                    const color = isUp ? "var(--up)" : "var(--down)";
                    const cx = chart.x(i);
                    const bodyTop = chart.y(Math.max(o, c));
                    const bodyBot = chart.y(Math.min(o, c));
                    const bodyH = Math.max(bodyBot - bodyTop, 1);
                    const cw = chart.candleW;
                    const volH = chart.volY(v);
                    return (
                      <g key={i}>
                        <line x1={cx} y1={chart.y(h)} x2={cx} y2={chart.y(l)} stroke={color} strokeWidth={1} />
                        <rect x={cx - cw / 2} y={bodyTop} width={cw} height={bodyH}
                          fill={isUp ? "transparent" : color} stroke={color} strokeWidth={1} />
                        <rect x={cx - cw / 2} y={priceH + VOL_H - volH} width={cw} height={volH}
                          fill={color} opacity={0.25} />
                      </g>
                    );
                  }) : (
                    <>
                      <path className={`area ${tone}`} d={chart.area} fill={`url(#area-${tone})`} />
                      <path className={`line ${tone}`} d={chart.line} />
                      {/* Volume bars in line mode */}
                      {visible.map((bar, i) => {
                        const volH = chart.volY(bar[5]);
                        return volH > 0 ? (
                          <rect key={i} x={chart.x(i) - chart.candleW / 2} y={priceH + VOL_H - volH}
                            width={chart.candleW} height={volH} fill="var(--muted)" opacity={0.2} />
                        ) : null;
                      })}
                    </>
                  )}
                </g>
                {/* Baseline (prev close on 1D) */}
                {chart.showBase && base != null && (
                  <>
                    <line className="baseline" x1={0} x2={innerW} y1={chart.y(base)} y2={chart.y(base)} />
                    <PriceTag x={innerW + 4} y={chart.y(base)} text={price(base)} kind="base" />
                  </>
                )}
                {/* LTP tag */}
                {last != null && <PriceTag x={innerW + 4} y={chart.y(last)} text={price(last)} kind={tone} />}
                {/* X axis */}
                {chart.timeTicks.map(([xPos, text], k) => (
                  <text key={k} className="axis" x={xPos} y={priceH + VOL_H + 16} textAnchor={k === 0 ? "start" : "middle"}>{text}</text>
                ))}
                {/* Crosshair + hover dot */}
                {hovered && hover != null && (
                  <g>
                    <line className="crosshair" x1={chart.x(hover)} x2={chart.x(hover)} y1={0} y2={priceH + VOL_H} />
                    <line className="crosshair" x1={0} x2={innerW} y1={chart.y(hovered[4])} y2={chart.y(hovered[4])} />
                    <circle className={`marker ${hovered[4] >= hovered[1] ? "up" : "down"}`} cx={chart.x(hover)} cy={chart.y(hovered[4])} r={3.5} />
                  </g>
                )}
              </g>
            </svg>
            {hovered && hover != null && (
              <div className="tooltip" style={{ left: Math.min(M.left + chart.x(hover) + 12, width - 190), top: 12 }}>
                <span className="muted">{range === "1d" ? clock(hovered[0]).slice(0, 5) : range === "5d" || range === "1mo" ? dateTime(hovered[0]) : axisDate(hovered[0], true)}</span>
                <strong className={`num ${hovered[4] >= hovered[1] ? "up" : "down"}`}>{price(hovered[4])}</strong>
                <span className="num muted">O {price(hovered[1])}  H {price(hovered[2])}  L {price(hovered[3])}</span>
                {hovered[5] > 0 && <span className="num muted">Vol {qty(hovered[5])}</span>}
              </div>
            )}
          </>
        )}
      </div>
      <p className="legend-note">
        {range === "1d" ? (
          <><span className="baseline-key" aria-hidden="true" /> Previous close {price(base)} {"·"} one-minute bars</>
        ) : (
          <>{range === "5d" ? "5-minute" : range === "1mo" ? "30-minute" : range === "5y" ? "weekly" : "daily"} bars</>
        )}
        {" · scroll to zoom, drag to pan"}
        {onPickDay && <> {"·"} <strong>click any day to see why it moved</strong></>}
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

const SESSION_MINUTES = 375;
const IST_OFFSET = 19_800;

function geometry(bars: Bar[], base: number | null, w: number, priceH: number, range: ChartRange) {
  let low = Infinity;
  let high = -Infinity;
  let maxVol = 0;
  for (const bar of bars) {
    low = Math.min(low, bar[3]);
    high = Math.max(high, bar[2]);
    maxVol = Math.max(maxVol, bar[5]);
  }
  const showBase = range === "1d" && base != null;
  if (showBase && base != null) {
    low = Math.min(low, base);
    high = Math.max(high, base);
  }
  const pad = Math.max((high - low) * 0.08, 5);
  low -= pad;
  high += pad;
  const n = bars.length;
  const open = Math.floor((bars[0][0] + IST_OFFSET) / 86_400) * 86_400 - IST_OFFSET + 555 * 60;
  const position = range === "1d"
    ? bars.map((bar) => Math.min(1, Math.max(0, (bar[0] - open) / 60 / SESSION_MINUTES)))
    : bars.map((_, i) => i / Math.max(1, n - 1));
  const x = (i: number) => position[i] * w;
  const y = (p: number) => (1 - (p - low) / (high - low)) * priceH;
  const volY = (v: number) => maxVol > 0 ? (v / maxVol) * VOL_H : 0;
  const ticks = niceTicks(low + pad, high - pad, 4);
  const count = Math.max(2, Math.min(8, Math.floor(w / 90)));
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
  const candleW = Math.max(1, Math.min(12, (w / n) * 0.7));
  // Line + area paths for line mode
  const line = bars.map((bar, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(bar[4]).toFixed(1)}`).join("");
  const area = `${line}L${x(n - 1).toFixed(1)},${priceH}L${x(0).toFixed(1)},${priceH}Z`;
  return { x, y, volY, ticks, timeTicks, showBase, candleW, line, area };
}

function niceTicks(low: number, high: number, count: number): number[] {
  const raw = Math.max(1, (high - low) / count);
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((s) => s >= raw) ?? raw;
  const out = [];
  for (let v = Math.ceil(low / step) * step; v <= high; v += step) out.push(Math.round(v));
  return out;
}
