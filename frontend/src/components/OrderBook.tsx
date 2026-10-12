import type { CSSProperties } from "react";

import type { Instrument, Level, MarketState } from "../api";
import { DASH, price, qty } from "../format";

interface Props {
  instrument: Instrument;
  state: MarketState;
  onPickPrice: (price: number) => void;
}

const ROWS = 5;

/** The five best buy prices and five best sell prices, with the quantity waiting at each. */
export function OrderBook({ instrument, state, onPickPrice }: Props) {
  const largest = Math.max(1, ...state.bids.map((l) => l[1]), ...state.asks.map((l) => l[1]));
  const bestBid = state.bids[0]?.[0];
  const bestAsk = state.asks[0]?.[0];
  const spread = bestBid != null && bestAsk != null ? bestAsk - bestBid : null;

  return (
    <section className="panel book">
      <div className="panel-head">
        <h2>Order book</h2>
        <span className="muted">
          Spread <span className="num">{spread == null ? DASH : price(spread)}</span>, tick <span className="num">{price(instrument.tick)}</span>
        </span>
      </div>
      <div className="book-grid">
        <table className="bids">
          <caption>Buy orders (bids)</caption>
          <thead>
            <tr>
              <th>Orders</th>
              <th>Quantity</th>
              <th className="price">Price</th>
            </tr>
          </thead>
          <tbody>
            {rows(state.bids).map((level, i) => (
              <BookRow key={level ? level[0] : `empty-${i}`} level={level} side="bid" largest={largest} onPick={onPickPrice} />
            ))}
          </tbody>
        </table>
        <table className="asks">
          <caption>Sell orders (asks)</caption>
          <thead>
            <tr>
              <th className="price">Price</th>
              <th>Quantity</th>
              <th>Orders</th>
            </tr>
          </thead>
          <tbody>
            {rows(state.asks).map((level, i) => (
              <BookRow key={level ? level[0] : `empty-${i}`} level={level} side="ask" largest={largest} onPick={onPickPrice} />
            ))}
          </tbody>
        </table>
      </div>
      <p className="hint">Click a row to copy its price into the order form.</p>
    </section>
  );
}

function rows(levels: Level[]): (Level | null)[] {
  return Array.from({ length: ROWS }, (_, i) => levels[i] ?? null);
}

function BookRow({ level, side, largest, onPick }: { level: Level | null; side: "bid" | "ask"; largest: number; onPick: (p: number) => void }) {
  if (!level) {
    return (
      <tr className="empty-row">
        <td>{DASH}</td>
        <td>{DASH}</td>
        <td>{DASH}</td>
      </tr>
    );
  }
  const [levelPrice, quantity, orders] = level;
  const cells = [
    <td key="orders" className="num muted">{orders}</td>,
    <td key="qty" className="num">{qty(quantity)}</td>,
    <td key="price" className={`num price ${side}`}>{price(levelPrice)}</td>,
  ];
  // The bar shows this level's quantity against the largest level on screen.
  const bar = { "--fill": `${Math.round((quantity / largest) * 100)}%` } as CSSProperties;
  return (
    <tr className={`level ${side}`} style={bar} onClick={() => onPick(levelPrice)} tabIndex={0}
      onKeyDown={(event) => event.key === "Enter" && onPick(levelPrice)}>
      {side === "bid" ? cells : [...cells].reverse()}
    </tr>
  );
}
