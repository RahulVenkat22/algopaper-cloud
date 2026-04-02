"""
SIGNAL AGENT
Combines: Technical Indicators + News Sentiment + Global Events
Output: BUY / SELL / HOLD with confidence score 0-10
Runs every time new price or news data arrives.
"""
import json
from datetime import datetime
from pathlib import Path

CACHE_DIR = Path("data")

class SignalAgent:
    def __init__(self, watchlist):
        self.watchlist = watchlist

    def load_prices(self, symbol):
        f = CACHE_DIR / f"{symbol.replace('.', '_')}.json"
        if f.exists():
            try:
                return json.loads(f.read_text()).get("prices", [])
            except Exception:
                return []
        return []

    def load_news(self):
        f = CACHE_DIR / "news_cache.json"
        if f.exists():
            return json.loads(f.read_text())
        return {}

    def sma(self, prices, period):
        closes = [p["close"] for p in prices]
        if len(closes) < period:
            return None
        return sum(closes[-period:]) / period

    def rsi(self, prices, period=14):
        closes = [p["close"] for p in prices]
        if len(closes) < period + 1:
            return None
        gains, losses = [], []
        for i in range(1, period + 1):
            diff = closes[-period + i] - closes[-period + i - 1]
            if diff > 0:
                gains.append(diff)
            else:
                losses.append(abs(diff))
        avg_gain = sum(gains) / period if gains else 0
        avg_loss = sum(losses) / period if losses else 0
        if avg_loss == 0:
            return 100
        rs = avg_gain / avg_loss
        return round(100 - (100 / (1 + rs)), 2)

    def generate_signal(self, symbol):
        prices = self.load_prices(symbol)
        news_data = self.load_news()

        if len(prices) < 60:
            return {"symbol": symbol, "action": "INSUFFICIENT_DATA", "score": 0}

        score = 0.0
        reasons = []

        # Technical signals (max ±5 points)
        sma20 = self.sma(prices, 20)
        sma50 = self.sma(prices, 50)
        rsi_val = self.rsi(prices)
        latest_price = prices[-1]["close"]

        if sma20 and sma50:
            if sma20 > sma50:
                score += 1.5
                reasons.append("SMA20 above SMA50 (bullish trend)")
            else:
                score -= 1.5
                reasons.append("SMA20 below SMA50 (bearish trend)")

        if rsi_val:
            if rsi_val < 35:
                score += 2
                reasons.append(f"RSI oversold ({rsi_val}) — potential bounce")
            elif rsi_val > 65:
                score -= 2
                reasons.append(f"RSI overbought ({rsi_val}) — potential pullback")
            elif 45 <= rsi_val <= 55:
                reasons.append(f"RSI neutral ({rsi_val})")

        # Price momentum
        if len(prices) >= 5:
            week_ago = prices[-5]["close"]
            momentum = (latest_price - week_ago) / week_ago * 100
            if momentum > 3:
                score += 1
                reasons.append(f"Positive 5-day momentum (+{momentum:.1f}%)")
            elif momentum < -3:
                score -= 1
                reasons.append(f"Negative 5-day momentum ({momentum:.1f}%)")

        # News sentiment (max ±3 points)
        stock_news = news_data.get(symbol, {})
        news_sentiment = stock_news.get("overall_sentiment", "NEUTRAL")
        if news_sentiment == "POSITIVE":
            score += 2
            reasons.append("Company news sentiment: POSITIVE")
        elif news_sentiment == "NEGATIVE":
            score -= 2
            reasons.append("Company news sentiment: NEGATIVE")

        # Global macro sentiment (max ±2 points)
        global_news = news_data.get("GLOBAL", {})
        global_sentiment = global_news.get("overall_sentiment", "NEUTRAL")
        if global_sentiment == "POSITIVE":
            score += 1
            reasons.append("Global market sentiment: POSITIVE")
        elif global_sentiment == "NEGATIVE":
            score -= 1
            reasons.append("Global market sentiment: NEGATIVE")

        # Final decision
        if score >= 3:
            action = "BUY"
        elif score <= -3:
            action = "SELL"
        else:
            action = "HOLD"

        return {
            "symbol": symbol,
            "action": action,
            "score": round(score, 1),
            "confidence": min(abs(score) / 8 * 100, 100),
            "latest_price": latest_price,
            "sma20": sma20,
            "sma50": sma50,
            "rsi": rsi_val,
            "news_sentiment": news_sentiment,
            "global_sentiment": global_sentiment,
            "reasons": reasons,
            "generated_at": datetime.now().isoformat(),
        }

    def generate_all(self):
        signals = {}
        for symbol in self.watchlist:
            signals[symbol] = self.generate_signal(symbol)
            s = signals[symbol]
            print(f"[SignalAgent] {symbol}: {s['action']} (score={s['score']})")
        cache_file = CACHE_DIR / "signals.json"
        cache_file.write_text(json.dumps(signals, indent=2))
        return signals

if __name__ == "__main__":
    agent = SignalAgent(["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS"])
    results = agent.generate_all()
    for sym, sig in results.items():
        print(f"\n{sym}: {sig['action']} | Score: {sig['score']}")
        for r in sig['reasons']:
            print(f"  → {r}")
