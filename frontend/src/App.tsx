import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api } from "./api/client";
import type { Recommendation, Side } from "./api/types";
import { Footer } from "./components/layout/Footer";
import { MarketStrip } from "./components/layout/MarketStrip";
import { SectionNav } from "./components/layout/SectionNav";
import { TopBar } from "./components/layout/TopBar";
import { Movers } from "./components/market/Movers";
import { MarketDepth } from "./components/market/OrderBook";
import { NewsPanel } from "./components/news/News";
import { KeyStats } from "./components/quote/KeyStats";
import { PriceChart } from "./components/quote/PriceChart";
import { QuoteHeader } from "./components/quote/QuoteHeader";
import { Watchlist } from "./components/quote/Watchlist";
import { WhyMoved } from "./components/quote/WhyMoved";
import { DeliveryModal } from "./components/recommendations/DeliveryModal";
import { IntradayModal } from "./components/recommendations/IntradayModal";
import { RecommendationsPanel } from "./components/recommendations/RecommendationsPanel";
import { AccountSummary } from "./components/trading/AccountSummary";
import { AccountTabs } from "./components/trading/AccountTabs";
import { OrderTicket } from "./components/trading/OrderTicket";
import { useAccount } from "./hooks/useAccount";
import { instrumentOf, useInstrument } from "./hooks/useInstrument";
import { useLiveMarket } from "./hooks/useLiveMarket";
import { useNow } from "./hooks/useNow";
import { useOrderBook } from "./hooks/useOrderBook";
import { useSparklines } from "./hooks/useSparklines";
import { useSymbols } from "./hooks/useSymbols";
import { useTheme } from "./hooks/useTheme";
import { useWatchlist } from "./hooks/useWatchlist";
import { companyName } from "./lib/format";

type Dialog = "delivery" | "intraday" | null;

const INDICES = ["NIFTY 50", "SENSEX", "NIFTY BANK"];

export function App() {
  const { list, error: listError } = useSymbols();
  const { watchlist, toggle } = useWatchlist(list?.watchlist);
  const [theme, toggleTheme] = useTheme();
  const now = useNow();
  const [selected, setSelected] = useState("");
  const [side, setSide] = useState<Side>("BUY");
  const [pickedPrice, setPickedPrice] = useState<{ price: number; at: number } | null>(null);
  const [dialog, setDialog] = useState<Dialog>(null);
  const [following, setFollowing] = useState<string[]>([]);
  const [lastDelivery, setLastDelivery] = useState<Recommendation | null>(null);
  const [notice, setNotice] = useState("");
  const [booked, setBooked] = useState(0); // changes after each order, so "your orders" refreshes at once
  const [whyDate, setWhyDate] = useState<string | null>(null);
  const ticket = useRef<HTMLElement>(null);

  const symbol = selected || watchlist[0] || "RELIANCE";
  useEffect(() => setWhyDate(null), [symbol]);
  const explainDay = (date: string | null) => {
    setWhyDate(date);
    window.setTimeout(() => document.getElementById("why")?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
  };
  const { portfolio, orders, refresh } = useAccount("demo");
  const mine = useMemo(() => {
    const out = new Set<string>();
    portfolio?.holdings.forEach((h) => out.add(h.symbol));
    portfolio?.intraday.forEach((p) => out.add(p.symbol));
    orders.filter((o) => o.status === "OPEN" || o.status === "PARTIALLY_FILLED").forEach((o) => out.add(o.symbol));
    return [...out];
  }, [portfolio, orders]);
  const live = useLiveMarket([symbol, ...watchlist, ...mine, ...following]);
  const { detail, error: stockError } = useInstrument(symbol);
  const sparklines = useSparklines(watchlist);
  const book = useOrderBook(symbol, booked);
  const names = useMemo(() => new Map((list?.symbols ?? []).map(([s, n]) => [s, companyName(n)])), [list]);
  const rows = useMemo(() => new Map((list?.symbols ?? []).map((row) => [row[0], row])), [list]);
  const row = rows.get(symbol);
  const instrument = detail ?? (row && list ? instrumentOf(row, list.data_date) : null);
  const follow = useCallback((symbols: string[]) => setFollowing(symbols), []);

  const select = (next: string) => {
    setSelected(next);
    setNotice("");
  };

  const placed = () => {
    refresh();
    setBooked((n) => n + 1);
  };

  const act = async (action: () => Promise<unknown>) => {
    try {
      await action();
      setNotice("");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Something went wrong.");
    }
    placed();
  };

  const startTrade = (next: Side) => {
    setSide(next);
    ticket.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    ticket.current?.focus({ preventScroll: true });
  };

  const quote = live.quotes[symbol] ?? detail?.quote;
  const quotes = useMemo(() => (detail && !live.quotes[detail.symbol] ? { ...live.quotes, [detail.symbol]: detail.quote } : live.quotes), [live.quotes, detail]);
  const session = live.status?.session ?? null;
  const marginDivisor = live.status?.margin_divisor ?? 5;

  if (!list || !instrument) {
    return <p className="loading">{listError || stockError || (live.connected ? "Loading market data." : "Connecting to the server.")}</p>;
  }

  return (
    <>
      <a className="skip-link" href="#main">Skip to content</a>
      <TopBar symbols={list.symbols} quotes={quotes} watchlist={watchlist} connected={live.connected} status={live.status} now={now}
        portfolio={portfolio} theme={theme} onToggleTheme={toggleTheme} onSelect={select} />
      <MarketStrip indices={live.indices} indexOrder={INDICES} watchlist={watchlist} quotes={quotes} sparklines={sparklines}
        selected={symbol} onSelect={select} />
      {notice && <p className="notice container" role="alert">{notice}</p>}

      <div className="container page">
        <SectionNav />
        <main id="main" className="main-col">
          <QuoteHeader instrument={instrument} quote={quote} session={session} watched={watchlist.includes(symbol)}
            onToggleWatch={() => toggle(symbol)} onTrade={startTrade} onWhy={() => explainDay(null)} />
          <PriceChart symbol={symbol} quote={quote} onPickDay={explainDay} />
          <WhyMoved symbol={symbol} date={whyDate} onDate={setWhyDate} onOpenStock={select} />
          <KeyStats instrument={instrument} quote={quote} />
          <MarketDepth instrument={instrument} quote={quote} book={book} trades={live.tape[symbol] ?? []} now={now}
            onPickPrice={(p) => setPickedPrice({ price: p, at: Date.now() })} />
          <NewsPanel symbol={symbol} company={quote?.name ?? names.get(symbol) ?? symbol} />
          <RecommendationsPanel watchlist={watchlist} portfolio={portfolio} lastDelivery={lastDelivery}
            onOpenDelivery={() => setDialog("delivery")} onOpenIntraday={() => setDialog("intraday")} />
          <AccountTabs portfolio={portfolio} orders={orders} marketOpen={session?.state === "OPEN"}
            onCancel={(id) => act(() => api.cancelOrder(id))} onSquareOff={() => act(() => api.squareOff("demo"))} onSelect={select} />
          <Watchlist watchlist={watchlist} names={names} quotes={quotes} sparklines={sparklines} selected={symbol}
            onSelect={select} onRemove={toggle} />
        </main>
        <aside className="rail" aria-label="Trade and account">
          <OrderTicket ref={ticket} instrument={instrument} quote={quote} session={session} portfolio={portfolio} marginDivisor={marginDivisor}
            side={side} onSideChange={setSide} pickedPrice={pickedPrice} onPlaced={placed}
            onDeliveryClick={() => setDialog("delivery")} onIntradayClick={() => setDialog("intraday")} />
          <AccountSummary portfolio={portfolio} />
          <Movers symbols={watchlist} names={names} quotes={quotes} sparklines={sparklines} onSelect={select} />
        </aside>
      </div>

      <Footer dataDate={list.data_date} />

      <DeliveryModal open={dialog === "delivery"} onClose={() => setDialog(null)} symbols={list.symbols} names={names} quotes={quotes}
        watchlist={watchlist} portfolio={portfolio} preselect={symbol} onFollow={follow} onOrdersPlaced={placed} onResult={setLastDelivery} />
      <IntradayModal open={dialog === "intraday"} onClose={() => setDialog(null)} symbols={list.symbols} names={names} quotes={quotes}
        watchlist={watchlist} portfolio={portfolio} preselect={symbol} marginDivisor={marginDivisor} onFollow={follow} onOrdersPlaced={placed} />
    </>
  );
}
