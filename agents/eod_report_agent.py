"""
END OF DAY REPORT AGENT
━━━━━━━━━━━━━━━━━━━━━━━
Sends a complete daily dashboard to Telegram at 4:00 PM IST (market close).

Report includes:
- All trades executed today (BUY/SELL/STOP LOSS)
- Today's P&L in rupees and percentage
- Portfolio value vs starting capital
- Win/loss breakdown
- Top performing stock today
- Signals that fired but were not traded (held)
- Discovery picks performance
- What the memory agent learned today
- Tomorrow's outlook based on current signals
"""
import json
import logging
from datetime import datetime, date
from pathlib import Path

log = logging.getLogger("EODReport")
DATA_DIR = Path("data")

class EODReportAgent:
    def __init__(self, telegram_agent=None):
        self.telegram = telegram_agent

    def generate_and_send(self, portfolio: dict, signals: dict, memory_insights: dict):
        """Build full end-of-day report and send to Telegram."""
        report_text = self._build_report(portfolio, signals, memory_insights)

        # Split into chunks if too long (Telegram max 4096 chars)
        chunks = self._split_message(report_text, 4000)
        for i, chunk in enumerate(chunks):
            if self.telegram:
                self.telegram.send(chunk)
            log.info(f"[EOD] Sent report chunk {i+1}/{len(chunks)}")

        # Save report to disk
        today = date.today().isoformat()
        report_file = DATA_DIR / f"eod_report_{today}.json"
        report_file.write_text(json.dumps({
            "date": today,
            "generated_at": datetime.now().isoformat(),
            "portfolio_snapshot": portfolio,
            "signals_snapshot": signals,
        }, indent=2))
        log.info(f"[EOD] Daily report saved: {report_file}")

    def _build_report(self, portfolio: dict, signals: dict, memory_insights: dict) -> str:
        today = date.today().isoformat()
        now = datetime.now().strftime("%d %b %Y")

        # ── Portfolio metrics ──────────────────────────────
        initial   = portfolio.get("initial_capital", 100000)
        total_val = portfolio.get("total_value", initial)
        total_pnl = portfolio.get("total_pnl", 0)
        pnl_pct   = portfolio.get("total_pnl_pct", 0)
        cash      = portfolio.get("cash", initial)
        win_rate  = portfolio.get("win_rate", 0)
        positions = portfolio.get("positions", {})
        trades    = portfolio.get("trade_history", [])

        # ── Today's trades ─────────────────────────────────
        today_trades = [t for t in trades if t.get("date","").startswith(today)]
        today_buys   = [t for t in today_trades if t.get("type") == "BUY"]
        today_sells  = [t for t in today_trades if t.get("type") == "SELL"]
        today_pnl    = sum(t.get("pnl", 0) for t in today_sells if t.get("pnl"))

        # ── Signal summary ─────────────────────────────────
        buy_signals  = [s for s in signals.values() if s.get("action") == "BUY"]
        sell_signals = [s for s in signals.values() if s.get("action") == "SELL"]
        hold_signals = [s for s in signals.values() if s.get("action") == "HOLD"]

        # ── Open positions with unrealized P&L ────────────
        pos_lines = ""
        total_unrealized = 0
        for sym, pos in positions.items():
            upnl = pos.get("unrealized_pnl", 0)
            upct = pos.get("unrealized_pnl_pct", 0)
            total_unrealized += upnl
            arrow = "📈" if upnl >= 0 else "📉"
            pos_lines += (
                f"  {arrow} {sym.replace('.NS','')}: ₹{pos.get('current_price',0):.0f} "
                f"({'+' if upnl>=0 else ''}₹{upnl:,.0f} / {upct:+.1f}%)\n"
            )

        # ── Today's trade detail ────────────────────────────
        trade_lines = ""
        for t in today_trades:
            t_type = t.get("type","")
            sym = t.get("symbol","").replace(".NS","")
            price = t.get("price", 0)
            shares = t.get("shares", 0)
            pnl = t.get("pnl")
            if t_type == "BUY":
                trade_lines += f"  🟢 BUY  {sym}: {shares} shares @ ₹{price:.0f} (₹{shares*price:,.0f})\n"
            elif t_type == "SELL":
                pnl_str = f"{'+' if pnl>=0 else ''}₹{pnl:,.0f}" if pnl is not None else ""
                emoji = "✅" if (pnl or 0) >= 0 else "❌"
                trade_lines += f"  🔴 SELL {sym}: {shares} shares @ ₹{price:.0f} {emoji} {pnl_str}\n"

        # ── Memory learning today ───────────────────────────
        rules_today = memory_insights.get("recent_rules_written", [])
        rules_str = "\n".join([f"  💡 {r}" for r in rules_today[:3]]) if rules_today else "  No new rules today"

        # ── Current signals for tomorrow ───────────────────
        tomorrow_buys = ", ".join([s.get("symbol","").replace(".NS","") for s in buy_signals[:3]]) or "None"
        tomorrow_sells = ", ".join([s.get("symbol","").replace(".NS","") for s in sell_signals[:3]]) or "None"

        # ── Build full report ───────────────────────────────
        pnl_emoji = "📈" if total_pnl >= 0 else "📉"
        day_pnl_emoji = "✅" if today_pnl >= 0 else "❌"

        report = f"""📊 <b>END OF DAY REPORT — {now}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

💼 <b>PORTFOLIO SUMMARY</b>
{pnl_emoji} Total Value:   ₹{total_val:,.0f}
📊 Starting:      ₹{initial:,.0f}
{"✅" if total_pnl>=0 else "❌"} Total P&amp;L:    {'+' if total_pnl>=0 else ''}₹{total_pnl:,.0f} ({pnl_pct:+.1f}%)
💵 Cash Left:     ₹{cash:,.0f}
🎯 Win Rate:      {win_rate}%
━━━━━━━━━━━━━━━━━━━━━━━━━━

{day_pnl_emoji} <b>TODAY'S ACTIVITY</b>
📅 Date: {today}
🟢 Buys Today:   {len(today_buys)}
🔴 Sells Today:  {len(today_sells)}
💰 Today's P&amp;L: {'+' if today_pnl>=0 else ''}₹{today_pnl:,.0f}

<b>Trades Executed:</b>
{trade_lines if trade_lines else "  No trades today"}
━━━━━━━━━━━━━━━━━━━━━━━━━━

📂 <b>OPEN POSITIONS ({len(positions)})</b>
{pos_lines if pos_lines else "  No open positions"}
📊 Unrealized P&amp;L: {'+' if total_unrealized>=0 else ''}₹{total_unrealized:,.0f}
━━━━━━━━━━━━━━━━━━━━━━━━━━

🔮 <b>CURRENT SIGNALS</b>
🟢 BUY signals:  {', '.join([s.get('symbol','').replace('.NS','') for s in buy_signals]) or 'None'}
🔴 SELL signals: {', '.join([s.get('symbol','').replace('.NS','') for s in sell_signals]) or 'None'}
⚪ HOLD signals: {', '.join([s.get('symbol','').replace('.NS','') for s in hold_signals]) or 'None'}
━━━━━━━━━━━━━━━━━━━━━━━━━━

🧠 <b>WHAT AGENT LEARNED TODAY</b>
{rules_str}
📚 Total patterns known: {memory_insights.get('summary',{}).get('patterns_discovered', 0)}
━━━━━━━━━━━━━━━━━━━━━━━━━━

🌅 <b>TOMORROW'S OUTLOOK</b>
🟢 Watch to BUY:  {tomorrow_buys}
🔴 Watch to SELL: {tomorrow_sells}
━━━━━━━━━━━━━━━━━━━━━━━━━━
⏰ Report generated: {datetime.now().strftime('%H:%M IST')}
🤖 ALGO•PAPER — Paper Trading Mode"""

        return report

    def _split_message(self, text: str, max_len: int) -> list:
        """Split long message into Telegram-safe chunks."""
        if len(text) <= max_len:
            return [text]
        lines = text.split("\n")
        chunks, current = [], ""
        for line in lines:
            if len(current) + len(line) + 1 > max_len:
                chunks.append(current)
                current = line + "\n"
            else:
                current += line + "\n"
        if current:
            chunks.append(current)
        return chunks
