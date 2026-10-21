import { useCallback, useEffect, useRef, useState, type MouseEvent } from "react";

import type { Bar, ChartInterval, ChartRange, Quote } from "../../api/types";
import { useChart } from "../../hooks/useChart";
import { useElementWidth } from "../../hooks/useElementWidth";
import { axisDate, dateTime, price, qty } from "../../lib/format";

interface Props {
  symbol: string;
  quote: Quote | undefined;
  onPickDay?: (date: string) => void;
}

const RANGES: [ChartRange, string][] = [
  ["1d", "1D"], ["5d", "5D"], ["1mo", "1M"], ["3mo", "3M"],
  ["6mo", "6M"], ["ytd", "YTD"], ["1y", "1Y"], ["5y", "5Y"], ["max", "Max"],
];

const ALL_INTERVALS: [ChartInterval, string][] = [
  ["1m", "1 min"], ["2m", "2 mins"], ["5m", "5 mins"], ["15m", "15 mins"],
  ["30m", "30 mins"], ["1h", "1 hour"], ["1d", "1 day"], ["1wk", "1 week"], ["1mo", "1 month"],
];

const VALID_INTERVALS: Record<ChartRange, ChartInterval[]> = {
  "1d":  ["1m", "2m", "5m", "15m", "30m", "1h"],
  "5d":  ["1m", "2m", "5m", "15m", "30m", "1h"],
  "1mo": ["2m", "5m", "15m", "30m", "1h", "1d"],
  "3mo": ["1h", "1d", "1wk"],
  "6mo": ["1d", "1wk"],
  "ytd": ["1d", "1wk"],
  "1y":  ["1d", "1wk"],
  "5y":  ["1wk", "1mo"],
  "max": ["1wk", "1mo"],
};

const DEFAULT_INTERVAL: Record<ChartRange, ChartInterval> = {
  "1d": "1m", "5d": "5m", "1mo": "30m", "3mo": "1d",
  "6mo": "1d", "ytd": "1d", "1y": "1d", "5y": "1wk", "max": "1mo",
};

const INTRADAY_INTERVALS = new Set<ChartInterval>(["1m", "2m", "5m", "15m", "30m", "1h"]);

const HEIGHT = 340;
const VOL_H = 50;
const M = { top: 16, right: 76, bottom: 28, left: 8 };
const MIN_VISIBLE = 10;

export function PriceChart({ symbol, quote, onPickDay }: Props) {
  const [range, setRange] = useState<ChartRange>("1d");
  const [interval, setInterval] = useState<ChartInterval>("1m");
  const [mode, setMode] = useState<"candle" | "line">("candle");
  const [hover, setHover] = useState<number | null>(null);
  const [frame, width] = useElementWidth<HTMLDivElement>(700);
  const { bars, prevClose, loading, error } = useChart(symbol, range, interval, quote);

  const [visibleEnd, setVisibleEnd] = useState<number | null>(null);
  const [visibleCount, setVisibleCount] = useState<number | null>(null);
  const [dragging, setDragging] = useState(false);
  const dragStart = useRef<{ x: number; end: number } | null>(null);
  const dragMoved = useRef(false);

  useEffect(() => { setVisibleEnd(null); setVisibleCount(null); setHover(null); }, [range, interval, symbol]);

  const changeRange = (r: ChartRange) => {
    setRange(r);
    const valid = VALID_INTERVALS[r];
    if (!valid.includes(interval)) setInterval(DEFAULT_INTERVAL[r]);
    setHover(null);
  };

  const changeInterval = (iv: ChartInterval) => {
    setInterval(iv);
    setHover(null);
  };

  const n = bars.length;
  const vCount = Math.min(n, visibleCount ?? n);
  const vEnd = Math.min(n, visibleEnd ?? n);
  const vStart = Math.max(0, vEnd - vCount);
  const visible = bars.slice(vStart, vEnd);
  const isZoomed = vCount < n;

  const base = range === "1d" && interval === "1m" ? prevClose ?? quote?.prev_close ?? null : bars[0]?.[4] ?? null;
  const innerW = Math.max(100, width - M.left - M.right);
  const priceH = HEIGHT - M.top - M.bottom - VOL_H;
  const isIntraday = INTRADAY_INTERVALS.has(interval);
  const chart = visible.length >= 2 ? geometry(visible, base, innerW, priceH, range, interval, isZoomed, isIntraday) : null;
  const last = visible.length ? visible[visible.length - 1][4] : null;
  const tone = last != null && base != null && last < base ? "down" : "up";
  const hovered = hover == null ? null : visible[hover];
  const change = last != null && base ? ((last - base) / base) * 100 : null;

  // All interaction via native listeners to avoid React passive-event issues
  const stateRef = useRef({ visibleCount: null as number | null, visibleEnd: null as number | null, n: 0, innerW: 0, vCount: 0, isZoomed: false });
  stateRef.current = { visibleCount, visibleEnd, n, innerW, vCount, isZoomed };

  const svgRef = useRef<SVGSVGElement>(null);

  // Wheel zoom — native non-passive listener so preventDefault works
  useEffect(() => {
    const el = svgRef.current;
    if (!el) return;
    const handleWheel = (e: globalThis.WheelEvent) => {
      const { n, visibleCount, visibleEnd, innerW } = stateRef.current;
      if (n < MIN_VISIBLE) return;
      e.preventDefault();
      const curCount = visibleCount ?? n;
      const curEnd = visibleEnd ?? n;
      const factor = e.deltaY > 0 ? 1.08 : 1 / 1.08;
      let newCount = Math.round(curCount * factor);
      newCount = Math.max(MIN_VISIBLE, Math.min(n, newCount));
      if (newCount === curCount) return;
      const rect = el.getBoundingClientRect();
      const mouseX = e.clientX - rect.left - M.left;
      const frac = Math.max(0, Math.min(1, mouseX / innerW));
      const mouseIdx = Math.round(curEnd - curCount + frac * curCount);
      const newStart = Math.max(0, mouseIdx - Math.round(frac * newCount));
      const newEnd = Math.min(n, newStart + newCount);
      setVisibleCount(newCount);
      setVisibleEnd(newEnd);
      setHover(null);
    };
    el.addEventListener("wheel", handleWheel, { passive: false });
    return () => el.removeEventListener("wheel", handleWheel);
  }, [chart !== null]);

  // Drag pan — mousedown on SVG, mousemove/mouseup on window so it never gets stuck
  useEffect(() => {
    const el = svgRef.current;
    if (!el) return;

    const handleDown = (e: globalThis.MouseEvent) => {
      if (!stateRef.current.isZoomed) return;
      e.preventDefault();
      dragMoved.current = false;
      setDragging(true);
      dragStart.current = { x: e.clientX, end: stateRef.current.visibleEnd ?? stateRef.current.n };
    };

    const handleMove = (e: globalThis.MouseEvent) => {
      if (!dragStart.current) return;
      const dx = e.clientX - dragStart.current.x;
      if (Math.abs(dx) > 3) dragMoved.current = true;
      const { vCount, innerW, n } = stateRef.current;
      const barsPerPx = vCount / innerW;
      const shift = Math.round(-dx * barsPerPx);
      let newEnd = dragStart.current.end + shift;
      newEnd = Math.max(vCount, Math.min(n, newEnd));
      setVisibleEnd(newEnd);
      setHover(null);
    };

    const handleUp = () => {
      setDragging(false);
      dragStart.current = null;
    };

    el.addEventListener("mousedown", handleDown);
    window.addEventListener("mousemove", handleMove);
    window.addEventListener("mouseup", handleUp);
    return () => {
      el.removeEventListener("mousedown", handleDown);
      window.removeEventListener("mousemove", handleMove);
      window.removeEventListener("mouseup", handleUp);
    };
  }, [chart !== null]);

  const zoomBy = useCallback((direction: 1 | -1) => {
    const { n, visibleCount, visibleEnd } = stateRef.current;
    if (n < MIN_VISIBLE) return;
    const curCount = visibleCount ?? n;
    const curEnd = visibleEnd ?? n;
    const factor = direction > 0 ? 1 / 1.3 : 1.3;
    let newCount = Math.round(curCount * factor);
    newCount = Math.max(MIN_VISIBLE, Math.min(n, newCount));
    if (newCount === curCount) return;
    const mid = curEnd - Math.round(curCount / 2);
    const newStart = Math.max(0, mid - Math.round(newCount / 2));
    const newEnd = Math.min(n, newStart + newCount);
    setVisibleCount(newCount);
    setVisibleEnd(newEnd);
    setHover(null);
  }, []);

  const onMove = useCallback((e: MouseEvent<SVGSVGElement>) => {
    if (!chart || dragging) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const at = e.clientX - rect.left - M.left;
    let nearest = 0;
    for (let i = 1; i < visible.length; i++) if (Math.abs(chart.x(i) - at) < Math.abs(chart.x(nearest) - at)) nearest = i;
    setHover(nearest);
  }, [chart, dragging, visible.length]);

  const validIntervals = VALID_INTERVALS[range];
  const intervalLabel = ALL_INTERVALS.find(([iv]) => iv === interval)?.[1] ?? interval;

  return (
    <section className="card chart-card" id="chart" aria-labelledby="chart-title">
      <div className="card-head">
        <h2 id="chart-title" className="sr-only">Price chart</h2>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <div className="range-tabs" role="radiogroup" aria-label="Chart style">
            <button type="button" className={mode === "candle" ? "on" : ""} onClick={() => setMode("candle")} title="Candlestick">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5"><line x1="7" y1="1" x2="7" y2="13"/><rect x="4" y="4" width="6" height="6" rx="0.5"/></svg>
            </button>
            <button type="button" className={mode === "line" ? "on" : ""} onClick={() => setMode("line")} title="Line">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5"><polyline points="1,10 4,6 7,8 10,3 13,5"/></svg>
            </button>
          </div>
          <div className="range-tabs" role="group" aria-label="Zoom">
            <button type="button" onClick={() => zoomBy(1)} title="Zoom in" disabled={n < MIN_VISIBLE}>
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><line x1="3" y1="7" x2="11" y2="7"/><line x1="7" y1="3" x2="7" y2="11"/></svg>
            </button>
            <button type="button" onClick={() => zoomBy(-1)} title="Zoom out" disabled={!isZoomed}>
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><line x1="3" y1="7" x2="11" y2="7"/></svg>
            </button>
            {isZoomed && (
              <button type="button" className="zoom-reset" onClick={() => { setVisibleCount(null); setVisibleEnd(null); }}>
                Reset
              </button>
            )}
          </div>
          {change != null && (
            <span className={`num small ${change < 0 ? "down" : "up"}`}>
              {change >= 0 ? "+" : "−"}{Math.abs(change).toFixed(2)}%
              {range === "1d" ? " today" : ""}
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
              onMouseMove={onMove} onMouseLeave={() => { setHover(null); }}
              role="img"
              className={`${onPickDay ? "pickable" : ""} ${isZoomed ? "pannable" : ""}`}
              onClick={() => !dragMoved.current && hovered && onPickDay?.(new Date(hovered[0] * 1000).toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" }))}
              aria-label={`${symbol} price, ${intervalLabel} candles; now ${price(last)}`}>
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
                {chart.ticks.map((value) => (
                  <g key={value}>
                    <line className="grid" x1={0} x2={innerW} y1={chart.y(value)} y2={chart.y(value)} />
                    <text className="axis" x={innerW + 8} y={chart.y(value)} dominantBaseline="middle">{price(value)}</text>
                  </g>
                ))}
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
                {chart.showBase && base != null && (
                  <>
                    <line className="baseline" x1={0} x2={innerW} y1={chart.y(base)} y2={chart.y(base)} />
                    <PriceTag x={innerW + 4} y={chart.y(base)} text={price(base)} kind="base" />
                  </>
                )}
                {last != null && <PriceTag x={innerW + 4} y={chart.y(last)} text={price(last)} kind={tone} />}
                {chart.timeTicks.map(([xPos, text], k) => (
                  <text key={k} className="axis" x={xPos} y={priceH + VOL_H + 16} textAnchor={k === 0 ? "start" : "middle"}>{text}</text>
                ))}
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
                <span className="muted">{isIntraday ? dateTime(hovered[0]) : axisDate(hovered[0], true)}</span>
                <strong className={`num ${hovered[4] >= hovered[1] ? "up" : "down"}`}>{price(hovered[4])}</strong>
                <span className="num muted">O {price(hovered[1])}  H {price(hovered[2])}  L {price(hovered[3])}</span>
                {hovered[5] > 0 && <span className="num muted">Vol {qty(hovered[5])}</span>}
              </div>
            )}
          </>
        )}
      </div>
      <div className="chart-controls">
        <div className="range-tabs" role="tablist" aria-label="Chart range">
          {RANGES.map(([value, label]) => (
            <button key={value} type="button" role="tab" aria-selected={range === value}
              className={range === value ? "on" : ""} onClick={() => changeRange(value)}>
              {label}
            </button>
          ))}
        </div>
        <div className="interval-picker">
          <span className="interval-label">Interval:</span>
          <select value={interval} onChange={(e) => changeInterval(e.target.value as ChartInterval)}
            aria-label="Bar interval">
            {validIntervals.map((iv) => {
              const label = ALL_INTERVALS.find(([v]) => v === iv)?.[1] ?? iv;
              return <option key={iv} value={iv}>{label}</option>;
            })}
          </select>
        </div>
      </div>
      {range === "1d" && interval === "1m" && base != null && (
        <p className="legend-note">
          <span className="baseline-key" aria-hidden="true" /> Previous close {price(base)}
          {" · scroll to zoom, drag to pan"}
          {onPickDay && <> · <strong>click any bar to see why it moved</strong></>}
        </p>
      )}
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


function geometry(bars: Bar[], base: number | null, w: number, priceH: number, range: ChartRange, interval: ChartInterval, isZoomed: boolean, isIntraday: boolean) {
  let low = Infinity;
  let high = -Infinity;
  let maxVol = 0;
  for (const bar of bars) {
    low = Math.min(low, bar[3]);
    high = Math.max(high, bar[2]);
    maxVol = Math.max(maxVol, bar[5]);
  }
  const showBase = range === "1d" && interval === "1m" && base != null && !isZoomed;
  if (showBase && base != null) {
    low = Math.min(low, base);
    high = Math.max(high, base);
  }
  const pad = Math.max((high - low) * 0.08, 5);
  low -= pad;
  high += pad;
  const n = bars.length;

  const x = (i: number) => (i / Math.max(1, n - 1)) * w;
  const y = (p: number) => (1 - (p - low) / (high - low)) * priceH;
  const volY = (v: number) => maxVol > 0 ? (v / maxVol) * VOL_H : 0;
  const ticks = niceTicks(low + pad, high - pad, 4);

  const count = Math.max(2, Math.min(8, Math.floor(w / 90)));
  const timeTicks: [number, string][] = [];
  for (let k = 0; k < count; k++) {
    const fraction = k / (count - 1);
    if (k < count - 1 || n > 1) {
      const i = Math.round(fraction * (n - 1));
      timeTicks.push([x(i), tickLabel(bars[i][0], isIntraday)]);
    }
  }

  const candleW = Math.max(1, Math.min(12, (w / n) * 0.7));
  const line = bars.map((bar, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(bar[4]).toFixed(1)}`).join("");
  const area = `${line}L${x(n - 1).toFixed(1)},${priceH}L${x(0).toFixed(1)},${priceH}Z`;
  return { x, y, volY, ticks, timeTicks, showBase, candleW, line, area };
}

function tickLabel(t: number, isIntraday: boolean): string {
  if (isIntraday) return dateTime(t);
  return axisDate(t, true);
}

function niceTicks(low: number, high: number, count: number): number[] {
  const raw = Math.max(1, (high - low) / count);
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((s) => s >= raw) ?? raw;
  const out = [];
  for (let v = Math.ceil(low / step) * step; v <= high; v += step) out.push(Math.round(v));
  return out;
}
