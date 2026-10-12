import { useEffect, useState, type FormEvent } from "react";

import { api, type Instrument, type MarketState, type Order, type OrderType, type Portfolio, type Product, type Side } from "../api";
import { money, price, qty as formatQty, reasonText } from "../format";

interface Props {
  instrument: Instrument;
  state: MarketState;
  portfolio: Portfolio | null;
  marginDivisor: number;
  /** Set when the user clicks a price in the order book. */
  pickedPrice: { price: number; at: number } | null;
  onPlaced: () => void;
}

export function OrderTicket({ instrument, state, portfolio, marginDivisor, pickedPrice, onPlaced }: Props) {
  const [side, setSide] = useState<Side>("BUY");
  const [product, setProduct] = useState<Product>("CNC");
  const [type, setType] = useState<OrderType>("LIMIT");
  const [quantity, setQuantity] = useState("10");
  const [limit, setLimit] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);

  // Start each stock at its last price; a click in the order book overrides it.
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
  let requirement = "";
  if (orderValue != null) {
    if (product === "MIS") requirement = `Margin needed: up to ${money(Math.floor(orderValue / marginDivisor))} (${100 / marginDivisor}% of the value)`;
    else if (side === "BUY") requirement = `Cash needed: ${money(orderValue)}`;
    else requirement = `Shares needed: ${formatQty(qtyValue)} (you can sell ${formatQty(freeShares)})`;
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!validQty || !validPrice) return;
    setBusy(true);
    setResult(null);
    try {
      const order = await api.placeOrder({
        symbol: instrument.symbol, side, type, product, qty: qtyValue,
        price: type === "LIMIT" ? limitPaise : undefined,
      });
      setResult(describe(order));
      onPlaced();
    } catch (error) {
      setResult({ ok: false, text: error instanceof Error ? error.message : "The order could not be sent." });
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel ticket">
      <h2>Place order: {instrument.symbol}</h2>
      <form onSubmit={submit} noValidate>
        <Toggle label="Side" value={side} onChange={setSide} options={[["BUY", "Buy"], ["SELL", "Sell"]]} tone />
        <Toggle label="Product" value={product} onChange={setProduct} options={[["CNC", "Delivery"], ["MIS", "Intraday"]]} />
        <Toggle label="Order type" value={type} onChange={setType} options={[["LIMIT", "Limit"], ["MARKET", "Market"]]} />

        <label>
          Quantity
          <input type="number" min={1} step={1} inputMode="numeric" value={quantity} onChange={(e) => setQuantity(e.target.value)} />
        </label>
        <label>
          Price (rupees)
          <input type="number" step={instrument.tick / 100} min={0}
            value={type === "MARKET" ? "" : limit} placeholder={type === "MARKET" ? "Best available price" : ""}
            disabled={type === "MARKET"} onChange={(e) => setLimit(e.target.value)} />
        </label>
        <p className="hint">
          Allowed: {price(instrument.lower_band)} to {price(instrument.upper_band)}, in steps of {price(instrument.tick)}.
        </p>
        <p className="requirement">{requirement || " "}</p>

        <button type="submit" className={side === "BUY" ? "primary buy" : "primary sell"} disabled={busy || !validQty || !validPrice}>
          {side === "BUY" ? "Buy" : "Sell"} {validQty ? formatQty(qtyValue) : ""} {instrument.symbol}
        </button>
      </form>
      {result && <p className={result.ok ? "result ok" : "result bad"} role="status">{result.text}</p>}
    </section>
  );
}

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

function Toggle<T extends string>({ label, value, onChange, options, tone }: {
  label: string; value: T; onChange: (value: T) => void; options: [T, string][]; tone?: boolean;
}) {
  return (
    <div className="toggle" role="group" aria-label={label}>
      {options.map(([option, text]) => (
        <button key={option} type="button" aria-pressed={value === option}
          className={`${value === option ? "on" : ""} ${tone ? option.toLowerCase() : ""}`} onClick={() => onChange(option)}>
          {text}
        </button>
      ))}
    </div>
  );
}
