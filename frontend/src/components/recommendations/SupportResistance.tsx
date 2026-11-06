import type { PivotEntry, PivotLevels } from "../../api/types";
import { price } from "../../lib/format";

interface Props {
  levels: PivotLevels | null | undefined;
  ltp: number | null | undefined;
  entry: PivotEntry | null | undefined;
  loading?: boolean;
}

/** Where the current price sits among the seven pivot levels (above R3, between R3 and R2, …, below S3). */
function priceSlot(levels: PivotLevels, ltp: number): number {
  // Returns 0 (above R3) through 7 (below S3), or the index where ltp sits.
  if (ltp > (levels.r3 ?? -Infinity)) return 0;
  if (ltp > (levels.r2 ?? -Infinity)) return 1;
  if (ltp > (levels.r1 ?? -Infinity)) return 2;
  if (ltp > (levels.pp ?? -Infinity)) return 3;
  if (ltp > (levels.s1 ?? -Infinity)) return 4;
  if (ltp > (levels.s2 ?? -Infinity)) return 5;
  if (ltp > (levels.s3 ?? -Infinity)) return 6;
  return 7;
}

function PricePill({ ltp }: { ltp: number }) {
  return (
    <div className="sr-price-pill" aria-label={`Current price ${price(ltp)}`}>
      PRICE {price(ltp)}
    </div>
  );
}

function PivotPill({ pp }: { pp: number }) {
  return <div className="sr-pivot-pill">PIVOT {price(pp)}</div>;
}

function LevelRow({ label, value, tone }: { label: string; value: number | null; tone: "up" | "down" | "" }) {
  return (
    <li className={`sr-row${tone ? ` sr-row-${tone}` : ""}`}>
      <span className="sr-label">{label}</span>
      <span className="sr-value num">{value != null ? price(value) : "—"}</span>
    </li>
  );
}

export function SupportResistance({ levels, ltp, entry, loading }: Props) {
  if (loading) {
    return (
      <div className="sr-panel">
        <div className="sr-header">
          <span className="strong">Support and Resistance</span>
        </div>
        <div className="sr-card sr-skeleton">
          {[0, 1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} className="sr-skeleton-row" />
          ))}
        </div>
      </div>
    );
  }

  if (!levels || levels.error) {
    return (
      <div className="sr-panel">
        <div className="sr-header">
          <span className="strong">Support and Resistance</span>
        </div>
        <div className="sr-card sr-empty">
          <span className="muted small">{levels?.error ?? "Not enough data yet"}</span>
        </div>
      </div>
    );
  }

  const slot = ltp != null ? priceSlot(levels, ltp) : -1;

  // Announce price position accessibly
  const slotLabels = [
    "above R3", "between R2 and R3", "between R1 and R2", "between PP and R1",
    "between PP and S1", "between S1 and S2", "between S2 and S3", "below S3",
  ];
  const ariaLive = ltp != null && slot >= 0
    ? `Current price ${price(ltp)}, ${slotLabels[slot]}`
    : undefined;

  return (
    <div className="sr-panel">
      <div className="sr-header">
        <span className="strong">Support and Resistance</span>
        <span className="sr-info" title="Classic (Floor) pivot levels from the previous session's High, Low and Close. The price marker updates live; levels change only when the session rolls over." aria-label="Info: Classic pivot levels from the previous session">ⓘ</span>
      </div>

      <ul className="sr-card" role="list" aria-label="Support and resistance levels">
        {/* PRICE pill above R3 */}
        {slot === 0 && ltp != null && (
          <li className="sr-pill-row" aria-live="polite" aria-atomic="true" aria-label={ariaLive}>
            <PricePill ltp={ltp} />
          </li>
        )}

        <LevelRow label="R3" value={levels.r3} tone="up" />
        {slot === 1 && ltp != null && (
          <li className="sr-pill-row" aria-live="polite" aria-atomic="true" aria-label={ariaLive}>
            <PricePill ltp={ltp} />
          </li>
        )}

        <LevelRow label="R2" value={levels.r2} tone="up" />
        {slot === 2 && ltp != null && (
          <li className="sr-pill-row" aria-live="polite" aria-atomic="true" aria-label={ariaLive}>
            <PricePill ltp={ltp} />
          </li>
        )}

        <LevelRow label="R1" value={levels.r1} tone="up" />
        {slot === 3 && ltp != null && (
          <li className="sr-pill-row" aria-live="polite" aria-atomic="true" aria-label={ariaLive}>
            <PricePill ltp={ltp} />
          </li>
        )}

        {levels.pp != null && (
          <li className="sr-pivot-row" aria-label={`Pivot point ${price(levels.pp)}`}>
            <PivotPill pp={levels.pp} />
          </li>
        )}

        {slot === 4 && ltp != null && (
          <li className="sr-pill-row" aria-live="polite" aria-atomic="true" aria-label={ariaLive}>
            <PricePill ltp={ltp} />
          </li>
        )}

        <LevelRow label="S1" value={levels.s1} tone="down" />
        {slot === 5 && ltp != null && (
          <li className="sr-pill-row" aria-live="polite" aria-atomic="true" aria-label={ariaLive}>
            <PricePill ltp={ltp} />
          </li>
        )}

        <LevelRow label="S2" value={levels.s2} tone="down" />
        {slot === 6 && ltp != null && (
          <li className="sr-pill-row" aria-live="polite" aria-atomic="true" aria-label={ariaLive}>
            <PricePill ltp={ltp} />
          </li>
        )}

        <LevelRow label="S3" value={levels.s3} tone="down" />

        {/* PRICE pill below S3 */}
        {slot === 7 && ltp != null && (
          <li className="sr-pill-row" aria-live="polite" aria-atomic="true" aria-label={ariaLive}>
            <PricePill ltp={ltp} />
          </li>
        )}
      </ul>

      {entry && (
        <EntryExitCard entry={entry} ltp={ltp} />
      )}

      <p className="sr-disclaimer hint">
        Algorithmic levels for reference only — not financial advice.
      </p>
    </div>
  );
}

function EntryExitCard({ entry }: { entry: PivotEntry; ltp?: number | null }) {
  if (entry.entry == null) {
    return (
      <div className="sr-entry-card sr-entry-invalid">
        <span className="sr-entry-label">Entry/Exit</span>
        <span className="muted small">{entry.reason}</span>
      </div>
    );
  }

  const rr = entry.risk_reward != null ? entry.risk_reward.toFixed(1) : "—";

  return (
    <div className={`sr-entry-card${!entry.valid ? " sr-entry-caution" : ""}`}>
      <div className="sr-entry-header">
        <span className="sr-entry-label">Entry / Exit</span>
        <span className="sr-entry-type">{entry.type === "support_buy" ? "Support entry" : "Breakout entry"}</span>
      </div>
      <div className="sr-entry-grid">
        <div className="sr-entry-cell">
          <span className="sr-cell-label">Entry</span>
          <span className="sr-cell-value num">{price(entry.entry)}</span>
        </div>
        <div className="sr-entry-cell sr-cell-target">
          <span className="sr-cell-label">Target</span>
          <span className="sr-cell-value num up">{price(entry.target)}</span>
        </div>
        <div className="sr-entry-cell sr-cell-stop">
          <span className="sr-cell-label">Stop-loss</span>
          <span className="sr-cell-value num down">{price(entry.stop_loss)}</span>
        </div>
        <div className="sr-entry-cell">
          <span className="sr-cell-label">Risk/Reward</span>
          <span className={`sr-cell-value num${!entry.valid ? " down" : ""}`}>{rr}×</span>
        </div>
      </div>
      <p className="sr-entry-reason hint">{entry.reason}</p>
    </div>
  );
}
