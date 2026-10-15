import type { CSSProperties } from "react";

import type { Instrument, Level, MarketState, Trade } from "../../api/types";
import { DASH, clock, price, qty } from "../../lib/format";

const ROWS = 5;

/** Market depth: the best five buy and sell prices, and the latest trades. */
export function MarketDepth({ instrument, state, trades, onPickPrice }: {
  instrument: Instrument; state: MarketState; trades: Trade[]; onPickPrice: (price: number) => void;
}) {
  return (
    <section className="section" id="depth" aria-labelledby="depth-title">
      <h2 id="depth-title" className="section-title">Order book</h2>
      <div className="depth-grid">
        <OrderBook instrument={instrument} state={state} onPickPrice={onPickPrice} />
        <TimeAndSales trades={trades} />
      </div>
    </section>
  );
}

function OrderBook({ instrument, state, onPickPrice }: { instrument: Instrument; state: MarketState; onPickPrice: (price: number) => void }) {
  const largest = Math.max(1, ...state.bids.map((l) => l[1]), ...state.asks.map((l) => l[1]));
  const bestBid = state.bids[0]?.[0];
  const bestAsk = state.asks[0]?.[0];
  const spread = bestBid != null && bestAsk != null ? bestAsk - bestBid : null;
  const bidTotal = state.bids.reduce((sum, l) => sum + l[1], 0);
  const askTotal = state.asks.reduce((sum, l) => sum + l[1], 0);
  const buyShare = bidTotal + askTotal ? bidTotal / (bidTotal + askTotal) : 0.5;

  return (
    <div className="card book-card">
      <div className="card-head">
        <h3>Market depth</h3>
        <span className="muted small">Spread <span className="num">{spread == null ? DASH : price(spread)}</span> {"·"} tick <span className="num">{price(instrument.tick)}</span></span>
      </div>
      <div className="book">
        <table className="book-side bids" aria-label="Buy orders">
          <thead><tr><th className="num">Orders</th><th className="num">Qty</th><th className="num">Bid</th></tr></thead>
          <tbody>{rows(state.bids).map((l, i) => <BookRow key={l ? l[0] : `b${i}`} level={l} side="bid" largest={largest} onPick={onPickPrice} />)}</tbody>
        </table>
        <table className="book-side asks" aria-label="Sell orders">
          <thead><tr><th>Ask</th><th className="num">Qty</th><th className="num">Orders</th></tr></thead>
          <tbody>{rows(state.asks).map((l, i) => <BookRow key={l ? l[0] : `a${i}`} level={l} side="ask" largest={largest} onPick={onPickPrice} />)}</tbody>
        </table>
      </div>
      <div className="pressure" role="img" aria-label={`Buy quantity ${Math.round(buyShare * 100)}%, sell quantity ${Math.round((1 - buyShare) * 100)}% of the best five levels`}>
        <span className="pressure-bar"><span className="buy" style={{ width: `${buyShare * 100}%` }} /></span>
        <span className="pressure-text small">
          <span className="up">Buy {qty(bidTotal)} ({Math.round(buyShare * 100)}%)</span>
          <span className="down">{qty(askTotal)} ({Math.round((1 - buyShare) * 100)}%) Sell</span>
        </span>
      </div>
      <p className="hint">Click a price to copy it into the order form.</p>
    </div>
  );
}

function rows(levels: Level[]): (Level | null)[] {
  return Array.from({ length: ROWS }, (_, i) => levels[i] ?? null);
}

function BookRow({ level, side, largest, onPick }: { level: Level | null; side: "bid" | "ask"; largest: number; onPick: (p: number) => void }) {
  if (!level) {
    return <tr className="empty-row"><td>{DASH}</td><td>{DASH}</td><td>{DASH}</td></tr>;
  }
  const [levelPrice, quantity, orders] = level;
  const cells = [
    <td key="orders" className="num muted">{orders}</td>,
    <td key="qty" className="num">{qty(quantity)}</td>,
    <td key="price" className={`num price ${side === "bid" ? "up" : "down"}`}>{price(levelPrice)}</td>,
  ];
  const style = { "--fill": `${Math.round((quantity / largest) * 100)}%` } as CSSProperties;
  return (
    <tr className={`level ${side}`} style={style} tabIndex={0} onClick={() => onPick(levelPrice)}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onPick(levelPrice)} aria-label={`${side === "bid" ? "Bid" : "Ask"} ${price(levelPrice)}, ${qty(quantity)} shares`}>
      {side === "bid" ? cells : [...cells].reverse()}
    </tr>
  );
}

function TimeAndSales({ trades }: { trades: Trade[] }) {
  return (
    <div className="card tape-card">
      <div className="card-head"><h3>Time and sales</h3><span className="muted small">Newest first</span></div>
      {trades.length === 0 ? (
        <p className="empty">No trades yet.</p>
      ) : (
        <div className="tape-scroll">
          <table className="tape">
            <thead><tr><th>Time</th><th className="num">Price</th><th className="num">Qty</th><th>Side</th></tr></thead>
            <tbody>
              {trades.map((t) => (
                <tr key={t.id}>
                  <td className="num muted">{clock(t.ts)}</td>
                  <td className={`num ${t.side === "BUY" ? "up" : "down"}`}>{price(t.price)}</td>
                  <td className="num">{qty(t.qty)}</td>
                  <td className="muted">{t.side === "BUY" ? "Buy" : "Sell"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
