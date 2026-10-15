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

/** A price change with an explicit sign: "+1.40", "\u22121.80". */
export function signedPrice(paise: number): string {
  if (paise === 0) return "0.00";
  return (paise > 0 ? "+" : "\u2212") + price2.format(Math.abs(paise) / 100);
}

export function qty(value: number): string {
  return whole.format(value);
}

export function percentChange(current: number | null | undefined, base: number | null | undefined): string {
  if (current == null || !base) return DASH;
  const change = ((current - base) / base) * 100;
  return (change > 0 ? "+" : change < 0 ? "−" : "") + Math.abs(change).toFixed(2) + "%";
}

/** Indian grouping for big numbers: 2,34,56,789 -> "2.35 Cr", 4,56,789 -> "4.57 L". */
export function compact(value: number | null | undefined): string {
  if (value == null) return DASH;
  if (value >= 1e7) return `${(value / 1e7).toFixed(2)} Cr`;
  if (value >= 1e5) return `${(value / 1e5).toFixed(2)} L`;
  return whole.format(value);
}

/** Market value in rupees: "₹15,98,185 Cr". */
export function crores(rupees: number | null | undefined): string {
  if (rupees == null) return DASH;
  return `₹${whole.format(Math.round(rupees / 1e7))} Cr`;
}

/** "up", "down" or "flat", used to pick a colour class. */
export function direction(value: number): "up" | "down" | "flat" {
  return value > 0 ? "up" : value < 0 ? "down" : "flat";
}

/** Times are shown in Indian time wherever the browser is. */
const IST = "Asia/Kolkata";

export function clock(epochSeconds: number): string {
  return new Date(epochSeconds * 1000).toLocaleTimeString("en-IN", { hour12: false, timeZone: IST });
}

/** "9:15 am" */
export function shortTime(epochSeconds: number): string {
  return new Date(epochSeconds * 1000).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit", hour12: true, timeZone: IST });
}

/** "Fri 16 Oct" */
export function shortDay(epochSeconds: number): string {
  return new Date(epochSeconds * 1000).toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short", timeZone: IST });
}

/** "16 Oct" or "16 Oct 2025" for chart axes. */
export function axisDate(epochSeconds: number, withYear: boolean): string {
  return new Date(epochSeconds * 1000).toLocaleDateString("en-IN", { day: "numeric", month: "short", ...(withYear ? { year: "numeric" } : {}), timeZone: IST });
}

/** "just now", "12 min ago", "3 h ago", "2 days ago". */
export function timeAgo(epochSeconds: number, now = Date.now() / 1000): string {
  const minutes = Math.floor((now - epochSeconds) / 60);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.floor(hours / 24);
  return days === 1 ? "1 day ago" : `${days} days ago`;
}

export function dateTime(epochSeconds: number): string {
  return new Date(epochSeconds * 1000).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hour12: false, timeZone: IST });
}

/** "RELIANCE INDUSTRIES LIMITED" -> "Reliance Industries Limited"; short words like "HDFC" or "ITC" stay as they are. */
export function companyName(name: string): string {
  if (name !== name.toUpperCase()) return name;
  return name.split(" ").map((w) => (w.length <= 4 && !["AND", "OF", "THE", "LTD", "LTD."].includes(w) && /^[A-Z&]+$/.test(w) ? w
    : w.charAt(0) + w.slice(1).toLowerCase())).join(" ").replace(/\bAnd\b/g, "and").replace(/\bOf\b/g, "of");
}

export function longDate(iso: string): string {
  return new Date(iso + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

const REASONS: Record<string, string> = {
  INSUFFICIENT_FUNDS: "Not enough available cash for this order and its charges.",
  INSUFFICIENT_SHARES: "You do not hold enough shares to sell for delivery.",
  OUTSIDE_PRICE_BAND: "The price is outside today's price band for this stock.",
  BAD_TICK: "The price is not a multiple of the tick size.",
  BAD_QUANTITY: "Quantity must be at least 1.",
  ORDER_SIZE_EXCEEDED: "The quantity is above the maximum order size.",
  PRICE_REQUIRED: "A limit order needs a price.",
  UNKNOWN_SYMBOL: "This stock is not listed on NSE's cash market.",
  NO_LIVE_PRICE: "No live price has arrived for this stock yet. Try again in a few seconds.",
  SELF_TRADE: "This would trade with your own open order on the other side. Cancel that order first.",
  INTRADAY_CLOSED: "Intraday orders can be placed from 9:15 am to 3:20 pm; after that they may only close a position.",
  INTRADAY_NOT_ALLOWED: "This stock is in the trade-for-trade (BE) segment: delivery only, no intraday.",
  NO_LIQUIDITY: "There was not enough on the other side to fill it completely.",
  USER_CANCELLED: "Cancelled by you.",
  EXPIRED: "Expired at the close: orders are valid for the day.",
  AUTO_SQUARE_OFF: "Closed by the 3:20 pm intraday square-off.",
};

export function reasonText(code: string | null): string {
  return code ? REASONS[code] ?? code : "";
}
