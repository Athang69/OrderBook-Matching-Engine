import type { IndexQuote } from "../../api/types";
import { price } from "../../lib/format";

interface Props {
  indices: Record<string, IndexQuote>;
  indexOrder: string[];
  onGlobal?: () => void;
}

export function IndicesBar({ indices, indexOrder, onGlobal }: Props) {
  return (
    <div className="indices-bar" role="region" aria-label="Market indices">
      <div className="container indices-row">
        <div className="indices-scroll">
          {indexOrder.map((name) => {
            const idx = indices[name];
            const pct = idx?.ltp != null && idx.prev_close
              ? ((idx.ltp - idx.prev_close) / idx.prev_close) * 100
              : null;
            const dir = pct == null ? "" : pct > 0 ? "up" : pct < 0 ? "down" : "";
            return (
              <div key={name} className="index-tile">
                <span className="idx-name">{name}</span>
                <span className={`idx-val num ${idx?.ltp == null ? "faint" : ""}`}>
                  {price(idx?.ltp ?? null)}
                </span>
                {pct != null && (
                  <span className={`idx-chg num ${dir}`}>
                    {pct >= 0 ? "+" : ""}{pct.toFixed(2)}%
                  </span>
                )}
              </div>
            );
          })}
        </div>

        {onGlobal && (
          <button
            type="button"
            className="idx-global-btn"
            onClick={onGlobal}
            aria-label="Open global markets"
          >
            <svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" strokeWidth="1.3" aria-hidden="true">
              <circle cx="6.5" cy="6.5" r="5" />
              <ellipse cx="6.5" cy="6.5" rx="2.2" ry="5" />
              <line x1="1.5" y1="6.5" x2="11.5" y2="6.5" />
              <line x1="2.3" y1="4" x2="10.7" y2="4" />
              <line x1="2.3" y1="9" x2="10.7" y2="9" />
            </svg>
            <span>Markets</span>
          </button>
        )}
      </div>
    </div>
  );
}
