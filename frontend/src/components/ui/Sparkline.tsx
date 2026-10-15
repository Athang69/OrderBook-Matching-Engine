import type { PricePoint } from "../../api/types";

interface Props {
  points: PricePoint[];
  /** Reference price: green above it, red below it. */
  base: number;
  width?: number;
  height?: number;
  label: string;
}

/** A small line of the recent price, with a dotted line at the previous close. */
export function Sparkline({ points, base, width = 88, height = 30, label }: Props) {
  if (points.length < 2) return <svg className="sparkline" width={width} height={height} aria-hidden="true" />;
  let low = Infinity;
  let high = -Infinity;
  for (const [, p] of points) {
    low = Math.min(low, p);
    high = Math.max(high, p);
  }
  const span = Math.max(high - low, 1);
  const showBase = base >= low && base <= high;
  const t0 = points[0][0];
  const t1 = points[points.length - 1][0];
  const x = (t: number) => ((t - t0) / Math.max(1, t1 - t0)) * (width - 2) + 1;
  const y = (p: number) => 2 + (1 - (p - low) / span) * (height - 4);
  const line = points.map(([t, p], i) => `${i ? "L" : "M"}${x(t).toFixed(1)},${y(p).toFixed(1)}`).join("");
  const tone = points[points.length - 1][1] >= base ? "up" : "down";
  return (
    <svg className={`sparkline ${tone}`} width={width} height={height} role="img" aria-label={label}>
      {showBase && <line className="sparkline-base" x1={0} x2={width} y1={y(base)} y2={y(base)} />}
      <path className="sparkline-area" d={`${line}L${x(t1)},${height}L${x(t0)},${height}Z`} />
      <path className="sparkline-line" d={line} />
    </svg>
  );
}
