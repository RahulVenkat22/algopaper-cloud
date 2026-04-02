"""
NEWS AGENT
Monitors news for each stock every 60 minutes.
Sources: NewsAPI + Google News RSS (no key needed for RSS)
Scores news sentiment: positive = buy signal boost, negative = sell signal boost
"""
import feedparser
import json
import re
from datetime import datetime
from pathlib import Path

NEWS_CACHE = Path("data")

STOCK_KEYWORDS = {
    "RELIANCE.NS": ["Reliance Industries", "RIL", "Mukesh Ambani", "Jio"],
    "TCS.NS": ["TCS", "Tata Consultancy", "Tata Consultancy Services"],
    "HDFCBANK.NS": ["HDFC Bank", "HDFC", "Sashidhar Jagdishan"],
    "INFY.NS": ["Infosys", "Infy", "Salil Parekh"],
    "ICICIBANK.NS": ["ICICI Bank", "ICICI"],
}

GLOBAL_KEYWORDS = ["RBI", "Federal Reserve", "inflation", "recession", "war",
                   "earthquake", "oil price", "SENSEX", "NIFTY", "crude oil"]

POSITIVE_WORDS = ["profit", "growth", "record", "surge", "rally", "beat", "strong",
                  "upgrade", "buy", "outperform", "expansion", "win", "deal"]
NEGATIVE_WORDS = ["loss", "decline", "fall", "crash", "weak", "miss", "downgrade",
                  "sell", "underperform", "fraud", "penalty", "resign", "war", "disaster"]

def score_sentiment(text):
    text_lower = text.lower()
    pos = sum(1 for w in POSITIVE_WORDS if w in text_lower)
    neg = sum(1 for w in NEGATIVE_WORDS if w in text_lower)
    if pos > neg:
        return "POSITIVE", pos - neg
    elif neg > pos:
        return "NEGATIVE", neg - pos
    return "NEUTRAL", 0

class NewsAgent:
    def __init__(self, watchlist):
        self.watchlist = watchlist

    def fetch_rss(self, query):
        url = f"https://news.google.com/rss/search?q={query}+NSE+India&hl=en-IN&gl=IN&ceid=IN:en"
        try:
            feed = feedparser.parse(url)
            articles = []
            for entry in feed.entries[:5]:
                sentiment, score = score_sentiment(entry.get("title", "") + " " + entry.get("summary", ""))
                articles.append({
                    "title": entry.get("title", ""),
                    "link": entry.get("link", ""),
                    "published": entry.get("published", ""),
                    "sentiment": sentiment,
                    "sentiment_score": score,
                })
            return articles
        except Exception as e:
            print(f"[NewsAgent] RSS error for {query}: {e}")
            return []

    def fetch_all(self):
        print(f"\n[NewsAgent] Running at {datetime.now().strftime('%H:%M:%S')}")
        all_news = {}

        # Stock-specific news
        for symbol, keywords in STOCK_KEYWORDS.items():
            if symbol not in self.watchlist:
                continue
            articles = []
            for kw in keywords[:2]:
                articles.extend(self.fetch_rss(kw))
            all_news[symbol] = {
                "last_updated": datetime.now().isoformat(),
                "articles": articles[:8],
                "overall_sentiment": self._aggregate_sentiment(articles),
            }
            print(f"[NewsAgent] {symbol}: {len(articles)} articles, sentiment={all_news[symbol]['overall_sentiment']}")

        # Global macro news
        global_articles = []
        for kw in ["NIFTY India stock market", "RBI interest rate", "India economy"]:
            global_articles.extend(self.fetch_rss(kw))

        all_news["GLOBAL"] = {
            "last_updated": datetime.now().isoformat(),
            "articles": global_articles[:10],
            "overall_sentiment": self._aggregate_sentiment(global_articles),
        }

        # Cache
        cache_file = NEWS_CACHE / "news_cache.json"
        with open(cache_file, "w") as f:
            json.dump(all_news, f, indent=2)

        return all_news

    def _aggregate_sentiment(self, articles):
        if not articles:
            return "NEUTRAL"
        pos = sum(1 for a in articles if a["sentiment"] == "POSITIVE")
        neg = sum(1 for a in articles if a["sentiment"] == "NEGATIVE")
        if pos > neg:
            return "POSITIVE"
        elif neg > pos:
            return "NEGATIVE"
        return "NEUTRAL"

if __name__ == "__main__":
    agent = NewsAgent(["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS"])
    results = agent.fetch_all()
    print(json.dumps(results, indent=2)[:1000])
