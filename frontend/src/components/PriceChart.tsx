import { useEffect, useLayoutEffect, useRef, useState, type MouseEvent } from "react";

import { api } from "../api";
import { clock, price } from "../format";

interface Props {
  symbol: string;
  ltp: number | null;
  prevClose: number;
}

type Point = [number, number]; // epoch seconds, price in paise

const HEIGHT = 190;
const MARGIN = { top: 12, right: 64, bottom: 24, left: 8 };
const MAX_POINTS = 1800;

/** Last traded price, one point per second, for the selected stock. */
export function PriceChart({ symbol, ltp, prevClose }: Props) {
  const [points, setPoints] = useState<Point[]>([]);
  const [hover, setHover] = useState<number | null>(null);
  const [width, setWidth] = useState(600);
  const frame = useRef<HTMLDivElement>(null);
  const latest = useRef(ltp);
  latest.current = ltp;

  useLayoutEffect(() => {
    const element = frame.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(240, entry.contentRect.width)));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  // Load what the server has recorded so far, then add one point a second.
  useEffect(() => {
    let cancelled = false;
    setPoints([]);
    setHover(null);
    api.history(symbol).then((history) => !cancelled && setPoints(history)).catch(() => undefined);
    const timer = window.setInterval(() => {
      const current = latest.current;
      if (current == null) return;
      setPoints((prev) => [...prev, [Math.floor(Date.now() / 1000), current] as Point].slice(-MAX_POINTS));
    }, 1000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [symbol]);

  if (points.length < 2) {
    return (
      <section className="panel chart" ref={frame}>
        <h2>Last traded price</h2>
        <p className="empty" style={{ height: HEIGHT }}>Waiting for trades.</p>
      </section>
    );
  }

  const innerW = width - MARGIN.left - MARGIN.right;
  const innerH = HEIGHT - MARGIN.top - MARGIN.bottom;
  const t0 = points[0][0];
  const t1 = points[points.length - 1][0];
  let low = Infinity;
  let high = -Infinity;
  for (const [, p] of points) {
    low = Math.min(low, p);
    high = Math.max(high, p);
  }
  const pad = Math.max((high - low) * 0.12, prevClose * 0.0005);
  low -= pad;
  high += pad;
  const x = (t: number) => MARGIN.left + ((t - t0) / Math.max(1, t1 - t0)) * innerW;
  const y = (p: number) => MARGIN.top + (1 - (p - low) / (high - low)) * innerH;
  const path = points.map(([t, p], i) => `${i === 0 ? "M" : "L"}${x(t).toFixed(1)},${y(p).toFixed(1)}`).join(" ");
  const ticks = [high - pad, (high + low) / 2, low + pad];
  const showPrevClose = prevClose > low && prevClose < high;
  const hovered = hover == null ? null : points[hover];

  const onMove = (event: MouseEvent<SVGSVGElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const t = t0 + ((event.clientX - rect.left - MARGIN.left) / innerW) * (t1 - t0);
    // Points are one second apart, so the nearest one is found by position.
    let nearest = 0;
    for (let i = 1; i < points.length; i++) {
      if (Math.abs(points[i][0] - t) < Math.abs(points[nearest][0] - t)) nearest = i;
    }
    setHover(nearest);
  };

  return (
    <section className="panel chart" ref={frame}>
      <h2>Last traded price</h2>
      <svg width={width} height={HEIGHT} onMouseMove={onMove} onMouseLeave={() => setHover(null)} role="img"
        aria-label={`Last traded price of ${symbol}, from ${clock(t0)} to ${clock(t1)}`}>
        {ticks.map((value) => (
          <g key={value}>
            <line className="grid" x1={MARGIN.left} x2={MARGIN.left + innerW} y1={y(value)} y2={y(value)} />
            <text className="axis" x={MARGIN.left + innerW + 8} y={y(value)} dominantBaseline="middle">{price(Math.round(value))}</text>
          </g>
        ))}
        {showPrevClose && (
          <g>
            <line className="reference" x1={MARGIN.left} x2={MARGIN.left + innerW} y1={y(prevClose)} y2={y(prevClose)} />
            <text className="axis" x={MARGIN.left + 4} y={y(prevClose) - 5}>Previous close {price(prevClose)}</text>
          </g>
        )}
        <path className="line" d={path} />
        <text className="axis" x={MARGIN.left} y={HEIGHT - 6}>{clock(t0)}</text>
        <text className="axis" x={MARGIN.left + innerW} y={HEIGHT - 6} textAnchor="end">{clock(t1)}</text>
        {hovered && (
          <g>
            <line className="crosshair" x1={x(hovered[0])} x2={x(hovered[0])} y1={MARGIN.top} y2={MARGIN.top + innerH} />
            <circle className="marker" cx={x(hovered[0])} cy={y(hovered[1])} r={4} />
          </g>
        )}
      </svg>
      {hovered && (
        <div className="tooltip" style={{ left: Math.min(x(hovered[0]) + 12, width - 150), top: 38 }}>
          <span className="muted">{clock(hovered[0])}</span>
          <strong className="num">{price(hovered[1])}</strong>
        </div>
      )}
    </section>
  );
}
