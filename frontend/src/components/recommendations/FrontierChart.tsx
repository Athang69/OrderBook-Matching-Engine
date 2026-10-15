import { useLayoutEffect, useRef, useState, type MouseEvent } from "react";

export interface FrontierMarker {
  kind: "best" | "safest" | "yours";
  label: string;
  volatility: number;
  ret: number;
}

interface Props {
  /** Random portfolios: [annual volatility, annual return, Sharpe ratio]. */
  points: [number, number, number][];
  markers: FrontierMarker[];
}

const HEIGHT = 300;
const MARGIN = { top: 14, right: 24, bottom: 46, left: 62 };

const pct = (value: number, digits = 0) => `${(value * 100).toFixed(digits)}%`;

/** Risk against return for the random portfolios, as in the original script's efficient-frontier plot. */
export function FrontierChart({ points, markers }: Props) {
  const frame = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(640);
  const [hover, setHover] = useState<{ x: number; y: number; vol: number; ret: number; sharpe: number | null; label?: string } | null>(null);

  useLayoutEffect(() => {
    const element = frame.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(280, entry.contentRect.width)));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const vols = [...points.map((p) => p[0]), ...markers.map((m) => m.volatility)];
  const rets = [...points.map((p) => p[1]), ...markers.map((m) => m.ret)];
  const sharpes = points.map((p) => p[2]);
  const [vMin, vMax] = padded(Math.min(...vols), Math.max(...vols));
  const [rMin, rMax] = padded(Math.min(...rets), Math.max(...rets));
  const sMin = Math.min(...sharpes);
  const sMax = Math.max(...sharpes);
  const innerW = width - MARGIN.left - MARGIN.right;
  const innerH = HEIGHT - MARGIN.top - MARGIN.bottom;
  const x = (v: number) => MARGIN.left + ((v - vMin) / (vMax - vMin)) * innerW;
  const y = (r: number) => MARGIN.top + (1 - (r - rMin) / (rMax - rMin)) * innerH;
  const shade = (s: number) => 0.12 + 0.78 * ((s - sMin) / Math.max(1e-9, sMax - sMin));

  const onMove = (event: MouseEvent<SVGSVGElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const mx = event.clientX - rect.left;
    const my = event.clientY - rect.top;
    let best: typeof hover = null;
    let bestDistance = 18 * 18; // only points within 18px count
    for (const m of markers) {
      const d = (x(m.volatility) - mx) ** 2 + (y(m.ret) - my) ** 2;
      if (d < bestDistance * 1.5) {
        bestDistance = d / 1.5;
        best = { x: x(m.volatility), y: y(m.ret), vol: m.volatility, ret: m.ret, sharpe: null, label: m.label };
      }
    }
    for (const [vol, ret, sharpe] of points) {
      const d = (x(vol) - mx) ** 2 + (y(ret) - my) ** 2;
      if (d < bestDistance) {
        bestDistance = d;
        best = { x: x(vol), y: y(ret), vol, ret, sharpe };
      }
    }
    setHover(best);
  };

  return (
    <div className="frontier" ref={frame}>
      <ul className="legend">
        <li><span className="swatch cloud" />Random portfolios (darker means a higher Sharpe ratio)</li>
        {markers.map((m) => (
          <li key={m.kind}><span className={`swatch ${m.kind}`} />{m.label}</li>
        ))}
      </ul>
      <svg width={width} height={HEIGHT} onMouseMove={onMove} onMouseLeave={() => setHover(null)} role="img"
        aria-label="Annual risk against expected annual return for 1,500 random portfolios and the highlighted portfolios">
        {ticks(rMin, rMax).map((t) => (
          <g key={`y${t}`}>
            <line className="grid" x1={MARGIN.left} x2={MARGIN.left + innerW} y1={y(t)} y2={y(t)} />
            <text className="axis" x={MARGIN.left - 8} y={y(t)} textAnchor="end" dominantBaseline="middle">{pct(t)}</text>
          </g>
        ))}
        {ticks(vMin, vMax).map((t) => (
          <text key={`x${t}`} className="axis" x={x(t)} y={MARGIN.top + innerH + 18} textAnchor="middle">{pct(t)}</text>
        ))}
        <text className="axis-title" x={MARGIN.left + innerW / 2} y={HEIGHT - 6} textAnchor="middle">Annual volatility (risk)</text>
        <text className="axis-title" transform={`translate(14 ${MARGIN.top + innerH / 2}) rotate(-90)`} textAnchor="middle">Expected annual return</text>
        {points.map(([vol, ret, sharpe], i) => (
          <circle key={i} className="cloud-point" cx={x(vol)} cy={y(ret)} r={2.3} fillOpacity={shade(sharpe)} />
        ))}
        {markers.map((m) => (
          <Marker key={m.kind} kind={m.kind} cx={x(m.volatility)} cy={y(m.ret)} />
        ))}
        {hover && <circle className="hover-ring" cx={hover.x} cy={hover.y} r={7} />}
      </svg>
      {hover && (
        <div className="tooltip" style={{ left: Math.min(hover.x + 14, width - 190), top: Math.max(hover.y - 10, 30) }}>
          {hover.label && <strong>{hover.label}</strong>}
          <span>Expected return <b className="num">{pct(hover.ret, 1)}</b></span>
          <span>Volatility <b className="num">{pct(hover.vol, 1)}</b></span>
          {hover.sharpe != null && <span>Sharpe ratio <b className="num">{hover.sharpe.toFixed(2)}</b></span>}
        </div>
      )}
    </div>
  );
}

function Marker({ kind, cx, cy }: { kind: FrontierMarker["kind"]; cx: number; cy: number }) {
  if (kind === "best") {
    return <path className="marker best" d={`M${cx} ${cy - 8} L${cx + 8} ${cy} L${cx} ${cy + 8} L${cx - 8} ${cy} Z`} />;
  }
  if (kind === "safest") {
    return <rect className="marker safest" x={cx - 6.5} y={cy - 6.5} width={13} height={13} rx={2} />;
  }
  return <circle className="marker yours" cx={cx} cy={cy} r={7} />;
}

function padded(min: number, max: number): [number, number] {
  const span = Math.max(max - min, 0.01);
  return [min - span * 0.06, max + span * 0.06];
}

/** About five round tick values between min and max. */
function ticks(min: number, max: number): number[] {
  const raw = (max - min) / 5;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((s) => s >= raw) ?? raw;
  const out = [];
  for (let t = Math.ceil(min / step) * step; t <= max; t += step) out.push(Number(t.toFixed(10)));
  return out;
}
