// The same charges the server applies on each fill (backend/app/charges.py), for an estimate before ordering.
import type { Product, Side } from "../api/types";

const STT: Record<string, number> = { "CNC-BUY": 0.001, "CNC-SELL": 0.001, "MIS-BUY": 0, "MIS-SELL": 0.00025 };
const STAMP: Record<string, number> = { "CNC-BUY": 0.00015, "MIS-BUY": 0.00003 };

/** Brokerage, taxes and fees in paise for an order worth `value` paise. */
export function estimateCharges(product: Product, side: Side, value: number): number {
  const key = `${product}-${side}`;
  const brokerage = product === "MIS" ? Math.min(Math.round(value * 0.0003), 20_00) : 0;
  const exchange = Math.round(value * 0.0000297);
  const sebi = Math.round(value * 0.000001);
  const gst = Math.round((brokerage + exchange + sebi) * 0.18);
  return brokerage + Math.round(value * (STT[key] ?? 0)) + exchange + sebi + Math.round(value * (STAMP[key] ?? 0)) + gst;
}
