"""
PORTFOLIO AGENT — Automatic Paper Trading Executor
Executes BUY/SELL automatically. Supports live_trader for real orders.
Per-user portfolio isolation via MultiUserManager.
"""
import json, os, logging
from datetime import datetime
from pathlib import Path

log = logging.getLogger("PortfolioAgent")
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

STOP_LOSS_PCT    = float(os.getenv("STOP_LOSS_PCT", "5.0"))
BUY_THRESHOLD    = float(os.getenv("BUY_THRESHOLD", "3.0"))
SELL_THRESHOLD   = float(os.getenv("SELL_THRESHOLD", "-3.0"))
MAX_POSITIONS    = int(os.getenv("MAX_POSITIONS", "5"))

class PortfolioAgent:
    def __init__(self, telegram_agent=None, memory_agent=None):
        self.telegram = telegram_agent
        self.memory   = memory_agent
        self.portfolio = self._load()

    def _load(self) -> dict:
        f = DATA_DIR / "portfolio.json"
        if f.exists():
            return json.loads(f.read_text())
        capital = float(os.getenv("PAPER_CAPITAL","100000"))
        return {
            "initial_capital": capital, "cash": capital,
            "positions": {}, "trade_history": [],
            "total_value": capital, "total_pnl": 0, "total_pnl_pct": 0,
            "created_at": datetime.now().isoformat(),
        }

    def _save(self):
        self.portfolio["last_updated"] = datetime.now().isoformat()
        (DATA_DIR / "portfolio.json").write_text(json.dumps(self.portfolio, indent=2))

    def _update_value(self, current_prices: dict):
        total = self.portfolio["cash"]
        for symbol, pos in self.portfolio["positions"].items():
            price = current_prices.get(symbol, pos["entry_price"])
            pos["current_price"] = price
            pos["unrealized_pnl"] = round((price - pos["entry_price"]) * pos["shares"], 2)
            pos["unrealized_pnl_pct"] = round((price - pos["entry_price"]) / pos["entry_price"] * 100, 2)
            total += price * pos["shares"]
        self.portfolio["total_value"] = round(total, 2)
        self.portfolio["total_pnl"] = round(total - self.portfolio["initial_capital"], 2)
        self.portfolio["total_pnl_pct"] = round(
            self.portfolio["total_pnl"] / self.portfolio["initial_capital"] * 100, 2)

    def execute_signals(self, signals: dict, live_trader=None) -> dict:
        actions = {}
        current_prices = {s: sig["latest_price"] for s, sig in signals.items() if sig.get("latest_price")}
        self._update_value(current_prices)

        for symbol, signal in signals.items():
            action = signal.get("action")
            price  = signal.get("latest_price", 0)
            score  = signal.get("score", 0)
            if not price or price <= 0:
                continue

            # ── STOP LOSS CHECK ──────────────────────────────
            if symbol in self.portfolio["positions"]:
                pos = self.portfolio["positions"][symbol]
                drop_pct = (price - pos["entry_price"]) / pos["entry_price"] * 100
                if drop_pct <= -STOP_LOSS_PCT:
                    log.info(f"STOP LOSS: {symbol} dropped {drop_pct:.1f}%")
                    pnl = self._sell(symbol, price, "STOP_LOSS", signal, live_trader)
                    actions[symbol] = {"action":"STOP_LOSS","price":price,"pnl":pnl}
                    if self.telegram:
                        self.telegram.alert_stop_loss(symbol, pos["entry_price"], price, pos["shares"])
                    continue

            # ── BUY LOGIC ────────────────────────────────────
            if (action == "BUY"
                    and score >= BUY_THRESHOLD
                    and symbol not in self.portfolio["positions"]
                    and len(self.portfolio["positions"]) < MAX_POSITIONS
                    and self.portfolio["cash"] > price * 10):

                shares = int((self.portfolio["cash"] * 0.95) / price)
                if shares > 0:
                    cost = round(shares * price, 2)

                    # Execute via live_trader if available
                    if live_trader:
                        order = live_trader.execute_buy(symbol, shares, price)
                        if order.get("status") == "ERROR":
                            log.error(f"BUY order failed for {symbol}: {order.get('reason')}")
                            continue

                    self.portfolio["cash"] = round(self.portfolio["cash"] - cost, 2)
                    self.portfolio["positions"][symbol] = {
                        "shares": shares, "entry_price": price,
                        "entry_date": datetime.now().isoformat(),
                        "current_price": price, "unrealized_pnl": 0, "unrealized_pnl_pct": 0,
                    }
                    trade = {
                        "type":"BUY","symbol":symbol,"price":price,
                        "shares":shares,"cost":cost,"score":score,
                        "date":datetime.now().isoformat(),"reasons":signal.get("reasons",[])
                    }
                    self.portfolio["trade_history"].append(trade)
                    actions[symbol] = {"action":"BUY","shares":shares,"price":price}
                    log.info(f"BUY: {symbol} @ ₹{price} × {shares} = ₹{cost}")
                    if self.memory:
                        self.memory.record_trade_opened(symbol, signal, {})
                    if self.telegram:
                        self.telegram.alert_buy(signal, self.portfolio)

            # ── SELL LOGIC ───────────────────────────────────
            elif (action == "SELL"
                    and score <= SELL_THRESHOLD
                    and symbol in self.portfolio["positions"]):
                pnl = self._sell(symbol, price, "SIGNAL", signal, live_trader)
                actions[symbol] = {"action":"SELL","price":price,"pnl":pnl}

        self._update_value(current_prices)
        self._save()
        return actions

    def _sell(self, symbol: str, price: float, reason: str, signal: dict, live_trader=None) -> float:
        pos = self.portfolio["positions"].pop(symbol)
        proceeds = round(pos["shares"] * price, 2)
        pnl = round((price - pos["entry_price"]) * pos["shares"], 2)

        if live_trader:
            order = live_trader.execute_sell(symbol, pos["shares"], price)
            if order.get("status") == "ERROR":
                log.error(f"SELL order failed for {symbol}: {order.get('reason')}")
                # Put position back
                self.portfolio["positions"][symbol] = pos
                return 0

        self.portfolio["cash"] = round(self.portfolio["cash"] + proceeds, 2)
        trade = {
            "type":"SELL","symbol":symbol,"price":price,
            "shares":pos["shares"],"proceeds":proceeds,"pnl":pnl,
            "reason":reason,"date":datetime.now().isoformat(),
            "entry_price":pos["entry_price"],"reasons":signal.get("reasons",[])
        }
        self.portfolio["trade_history"].append(trade)
        log.info(f"SELL ({reason}): {symbol} @ ₹{price} | P&L: ₹{pnl}")
        if self.memory:
            self.memory.record_trade_closed(symbol, price, pnl, reason)
        if self.telegram:
            self.telegram.alert_sell(signal, pos, pnl)
        return pnl

    def get_summary(self) -> dict:
        sells = [t for t in self.portfolio["trade_history"] if t["type"]=="SELL"]
        wins  = [t for t in sells if t.get("pnl",0) > 0]
        return {
            **self.portfolio,
            "win_rate": round(len(wins)/len(sells)*100,1) if sells else 0,
            "total_trades": len(self.portfolio["trade_history"]),
            "open_positions": len(self.portfolio["positions"]),
        }
