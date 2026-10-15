import { forwardRef, useEffect, useState, type FormEvent } from "react";

import { api } from "../../api/client";
import type { Instrument, MarketState, Order, OrderType, Portfolio, Product, Side } from "../../api/types";
import { money, price, qty as formatQty, reasonText } from "../../lib/format";
import { Segmented } from "../ui/Segmented";

interface Props {
  instrument: Instrument;
  state: MarketState;
  portfolio: Portfolio | null;
  marginDivisor: number;
  side: Side;
  onSideChange: (side: Side) => void;
  /** Set when a price in the order book is clicked. */
  pickedPrice: { price: number; at: number } | null;
  onPlaced: () => void;
  /** Clicking Delivery or Intraday opens that recommendation pop-up. */
  onDeliveryClick: () => void;
  onIntradayClick: () => void;
}

export const OrderTicket = forwardRef<HTMLElement, Props>(function OrderTicket(
  { instrument, state, portfolio, marginDivisor, side, onSideChange, pickedPrice, onPlaced, onDeliveryClick, onIntradayClick }, ref,
) {
  const [product, setProduct] = useState<Product>("CNC");
  const [type, setType] = useState<OrderType>("LIMIT");
  const [quantity, setQuantity] = useState("10");
  const [limit, setLimit] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);

  // Each stock starts at its last price; clicking the order book overrides it.
  useEffect(() => {
    setLimit(((state.ltp ?? instrument.prev_close) / 100).toFixed(2));
    setResult(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [instrument.symbol]);
  useEffect(() => {
    if (pickedPrice) {
      setLimit((pickedPrice.price / 100).toFixed(2));
      setType("LIMIT");
    }
  }, [pickedPrice]);

  const qtyValue = Number.parseInt(quantity, 10);
  const limitPaise = Math.round(Number.parseFloat(limit) * 100);
  const validQty = Number.isInteger(qtyValue) && qtyValue > 0;
  const validPrice = type === "MARKET" || (Number.isFinite(limitPaise) && limitPaise > 0);
  // A market order is reserved at the upper band, the worst price it could trade at.
  const worstPrice = type === "LIMIT" ? limitPaise : instrument.upper_band;
  const orderValue = validQty && validPrice ? qtyValue * worstPrice : null;
  const held = portfolio?.holdings.find((h) => h.symbol === instrument.symbol);
  const freeShares = held ? held.qty - held.blocked : 0;

  let requirement = " ";
  if (orderValue != null) {
    if (product === "MIS") requirement = `Margin needed: up to ${money(Math.floor(orderValue / marginDivisor))}`;
    else if (side === "BUY") requirement = `Cash needed: ${money(orderValue)}`;
    else requirement = `Shares needed: ${formatQty(qtyValue)} (you can sell ${formatQty(freeShares)})`;
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!validQty || !validPrice) return;
    setBusy(true);
    setResult(null);
    try {
      const order = await api.placeOrder({ symbol: instrument.symbol, side, type, product, qty: qtyValue, price: type === "LIMIT" ? limitPaise : undefined });
      setResult(describe(order));
      onPlaced();
    } catch (error) {
      setResult({ ok: false, text: error instanceof Error ? error.message : "The order could not be sent." });
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card ticket" ref={ref} aria-labelledby="ticket-title" tabIndex={-1}>
      <h2 id="ticket-title" className="card-title">Trade {instrument.symbol}</h2>
      <form onSubmit={submit} noValidate>
        <Segmented label="Side" value={side} onSelect={onSideChange} options={[["BUY", "Buy"], ["SELL", "Sell"]]} sideColours />
        <Segmented label="Product" value={product} options={[["CNC", "Delivery"], ["MIS", "Intraday"]]}
          onSelect={(next) => {
            setProduct(next);
            if (next === "CNC") onDeliveryClick();
            else onIntradayClick();
          }} />
        <button type="button" className="link-button" onClick={product === "CNC" ? onDeliveryClick : onIntradayClick}>
          {product === "CNC" ? "Which stocks should I buy?" : "What should I trade right now?"}
        </button>
        <Segmented label="Order type" value={type} onSelect={setType} options={[["LIMIT", "Limit"], ["MARKET", "Market"]]} />
        <div className="ticket-fields">
          <label className="field">
            <span>Quantity</span>
            <input type="number" min={1} step={1} inputMode="numeric" value={quantity} onChange={(e) => setQuantity(e.target.value)} />
          </label>
          <label className="field">
            <span>Price</span>
            <input type="number" step={instrument.tick / 100} min={0} value={type === "MARKET" ? "" : limit}
              placeholder={type === "MARKET" ? "Market" : ""} disabled={type === "MARKET"} onChange={(e) => setLimit(e.target.value)} />
          </label>
        </div>
        <p className="hint">Allowed {price(instrument.lower_band)} to {price(instrument.upper_band)}, in steps of {price(instrument.tick)}.</p>
        <p className="requirement">{requirement}</p>
        <button type="submit" className={`button block ${side === "BUY" ? "buy" : "sell"}`} disabled={busy || !validQty || !validPrice}>
          {busy ? "Sending" : `${side === "BUY" ? "Buy" : "Sell"} ${validQty ? formatQty(qtyValue) : ""} ${instrument.symbol}`}
        </button>
      </form>
      {result && <p className={`result ${result.ok ? "up" : "down"}`} role="status">{result.text}</p>}
    </section>
  );
});

function describe(order: Order): { ok: boolean; text: string } {
  const filled = order.filled > 0 ? `${formatQty(order.filled)} filled at an average of ${price(order.avg_price)}` : "";
  switch (order.status) {
    case "FILLED":
      return { ok: true, text: `Order ${order.id} filled: ${filled}.` };
    case "PARTIALLY_FILLED":
      return { ok: true, text: `Order ${order.id}: ${filled}; ${formatQty(order.remaining)} waiting in the book.` };
    case "OPEN":
      return { ok: true, text: `Order ${order.id} is waiting in the book at ${price(order.price)}.` };
    case "CANCELLED":
      return { ok: order.filled > 0, text: `Order ${order.id}: ${filled ? filled + "; the rest was cancelled. " : "cancelled. "}${reasonText(order.reason)}` };
    default:
      return { ok: false, text: `Order rejected. ${reasonText(order.reason)}` };
  }
}
