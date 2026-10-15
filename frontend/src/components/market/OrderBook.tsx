import type { CSSProperties } from "react";

import type { Instrument, Level, Quote, TopOfBook, Trade } from "../../api/types";
import { DASH, clock, price, qty } from "../../lib/format";

interface Props {
  instrument: Instrument;
  quote: Quote | undefined;
  book: TopOfBook | null;
  trades: Trade[];
  now: number;
  onPickPrice: (price: number) => void;
}

/** The real best bid and offer, your orders waiting in the matching engine, and the latest real trades. */
export function MarketDepth({ instrument, quote, book, trades, now, onPickPrice }: Props) {
  return (
    <section className="section" id="depth" aria-labelledby="depth-title">
      <h2 id="depth-title" className="section-title">Order book</h2>
      <div className="depth-grid">
        <div className="depth-column">
          <BestPrices instrument={instrument} quote={quote} now={now} onPickPrice={onPickPrice} />
          <YourOrders book={book} onPickPrice={onPickPrice} />
        </div>
        <TimeAndSales trades={trades} />
      </div>
    </section>
  );
}

function BestPrices({ instrument, quote, now, onPickPrice }: { instrument: Instrument; quote: Quote | undefined; now: number; onPickPrice: (p: number) => void }) {
  const bid = quote?.bid ?? null;
  const ask = quote?.ask ?? null;
  const spread = bid != null && ask != null ? ask - bid : null;
  const age = quote?.polled_at ? Math.max(0, Math.round(now - quote.polled_at)) : null;
  return (
    <div className="card book-card">
      <div className="card-head">
        <h3>Best bid and offer</h3>
        <span className="muted small">
          Spread <span className="num">{spread == null ? DASH : price(spread)}</span> {"·"} tick <span className="num">{price(instrument.tick)}</span>
          {age != null && <> {"·"} {age} s ago</>}
        </span>
      </div>
      <div className="touch">
        <button type="button" className="touch-side bid" disabled={bid == null} onClick={() => bid != null && onPickPrice(bid)}>
          <span className="muted small">Best bid (buyers)</span>
          <span className="num up big-price">{price(bid)}</span>
        </button>
        <button type="button" className="touch-side ask" disabled={ask == null} onClick={() => ask != null && onPickPrice(ask)}>
          <span className="muted small">Best offer (sellers)</span>
          <span className="num down big-price">{price(ask)}</span>
        </button>
      </div>
      <p className="hint">
        Real prices from NSE, through Yahoo Finance. The quantities and the next four levels are sent only to brokers'
        own data feeds, so they are not shown. Click a price to copy it into the order form.
      </p>
    </div>
  );
}

function YourOrders({ book, onPickPrice }: { book: TopOfBook | null; onPickPrice: (p: number) => void }) {
  const bids = book?.your_bids ?? [];
  const asks = book?.your_asks ?? [];
  const largest = Math.max(1, ...bids.map((l) => l[1]), ...asks.map((l) => l[1]));
  return (
    <div className="card book-card">
      <div className="card-head">
        <h3>Your orders in the matching engine</h3>
        <span className="muted small">Price-time priority</span>
      </div>
      {bids.length + asks.length === 0 ? (
        <p className="muted small">
          None waiting. A limit order that cannot trade at once waits here, and fills when NSE trades at its price or better,
          up to the quantity that really traded.
        </p>
      ) : (
        <div className="book">
          <Side levels={bids} side="bid" largest={largest} onPick={onPickPrice} />
          <Side levels={asks} side="ask" largest={largest} onPick={onPickPrice} />
        </div>
      )}
    </div>
  );
}

function Side({ levels, side, largest, onPick }: { levels: Level[]; side: "bid" | "ask"; largest: number; onPick: (p: number) => void }) {
  return (
    <table className={`book-side ${side === "bid" ? "bids" : "asks"}`} aria-label={side === "bid" ? "Your buy orders" : "Your sell orders"}>
      <thead>
        {side === "bid"
          ? <tr><th className="num">Orders</th><th className="num">Qty</th><th className="num">Buy at</th></tr>
          : <tr><th>Sell at</th><th className="num">Qty</th><th className="num">Orders</th></tr>}
      </thead>
      <tbody>
        {levels.length === 0 ? (
          <tr className="empty-row"><td>{DASH}</td><td>{DASH}</td><td>{DASH}</td></tr>
        ) : levels.map(([levelPrice, quantity, orders]) => {
          const cells = [
            <td key="orders" className="num muted">{orders}</td>,
            <td key="qty" className="num">{qty(quantity)}</td>,
            <td key="price" className={`num price ${side === "bid" ? "up" : "down"}`}>{price(levelPrice)}</td>,
          ];
          const style = { "--fill": `${Math.round((quantity / largest) * 100)}%` } as CSSProperties;
          return (
            <tr key={levelPrice} className={`level ${side}`} style={style} tabIndex={0} onClick={() => onPick(levelPrice)}
              onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onPick(levelPrice)}>
              {side === "bid" ? cells : [...cells].reverse()}
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function TimeAndSales({ trades }: { trades: Trade[] }) {
  return (
    <div className="card tape-card">
      <div className="card-head"><h3>Time and sales</h3><span className="muted small">Real NSE trades, newest first</span></div>
      {trades.length === 0 ? (
        <p className="empty">No trades yet. They appear while the market is open.</p>
      ) : (
        <div className="tape-scroll">
          <table className="tape">
            <thead><tr><th>Time</th><th className="num">Price</th><th className="num">Qty</th><th>Side</th></tr></thead>
            <tbody>
              {trades.map((t) => (
                <tr key={t.id}>
                  <td className="num muted">{clock(t.ts)}</td>
                  <td className={`num ${t.side === "BUY" ? "up" : t.side === "SELL" ? "down" : ""}`}>{price(t.price)}</td>
                  <td className="num">{qty(t.qty)}</td>
                  <td className="muted">{t.side === "BUY" ? "Buy" : t.side === "SELL" ? "Sell" : DASH}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="hint">Each row is the volume traded since the previous price update. Buy or sell is by the tick test: a rise is a buy.</p>
    </div>
  );
}
