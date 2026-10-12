/**
 * Placeholder for the portfolio suggestion (FinBERT news sentiment + SLSQP allocation).
 * That module is a separate project and is not connected yet. When it is, this panel
 * shows its buy or do-not-buy suggestion and the suggested allocation for `symbol`.
 */
export function SuggestionSlot({ symbol }: { symbol: string }) {
  return (
    <section className="panel suggestion">
      <div className="panel-head">
        <h2>Portfolio suggestion</h2>
        <span className="pill">Not connected</span>
      </div>
      <p className="muted">
        The buy or do-not-buy suggestion and the suggested allocation for {symbol} will appear here once the
        portfolio module is connected.
      </p>
    </section>
  );
}
