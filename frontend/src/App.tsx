import { useEffect, useRef, useState } from "react";

import { api } from "./api/client";
import type { Recommendation, Side, Trade } from "./api/types";
import { Footer } from "./components/layout/Footer";
import { MarketStrip } from "./components/layout/MarketStrip";
import { SectionNav } from "./components/layout/SectionNav";
import { TopBar } from "./components/layout/TopBar";
import { Movers } from "./components/market/Movers";
import { MarketDepth } from "./components/market/OrderBook";
import { NewsPanel } from "./components/news/News";
import { KeyStats } from "./components/quote/KeyStats";
import { OtherStocks } from "./components/quote/OtherStocks";
import { PriceChart } from "./components/quote/PriceChart";
import { QuoteHeader } from "./components/quote/QuoteHeader";
import { DeliveryModal } from "./components/recommendations/DeliveryModal";
import { IntradayModal } from "./components/recommendations/IntradayModal";
import { RecommendationsPanel } from "./components/recommendations/RecommendationsPanel";
import { AccountSummary } from "./components/trading/AccountSummary";
import { AccountTabs } from "./components/trading/AccountTabs";
import { OrderTicket } from "./components/trading/OrderTicket";
import { useAccount } from "./hooks/useAccount";
import { useMarketData } from "./hooks/useMarketData";
import { usePriceHistory } from "./hooks/usePriceHistory";
import { useTheme } from "./hooks/useTheme";

type Dialog = "delivery" | "intraday" | null;

export function App() {
  const { connected, instruments, market, tape, sim } = useMarketData();
  const history = usePriceHistory(market);
  const { portfolio, orders, refresh } = useAccount(sim?.demo_user);
  const [theme, toggleTheme] = useTheme();
  const [selected, setSelected] = useState("");
  const [side, setSide] = useState<Side>("BUY");
  const [pickedPrice, setPickedPrice] = useState<{ price: number; at: number } | null>(null);
  const [dialog, setDialog] = useState<Dialog>(null);
  const [lastDelivery, setLastDelivery] = useState<Recommendation | null>(null);
  const [earlierTrades, setEarlierTrades] = useState<Trade[]>([]);
  const [notice, setNotice] = useState("");
  const ticket = useRef<HTMLElement>(null);

  const symbol = selected || instruments[0]?.symbol || "";
  const instrument = instruments.find((i) => i.symbol === symbol);
  const state = market[symbol];

  // Trades from before this page connected; newer ones arrive over the WebSocket.
  useEffect(() => {
    if (!symbol) return;
    let cancelled = false;
    setEarlierTrades([]);
    api.trades(symbol).then((trades) => !cancelled && setEarlierTrades(trades)).catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [symbol]);

  const act = async (action: () => Promise<unknown>) => {
    try {
      await action();
      setNotice("");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Something went wrong.");
    }
    refresh();
  };

  const startTrade = (next: Side) => {
    setSide(next);
    ticket.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    ticket.current?.focus({ preventScroll: true });
  };

  if (!instrument || !state) {
    return <p className="loading">{connected ? "Loading market data." : "Connecting to the simulator."}</p>;
  }

  const live = tape[symbol] ?? [];
  const seen = new Set(live.map((t) => t.id));
  const trades = [...live, ...earlierTrades.filter((t) => !seen.has(t.id))].slice(0, 40);
  const marginDivisor = sim?.margin_divisor ?? 5;

  return (
    <>
      <a className="skip-link" href="#main">Skip to content</a>
      <TopBar instruments={instruments} market={market} connected={connected} sim={sim} portfolio={portfolio}
        theme={theme} onToggleTheme={toggleTheme} onToggleBots={(enabled) => act(() => api.setBots(enabled))} onSelect={setSelected} />
      <MarketStrip instruments={instruments} market={market} history={history} selected={symbol} onSelect={setSelected} />
      {notice && <p className="notice container" role="alert">{notice}</p>}

      <div className="container page">
        <SectionNav />
        <main id="main" className="main-col">
          <QuoteHeader instrument={instrument} state={state} sim={sim} onTrade={startTrade} />
          <PriceChart symbol={symbol} points={history[symbol] ?? []} prevClose={instrument.prev_close} />
          <KeyStats instrument={instrument} state={state} />
          <MarketDepth instrument={instrument} state={state} trades={trades} onPickPrice={(p) => setPickedPrice({ price: p, at: Date.now() })} />
          <NewsPanel symbol={symbol} company={instrument.company} />
          <RecommendationsPanel instruments={instruments} portfolio={portfolio} lastDelivery={lastDelivery}
            onOpenDelivery={() => setDialog("delivery")} onOpenIntraday={() => setDialog("intraday")} />
          <AccountTabs portfolio={portfolio} orders={orders} onCancel={(id) => act(() => api.cancelOrder(id))}
            onSquareOff={() => sim && act(() => api.squareOff(sim.demo_user))} />
          <OtherStocks instruments={instruments} market={market} selected={symbol} onSelect={setSelected} />
        </main>
        <aside className="rail" aria-label="Trade and account">
          <OrderTicket ref={ticket} instrument={instrument} state={state} portfolio={portfolio} marginDivisor={marginDivisor}
            side={side} onSideChange={setSide} pickedPrice={pickedPrice} onPlaced={refresh}
            onDeliveryClick={() => setDialog("delivery")} onIntradayClick={() => setDialog("intraday")} />
          <AccountSummary portfolio={portfolio} />
          <Movers instruments={instruments} market={market} history={history} onSelect={setSelected} />
        </aside>
      </div>

      <Footer dataDate={instrument.data_date} />

      <DeliveryModal open={dialog === "delivery"} onClose={() => setDialog(null)} instruments={instruments} market={market}
        portfolio={portfolio} preselect={symbol} onOrdersPlaced={refresh} onResult={setLastDelivery} />
      <IntradayModal open={dialog === "intraday"} onClose={() => setDialog(null)} instruments={instruments} market={market}
        portfolio={portfolio} preselect={symbol} marginDivisor={marginDivisor} onOrdersPlaced={refresh} />
    </>
  );
}
