import type { Trade } from "../api";
import { clock, price, qty } from "../format";

/** Recent trades for the selected stock, newest first. */
export function TradeTape({ trades }: { trades: Trade[] }) {
  return (
    <section className="panel tape">
      <h2>Recent trades</h2>
      {trades.length === 0 ? (
        <p className="empty">No trades yet.</p>
      ) : (
        <div className="scroll">
          <table>
            <thead>
              <tr>
                <th className="num">Time</th>
                <th className="num">Price</th>
                <th className="num">Quantity</th>
                <th>Taker</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((trade) => (
                <tr key={trade.id}>
                  <td className="num muted">{clock(trade.ts)}</td>
                  <td className={`num ${trade.side === "BUY" ? "up" : "down"}`}>{price(trade.price)}</td>
                  <td className="num">{qty(trade.qty)}</td>
                  <td className="muted">{trade.side === "BUY" ? "Buyer" : "Seller"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
