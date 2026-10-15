import type { Status } from "../../api/types";
import { clock, shortDay, shortTime } from "../../lib/format";

/** "Market open · 10:42:13 IST", or when the market opens next; the dot shows the live feed's health. */
export function MarketStatus({ status, connected, now }: { status: Status | null; connected: boolean; now: number }) {
  if (!status) return <div className="session"><span className="status-dot off" aria-hidden="true" /><span>Connecting</span></div>;
  const { session, feed } = status;
  const lastPrice = feed.last_tick ? Math.max(0, Math.round(now - feed.last_tick)) : null;
  const streaming = connected && status.live && feed.stream_connected;
  let text: string;
  if (!connected) text = "Reconnecting to the server";
  else if (session.state === "OPEN") text = `${session.label} · ${clock(now)} IST`;
  else if (session.state === "PRE_OPEN") text = `Pre-open · trading starts ${shortTime(session.opens_at)}`;
  else text = `${session.label} · opens ${sameDay(session.opens_at, now) ? "" : shortDay(session.opens_at) + ", "}${shortTime(session.opens_at)}`;
  const tone = !connected || (status.live && !feed.stream_connected) ? "off" : session.state === "OPEN" && streaming ? "live" : "paused";
  const title = !status.live
    ? "Live prices are switched off (ORDERBOOK_LIVE=0)."
    : `Live prices from Yahoo Finance, about 2 seconds behind NSE. ${feed.stream_connected ? "Stream connected" : "Stream reconnecting"}${lastPrice != null ? `; last price ${lastPrice} s ago` : ""}.${feed.quote_error ? ` Quotes: ${feed.quote_error}` : ""}`;
  return (
    <div className="session" title={title}>
      <span className={`status-dot ${tone}`} aria-hidden="true" />
      <span>{text}</span>
    </div>
  );
}

function sameDay(a: number, b: number) {
  return shortDay(a) === shortDay(b);
}
