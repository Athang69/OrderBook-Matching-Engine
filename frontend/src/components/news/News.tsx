import type { NewsArticle, StockNews } from "../../api/types";
import { dateTime, timeAgo } from "../../lib/format";
import { useNews } from "../../hooks/useNews";

const SOURCE_NOTE = "Headlines from Google News, past seven days. They are for you to read; recommendations do not use them.";

export interface StockLabel {
  text: string;
  tone: "up" | "down" | "neutral";
}

/** Up to three headlines, newest first; each opens the article in a new tab. */
export function NewsList({ news, loading }: { news: StockNews | undefined; loading: boolean }) {
  if (!news) return <p className="news-empty">{loading ? "Loading headlines." : "No headlines loaded."}</p>;
  return (
    <>
      {news.articles.length === 0 ? (
        <p className="news-empty">No news about {news.company} in the past week.</p>
      ) : (
        <ul className="news-list">
          {news.articles.map((article) => <Headline key={article.url} article={article} />)}
        </ul>
      )}
      {news.error && <p className="news-warning">{news.error}</p>}
    </>
  );
}

function Headline({ article }: { article: NewsArticle }) {
  return (
    <li>
      <span className="news-source-mark" aria-hidden="true">{(article.source || "?").slice(0, 1).toUpperCase()}</span>
      <span className="news-text">
        <a href={article.url} target="_blank" rel="noopener noreferrer">{article.title}</a>
        <span className="news-meta">
          {article.source}
          {article.source ? " · " : ""}
          <time dateTime={new Date(article.published * 1000).toISOString()} title={dateTime(article.published)}>{timeAgo(article.published)}</time>
        </span>
      </span>
    </li>
  );
}

/** Main page: the latest headlines for the stock on screen. */
export function NewsPanel({ symbol, company }: { symbol: string; company: string }) {
  const { stocks, loading, error, refresh } = useNews(symbol ? [symbol] : []);
  return (
    <section className="section" id="news" aria-labelledby="news-title">
      <div className="section-head">
        <h2 id="news-title" className="section-title">Latest news: {company}</h2>
        <button type="button" className="button ghost small" onClick={refresh} disabled={loading}>{loading ? "Loading" : "Refresh"}</button>
      </div>
      {error ? <p className="news-warning">{error}</p> : <NewsList news={stocks[symbol]} loading={loading} />}
      <p className="hint">{SOURCE_NOTE}</p>
    </section>
  );
}

/** Recommendation results: headlines for every stock, each card labelled with its decision. */
export function NewsSection({ symbols, labels }: { symbols: string[]; labels: Record<string, StockLabel> }) {
  const { stocks, loading, error, refresh } = useNews(symbols);
  return (
    <section className="news-section" aria-labelledby="news-section-title">
      <div className="section-head">
        <h3 id="news-section-title">Latest news on these stocks</h3>
        <button type="button" className="button ghost small" onClick={refresh} disabled={loading}>{loading ? "Loading" : "Refresh"}</button>
      </div>
      {error && <p className="news-warning">{error}</p>}
      <div className="news-grid">
        {symbols.map((symbol) => {
          const label = labels[symbol];
          return (
            <article key={symbol} className={`news-card ${label?.tone ?? "neutral"}`}>
              <header>
                <strong>{symbol}</strong>
                <span className="muted small ellipsis">{stocks[symbol]?.company ?? ""}</span>
                {label && <span className={`badge ${label.tone}`}>{label.text}</span>}
              </header>
              <NewsList news={stocks[symbol]} loading={loading} />
            </article>
          );
        })}
      </div>
      <p className="hint">{SOURCE_NOTE}</p>
    </section>
  );
}
