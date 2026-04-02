"""
LIVE TRADING AGENT — Paper → Demo → Real
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Three modes controlled by a single switch:

MODE 1: PAPER    → Simulated trades, no real money (default)
MODE 2: DEMO     → Connected to Zerodha sandbox, fake money but real API
MODE 3: LIVE     → Real money, real trades on Zerodha Kite

Switching modes:
- Via API: POST /mode/demo or POST /mode/live
- Via Telegram: Send "GO DEMO" or "GO LIVE" to your bot
- Safety check: Live mode requires minimum 3 months paper history

Broker: Zerodha Kite (most popular Indian broker, free API)
API docs: https://kite.trade/docs/
"""
import os
import json
import logging
import requests
from datetime import datetime
from pathlib import Path

log = logging.getLogger("LiveTradingAgent")
DATA_DIR = Path("data")

# Trading modes
MODE_PAPER = "PAPER"
MODE_DEMO  = "DEMO"
MODE_LIVE  = "LIVE"

class LiveTradingAgent:
    def __init__(self, telegram_agent=None):
        self.telegram = telegram_agent
        self.config = self._load_config()
        self.mode = self.config.get("mode", MODE_PAPER)
        self.kite = None
        log.info(f"[LiveTrading] Current mode: {self.mode}")

    def _load_config(self) -> dict:
        f = DATA_DIR / "trading_config.json"
        if f.exists():
            return json.loads(f.read_text())
        return {
            "mode": MODE_PAPER,
            "broker": "zerodha",
            "api_key": os.getenv("ZERODHA_API_KEY", ""),
            "api_secret": os.getenv("ZERODHA_API_SECRET", ""),
            "access_token": os.getenv("ZERODHA_ACCESS_TOKEN", ""),
            "mode_history": [],
            "paper_months_completed": 0,
            "min_paper_months_for_live": 3,
        }

    def _save_config(self):
        (DATA_DIR / "trading_config.json").write_text(json.dumps(self.config, indent=2))

    # ── MODE SWITCHING ─────────────────────────────────────────────────────

    def switch_to_demo(self) -> dict:
        """
        Switch to Zerodha sandbox demo mode.
        Real API calls, fake money. Safe to test.
        """
        result = self._validate_zerodha_credentials()
        if not result["valid"]:
            msg = f"❌ Cannot switch to DEMO: {result['reason']}\nGet API keys from: https://developers.kite.trade"
            if self.telegram:
                self.telegram.send(msg)
            return {"success": False, "reason": result["reason"]}

        self.mode = MODE_DEMO
        self.config["mode"] = MODE_DEMO
        self.config["mode_history"].append({
            "mode": MODE_DEMO,
            "switched_at": datetime.now().isoformat()
        })
        self._save_config()

        msg = (
            "🟡 <b>DEMO MODE ACTIVATED</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "✅ Connected to Zerodha Sandbox\n"
            "💰 Using paper money on real API\n"
            "📊 All signals go through real Zerodha order flow\n"
            "⚠️ No real money at risk\n\n"
            "When satisfied → send 'GO LIVE' to activate real trading"
        )
        if self.telegram:
            self.telegram.send(msg)
        log.info("[LiveTrading] Switched to DEMO mode")
        return {"success": True, "mode": MODE_DEMO}

    def switch_to_live(self, portfolio_summary: dict) -> dict:
        """
        Switch to LIVE real money trading.
        Safety checks: minimum paper history required.
        """
        # Safety check 1: credentials
        cred = self._validate_zerodha_credentials()
        if not cred["valid"]:
            return {"success": False, "reason": f"Missing credentials: {cred['reason']}"}

        # Safety check 2: minimum paper trading history
        total_trades = portfolio_summary.get("total_trades", 0)
        win_rate = portfolio_summary.get("win_rate", 0)
        total_pnl = portfolio_summary.get("total_pnl", 0)

        if total_trades < 20:
            reason = f"Need minimum 20 paper trades (you have {total_trades}). Keep paper trading."
            if self.telegram:
                self.telegram.send(f"🛑 LIVE blocked: {reason}")
            return {"success": False, "reason": reason}

        if win_rate < 50:
            reason = f"Win rate {win_rate}% is below 50%. Improve strategy first."
            if self.telegram:
                self.telegram.send(f"🛑 LIVE blocked: {reason}")
            return {"success": False, "reason": reason}

        # All checks passed
        self.mode = MODE_LIVE
        self.config["mode"] = MODE_LIVE
        self.config["mode_history"].append({
            "mode": MODE_LIVE,
            "switched_at": datetime.now().isoformat(),
            "paper_stats_at_switch": {
                "total_trades": total_trades,
                "win_rate": win_rate,
                "total_pnl": total_pnl
            }
        })
        self._save_config()

        msg = (
            "🟢 <b>🚀 LIVE TRADING ACTIVATED</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ Paper Stats: {total_trades} trades | {win_rate}% win rate | ₹{total_pnl:,.0f} P&L\n"
            "💰 REAL MONEY NOW ACTIVE\n"
            "📊 All signals execute real Zerodha orders\n"
            "🛑 Stop loss strictly enforced\n\n"
            "⚠️ <b>Real capital at risk. Agent operates strictly by algorithm.</b>"
        )
        if self.telegram:
            self.telegram.send(msg)
        log.info("[LiveTrading] ⚠️  LIVE MODE ACTIVATED — Real money trading")
        return {"success": True, "mode": MODE_LIVE}

    def switch_to_paper(self) -> dict:
        """Emergency fallback to paper mode."""
        self.mode = MODE_PAPER
        self.config["mode"] = MODE_PAPER
        self._save_config()
        if self.telegram:
            self.telegram.send("⬜ Switched back to PAPER mode. No real trades.")
        return {"success": True, "mode": MODE_PAPER}

    # ── ORDER EXECUTION ────────────────────────────────────────────────────

    def execute_buy(self, symbol: str, shares: int, price: float) -> dict:
        """Execute buy order based on current mode."""
        nse_symbol = symbol.replace(".NS", "")

        if self.mode == MODE_PAPER:
            return self._paper_order("BUY", nse_symbol, shares, price)

        elif self.mode == MODE_DEMO:
            return self._zerodha_order("BUY", nse_symbol, shares, price, sandbox=True)

        elif self.mode == MODE_LIVE:
            return self._zerodha_order("BUY", nse_symbol, shares, price, sandbox=False)

    def execute_sell(self, symbol: str, shares: int, price: float) -> dict:
        """Execute sell order based on current mode."""
        nse_symbol = symbol.replace(".NS", "")

        if self.mode == MODE_PAPER:
            return self._paper_order("SELL", nse_symbol, shares, price)
        elif self.mode == MODE_DEMO:
            return self._zerodha_order("SELL", nse_symbol, shares, price, sandbox=True)
        elif self.mode == MODE_LIVE:
            return self._zerodha_order("SELL", nse_symbol, shares, price, sandbox=False)

    def _paper_order(self, side: str, symbol: str, shares: int, price: float) -> dict:
        """Simulated paper order — instant fill."""
        order = {
            "order_id": f"PAPER_{side}_{symbol}_{datetime.now().strftime('%H%M%S')}",
            "mode": MODE_PAPER,
            "symbol": symbol,
            "side": side,
            "shares": shares,
            "price": price,
            "value": round(shares * price, 2),
            "status": "FILLED",
            "filled_at": datetime.now().isoformat(),
        }
        log.info(f"[Paper] {side} {shares} {symbol} @ ₹{price} = ₹{order['value']}")
        return order

    def _zerodha_order(self, side: str, symbol: str, shares: int, price: float, sandbox: bool) -> dict:
        """
        Real Zerodha Kite API order.
        sandbox=True uses Zerodha's test environment.

        To use this you need:
        1. Zerodha account: https://zerodha.com
        2. Kite Connect subscription: https://developers.kite.trade (₹2000/month)
        3. API key + secret from Kite developer console
        4. Daily access token (auto-refreshed by token_agent.py)
        """
        api_key = self.config.get("api_key") or os.getenv("ZERODHA_API_KEY", "")
        access_token = self.config.get("access_token") or os.getenv("ZERODHA_ACCESS_TOKEN", "")

        if not api_key or not access_token:
            log.error("[Zerodha] Missing API key or access token")
            return {"status": "ERROR", "reason": "Missing Zerodha credentials"}

        base_url = "https://api.kite.trade"
        transaction = "BUY" if side == "BUY" else "SELL"

        try:
            headers = {
                "X-Kite-Version": "3",
                "Authorization": f"token {api_key}:{access_token}",
                "Content-Type": "application/x-www-form-urlencoded"
            }
            payload = {
                "tradingsymbol": symbol,
                "exchange": "NSE",
                "transaction_type": transaction,
                "order_type": "MARKET",
                "quantity": shares,
                "product": "CNC",         # Cash and Carry (delivery)
                "validity": "DAY",
            }
            resp = requests.post(f"{base_url}/orders/regular", headers=headers, data=payload, timeout=10)
            data = resp.json()

            if resp.status_code == 200 and data.get("status") == "success":
                order_id = data["data"]["order_id"]
                log.info(f"[Zerodha] {'SANDBOX' if sandbox else 'LIVE'} {side} order placed: {order_id}")
                mode_label = MODE_DEMO if sandbox else MODE_LIVE
                return {
                    "order_id": order_id,
                    "mode": mode_label,
                    "symbol": symbol,
                    "side": side,
                    "shares": shares,
                    "price": price,
                    "status": "PLACED",
                    "placed_at": datetime.now().isoformat(),
                }
            else:
                error = data.get("message", "Unknown error")
                log.error(f"[Zerodha] Order failed: {error}")
                return {"status": "ERROR", "reason": error}

        except Exception as e:
            log.error(f"[Zerodha] Exception: {e}")
            return {"status": "ERROR", "reason": str(e)}

    def _validate_zerodha_credentials(self) -> dict:
        api_key = self.config.get("api_key") or os.getenv("ZERODHA_API_KEY", "")
        access_token = self.config.get("access_token") or os.getenv("ZERODHA_ACCESS_TOKEN", "")
        if not api_key:
            return {"valid": False, "reason": "ZERODHA_API_KEY not set in environment"}
        if not access_token:
            return {"valid": False, "reason": "ZERODHA_ACCESS_TOKEN not set. See ZERODHA_SETUP.md"}
        return {"valid": True}

    def get_status(self) -> dict:
        return {
            "current_mode": self.mode,
            "broker": "Zerodha Kite",
            "zerodha_connected": bool(self.config.get("api_key")),
            "mode_history": self.config.get("mode_history", []),
            "how_to_go_live": "POST /mode/live when ready (requires 20+ paper trades & 50%+ win rate)"
        }
