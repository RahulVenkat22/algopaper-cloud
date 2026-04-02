"""
TELEGRAM ALERT AGENT
━━━━━━━━━━━━━━━━━━━━
Sends real-time alerts to your phone for:
- BUY signals (with full reasoning)
- SELL signals (with P&L)
- Discovery alerts (new stocks to watch)
- Daily portfolio summary (9 AM IST)
- Stop loss triggers

No manual intervention needed — fully automatic.
"""
import os
import requests
import json
import logging
from datetime import datetime
from pathlib import Path

log = logging.getLogger("TelegramAgent")
DATA_DIR = Path("data")

class TelegramAgent:
    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        raw_ids = os.getenv("TELEGRAM_CHAT_IDS", os.getenv("TELEGRAM_CHAT_ID", ""))
        self.chat_ids = [cid.strip() for cid in raw_ids.split(",") if cid.strip()]
        self.enabled = bool(self.token and self.chat_ids)
        if not self.enabled:
            log.warning("Telegram not configured. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_IDS.")
        else:
            log.info(f"Telegram ready for {len(self.chat_ids)} recipient(s)")

    def send(self, message: str):
        """Send message to all configured chat IDs."""
        if not self.enabled:
            log.info(f"[Telegram MOCK] {message[:80]}...")
            return
        for chat_id in self.chat_ids:
            try:
                url = f"https://api.telegram.org/bot{self.token}/sendMessage"
                resp = requests.post(url, json={
                    "chat_id": chat_id,
                    "text": message,
                    "parse_mode": "HTML"
                }, timeout=10)
                if resp.status_code == 200:
                    log.info(f"Telegram sent to {chat_id}")
                else:
                    log.error(f"Telegram failed: {resp.text}")
            except Exception as e:
                log.error(f"Telegram error: {e}")

    def alert_buy(self, signal: dict, portfolio: dict):
        capital = portfolio.get("cash", 0)
        shares = int((capital * 0.95) / signal["latest_price"]) if signal["latest_price"] > 0 else 0
        invest = round(shares * signal["latest_price"], 2)
        reasons = "\n".join([f"  • {r}" for r in signal.get("reasons", [])[:4]])
        msg = (
            f"🚀 <b>BUY SIGNAL — ALGO•PAPER</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📈 Stock: <b>{signal['symbol']}</b>\n"
            f"💰 Price: ₹{signal['latest_price']}\n"
            f"📊 Score: <b>{signal['score']}/10</b>\n"
            f"🔢 RSI: {signal.get('rsi', 'N/A')}\n"
            f"📰 News: {signal.get('news_sentiment', 'NEUTRAL')}\n"
            f"🌍 Global: {signal.get('global_sentiment', 'NEUTRAL')}\n\n"
            f"<b>Why BUY:</b>\n{reasons}\n\n"
            f"📦 Paper Order: {shares} shares @ ₹{signal['latest_price']}\n"
            f"💵 Investing: ₹{invest:,.0f}\n"
            f"⏰ {datetime.now().strftime('%d %b %Y %H:%M IST')}"
        )
        self.send(msg)

    def alert_sell(self, signal: dict, position: dict, pnl: float):
        pnl_emoji = "✅" if pnl >= 0 else "❌"
        pnl_sign = "+" if pnl >= 0 else ""
        reasons = "\n".join([f"  • {r}" for r in signal.get("reasons", [])[:3]])
        msg = (
            f"🔴 <b>SELL SIGNAL — ALGO•PAPER</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📉 Stock: <b>{signal['symbol']}</b>\n"
            f"💰 Exit Price: ₹{signal['latest_price']}\n"
            f"📊 Score: {signal['score']}/10\n\n"
            f"<b>Why SELL:</b>\n{reasons}\n\n"
            f"📦 Entry: ₹{position.get('entry_price', 0)} × {position.get('shares', 0)} shares\n"
            f"{pnl_emoji} Paper P&amp;L: <b>{pnl_sign}₹{pnl:,.0f}</b>\n"
            f"⏰ {datetime.now().strftime('%d %b %Y %H:%M IST')}"
        )
        self.send(msg)

    def alert_stop_loss(self, symbol: str, entry: float, current: float, shares: int):
        loss = (current - entry) * shares
        msg = (
            f"🛑 <b>STOP LOSS TRIGGERED — ALGO•PAPER</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Stock: <b>{symbol}</b>\n"
            f"Entry: ₹{entry} → Current: ₹{current}\n"
            f"Drop: {((current-entry)/entry*100):.1f}%\n"
            f"❌ Paper Loss: ₹{loss:,.0f}\n"
            f"✅ Position closed to protect capital\n"
            f"⏰ {datetime.now().strftime('%d %b %Y %H:%M IST')}"
        )
        self.send(msg)

    def alert_discovery(self, picks: list):
        if not picks:
            return
        top = picks[0]
        others = ", ".join([p["symbol"].replace(".NS","") for p in picks[1:4]])
        reasons = "\n".join([f"  ⭐ {s}" for s in top.get("signals", [])[:3]])
        msg = (
            f"⭐ <b>DISCOVERY ALERT — NEW STOCKS FOUND</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🏆 Top Pick: <b>{top['symbol']}</b>\n"
            f"💰 Price: ₹{top['latest_price']}\n"
            f"📊 Score: {top['score']}/100\n"
            f"🔢 RSI: {top.get('rsi', 'N/A')}\n"
            f"📅 Outlook: {top.get('outlook', '1-2 weeks')}\n\n"
            f"<b>Why this stock:</b>\n{reasons}\n\n"
            f"📋 Also watching: {others}\n"
            f"⏰ {datetime.now().strftime('%d %b %Y %H:%M IST')}"
        )
        self.send(msg)

    def daily_summary(self, portfolio: dict, signals: dict):
        """Send daily morning summary at 9 AM IST."""
        positions = portfolio.get("positions", [])
        total_value = portfolio.get("total_value", portfolio.get("cash", 0))
        capital = portfolio.get("initial_capital", 100000)
        total_pnl = total_value - capital
        pnl_pct = (total_pnl / capital * 100) if capital > 0 else 0
        pnl_emoji = "📈" if total_pnl >= 0 else "📉"

        buy_signals = [s for s in signals.values() if s.get("action") == "BUY"]
        sell_signals = [s for s in signals.values() if s.get("action") == "SELL"]

        pos_lines = ""
        for pos in positions[:5]:
            p = pos.get("unrealized_pnl", 0)
            pos_lines += f"  • {pos['symbol']}: ₹{pos.get('current_price',0)} ({'+' if p>=0 else ''}₹{p:,.0f})\n"

        msg = (
            f"☀️ <b>DAILY SUMMARY — ALGO•PAPER</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{pnl_emoji} Portfolio: ₹{total_value:,.0f}\n"
            f"{'✅' if total_pnl>=0 else '❌'} Total P&amp;L: {'+' if total_pnl>=0 else ''}₹{total_pnl:,.2f} ({pnl_pct:+.1f}%)\n\n"
            f"<b>Open Positions:</b>\n{pos_lines if pos_lines else '  None\n'}\n"
            f"<b>Today's Signals:</b>\n"
            f"  🟢 BUY: {', '.join([s['symbol'].replace('.NS','') for s in buy_signals]) or 'None'}\n"
            f"  🔴 SELL: {', '.join([s['symbol'].replace('.NS','') for s in sell_signals]) or 'None'}\n\n"
            f"⏰ {datetime.now().strftime('%d %b %Y')} | Market opens 9:15 AM IST"
        )
        self.send(msg)

    def startup_message(self, watchlist: list):
        stocks = ", ".join([s.replace(".NS","") for s in watchlist])
        msg = (
            f"🤖 <b>ALGO•PAPER STARTED</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ System is live and monitoring\n"
            f"📊 Watching: {stocks}\n"
            f"🔄 Price updates: every 15 min\n"
            f"📰 News updates: every 60 min\n"
            f"⭐ Discovery scan: every 6 hours\n\n"
            f"You'll receive alerts for:\n"
            f"  • BUY/SELL signals\n"
            f"  • Stop loss triggers\n"
            f"  • New stock discoveries\n"
            f"  • Daily 9 AM summary\n\n"
            f"⏰ Started: {datetime.now().strftime('%d %b %Y %H:%M IST')}"
        )
        self.send(msg)
