import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api } from "./api/client";
import type { Recommendation, Side } from "./api/types";
import { Dashboard } from "./components/layout/Dashboard";
import { Footer } from "./components/layout/Footer";
import { IndicesBar } from "./components/layout/IndicesBar";
import { SectionNav } from "./components/layout/SectionNav";
import { TopBar } from "./components/layout/TopBar";
import { GlobalMarkets } from "./components/market/GlobalMarkets";
import { Movers } from "./components/market/Movers";
import { MarketDepth } from "./components/market/OrderBook";
import { NewsPanel } from "./components/news/News";
import { KeyStats } from "./components/quote/KeyStats";
import { PriceChart } from "./components/quote/PriceChart";
import { QuoteHeader } from "./components/quote/QuoteHeader";
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
import { useWatchlist } from "./hooks/useWatchlist";
import { companyName } from "./lib/format";

type Dialog = "delivery" | "intraday" | "global" | null;

const STRIP_INDICES = [
  "NIFTY 50", "SENSEX", "NIFTY BANK", "S&P 500", "NASDAQ",
  "GOLD", "CRUDE OIL", "BITCOIN", "USD/INR",
];

export function App() {
  const { list, error: listError } = useSymbols();
  const { watchlist, toggle } = useWatchlist(list?.watchlist);
  const now = useNow();
  const [selected, setSelected] = useState("");       // empty = dashboard
  const [side, setSide] = useState<Side>("BUY");
  const [pickedPrice, setPickedPrice] = useState<{ price: number; at: number } | null>(null);
  const [dialog, setDialog] = useState<Dialog>(null);
  const [globalTicker, setGlobalTicker] = useState<string | undefined>(undefined);
  const [following, setFollowing] = useState<string[]>([]);
  const [lastDelivery, setLastDelivery] = useState<Recommendation | null>(null);
  const [notice, setNotice] = useState("");
  const [booked, setBooked] = useState(0);
  const [whyDate, setWhyDate] = useState<string | null>(null);
  const ticket = useRef<HTMLElement>(null);

  // Reset why-date when symbol changes
  useEffect(() => setWhyDate(null), [selected]);

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

  const live = useLiveMarket([selected, ...watchlist, ...mine, ...following].filter(Boolean));
  const { detail, error: stockError } = useInstrument(selected);
  const sparklines = useSparklines(watchlist);
  const book = useOrderBook(selected, booked);

  const names = useMemo(() => new Map((list?.symbols ?? []).map(([s, n]) => [s, companyName(n)])), [list]);
  const rows = useMemo(() => new Map((list?.symbols ?? []).map((row) => [row[0], row])), [list]);
  const row = rows.get(selected);
  const instrument = detail ?? (row && list ? instrumentOf(row, list.data_date) : null);

  const follow = useCallback((symbols: string[]) => setFollowing(symbols), []);

  const select = (next: string) => {
    setSelected(next);
    setNotice("");
    window.scrollTo({ top: 0, behavior: "smooth" });
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

  const quote = live.quotes[selected] ?? detail?.quote;
  const quotes = useMemo(
    () => (detail && !live.quotes[detail.symbol] ? { ...live.quotes, [detail.symbol]: detail.quote } : live.quotes),
    [live.quotes, detail],
  );
  const session = live.status?.session ?? null;
  const marginDivisor = live.status?.margin_divisor ?? 5;

  if (!list) {
    return (
      <p className="loading">
        {listError || (live.connected ? "Loading market data…" : "Connecting to the server…")}
      </p>
    );
  }

  const showDetail = selected && instrument;

  return (
    <>
      <a className="skip-link" href="#main">Skip to content</a>

      <TopBar
        symbols={list.symbols}
        quotes={quotes}
        watchlist={watchlist}
        connected={live.connected}
        status={live.status}
        now={now}
        portfolio={portfolio}
        onSelect={select}
        onGlobalSelect={(ticker) => { setGlobalTicker(ticker); setDialog("global"); }}
      />

      <IndicesBar
        indices={live.indices}
        indexOrder={STRIP_INDICES}
        onGlobal={() => setDialog("global")}
      />

      {notice && <p className="notice container" role="alert">{notice}</p>}

      {showDetail ? (
        /* ---- STOCK DETAIL VIEW ---- */
        <div className="container detail-layout">
          <SectionNav />

          <main id="main" className="main-col">
            {/* Back to dashboard */}
            <button type="button" className="back-btn" onClick={() => setSelected("")}>
              <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
                <path d="M9 2L4 7l5 5" />
              </svg>
              Dashboard
            </button>

            <QuoteHeader
              instrument={instrument}
              quote={quote}
              session={session}
              watched={watchlist.includes(selected)}
              onToggleWatch={() => toggle(selected)}
              onTrade={startTrade}
              onWhy={() => explainDay(null)}
            />
            <PriceChart symbol={selected} quote={quote} onPickDay={explainDay} />
            <WhyMoved symbol={selected} date={whyDate} onDate={setWhyDate} onOpenStock={select} />
            <KeyStats instrument={instrument} quote={quote} />
            <MarketDepth
              instrument={instrument}
              quote={quote}
              book={book}
              trades={live.tape[selected] ?? []}
              now={now}
              onPickPrice={(p) => setPickedPrice({ price: p, at: Date.now() })}
            />
            <NewsPanel symbol={selected} company={quote?.name ?? names.get(selected) ?? selected} />
            <RecommendationsPanel
              watchlist={watchlist}
              portfolio={portfolio}
              lastDelivery={lastDelivery}
              onOpenDelivery={() => setDialog("delivery")}
              onOpenIntraday={() => setDialog("intraday")}
            />
            <AccountTabs
              portfolio={portfolio}
              orders={orders}
              marketOpen={session?.state === "OPEN"}
              onCancel={(id) => act(() => api.cancelOrder(id))}
              onSquareOff={() => act(() => api.squareOff("demo"))}
              onSelect={select}
            />
          </main>

          <aside className="rail">
            <OrderTicket
              ref={ticket}
              instrument={instrument}
              quote={quote}
              session={session}
              portfolio={portfolio}
              marginDivisor={marginDivisor}
              side={side}
              onSideChange={setSide}
              pickedPrice={pickedPrice}
              onPlaced={placed}
              onDeliveryClick={() => setDialog("delivery")}
              onIntradayClick={() => setDialog("intraday")}
            />
            <AccountSummary portfolio={portfolio} />
            <Movers symbols={watchlist} names={names} quotes={quotes} sparklines={sparklines} onSelect={select} />
          </aside>
        </div>
      ) : (
        /* ---- DASHBOARD VIEW ---- */
        <div className="container dashboard-layout">
          <main id="main" className="main-col">
            <Dashboard
              watchlist={watchlist}
              names={names}
              quotes={quotes}
              sparklines={sparklines}
              portfolio={portfolio}
              onSelect={select}
              symbolRows={list.symbols}
            />
            <AccountTabs
              portfolio={portfolio}
              orders={orders}
              marketOpen={session?.state === "OPEN"}
              onCancel={(id) => act(() => api.cancelOrder(id))}
              onSquareOff={() => act(() => api.squareOff("demo"))}
              onSelect={select}
            />
          </main>

          <aside className="rail" aria-label="Account">
            <AccountSummary portfolio={portfolio} />
            <Movers symbols={watchlist} names={names} quotes={quotes} sparklines={sparklines} onSelect={select} />
            <RecommendationsPanel
              watchlist={watchlist}
              portfolio={portfolio}
              lastDelivery={lastDelivery}
              onOpenDelivery={() => setDialog("delivery")}
              onOpenIntraday={() => setDialog("intraday")}
            />
          </aside>
        </div>
      )}

      {stockError && !showDetail && (
        <p className="container notice" style={{ marginTop: 8 }}>{stockError}</p>
      )}

      <Footer dataDate={list.data_date} />

      <DeliveryModal
        open={dialog === "delivery"}
        onClose={() => setDialog(null)}
        symbols={list.symbols}
        names={names}
        quotes={quotes}
        watchlist={watchlist}
        portfolio={portfolio}
        preselect={selected || watchlist[0] || ""}
        onFollow={follow}
        onOrdersPlaced={placed}
        onResult={setLastDelivery}
      />
      <IntradayModal
        open={dialog === "intraday"}
        onClose={() => setDialog(null)}
        symbols={list.symbols}
        names={names}
        quotes={quotes}
        watchlist={watchlist}
        portfolio={portfolio}
        preselect={selected || watchlist[0] || ""}
        marginDivisor={marginDivisor}
        onFollow={follow}
        onOrdersPlaced={placed}
      />
      {dialog === "global" && <GlobalMarkets onClose={() => { setDialog(null); setGlobalTicker(undefined); }} initialTicker={globalTicker} />}
    </>
  );
}
