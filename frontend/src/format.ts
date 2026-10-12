// Display helpers. The API sends money as integer paise; these turn it into rupee text.

const price2 = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const whole = new Intl.NumberFormat("en-IN");

export const DASH = "—";

/** 117940 -> "1,179.40" */
export function price(paise: number | null | undefined): string {
  return paise == null ? DASH : price2.format(paise / 100);
}

/** 98820600 -> "₹9,88,206.00" */
export function money(paise: number | null | undefined): string {
  if (paise == null) return DASH;
  return (paise < 0 ? "−₹" : "₹") + price2.format(Math.abs(paise) / 100);
}

/** Profit and loss with an explicit sign. */
export function signedMoney(paise: number): string {
  if (paise === 0) return "₹0.00";
  return (paise > 0 ? "+₹" : "−₹") + price2.format(Math.abs(paise) / 100);
}

export function qty(value: number): string {
  return whole.format(value);
}

export function percentChange(current: number | null, base: number): string {
  if (current == null) return DASH;
  const change = ((current - base) / base) * 100;
  return (change > 0 ? "+" : change < 0 ? "−" : "") + Math.abs(change).toFixed(2) + "%";
}

/** "up", "down" or "flat", used to pick a colour class. */
export function direction(value: number): "up" | "down" | "flat" {
  return value > 0 ? "up" : value < 0 ? "down" : "flat";
}

export function clock(epochSeconds: number): string {
  return new Date(epochSeconds * 1000).toLocaleTimeString("en-IN", { hour12: false });
}

export function longDate(iso: string): string {
  return new Date(iso + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

const REASONS: Record<string, string> = {
  INSUFFICIENT_FUNDS: "Not enough available cash for this order.",
  INSUFFICIENT_SHARES: "You do not hold enough shares to sell for delivery.",
  OUTSIDE_PRICE_BAND: "The price is outside today's price band for this stock.",
  BAD_TICK: "The price is not a multiple of the tick size.",
  BAD_QUANTITY: "Quantity must be at least 1.",
  ORDER_SIZE_EXCEEDED: "The quantity is above the maximum order size.",
  PRICE_REQUIRED: "A limit order needs a price.",
  UNKNOWN_SYMBOL: "This stock is not available in the simulator.",
  NO_LIQUIDITY: "There were not enough orders on the other side to fill it completely.",
  USER_CANCELLED: "Cancelled by you.",
};

export function reasonText(code: string | null): string {
  return code ? REASONS[code] ?? code : "";
}
