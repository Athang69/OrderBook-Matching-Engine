export function Footer({ dataDate }: { dataDate?: string }) {
  return (
    <footer className="footer">
      <div className="container">
        <p>
          Paper trading with virtual money on live NSE prices. Prices, quotes and charts come from Yahoo Finance, free and
          about two seconds behind the exchange; full market depth is not published there. The list of stocks, price bands
          and tick sizes come from NSE's daily files{dataDate ? ` (latest: ${dataDate})` : ""}. Headlines come from Google
          News and price history for recommendations from Yahoo Finance.
        </p>
        <p>
          For personal study on your own computer: live exchange prices may not be passed on to others for virtual trading.
          Nothing here is investment advice.
        </p>
      </div>
    </footer>
  );
}
