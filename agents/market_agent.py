"""
MARKET AGENT
Fetches REAL NSE/BSE price data from Yahoo Finance every 15 minutes.
No API key needed — Yahoo Finance is free.
"""
import yfinance as yf
import json
from datetime import datetime
from pathlib import Path

CACHE_DIR = Path("data")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

class MarketAgent:
    def __init__(self, watchlist):
        self.watchlist = watchlist
        self.last_update = None

    def fetch_stock(self, symbol, period="5y", interval="1d"):
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period, interval=interval)
            if df.empty:
                print(f"No data for {symbol}")
                return {}
            info = ticker.info
            data = {
                "symbol": symbol,
                "name": info.get("longName", symbol),
                "sector": info.get("sector", "Unknown"),
                "last_updated": datetime.now().isoformat(),
                "prices": [
                    {
                        "date": str(idx.date()),
                        "open": round(row["Open"], 2),
                        "high": round(row["High"], 2),
                        "low": round(row["Low"], 2),
                        "close": round(row["Close"], 2),
                        "volume": int(row["Volume"]),
                    }
                    for idx, row in df.iterrows()
                ],
            }
            cache_file = CACHE_DIR / f"{symbol.replace('.', '_')}.json"
            with open(cache_file, "w") as f:
                json.dump(data, f, indent=2)
            print(f"[MarketAgent] {symbol}: {len(data['prices'])} days fetched")
            return data
        except Exception as e:
            print(f"[MarketAgent] Error fetching {symbol}: {e}")
            return {}

    def fetch_all(self):
        print(f"\n[MarketAgent] Running at {datetime.now().strftime('%H:%M:%S')}")
        results = {}
        for symbol in self.watchlist:
            results[symbol] = self.fetch_stock(symbol)
        self.last_update = datetime.now()
        return results

    def load_cached(self, symbol):
        cache_file = CACHE_DIR / f"{symbol.replace('.', '_')}.json"
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

if __name__ == "__main__":
    agent = MarketAgent(["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS"])
    agent.fetch_all()
