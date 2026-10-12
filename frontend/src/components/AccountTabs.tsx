import { useState } from "react";

import type { Order, Portfolio } from "../api";
import { clock, direction, money, price, qty, reasonText, signedMoney } from "../format";

interface Props {
  portfolio: Portfolio | null;
  orders: Order[];
  onCancel: (id: number) => void;
  onSquareOff: () => void;
}

type Tab = "positions" | "open" | "history" | "funds";

const STATUS_TEXT: Record<Order["status"], string> = {
  PENDING: "Pending", OPEN: "Open", PARTIALLY_FILLED: "Partly filled", FILLED: "Filled", CANCELLED: "Cancelled", REJECTED: "Rejected",
};

export function AccountTabs({ portfolio, orders, onCancel, onSquareOff }: Props) {
  const [tab, setTab] = useState<Tab>("positions");
  const open = orders.filter((o) => o.status === "OPEN" || o.status === "PARTIALLY_FILLED");
  const positions = portfolio ? portfolio.holdings.length + portfolio.intraday.length : 0;
  const tabs: [Tab, string][] = [
    ["positions", `Positions (${positions})`],
    ["open", `Open orders (${open.length})`],
    ["history", "Order history"],
    ["funds", "Funds"],
  ];

  return (
    <section className="panel account">
      <div className="tabs" role="tablist">
        {tabs.map(([id, label]) => (
          <button key={id} role="tab" aria-selected={tab === id} className={tab === id ? "on" : ""} onClick={() => setTab(id)}>
            {label}
          </button>
        ))}
      </div>
      <div className="scroll">
        {tab === "positions" && <Positions portfolio={portfolio} onSquareOff={onSquareOff} />}
        {tab === "open" && <OrdersTable orders={open} onCancel={onCancel} empty="No open orders." />}
        {tab === "history" && <OrdersTable orders={orders} empty="No orders yet." />}
        {tab === "funds" && <Funds portfolio={portfolio} />}
      </div>
    </section>
  );
}

function Positions({ portfolio, onSquareOff }: { portfolio: Portfolio | null; onSquareOff: () => void }) {
  if (!portfolio || portfolio.holdings.length + portfolio.intraday.length === 0) {
    return <p className="empty">No positions. Place an order to get started.</p>;
  }
  return (
    <>
      {portfolio.holdings.length > 0 && (
        <table>
          <caption>Delivery holdings</caption>
          <thead>
            <tr><th>Stock</th><th className="num">Quantity</th><th className="num">Average price</th><th className="num">Last price</th><th className="num">Value</th><th className="num">Profit / loss</th></tr>
          </thead>
          <tbody>
            {portfolio.holdings.map((h) => (
              <tr key={h.symbol}>
                <td>{h.symbol}</td>
                <td className="num">{qty(h.qty)}</td>
                <td className="num">{price(h.avg_price)}</td>
                <td className="num">{price(h.ltp)}</td>
                <td className="num">{money(h.value)}</td>
                <td className={`num ${direction(h.unrealised_pnl)}`}>{signedMoney(h.unrealised_pnl)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {portfolio.intraday.length > 0 && (
        <>
          <table>
            <caption>Intraday positions</caption>
            <thead>
              <tr><th>Stock</th><th className="num">Position</th><th className="num">Average price</th><th className="num">Last price</th><th className="num">Margin blocked</th><th className="num">Profit / loss</th></tr>
            </thead>
            <tbody>
              {portfolio.intraday.map((p) => (
                <tr key={p.symbol}>
                  <td>{p.symbol}</td>
                  <td className="num">{p.qty > 0 ? "Long" : "Short"} {qty(Math.abs(p.qty))}</td>
                  <td className="num">{price(p.avg_price)}</td>
                  <td className="num">{price(p.ltp)}</td>
                  <td className="num">{money(p.margin)}</td>
                  <td className={`num ${direction(p.unrealised_pnl)}`}>{signedMoney(p.unrealised_pnl)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <button className="ghost" onClick={onSquareOff}>Square off all intraday positions</button>
        </>
      )}
    </>
  );
}

function OrdersTable({ orders, onCancel, empty }: { orders: Order[]; onCancel?: (id: number) => void; empty: string }) {
  if (orders.length === 0) return <p className="empty">{empty}</p>;
  return (
    <table>
      <thead>
        <tr>
          <th className="num">Time</th><th>Stock</th><th>Side</th><th>Product</th><th>Type</th><th className="num">Quantity</th><th className="num">Filled</th>
          <th className="num">Price</th><th className="num">Average fill</th><th>Status</th>{onCancel && <th><span className="sr-only">Action</span></th>}
        </tr>
      </thead>
      <tbody>
        {orders.map((o) => (
          <tr key={o.id}>
            <td className="num muted">{clock(o.created_at)}</td>
            <td>{o.symbol}</td>
            <td className={o.side === "BUY" ? "up" : "down"}>{o.side === "BUY" ? "Buy" : "Sell"}</td>
            <td>{o.product === "CNC" ? "Delivery" : "Intraday"}</td>
            <td>{o.type === "LIMIT" ? "Limit" : "Market"}</td>
            <td className="num">{qty(o.qty)}</td>
            <td className="num">{qty(o.filled)}</td>
            <td className="num">{o.price == null ? "Market" : price(o.price)}</td>
            <td className="num">{price(o.avg_price)}</td>
            <td title={reasonText(o.reason)}>
              {STATUS_TEXT[o.status]}
              {o.status === "REJECTED" && o.reason ? <span className="muted">: {reasonText(o.reason)}</span> : null}
            </td>
            {onCancel && <td><button className="ghost small" onClick={() => onCancel(o.id)}>Cancel</button></td>}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Funds({ portfolio }: { portfolio: Portfolio | null }) {
  if (!portfolio) return <p className="empty">Loading.</p>;
  const rows: [string, string, string][] = [
    ["Cash", money(portfolio.cash), "Money in the account, including amounts that are blocked."],
    ["Blocked for open orders", money(portfolio.blocked_for_orders), "Reserved when an order is placed; released when it fills or is cancelled."],
    ["Blocked as intraday margin", money(portfolio.intraday_margin), "20% of the value of open intraday positions."],
    ["Available cash", money(portfolio.available), "Cash minus both blocked amounts. New orders are checked against this."],
    ["Value of holdings", money(portfolio.holdings_value), "Delivery holdings at the last traded price."],
    ["Realised profit / loss", signedMoney(portfolio.realised_pnl), "From shares sold and intraday positions closed."],
    ["Unrealised profit / loss", signedMoney(portfolio.unrealised_pnl), "On positions that are still open."],
    ["Account value", money(portfolio.equity), "Cash plus holdings plus open intraday profit or loss."],
  ];
  return (
    <table className="funds-table">
      <tbody>
        {rows.map(([label, value, note]) => (
          <tr key={label}>
            <th scope="row">{label}</th>
            <td className="num">{value}</td>
            <td className="muted">{note}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
