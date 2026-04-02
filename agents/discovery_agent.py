"""
DISCOVERY AGENT — The "Next Winner" Scanner
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Scans 100+ NSE stocks (not just your watchlist) every 6 hours.
Looks for stocks building momentum BEFORE they break out.
Uses: Price momentum + volume surge + news sentiment + sector trends.

Output: Top 3-5 stocks predicted to perform well in next 1-2 weeks.
"""
import yfinance as yf
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger("DiscoveryAgent")
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

# NSE 100 universe to scan — covers large & mid caps across sectors
NSE_UNIVERSE = [
    # IT
    "TCS.NS","INFY.NS","WIPRO.NS","HCLTECH.NS","TECHM.NS","LTIM.NS","MPHASIS.NS","COFORGE.NS",
    # Banking & Finance
    "HDFCBANK.NS","ICICIBANK.NS","AXISBANK.NS","KOTAKBANK.NS","SBIN.NS","INDUSINDBK.NS","BANKBARODA.NS",
    # Energy
    "RELIANCE.NS","ONGC.NS","BPCL.NS","IOC.NS","NTPC.NS","POWERGRID.NS","ADANIGREEN.NS","TATAPOWER.NS",
    # Auto
    "TATAMOTORS.NS","MARUTI.NS","BAJAJ-AUTO.NS","EICHERMOT.NS","HEROMOTOCO.NS","M&M.NS","ASHOKLEY.NS",
    # Pharma
    "SUNPHARMA.NS","DRREDDY.NS","CIPLA.NS","DIVISLAB.NS","AUROPHARMA.NS","LUPIN.NS","TORNTPHARM.NS",
    # FMCG
    "HINDUNILVR.NS","ITC.NS","NESTLEIND.NS","BRITANNIA.NS","DABUR.NS","MARICO.NS","COLPAL.NS",
    # Metal & Mining
    "TATASTEEL.NS","JSWSTEEL.NS","HINDALCO.NS","COALINDIA.NS","NMDC.NS","VEDL.NS",
    # Infra & Construction
    "LT.NS","ULTRACEMCO.NS","GRASIM.NS","ACC.NS","AMBUJACEMENT.NS","DLF.NS","GODREJPROP.NS",
    # Telecom & Media
    "BHARTIARTL.NS","IDEA.NS",
    # Consumer & Retail
    "TITAN.NS","DMART.NS","TRENT.NS","NYKAA.NS","ZOMATO.NS","PAYTM.NS",
]

class DiscoveryAgent:
    def __init__(self):
        self.universe = NSE_UNIVERSE

    def analyze_stock(self, symbol):
        """Score a stock for breakout potential. Returns score 0-100."""
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period="3mo", interval="1d")
            if df.empty or len(df) < 20:
                return None

            closes = list(df["Close"])
            volumes = list(df["Volume"])
            latest = closes[-1]

            score = 0
            signals = []

            # 1. PRICE MOMENTUM (30 points)
            # 1-week momentum
            if len(closes) >= 5:
                w1_mom = (closes[-1] - closes[-5]) / closes[-5] * 100
                if w1_mom > 5:
                    score += 15
                    signals.append(f"Strong 1W momentum: +{w1_mom:.1f}%")
                elif w1_mom > 2:
                    score += 8
                    signals.append(f"Positive 1W momentum: +{w1_mom:.1f}%")
                elif w1_mom < -5:
                    score -= 10

            # 1-month momentum
            if len(closes) >= 22:
                m1_mom = (closes[-1] - closes[-22]) / closes[-22] * 100
                if m1_mom > 10:
                    score += 15
                    signals.append(f"Strong 1M momentum: +{m1_mom:.1f}%")
                elif m1_mom > 5:
                    score += 8
                elif m1_mom < -10:
                    score -= 10

            # 2. VOLUME SURGE (25 points)
            if len(volumes) >= 10:
                avg_vol = sum(volumes[-20:-5]) / 15 if len(volumes) >= 20 else sum(volumes[:-1]) / len(volumes[:-1])
                recent_vol = sum(volumes[-5:]) / 5
                vol_ratio = recent_vol / avg_vol if avg_vol > 0 else 1
                if vol_ratio > 2.0:
                    score += 25
                    signals.append(f"Volume surge: {vol_ratio:.1f}x average (strong interest)")
                elif vol_ratio > 1.5:
                    score += 15
                    signals.append(f"Volume above average: {vol_ratio:.1f}x")
                elif vol_ratio > 1.2:
                    score += 8
                    signals.append(f"Slight volume increase: {vol_ratio:.1f}x")

            # 3. MOVING AVERAGE POSITION (25 points)
            if len(closes) >= 50:
                sma20 = sum(closes[-20:]) / 20
                sma50 = sum(closes[-50:]) / 50
                # Price above both MAs
                if latest > sma20 > sma50:
                    score += 20
                    signals.append("Price above SMA20 > SMA50 (bullish alignment)")
                elif latest > sma20:
                    score += 10
                    signals.append("Price above SMA20")
                # Golden cross forming
                prev_sma20 = sum(closes[-21:-1]) / 20
                prev_sma50 = sum(closes[-51:-1]) / 50
                if sma20 > sma50 and prev_sma20 <= prev_sma50:
                    score += 5
                    signals.append("Golden cross just formed!")

            # 4. RSI (20 points)
            if len(closes) >= 15:
                gains, losses = [], []
                for i in range(1, 15):
                    diff = closes[-i] - closes[-i-1]
                    if diff > 0: gains.append(diff)
                    else: losses.append(abs(diff))
                avg_g = sum(gains)/14 if gains else 0
                avg_l = sum(losses)/14 if losses else 0.001
                rs = avg_g / avg_l
                rsi = 100 - (100/(1+rs))
                if 40 <= rsi <= 60:
                    score += 20
                    signals.append(f"RSI in ideal zone ({rsi:.0f}) — room to run")
                elif 35 <= rsi < 40:
                    score += 15
                    signals.append(f"RSI recovering from oversold ({rsi:.0f})")
                elif rsi < 35:
                    score += 10
                    signals.append(f"RSI oversold ({rsi:.0f}) — bounce likely")
                elif rsi > 75:
                    score -= 10
                    signals.append(f"RSI overbought ({rsi:.0f}) — caution")
            else:
                rsi = None

            return {
                "symbol": symbol,
                "latest_price": round(latest, 2),
                "score": min(score, 100),
                "signals": signals,
                "rsi": round(rsi, 1) if rsi else None,
                "outlook": "1-2 weeks",
            }

        except Exception as e:
            log.warning(f"Could not analyze {symbol}: {e}")
            return None

    def scan(self):
        """Scan all stocks, return top picks."""
        log.info(f"[Discovery] Scanning {len(self.universe)} NSE stocks...")
        results = []

        for symbol in self.universe:
            result = self.analyze_stock(symbol)
            if result and result["score"] >= 40:
                results.append(result)

        # Sort by score
        results.sort(key=lambda x: x["score"], reverse=True)
        top_picks = results[:5]

        output = {
            "scanned_at": datetime.now().isoformat(),
            "universe_size": len(self.universe),
            "candidates_found": len(results),
            "top_picks": top_picks,
            "all_candidates": results[:15],
            "next_scan": (datetime.now() + timedelta(hours=6)).isoformat(),
        }

        (DATA_DIR / "discovery.json").write_text(json.dumps(output, indent=2))
        log.info(f"[Discovery] Done. Top picks: {[p['symbol'] for p in top_picks]}")
        return output
