import { Fragment, useCallback, useEffect, useRef, useState, type MouseEvent, type ReactNode } from "react";

import { api } from "../../api/client";
import type {
  Analysis, CandlePattern, ChartInterval, ChartRange, ExplainHeadline,
  Explanation, GlobalChart, GlobalQuote, OHLCBar, Scope, StockNews,
} from "../../api/types";
import { useActiveSection } from "../../hooks/useActiveSection";
import { useElementWidth } from "../../hooks/useElementWidth";
import { axisDate, dateTime, timeAgo } from "../../lib/format";

interface Props {
  ticker: string;
  onBack: () => void;
}

// ---- currency helpers ----
const CURRENCY_SYMBOLS: Record<string, string> = {
  INR: "₹", USD: "$", EUR: "€", GBP: "£", JPY: "¥", CNY: "¥",
  KRW: "₩", HKD: "HK$", AUD: "A$", SGD: "S$", TWD: "NT$",
};
function cur(c: string | null) { return c ? (CURRENCY_SYMBOLS[c] ?? c + " ") : ""; }
function fmt(v: number | null, c?: string | null, decimals?: number): string {
  if (v == null) return "—";
  const d = decimals ?? (Math.abs(v) < 1 ? 4 : Math.abs(v) >= 10000 ? 0 : 2);
  return (c ? cur(c) : "") + v.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
}
function fmtVol(v: number | null) {
  if (!v) return "—";
  if (v >= 1e9) return (v / 1e9).toFixed(1) + "B";
  if (v >= 1e6) return (v / 1e6).toFixed(1) + "M";
  if (v >= 1e3) return (v / 1e3).toFixed(1) + "K";
  return v.toString();
}
function fmtCap(v: number | null, c?: string | null) {
  if (!v) return "—";
  const sym = cur(c ?? null);
  if (v >= 1e12) return sym + (v / 1e12).toFixed(2) + "T";
  if (v >= 1e9)  return sym + (v / 1e9).toFixed(2) + "B";
  if (v >= 1e6)  return sym + (v / 1e6).toFixed(2) + "M";
  return sym + v.toLocaleString();
}
function dir(v: number | null) { return v == null || v === 0 ? "" : v > 0 ? "up" : "down"; }
function sign(v: number | null) { return v == null ? "—" : (v > 0 ? "+" : "") + v.toFixed(2); }
const pct = (x: number | null | undefined, digits = 2) =>
  x == null ? "—" : `${x > 0 ? "+" : x < 0 ? "−" : ""}${Math.abs(x * 100).toFixed(digits)}%`;
const tone = (x: number | null | undefined) => (x == null || x === 0 ? "" : x > 0 ? "up" : "down");

// ---- chart constants ----
type RangeOpt = { label: string; range: ChartRange; interval: ChartInterval };

const RANGES: RangeOpt[] = [
  { label: "1D",  range: "1d",  interval: "5m"  },
  { label: "5D",  range: "5d",  interval: "15m" },
  { label: "1M",  range: "1mo", interval: "1d"  },
  { label: "3M",  range: "3mo", interval: "1d"  },
  { label: "6M",  range: "6mo", interval: "1d"  },
  { label: "YTD", range: "ytd", interval: "1d"  },
  { label: "1Y",  range: "1y",  interval: "1wk" },
  { label: "5Y",  range: "5y",  interval: "1wk" },
  { label: "Max", range: "max", interval: "1mo" },
];

const ALL_INTERVALS: [ChartInterval, string][] = [
  ["1m", "1 min"], ["2m", "2 mins"], ["5m", "5 mins"], ["15m", "15 mins"],
  ["30m", "30 mins"], ["1h", "1 hour"], ["1d", "1 day"], ["1wk", "1 week"], ["1mo", "1 month"],
];

const VALID_INTERVALS: Record<ChartRange, ChartInterval[]> = {
  "1d":  ["1m", "2m", "5m", "15m", "30m", "1h"],
  "5d":  ["5m", "15m", "30m", "1h"],
  "1mo": ["30m", "1h", "1d"],
  "3mo": ["1d", "1wk"],
  "6mo": ["1d", "1wk"],
  "ytd": ["1d", "1wk"],
  "1y":  ["1d", "1wk"],
  "5y":  ["1wk", "1mo"],
  "max": ["1wk", "1mo"],
};

const DEFAULT_INTERVAL: Record<ChartRange, ChartInterval> = {
  "1d": "5m", "5d": "15m", "1mo": "1d", "3mo": "1d",
  "6mo": "1d", "ytd": "1d", "1y": "1wk", "5y": "1wk", "max": "1mo",
};

const INTRADAY_INTERVALS = new Set<ChartInterval>(["1m", "2m", "5m", "15m", "30m", "1h"]);

const HEIGHT = 340;
const VOL_H = 50;
const M = { top: 16, right: 72, bottom: 28, left: 0 };
const MIN_VISIBLE = 10;

// ---- chart geometry (same algorithm as PriceChart) ----
function geometry(bars: GlobalChart["bars"], base: number | null, w: number, priceH: number, range: ChartRange, _interval: ChartInterval, isZoomed: boolean, isIntraday: boolean) {
  let low = Infinity, high = -Infinity, maxVol = 0;
  for (const bar of bars) {
    low = Math.min(low, bar[3]);
    high = Math.max(high, bar[2]);
    maxVol = Math.max(maxVol, bar[5]);
  }
  const showBase = range === "1d" && isIntraday && base != null && !isZoomed;
  if (showBase && base != null) { low = Math.min(low, base); high = Math.max(high, base); }
  const pad = Math.max((high - low) * 0.08, 0.01);
  low -= pad; high += pad;
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
      timeTicks.push([x(i), isIntraday ? dateTime(bars[i][0]) : axisDate(bars[i][0], true)]);
    }
  }
  const candleW = Math.max(1, Math.min(12, (w / n) * 0.7));
  const line = bars.map((b, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(b[4]).toFixed(1)}`).join("");
  const area = `${line}L${x(n-1).toFixed(1)},${priceH}L${x(0).toFixed(1)},${priceH}Z`;
  return { x, y, volY, ticks, timeTicks, showBase, candleW, line, area };
}

function niceTicks(low: number, high: number, count: number): number[] {
  const raw = Math.max(1e-6, (high - low) / count);
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map(m => m * magnitude).find(s => s >= raw) ?? raw;
  const out: number[] = [];
  for (let v = Math.ceil(low / step) * step; v <= high + step * 0.01; v += step) out.push(parseFloat(v.toPrecision(10)));
  return out;
}

// ---- full chart component ----
function GlobalPriceChart({ ticker, prevClose, currency, onPickDay }: {
  ticker: string;
  prevClose: number | null;
  currency: string | null;
  onPickDay?: (date: string | null) => void;
}) {
  const [rangeOpt, setRangeOpt] = useState<RangeOpt>(RANGES[2]); // 1M default
  const [interval, setInterval] = useState<ChartInterval>("1d");
  const [mode, setMode] = useState<"candle" | "line">("candle");
  const [chartData, setChartData] = useState<GlobalChart | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [hover, setHover] = useState<number | null>(null);
  const [visibleEnd, setVisibleEnd] = useState<number | null>(null);
  const [visibleCount, setVisibleCount] = useState<number | null>(null);
  const [dragging, setDragging] = useState(false);
  const dragStart = useRef<{ x: number; end: number } | null>(null);
  const dragMoved = useRef(false);
  const [frame, width] = useElementWidth<HTMLDivElement>(700);
  const svgRef = useRef<SVGSVGElement>(null);

  const stateRef = useRef({ visibleCount: null as number | null, visibleEnd: null as number | null, n: 0, innerW: 0, vCount: 0, isZoomed: false });

  const load = useCallback((r: RangeOpt, iv: ChartInterval) => {
    setLoading(true); setError(""); setChartData(null);
    api.globalChart(ticker, r.range, iv)
      .then(d => setChartData(d))
      .catch(() => setError("Could not load chart."))
      .finally(() => setLoading(false));
  }, [ticker]);

  useEffect(() => {
    setVisibleEnd(null); setVisibleCount(null); setHover(null);
    load(rangeOpt, interval);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticker]);

  const changeRange = (r: RangeOpt) => {
    setRangeOpt(r);
    const valid = VALID_INTERVALS[r.range];
    const iv = valid.includes(interval) ? interval : DEFAULT_INTERVAL[r.range];
    setInterval(iv);
    setVisibleEnd(null); setVisibleCount(null); setHover(null);
    load(r, iv);
  };

  const changeInterval = (iv: ChartInterval) => {
    setInterval(iv);
    setVisibleEnd(null); setVisibleCount(null); setHover(null);
    load(rangeOpt, iv);
  };

  const bars = chartData?.bars ?? [];
  const n = bars.length;
  const vCount = Math.min(n, visibleCount ?? n);
  const vEnd = Math.min(n, visibleEnd ?? n);
  const vStart = Math.max(0, vEnd - vCount);
  const visible = bars.slice(vStart, vEnd);
  const isZoomed = vCount < n;
  const isIntraday = INTRADAY_INTERVALS.has(interval);
  const base = rangeOpt.range === "1d" && isIntraday ? (chartData?.prev_close ?? prevClose ?? null) : (visible[0]?.[4] ?? null);
  const innerW = Math.max(100, width - M.left - M.right);
  const priceH = HEIGHT - M.top - M.bottom - VOL_H;
  const chart = visible.length >= 2 ? geometry(visible, base, innerW, priceH, rangeOpt.range, interval, isZoomed, isIntraday) : null;
  const last = visible.length ? visible[visible.length - 1][4] : null;
  const chartTone = last != null && base != null && last < base ? "down" : "up";
  const hovered = hover != null ? visible[hover] : null;
  const change = last != null && base ? ((last - base) / base) * 100 : null;

  stateRef.current = { visibleCount, visibleEnd, n, innerW, vCount, isZoomed };

  // Wheel zoom
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
      setVisibleCount(newCount); setVisibleEnd(newEnd); setHover(null);
    };
    el.addEventListener("wheel", handleWheel, { passive: false });
    return () => el.removeEventListener("wheel", handleWheel);
  }, [chart !== null]);

  // Drag pan
  useEffect(() => {
    const el = svgRef.current;
    if (!el) return;
    const handleDown = (e: globalThis.MouseEvent) => {
      if (!stateRef.current.isZoomed) return;
      e.preventDefault(); dragMoved.current = false; setDragging(true);
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
      setVisibleEnd(newEnd); setHover(null);
    };
    const handleUp = () => { setDragging(false); dragStart.current = null; };
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
    const curCount = visibleCount ?? n; const curEnd = visibleEnd ?? n;
    const factor = direction > 0 ? 1 / 1.3 : 1.3;
    let newCount = Math.round(curCount * factor);
    newCount = Math.max(MIN_VISIBLE, Math.min(n, newCount));
    if (newCount === curCount) return;
    const mid = curEnd - Math.round(curCount / 2);
    const newStart = Math.max(0, mid - Math.round(newCount / 2));
    const newEnd = Math.min(n, newStart + newCount);
    setVisibleCount(newCount); setVisibleEnd(newEnd); setHover(null);
  }, []);

  const onMove = useCallback((e: MouseEvent<SVGSVGElement>) => {
    if (!chart || dragging) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const at = e.clientX - rect.left - M.left;
    let nearest = 0;
    for (let i = 1; i < visible.length; i++) {
      if (Math.abs(chart.x(i) - at) < Math.abs(chart.x(nearest) - at)) nearest = i;
    }
    setHover(nearest);
  }, [chart, dragging, visible.length]);

  const validIntervals = VALID_INTERVALS[rangeOpt.range];
  const fmtPrice = (v: number) => fmt(v, currency);

  return (
    <section className="card chart-card" id="chart" aria-labelledby="chart-title">
      <div className="card-head">
        <h2 id="chart-title" className="sr-only">Price chart</h2>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <div className="range-tabs" role="radiogroup" aria-label="Chart style">
            <button type="button" className={mode === "candle" ? "on" : ""} onClick={() => setMode("candle")} title="Candlestick">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5">
                <line x1="7" y1="1" x2="7" y2="13"/><rect x="4" y="4" width="6" height="6" rx="0.5"/>
              </svg>
            </button>
            <button type="button" className={mode === "line" ? "on" : ""} onClick={() => setMode("line")} title="Line">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5">
                <polyline points="1,10 4,6 7,8 10,3 13,5"/>
              </svg>
            </button>
          </div>
          <div className="range-tabs" role="group" aria-label="Zoom">
            <button type="button" onClick={() => zoomBy(1)} title="Zoom in" disabled={n < MIN_VISIBLE}>
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
                <line x1="3" y1="7" x2="11" y2="7"/><line x1="7" y1="3" x2="7" y2="11"/>
              </svg>
            </button>
            <button type="button" onClick={() => zoomBy(-1)} title="Zoom out" disabled={!isZoomed}>
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
                <line x1="3" y1="7" x2="11" y2="7"/>
              </svg>
            </button>
            {isZoomed && (
              <button type="button" className="zoom-reset" onClick={() => { setVisibleCount(null); setVisibleEnd(null); }}>Reset</button>
            )}
          </div>
          {change != null && (
            <span className={`num small ${change < 0 ? "down" : "up"}`}>
              {change >= 0 ? "+" : "−"}{Math.abs(change).toFixed(2)}%{rangeOpt.range === "1d" ? " today" : ""}
            </span>
          )}
        </div>
      </div>

      <div ref={frame} className="chart-frame">
        {!chart ? (
          <p className="empty" style={{ height: HEIGHT }}>
            {error || (loading ? "Loading the chart." : "No data for this range.")}
          </p>
        ) : (
          <>
            <svg ref={svgRef} width={width} height={HEIGHT}
              onMouseMove={onMove}
              onMouseLeave={() => { setHover(null); }}
              onClick={() => {
                if (!dragMoved.current && hovered && onPickDay) {
                  const d = new Date(hovered[0] * 1000).toLocaleDateString("en-CA");
                  onPickDay(d);
                }
              }}
              className={`${onPickDay ? "pickable" : ""} ${isZoomed ? "pannable" : ""}`}
              role="img" aria-label={`${ticker} price chart`}
              style={{ display: "block" }}>
              <defs>
                <clipPath id="gsd-clip"><rect width={innerW} height={priceH + VOL_H} /></clipPath>
                <linearGradient id="gsd-area-up" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" className="stop-up" stopOpacity="0.35" />
                  <stop offset="100%" className="stop-up" stopOpacity="0" />
                </linearGradient>
                <linearGradient id="gsd-area-down" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" className="stop-down" stopOpacity="0.35" />
                  <stop offset="100%" className="stop-down" stopOpacity="0" />
                </linearGradient>
              </defs>
              <g transform={`translate(${M.left},${M.top})`}>
                {chart.ticks.map(v => (
                  <g key={v}>
                    <line className="grid" x1={0} x2={innerW} y1={chart.y(v)} y2={chart.y(v)} />
                    <text className="axis" x={innerW + 6} y={chart.y(v)} dominantBaseline="middle" fontSize="11">
                      {fmtPrice(v)}
                    </text>
                  </g>
                ))}
                <g clipPath="url(#gsd-clip)">
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
                      <path className={`area ${chartTone}`} d={chart.area} fill={`url(#gsd-area-${chartTone})`} />
                      <path className={`line ${chartTone}`} d={chart.line} />
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
                  <line className="baseline" x1={0} x2={innerW} y1={chart.y(base)} y2={chart.y(base)} />
                )}
                {chart.timeTicks.map(([xPos, text], k) => (
                  <text key={k} className="axis" x={xPos} y={priceH + VOL_H + 16} textAnchor={k === 0 ? "start" : "middle"} fontSize="11">{text}</text>
                ))}
                {hovered && hover != null && (
                  <g>
                    <line className="crosshair" x1={chart.x(hover)} x2={chart.x(hover)} y1={0} y2={priceH + VOL_H} />
                    <line className="crosshair" x1={0} x2={innerW} y1={chart.y(hovered[4])} y2={chart.y(hovered[4])} />
                    <circle className={`marker ${hovered[4] >= hovered[1] ? "up" : "down"}`}
                      cx={chart.x(hover)} cy={chart.y(hovered[4])} r={3.5} />
                  </g>
                )}
              </g>
            </svg>
            {hovered && hover != null && (
              <div className="tooltip" style={{ left: Math.min(M.left + chart.x(hover) + 12, width - 200), top: 12 }}>
                <span className="muted">{isIntraday ? dateTime(hovered[0]) : axisDate(hovered[0], true)}</span>
                <strong className={`num ${hovered[4] >= hovered[1] ? "up" : "down"}`}>{fmt(hovered[4], currency)}</strong>
                <span className="num muted">O {fmt(hovered[1], currency)}  H {fmt(hovered[2], currency)}  L {fmt(hovered[3], currency)}</span>
                {hovered[5] > 0 && <span className="num muted">Vol {fmtVol(hovered[5])}</span>}
              </div>
            )}
          </>
        )}
      </div>

      <div className="chart-controls">
        <div className="range-tabs" role="tablist" aria-label="Chart range">
          {RANGES.map(r => (
            <button key={r.label} type="button" role="tab" aria-selected={rangeOpt.label === r.label}
              className={rangeOpt.label === r.label ? "on" : ""} onClick={() => changeRange(r)}>
              {r.label}
            </button>
          ))}
        </div>
        <div className="interval-picker">
          <span className="interval-label">Interval:</span>
          <select value={interval} onChange={e => changeInterval(e.target.value as ChartInterval)} aria-label="Bar interval">
            {validIntervals.map(iv => (
              <option key={iv} value={iv}>{ALL_INTERVALS.find(([v]) => v === iv)?.[1] ?? iv}</option>
            ))}
          </select>
        </div>
      </div>
      {chart?.showBase && base != null && (
        <p className="legend-note">
          <span className="baseline-key" aria-hidden="true" /> Previous close {fmt(base, currency)}
          {" · scroll to zoom, drag to pan"}
          {onPickDay && <> · <strong>click any bar to see why it moved</strong></>}
        </p>
      )}
    </section>
  );
}

// ---- signals panel ----
function GlobalSignalsPanel({ ticker }: { ticker: string; currency?: string | null }) {
  const [expl, setExpl] = useState<Explanation | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true); setExpl(null); setAnalysis(null);
    api.globalExplain(ticker)
      .then(e => {
        setExpl(e);
        return api.globalAnalysis(ticker, e.date);
      })
      .then(a => setAnalysis(a))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [ticker]);

  if (loading) return (
    <section className="section" id="signals" aria-labelledby="gsig-title">
      <div className="section-head"><h2 id="gsig-title" className="section-title">Signals &amp; Ideas</h2></div>
      <div className="why-loading" role="status"><div className="spinner" aria-hidden="true" /><span>Computing signals…</span></div>
    </section>
  );

  if (!expl) return null;

  // compute combined signal from CNN + FinBERT + AI verdict
  const cnnToday = expl.chart_cnn?.today;
  const cnnScore = cnnToday?.prob_up != null ? (cnnToday.prob_up - 0.5) * 2 : 0; // -1 to +1

  const allSentScores: number[] = [];
  if (expl.sentiment_totals) {
    Object.values(expl.sentiment_totals).forEach(t => { if (t) allSentScores.push(t.avg_score); });
  }
  const avgSentiment = allSentScores.length ? allSentScores.reduce((a,b) => a+b,0) / allSentScores.length : 0;

  const aiA = analysis?.analysis;
  const aiSign = aiA ? (expl.change >= 0 ? 1 : -1) * (aiA.confidence === "high" ? 1 : 0.5) : 0;
  const aiVerdictStr = aiA?.verdict ?? null;

  const combined = 0.4 * cnnScore + 0.3 * avgSentiment + 0.3 * aiSign;
  const signal = combined > 0.12 ? "BUY" : combined < -0.12 ? "SELL" : "HOLD";
  const signalColor = signal === "BUY" ? "up" : signal === "SELL" ? "down" : "";

  // technical bias from patterns
  const bullishPatterns = (expl.candle_patterns?.today ?? []).filter(p => p.bias === "bullish").length +
    (expl.candle_patterns?.previous ?? []).filter(p => p.bias === "bullish").length;
  const bearishPatterns = (expl.candle_patterns?.today ?? []).filter(p => p.bias === "bearish").length +
    (expl.candle_patterns?.previous ?? []).filter(p => p.bias === "bearish").length;
  const patternBias = bullishPatterns > bearishPatterns ? "bullish" : bearishPatterns > bullishPatterns ? "bearish" : "neutral";

  return (
    <section className="section" id="signals" aria-labelledby="gsig-title">
      <div className="section-head">
        <h2 id="gsig-title" className="section-title">Signals &amp; Ideas</h2>
        <span className="chip quiet">View only · paper trading on NSE stocks only</span>
      </div>

      <div className="card" style={{ padding: "20px 24px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 20 }}>
          <div style={{ textAlign: "center" }}>
            <div className={`num ${signalColor}`} style={{ fontSize: 28, fontWeight: 800 }}>{signal}</div>
            <div className="muted small">Combined signal</div>
          </div>
          <div style={{ height: 48, width: 1, background: "var(--border)" }} />
          <div className="muted small" style={{ lineHeight: 1.6, maxWidth: 400 }}>
            {aiA?.headline ?? `${ticker} moved ${pct(expl.change)} on ${new Date(expl.date + "T12:00:00Z").toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" })}.`}
          </div>
        </div>

        <div className="stat-cards" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))" }}>
          {/* CNN signal */}
          <div className="stat-card">
            <span className="stat-label">CNN model (5-day)</span>
            <strong className={`num ${cnnToday?.prob_up != null ? (cnnToday.prob_up > 0.5 ? "up" : "down") : ""}`}>
              {cnnToday?.prob_up != null ? `${(cnnToday.prob_up * 100).toFixed(1)}% up` : "—"}
            </strong>
            <span className="stat-note">{cnnToday?.accuracy != null ? `Test acc: ${(cnnToday.accuracy * 100).toFixed(0)}%` : ""}</span>
          </div>

          {/* FinBERT */}
          <div className="stat-card">
            <span className="stat-label">FinBERT sentiment</span>
            <strong className={`num ${avgSentiment > 0.05 ? "up" : avgSentiment < -0.05 ? "down" : ""}`}>
              {avgSentiment > 0.05 ? "Positive" : avgSentiment < -0.05 ? "Negative" : "Neutral"}
            </strong>
            <span className="stat-note">Score {(avgSentiment * 100).toFixed(0)}/100</span>
          </div>

          {/* Candlestick patterns */}
          <div className="stat-card">
            <span className="stat-label">Pattern bias</span>
            <strong className={`num ${patternBias === "bullish" ? "up" : patternBias === "bearish" ? "down" : ""}`}>
              {patternBias.charAt(0).toUpperCase() + patternBias.slice(1)}
            </strong>
            <span className="stat-note">{bullishPatterns}↑ {bearishPatterns}↓ patterns</span>
          </div>

          {/* AI verdict */}
          <div className="stat-card">
            <span className="stat-label">AI verdict</span>
            <strong className={`num ${aiA ? (expl.change >= 0 ? "up" : "down") : ""}`}>
              {aiVerdictStr ?? "—"}
            </strong>
            <span className="stat-note">{aiA ? aiA.confidence + " confidence" : "Analysis pending"}</span>
          </div>

          {/* Beta */}
          {expl.beta != null && (
            <div className="stat-card">
              <span className="stat-label">Beta vs S&amp;P 500</span>
              <strong className="num">{expl.beta.toFixed(2)}</strong>
              <span className="stat-note">Own move {pct(expl.change - (expl.market_part ?? 0))}</span>
            </div>
          )}

          {/* 52W position */}
          <div className="stat-card">
            <span className="stat-label">Move vs market</span>
            <strong className={`num ${tone(expl.change - (expl.market_part ?? 0))}`}>
              {pct(expl.change - (expl.market_part ?? 0))}
            </strong>
            <span className="stat-note">Stock's own move ({new Date(expl.date + "T12:00:00Z").toLocaleDateString("en-IN", { day: "numeric", month: "short" })})</span>
          </div>
        </div>

        {/* What to watch */}
        {aiA?.watch && aiA.watch.length > 0 && (
          <div style={{ marginTop: 20, paddingTop: 16, borderTop: "1px solid var(--border)" }}>
            <h3 style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>What to watch</h3>
            <ul style={{ paddingLeft: 18, margin: 0 }}>
              {aiA.watch.map((w, i) => <li key={i} className="muted small" style={{ lineHeight: 1.7 }}>{w}</li>)}
            </ul>
          </div>
        )}

        <p className="muted small" style={{ marginTop: 16, paddingTop: 12, borderTop: "1px solid var(--border)" }}>
          This signal combines CNN chart model, FinBERT news sentiment, candlestick patterns, and AI analysis.
          It is for reference only. Paper trading is available for NSE stocks.
          Not investment advice.
        </p>
      </div>
    </section>
  );
}

// ---- section nav ----
const GSD_SECTIONS: [string, string][] = [
  ["summary", "Summary"],
  ["chart", "Chart"],
  ["keystats", "Key stats"],
  ["why", "Why it moved"],
  ["signals", "Signals"],
  ["news", "News"],
];

function GlobalSectionNav() {
  const active = useActiveSection(GSD_SECTIONS.map(([id]) => id));
  return (
    <nav className="section-nav" aria-label="On this page">
      <ul>
        {GSD_SECTIONS.map(([id, text]) => (
          <li key={id}>
            <a href={`#${id}`} aria-current={active === id ? "location" : undefined}
              className={active === id ? "active" : ""}>{text}</a>
          </li>
        ))}
      </ul>
    </nav>
  );
}

// ---- news ----
function GlobalNewsPanel({ ticker, company }: { ticker: string; company: string }) {
  const [stocks, setStocks] = useState<Record<string, StockNews>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    setLoading(true); setError("");
    api.globalNews(ticker)
      .then(r => setStocks(r.stocks))
      .catch(() => setError("Could not load news."))
      .finally(() => setLoading(false));
  }, [ticker]);

  useEffect(() => { load(); }, [load]);

  const news = stocks[ticker];
  return (
    <section className="section" id="news" aria-labelledby="gnews-title">
      <div className="section-head">
        <h2 id="gnews-title" className="section-title">Latest news: {company}</h2>
        <button type="button" className="button ghost small" onClick={load} disabled={loading}>
          {loading ? "Loading" : "Refresh"}
        </button>
      </div>
      {error ? <p className="news-warning">{error}</p> : (
        !news ? <p className="news-empty">{loading ? "Loading headlines." : "No headlines loaded."}</p> :
        news.articles.length === 0 ? <p className="news-empty">No news about {company} in the past week.</p> :
        <ul className="news-list">
          {news.articles.map(a => (
            <li key={a.url}>
              <span className="news-source-mark" aria-hidden="true">{(a.source || "?").slice(0,1).toUpperCase()}</span>
              <span className="news-text">
                <a href={a.url} target="_blank" rel="noopener noreferrer">{a.title}</a>
                <span className="news-meta">
                  {a.source}{a.source ? " · " : ""}
                  <time dateTime={new Date(a.published * 1000).toISOString()}>{timeAgo(a.published)}</time>
                </span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// ---- WhyMoved ----
const SCOPE_LABEL: Record<Scope, string> = {
  company: "This company", peers: "Similar companies", industry: "Its industry",
  market: "Market", global: "World markets",
};

function GlobalWhyMoved({ ticker, currency, onDate }: {
  ticker: string;
  currency: string | null;
  onDate?: (date: string | null) => void;
}) {
  const [date, setDate] = useState<string | null>(null);
  const [expl, setExpl] = useState<Explanation | null>(null);
  const [loadingE, setLoadingE] = useState(false);
  const [errorE, setErrorE] = useState("");
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [loadingA, setLoadingA] = useState(false);
  const [errorA, setErrorA] = useState("");
  const [highlight, setHighlight] = useState<number | null>(null);

  const loadExpl = useCallback((d: string | null) => {
    setLoadingE(true); setExpl(null); setErrorE("");
    setAnalysis(null); setErrorA(""); setLoadingA(false);
    api.globalExplain(ticker, d)
      .then(e => { setExpl(e); setDate(e.date); onDate?.(e.date); })
      .catch(err => setErrorE(err instanceof Error ? err.message : "Could not load explanation."))
      .finally(() => setLoadingE(false));
  }, [ticker, onDate]);

  useEffect(() => { loadExpl(null); }, [loadExpl]);

  useEffect(() => {
    if (!expl) return;
    setLoadingA(true); setErrorA(""); setAnalysis(null);
    api.globalAnalysis(ticker, expl.date)
      .then(a => setAnalysis(a))
      .catch(err => setErrorA(err instanceof Error ? err.message : "AI analysis failed."))
      .finally(() => setLoadingA(false));
  }, [ticker, expl?.date]);

  const showEvidence = (n: number) => {
    setHighlight(n);
    document.getElementById(`gev-${n}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  const fell = expl ? expl.change < 0 : false;
  const longDay = (iso: string) =>
    new Date(`${iso}T12:00:00Z`).toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" });

  const evidence = analysis?.evidence ?? (expl ? numberLocally(expl) : []);
  const cited = citedNums(analysis);

  return (
    <section className="section why" id="why" aria-labelledby="gwhy-title">
      <div className="section-head">
        <h2 id="gwhy-title" className="section-title">
          {!expl ? `Why is ${ticker} moving?`
            : `Why did ${ticker} ${fell ? "fall" : "rise"} on ${longDay(expl.date)}?`}
        </h2>
        {expl && <span className={`badge ${fell ? "down" : "up"}`}>{pct(expl.change)}</span>}
      </div>

      {expl && (
        <div className="why-days" role="group">
          <span className="muted small">Explain:</span>
          <button type="button" className={date === null || date === expl.latest_date ? "day-chip on" : "day-chip"}
            onClick={() => loadExpl(null)}>Latest ({longDay(expl.latest_date)})</button>
          {expl.big_days.filter(b => b.date !== expl.latest_date).map(b => (
            <button key={b.date} type="button"
              className={date === b.date ? "day-chip on" : "day-chip"}
              onClick={() => loadExpl(b.date)}>
              {longDay(b.date)} <span className={tone(b.change)}>{pct(b.change, 1)}</span>
            </button>
          ))}
        </div>
      )}

      {loadingE && !expl && (
        <div className="why-loading" role="status">
          <div className="spinner" aria-hidden="true" />
          <span>Gathering {ticker}'s prices, similar companies and the news…</span>
        </div>
      )}
      {errorE && <p className="problems" role="alert">{errorE}</p>}

      {expl && (
        <>
          <article className="card why-ai" aria-live="polite">
            <header className="why-ai-head">
              <span className="ai-mark" aria-hidden="true">✦</span>
              <span className="strong">AI analysis</span>
              {analysis && <span className="chip quiet">{modelShort(analysis.model)} · {Math.round(analysis.seconds)}s</span>}
              {analysis?.analysis && (
                <>
                  <span className={`badge ${analysis.analysis.confidence === "high" ? "up" : analysis.analysis.confidence === "low" ? "down" : "neutral"}`}>
                    {analysis.analysis.confidence} confidence
                  </span>
                  <span className="chip">{analysis.analysis.verdict}</span>
                </>
              )}
            </header>
            {loadingA && (
              <div className="why-loading" role="status">
                <div className="spinner" aria-hidden="true" />
                <span>AI model reading {evidence.length} headlines and world markets… (~30–60 s)</span>
              </div>
            )}
            {errorA && !loadingA && <p className="problems" role="alert">{errorA}</p>}
            {analysis && !analysis.analysis && analysis.raw && <p className="why-raw">{analysis.raw}</p>}
            {analysis?.analysis && (() => {
              const a = analysis.analysis!;
              return (
                <>
                  <p className="why-headline">{citeInline(a.headline, showEvidence)}</p>
                  <div className="why-drivers">
                    {a.drivers.map((d, i) => (
                      <div key={i} className={`why-driver ${d.direction === "negative" ? "neg" : "pos"}`}>
                        <div className="why-driver-head">
                          <span className={`badge ${d.impact === "major" ? (d.direction === "negative" ? "down" : "up") : "neutral"}`}>{d.impact}</span>
                          <strong>{d.title}</strong>
                        </div>
                        <p>{citeInline(d.explanation, showEvidence)}</p>
                        {d.evidence.length > 0 && (
                          <p className="why-cites">Sources: {d.evidence.map(n => (
                            <button key={n} type="button" className="cite" onClick={() => showEvidence(n)}>[{n}]</button>
                          ))}</p>
                        )}
                      </div>
                    ))}
                  </div>
                  <div className="why-columns">
                    <div><h3>Market that day</h3><p>{citeInline(a.market_context, showEvidence)}</p></div>
                    <div><h3>Specific to {ticker}</h3><p>{citeInline(a.stock_specific, showEvidence)}</p></div>
                  </div>
                  {a.technical_view && (
                    <div className="why-columns">
                      <div style={{ gridColumn: "1 / -1" }}>
                        <h3>Technical view</h3>
                        <p>{citeInline(a.technical_view, showEvidence)}</p>
                      </div>
                    </div>
                  )}
                  <div className="why-columns">
                    <div><h3>What to watch</h3>
                      <ul className="why-watch">{a.watch.map((w,i) => <li key={i}>{citeInline(w, showEvidence)}</li>)}</ul>
                    </div>
                    <div><h3>How sure</h3><p>{citeInline(a.confidence_reason, showEvidence)}</p></div>
                  </div>
                </>
              );
            })()}
          </article>

          <TechCard explanation={expl} />

          <div className="why-facts">
            <div className="stat-cards">
              <StatCard label={`${ticker} on ${longDay(expl.date)}`} value={pct(expl.change)} t={tone(expl.change)}
                note={`${cur(currency)}${expl.prev_close.toFixed(2)} → ${cur(currency)}${expl.price.toFixed(2)}`} />
              <StatCard label="S&amp;P 500 that day" value={pct(expl.market.change)} t={tone(expl.market.change)} />
              {expl.market_part != null && <StatCard label="Market's part (beta)" value={pct(expl.market_part)} t={tone(expl.market_part)}
                note={expl.beta != null ? `Beta ${expl.beta.toFixed(2)}` : undefined} />}
              <StatCard label={`${ticker}'s own move`} value={pct(expl.change - (expl.market_part ?? 0))} t={tone(expl.change - (expl.market_part ?? 0))} />
            </div>
            {expl.peers.length > 0 && (
              <div className="why-chips">
                <span className="muted small">Similar companies today:</span>
                {expl.peers.map(p => (
                  <span key={p.symbol} className="market-chip">
                    {p.symbol} <span className={tone(p.change)}>{pct(p.change)}</span>
                  </span>
                ))}
              </div>
            )}
            {analysis && analysis.world.length > 0 && (
              <div className="why-chips">
                <span className="muted small">World markets:</span>
                {analysis.world.map(m => (
                  <span key={m.name} className="market-chip">
                    {m.name} <span className={tone(m.change)}>{pct(m.change)}</span>
                  </span>
                ))}
              </div>
            )}
          </div>

          <details className="card why-evidence" open>
            <summary>
              <strong>Evidence: {evidence.length} headlines</strong>
              <span className="muted small">{cited.size ? `; ${cited.size} cited by AI` : ""}</span>
            </summary>
            {expl.sentiment_totals && Object.keys(expl.sentiment_totals).length > 0 && (
              <div className="why-chips" style={{ marginTop: 8 }}>
                <span className="muted small">FinBERT sentiment:</span>
                {(Object.keys(SCOPE_LABEL) as Scope[]).filter(s => expl.sentiment_totals![s]).map(s => {
                  const t = expl.sentiment_totals![s]!;
                  return (
                    <span key={s} className="market-chip" title={`${t.positive} +, ${t.negative} −, ${t.neutral} ●`}>
                      {SCOPE_LABEL[s]}: <span className={t.avg_score > 0.05 ? "up" : t.avg_score < -0.05 ? "down" : ""}>{t.avg_score > 0 ? "+" : ""}{(t.avg_score * 100).toFixed(0)}</span>
                      <span className="muted small"> ({t.count})</span>
                    </span>
                  );
                })}
              </div>
            )}
            {evidence.length === 0 && <p className="muted">No headlines found for that day.</p>}
            {(Object.keys(SCOPE_LABEL) as Scope[]).filter(s => evidence.some(h => h.scope === s)).map(s => (
              <div key={s} className="ev-group">
                <h4>{SCOPE_LABEL[s]}</h4>
                <ol>
                  {evidence.filter(h => h.scope === s).map(h => (
                    <li key={h.n} id={`gev-${h.n}`} className={[h.n === highlight ? "hit" : "", cited.has(h.n) ? "cited" : ""].join(" ").trim()}>
                      <span className="ev-n">[{h.n}]</span>
                      <span className={`ev-dot ${h.tone > 0 ? "up" : h.tone < 0 ? "down" : ""}`} aria-hidden="true" />
                      <span className="ev-text">
                        <a href={h.url} target="_blank" rel="noopener noreferrer">{h.title}</a>
                        {h.sentiment && (
                          <span className={`finbert-badge ${h.sentiment.label}`}>
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
        </>
      )}
    </section>
  );
}

function TechCard({ explanation }: { explanation: Explanation }) {
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
        {hasCnn && cnn!.today && (
          <div className="tech-cnn">
            <img src={`data:image/png;base64,${cnn!.today.image_b64}`} alt="20-day candlestick chart"
              className="cnn-image" style={{ imageRendering: "pixelated" }} />
            <div className="cnn-info">
              <div className="cnn-prob">
                <span className="stat-label">P(up next 5 days)</span>
                <strong className={`num ${cnn!.today.prob_up != null && cnn!.today.prob_up > 0.5 ? "up" : "down"}`}>
                  {cnn!.today.prob_up != null ? `${(cnn!.today.prob_up * 100).toFixed(1)}%` : "—"}
                </strong>
              </div>
              {cnn!.today.accuracy != null && (
                <span className="muted small">Test accuracy: {(cnn!.today.accuracy * 100).toFixed(1)}% (baseline: {(cnn!.today.baseline! * 100).toFixed(1)}%)</span>
              )}
            </div>
          </div>
        )}
        <div className="tech-patterns">
          {hasBars && (
            <>
              <h4>Recent candles</h4>
              <MiniCandleChart bars={ohlcBars!} date={explanation.date} />
            </>
          )}
          {hasPatterns && (
            <>
              <h4>Patterns detected</h4>
              {patterns!.today.map(p => <PatternBadge key={p.name} pattern={p} when="today" />)}
              {patterns!.previous.map(p => <PatternBadge key={`prev-${p.name}`} pattern={p} when="previous day" />)}
            </>
          )}
        </div>
      </div>
    </article>
  );
}

function MiniCandleChart({ bars, date }: { bars: OHLCBar[]; date: string }) {
  if (!bars || bars.length === 0) return null;
  const W = 280, H = 140, PAD = 16;
  const cw = Math.floor((W - PAD * 2) / bars.length);
  const allPrices = bars.flatMap(b => [b.high, b.low]);
  const pMin = Math.min(...allPrices), pMax = Math.max(...allPrices);
  const range = pMax - pMin || 1;
  const y = (p: number) => PAD + (1 - (p - pMin) / range) * (H - PAD * 2);
  return (
    <svg className="candle-chart" viewBox={`0 0 ${W} ${H}`} width={W} height={H}>
      {bars.map((b, i) => {
        const x = PAD + i * cw + cw / 2;
        const isUp = b.close >= b.open;
        const color = isUp ? "var(--up)" : "var(--down)";
        const bodyTop = y(Math.max(b.open, b.close));
        const bodyH = Math.max(y(Math.min(b.open, b.close)) - bodyTop, 1);
        return (
          <g key={b.date}>
            <line x1={x} y1={y(b.high)} x2={x} y2={y(b.low)} stroke={color} strokeWidth={1} />
            <rect x={x - cw * 0.35} y={bodyTop} width={cw * 0.7} height={bodyH}
              fill={isUp ? "transparent" : color} stroke={color} strokeWidth={1} />
            {b.date === date && <line x1={x} y1={H - 4} x2={x} y2={H - 1} stroke="var(--accent)" strokeWidth={3} />}
          </g>
        );
      })}
    </svg>
  );
}

function PatternBadge({ pattern, when }: { pattern: CandlePattern; when: string }) {
  return (
    <div className={`pattern-row ${pattern.bias}`}>
      <span className={`badge ${pattern.bias === "bullish" ? "up" : pattern.bias === "bearish" ? "down" : "neutral"}`}>{pattern.name}</span>
      <span className="muted small">{when} · {pattern.bias} · hist. up rate {(pattern.up_rate * 100).toFixed(0)}% · {pattern.note}</span>
    </div>
  );
}

function StatCard({ label, value, t, note }: { label: string; value: string; t: string; note?: string }) {
  return (
    <div className="stat-card">
      <span className="stat-label">{label}</span>
      <strong className={`num ${t}`}>{value}</strong>
      {note && <span className="stat-note">{note}</span>}
    </div>
  );
}

function citeInline(text: string, onCite: (n: number) => void): ReactNode {
  const parts = text.split(/(\[\d+\])/g);
  return parts.map((part, i) => {
    const m = /^\[(\d+)\]$/.exec(part);
    return m ? <button key={i} type="button" className="cite" onClick={() => onCite(Number(m[1]))}>{part}</button>
             : <Fragment key={i}>{part}</Fragment>;
  });
}

function citedNums(analysis: Analysis | null): Set<number> {
  const out = new Set<number>();
  const a = analysis?.analysis;
  if (!a) return out;
  a.drivers.forEach(d => d.evidence.forEach(n => out.add(n)));
  const text = [a.headline, a.market_context, a.stock_specific, a.confidence_reason, ...a.watch, ...a.drivers.map(d => d.explanation)].join(" ");
  for (const m of text.matchAll(/\[(\d+)\]/g)) out.add(Number(m[1]));
  return out;
}

function numberLocally(e: Explanation): (ExplainHeadline & { n: number })[] {
  const out: (ExplainHeadline & { n: number })[] = [];
  for (const scope of Object.keys(SCOPE_LABEL) as Scope[]) {
    for (const h of (e.headlines[scope] ?? []).slice(0, 10)) out.push({ ...h, n: out.length + 1 });
  }
  return out;
}

function modelShort(id: string) {
  return id.split("/").pop()?.replace(":free", "") ?? id;
}

// ---- main component ----
export function GlobalStockDetail({ ticker, onBack }: Props) {
  const [quote, setQuote] = useState<GlobalQuote | null>(null);
  const [loadingQ, setLoadingQ] = useState(true);
  const [profile, setProfile] = useState<{ sector: string | null; industry: string | null; summary: string | null } | null>(null);
  const [, setWhyDate] = useState<string | null>(null);

  useEffect(() => {
    setLoadingQ(true); setQuote(null);
    api.globalQuote([ticker])
      .then(res => setQuote(res.quotes[ticker] ?? null))
      .catch(() => {})
      .finally(() => setLoadingQ(false));
    api.globalProfile(ticker)
      .then(p => setProfile(p))
      .catch(() => {});
  }, [ticker]);

  const scrollToWhy = () => {
    setWhyDate(null);
    setTimeout(() => document.getElementById("why")?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
  };

  const c = quote?.currency ?? null;
  const changeDir = dir(quote?.change ?? null);
  const isUp = (quote?.change ?? 0) >= 0;
  const lastTime = quote?.quote_time ?? null;
  const isRegular = quote?.market_state === "REGULAR";
  const MARKET_STATE: Record<string, string> = {
    REGULAR: "Open", PRE: "Pre-market", PREPRE: "Pre-pre-market",
    POST: "After hours", POSTPOST: "After hours", CLOSED: "Closed",
  };

  return (
    <div className="container detail-layout">
      <GlobalSectionNav />

      <main id="main" className="main-col">
        <button type="button" className="back-btn" onClick={onBack}>
          <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><path d="M9 2L4 7l5 5" /></svg>
          Dashboard
        </button>

        {/* quote header */}
        <header className="quote-header" id="summary">
          <p className="eyebrow">
            {quote?.exchange ?? ticker} {"·"} {quote?.quote_type ?? "Equity"} {"·"} {quote?.currency ?? "—"} {"·"} Live prices, view only
          </p>
          {loadingQ ? <p className="muted">Loading {ticker}…</p> : quote ? (
            <>
              <div className="quote-title">
                <h1>
                  {quote.name ?? ticker} <span className="muted">({ticker})</span>
                </h1>
              </div>
              <div className="quote-row">
                <div>
                  <div className="quote-price">
                    <span className="num big">{fmt(quote.price, c)}</span>
                    <span className={`num change ${changeDir}`}>
                      {sign(quote.change)} ({sign(quote.change_pct)}%)
                    </span>
                    {quote.price != null && (
                      <button type="button" className="why-button" onClick={scrollToWhy}>
                        Why {isUp ? "up" : "down"}? <span aria-hidden="true">→</span>
                      </button>
                    )}
                  </div>
                  <p className="as-of">
                    {!lastTime ? "No price yet." : isRegular
                      ? `Live · last trade at ${new Date(lastTime * 1000).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", timeZoneName: "short" })}.`
                      : `${MARKET_STATE[quote.market_state ?? ""] ?? quote.market_state ?? "Market closed"}.`}
                  </p>
                </div>
              </div>
            </>
          ) : <p className="muted">Could not load data for {ticker}.</p>}
        </header>

        {/* chart */}
        <GlobalPriceChart
          ticker={ticker}
          prevClose={quote?.prev_close ?? null}
          currency={c}
          onPickDay={(d) => {
            setWhyDate(d);
            setTimeout(() => document.getElementById("why")?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
          }}
        />

        {/* key stats */}
        {quote && (
          <section className="key-stats" id="keystats" aria-label="Key statistics">
            <dl>
              {([
                ["Previous close", fmt(quote.prev_close, c)],
                ["Open", fmt(quote.open, c)],
                ["Day's range", quote.low != null && quote.high != null ? `${fmt(quote.low, c)} – ${fmt(quote.high, c)}` : "—"],
                ["52-week range", quote.week52_low != null && quote.week52_high != null ? `${fmt(quote.week52_low, c)} – ${fmt(quote.week52_high, c)}` : "—"],
                ["Volume", fmtVol(quote.volume)],
                ["Average volume", fmtVol(quote.avg_volume)],
                ["Market cap", fmtCap(quote.market_cap, c)],
                ["P/E ratio", quote.pe != null ? quote.pe.toFixed(2) : "—"],
                ["Earnings per share", fmt(quote.eps, c, 2)],
                ["Dividend yield", quote.dividend_yield != null ? quote.dividend_yield.toFixed(2) + "%" : "—"],
                ...(profile?.sector ? [["Sector", profile.sector] as [string, string]] : []),
                ...(profile?.industry ? [["Industry", profile.industry] as [string, string]] : []),
              ] as [string, string][]).map(([label, value]) => (
                <div key={label}><dt>{label}</dt><dd className="num">{value}</dd></div>
              ))}
            </dl>
          </section>
        )}

        {/* why it moved */}
        <GlobalWhyMoved ticker={ticker} currency={c} onDate={setWhyDate} />

        {/* signals & ideas */}
        <GlobalSignalsPanel ticker={ticker} currency={c} />

        {/* news */}
        <GlobalNewsPanel ticker={ticker} company={quote?.name ?? ticker} />
      </main>

      <aside className="rail" aria-label="Market info">
        {profile?.summary && (
          <div className="rail-card">
            <div className="section-head"><h3 className="section-title small">About {quote?.name ?? ticker}</h3></div>
            <p className="muted small" style={{ lineHeight: 1.6, marginTop: 8 }}>{profile.summary.slice(0, 500)}{profile.summary.length > 500 ? "…" : ""}</p>
            {profile.sector && <p className="muted small" style={{ marginTop: 8 }}><strong>{profile.sector}</strong>{profile.industry ? ` · ${profile.industry}` : ""}</p>}
          </div>
        )}
        <div className="rail-card">
          <div className="section-head"><h3 className="section-title small">Market details</h3></div>
          <div className="gsd-about">
            <div><span className="label">Type</span><span>{quote?.quote_type ?? "—"}</span></div>
            <div><span className="label">Exchange</span><span>{quote?.exchange ?? "—"}</span></div>
            <div><span className="label">Currency</span><span>{quote?.currency ?? "—"}</span></div>
            <div><span className="label">Market</span>
              <span className={isRegular ? "up" : ""}>{quote?.market_state ? (MARKET_STATE[quote.market_state] ?? quote.market_state) : "—"}</span>
            </div>
            {quote?.bid != null && <div><span className="label">Bid</span><span className="num">{fmt(quote.bid, c)}</span></div>}
            {quote?.ask != null && <div><span className="label">Ask</span><span className="num">{fmt(quote.ask, c)}</span></div>}
          </div>
          <p className="muted small" style={{ marginTop: 12, lineHeight: 1.5 }}>
            Global stocks are shown for reference only. Paper trading is available for NSE stocks.
          </p>
        </div>
      </aside>
    </div>
  );
}
