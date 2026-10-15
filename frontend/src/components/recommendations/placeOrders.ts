import { api } from "../../api/client";
import type { Product, Side } from "../../api/types";
import { price, qty, reasonText } from "../../lib/format";

export interface OrderOutcome {
  symbol: string;
  ok: boolean;
  text: string;
}

/** Sends market orders one after another and reports each result as it arrives. */
export async function placeMarketOrders(items: { symbol: string; side: Side; qty: number }[], product: Product,
                                        onProgress: (done: OrderOutcome[]) => void): Promise<OrderOutcome[]> {
  const done: OrderOutcome[] = [];
  for (const item of items) {
    const verb = item.side === "BUY" ? "Bought" : "Sold";
    try {
      const order = await api.placeOrder({ symbol: item.symbol, side: item.side, type: "MARKET", product, qty: item.qty });
      if (order.status === "FILLED") {
        done.push({ symbol: item.symbol, ok: true, text: `${verb} ${qty(order.filled)} at an average of ${price(order.avg_price)}.` });
      } else if (order.filled > 0) {
        done.push({ symbol: item.symbol, ok: true, text: `${verb} ${qty(order.filled)} of ${qty(order.qty)}. ${reasonText(order.reason)}` });
      } else {
        done.push({ symbol: item.symbol, ok: false, text: `Not placed. ${reasonText(order.reason)}` });
      }
    } catch (err) {
      done.push({ symbol: item.symbol, ok: false, text: err instanceof Error ? err.message : "The order could not be sent." });
    }
    onProgress([...done]);
  }
  return done;
}
