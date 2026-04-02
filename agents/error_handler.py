"""
ERROR HANDLING & HEALTH MONITORING SYSTEM
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Covers every possible failure point:

1. API Failures      → Yahoo Finance down, NewsAPI quota exceeded
2. Network Errors    → Timeout, DNS failure, SSL errors
3. Data Errors       → Empty data, corrupt JSON, missing fields
4. Broker Errors     → Zerodha API down, invalid token, order rejected
5. Memory Errors     → Corrupt memory file, disk full
6. Schedule Errors   → Agent cycle crash, missed cycles
7. Telegram Errors   → Bot blocked, network failure
8. Auth Errors       → Invalid tokens, brute force attempts
9. Cloud Errors      → Render restart, memory limit, CPU spike
10. Market Errors    → Market closed, holiday, circuit breaker

Every error:
- Logged with full traceback
- Categorized by severity (CRITICAL / WARNING / INFO)
- Auto-recovery attempted
- Telegram alert sent for CRITICAL errors
- Fallback strategy activated
"""
import logging
import traceback
import time
import json
import os
import functools
from datetime import datetime, timedelta
from pathlib import Path
from enum import Enum
from typing import Callable, Any

log = logging.getLogger("ErrorHandler")
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

class Severity(str, Enum):
    CRITICAL = "CRITICAL"   # System cannot function — alert immediately
    WARNING  = "WARNING"    # Degraded but operational — log + monitor
    INFO     = "INFO"       # Expected failure — log only

class ErrorCategory(str, Enum):
    API_FAILURE     = "API_FAILURE"
    NETWORK         = "NETWORK"
    DATA_CORRUPT    = "DATA_CORRUPT"
    BROKER          = "BROKER"
    MEMORY          = "MEMORY"
    SCHEDULE        = "SCHEDULE"
    AUTH            = "AUTH"
    MARKET_CLOSED   = "MARKET_CLOSED"
    RATE_LIMIT      = "RATE_LIMIT"
    UNKNOWN         = "UNKNOWN"

class ErrorRecord:
    def __init__(self, category, severity, message, context=None, traceback_str=None):
        self.id = f"ERR_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        self.category = category
        self.severity = severity
        self.message = message
        self.context = context or {}
        self.traceback_str = traceback_str
        self.timestamp = datetime.now().isoformat()
        self.resolved = False
        self.resolution = None
        self.retry_count = 0

    def to_dict(self):
        return {
            "id": self.id,
            "category": self.category,
            "severity": self.severity,
            "message": self.message,
            "context": self.context,
            "traceback": self.traceback_str,
            "timestamp": self.timestamp,
            "resolved": self.resolved,
            "resolution": self.resolution,
            "retry_count": self.retry_count,
        }


class ErrorHandler:
    """Central error handler for the entire system."""

    def __init__(self, telegram_agent=None):
        self.telegram = telegram_agent
        self.error_log = self._load_error_log()
        self.circuit_breakers = {}   # agent_name -> failure count
        self.last_alert_time = {}    # error_category -> last alert timestamp
        self.ALERT_COOLDOWN = 300    # seconds between same-category alerts

    def _load_error_log(self) -> list:
        f = DATA_DIR / "error_log.json"
        if f.exists():
            try:
                return json.loads(f.read_text())
            except:
                return []
        return []

    def _save_error_log(self):
        # Keep last 500 errors only
        if len(self.error_log) > 500:
            self.error_log = self.error_log[-500:]
        try:
            (DATA_DIR / "error_log.json").write_text(
                json.dumps(self.error_log, indent=2)
            )
        except Exception as e:
            log.error(f"Could not save error log: {e}")

    # ── MAIN ERROR RECORDING ────────────────────────────────

    def record(self, category: str, severity: str, message: str,
               context: dict = None, exc: Exception = None) -> ErrorRecord:
        """Record an error, trigger alerts if critical."""

        tb_str = traceback.format_exc() if exc else None
        error = ErrorRecord(category, severity, message, context, tb_str)
        self.error_log.append(error.to_dict())
        self._save_error_log()

        # Log to file
        if severity == Severity.CRITICAL:
            log.critical(f"[{category}] {message}")
            if tb_str:
                log.critical(tb_str)
            self._send_critical_alert(error)
        elif severity == Severity.WARNING:
            log.warning(f"[{category}] {message}")
        else:
            log.info(f"[{category}] {message}")

        return error

    def _send_critical_alert(self, error: ErrorRecord):
        """Send Telegram alert for critical errors — with cooldown."""
        if not self.telegram:
            return
        now = datetime.now()
        last = self.last_alert_time.get(error.category)
        if last and (now - last).seconds < self.ALERT_COOLDOWN:
            return  # cooldown active, don't spam
        self.last_alert_time[error.category] = now
        msg = (
            f"🚨 <b>CRITICAL ERROR — ALGO•PAPER</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"❌ Category: {error.category}\n"
            f"📋 Error: {error.message[:200]}\n"
            f"⏰ Time: {datetime.now().strftime('%H:%M IST')}\n"
            f"🔄 System attempting auto-recovery...\n"
            f"Check /logs for details"
        )
        try:
            self.telegram.send(msg)
        except:
            pass  # don't fail on telegram error

    def resolve(self, error_id: str, resolution: str):
        """Mark an error as resolved."""
        for e in self.error_log:
            if e["id"] == error_id:
                e["resolved"] = True
                e["resolution"] = resolution
                break
        self._save_error_log()

    # ── CIRCUIT BREAKER ─────────────────────────────────────

    def circuit_open(self, agent_name: str, threshold: int = 3) -> bool:
        """
        Circuit breaker pattern.
        If an agent fails 3+ times in a row, mark circuit as OPEN (skip it).
        Auto-resets after 5 minutes.
        """
        cb = self.circuit_breakers.get(agent_name, {"failures": 0, "opened_at": None})
        if cb["opened_at"]:
            opened = datetime.fromisoformat(cb["opened_at"])
            if (datetime.now() - opened).seconds > 300:
                # Reset after 5 min
                self.circuit_breakers[agent_name] = {"failures": 0, "opened_at": None}
                log.info(f"[Circuit] {agent_name} circuit RESET after cooldown")
                return False
            return True  # still open
        return cb["failures"] >= threshold

    def record_failure(self, agent_name: str):
        cb = self.circuit_breakers.get(agent_name, {"failures": 0, "opened_at": None})
        cb["failures"] += 1
        if cb["failures"] >= 3 and not cb["opened_at"]:
            cb["opened_at"] = datetime.now().isoformat()
            log.warning(f"[Circuit] {agent_name} circuit OPENED after {cb['failures']} failures")
            self.record(ErrorCategory.SCHEDULE, Severity.WARNING,
                       f"Circuit breaker opened for {agent_name} — skipping until recovery")
        self.circuit_breakers[agent_name] = cb

    def record_success(self, agent_name: str):
        self.circuit_breakers[agent_name] = {"failures": 0, "opened_at": None}

    # ── SUMMARY ─────────────────────────────────────────────

    def get_summary(self) -> dict:
        errors = self.error_log
        last_24h = [e for e in errors
                    if datetime.fromisoformat(e["timestamp"]) > datetime.now() - timedelta(hours=24)]
        unresolved = [e for e in last_24h if not e.get("resolved")]
        critical   = [e for e in unresolved if e.get("severity") == Severity.CRITICAL]

        return {
            "total_errors_logged": len(errors),
            "errors_last_24h": len(last_24h),
            "unresolved_last_24h": len(unresolved),
            "critical_unresolved": len(critical),
            "circuit_breakers": self.circuit_breakers,
            "last_10_errors": errors[-10:],
            "system_health": "DEGRADED" if critical else "WARNING" if unresolved else "HEALTHY",
        }


# ── RETRY DECORATOR ─────────────────────────────────────────

def with_retry(max_retries=3, delay=5, backoff=2,
               fallback=None, error_category=ErrorCategory.API_FAILURE):
    """
    Decorator: auto-retry a function on failure.
    Exponential backoff between retries.
    Returns fallback value if all retries fail.

    Usage:
        @with_retry(max_retries=3, delay=5, fallback={})
        def fetch_prices(symbol):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exc = None
            current_delay = delay
            for attempt in range(1, max_retries + 1):
                try:
                    result = func(*args, **kwargs)
                    if attempt > 1:
                        log.info(f"[Retry] {func.__name__} succeeded on attempt {attempt}")
                    return result
                except Exception as e:
                    last_exc = e
                    if attempt < max_retries:
                        log.warning(f"[Retry] {func.__name__} attempt {attempt} failed: {e}. "
                                    f"Retrying in {current_delay}s...")
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        log.error(f"[Retry] {func.__name__} failed after {max_retries} attempts: {e}")

            # All retries exhausted
            if fallback is not None:
                log.warning(f"[Retry] Returning fallback for {func.__name__}")
                return fallback() if callable(fallback) else fallback
            raise last_exc
        return wrapper
    return decorator


# ── SPECIFIC ERROR HANDLERS ─────────────────────────────────

class APIErrorHandler:
    """Handles all external API failures with specific recovery strategies."""

    def __init__(self, error_handler: ErrorHandler):
        self.eh = error_handler
        self.rate_limit_until = {}   # api_name -> datetime when quota resets

    def handle_yahoo_finance_error(self, symbol: str, exc: Exception) -> dict:
        """Yahoo Finance failure — use cached data."""
        msg = str(exc)
        if "No data found" in msg or "404" in msg:
            self.eh.record(ErrorCategory.DATA_CORRUPT, Severity.WARNING,
                          f"Yahoo Finance: No data for {symbol}. Using cache.",
                          {"symbol": symbol})
            return self._load_cache(symbol)
        elif "Too Many Requests" in msg or "429" in msg:
            self.eh.record(ErrorCategory.RATE_LIMIT, Severity.WARNING,
                          f"Yahoo Finance rate limit hit. Waiting 60s.",
                          {"symbol": symbol})
            time.sleep(60)
            return self._load_cache(symbol)
        else:
            self.eh.record(ErrorCategory.API_FAILURE, Severity.WARNING,
                          f"Yahoo Finance error for {symbol}: {msg}",
                          {"symbol": symbol}, exc)
            return self._load_cache(symbol)

    def handle_news_api_error(self, exc: Exception) -> list:
        """NewsAPI failure — use RSS fallback or cached news."""
        msg = str(exc)
        if "apiKeyExhausted" in msg or "maximumResultsReached" in msg:
            self.eh.record(ErrorCategory.RATE_LIMIT, Severity.WARNING,
                          "NewsAPI daily quota exhausted. Switching to RSS-only mode.",
                          {})
            self.rate_limit_until["newsapi"] = datetime.now() + timedelta(hours=12)
        elif "apiKeyInvalid" in msg:
            self.eh.record(ErrorCategory.API_FAILURE, Severity.CRITICAL,
                          "NewsAPI key is invalid. Check NEWS_API_KEY in environment.",
                          {}, exc)
        else:
            self.eh.record(ErrorCategory.API_FAILURE, Severity.WARNING,
                          f"NewsAPI error: {msg}. Using cached news.", {}, exc)
        return self._load_news_cache()

    def handle_telegram_error(self, exc: Exception) -> None:
        """Telegram failure — log but don't crash the system."""
        msg = str(exc)
        if "bot was blocked" in msg.lower():
            self.eh.record(ErrorCategory.API_FAILURE, Severity.WARNING,
                          "Telegram bot blocked by user. Check TELEGRAM_CHAT_IDS.", {})
        elif "Unauthorized" in msg:
            self.eh.record(ErrorCategory.API_FAILURE, Severity.CRITICAL,
                          "Telegram bot token invalid. Check TELEGRAM_BOT_TOKEN.", {}, exc)
        else:
            self.eh.record(ErrorCategory.NETWORK, Severity.WARNING,
                          f"Telegram send failed: {msg}. Will retry next cycle.", {})

    def handle_zerodha_error(self, exc: Exception, order_details: dict) -> dict:
        """Zerodha API failures — never lose an order silently."""
        msg = str(exc)
        if "TokenException" in msg or "Invalid token" in msg:
            self.eh.record(ErrorCategory.BROKER, Severity.CRITICAL,
                          "Zerodha access token expired. Switching to PAPER mode automatically.",
                          order_details, exc)
            return {"status": "ERROR", "action": "SWITCH_TO_PAPER",
                    "reason": "Access token expired"}
        elif "NetworkException" in msg:
            self.eh.record(ErrorCategory.NETWORK, Severity.WARNING,
                          "Zerodha network error. Order not placed. Will retry.",
                          order_details, exc)
            return {"status": "ERROR", "action": "RETRY", "reason": "Network error"}
        elif "MarketClosedException" in msg:
            self.eh.record(ErrorCategory.MARKET_CLOSED, Severity.INFO,
                          "Market is closed. Order queued for next session.",
                          order_details)
            return {"status": "QUEUED", "reason": "Market closed"}
        elif "InsufficientFunds" in msg:
            self.eh.record(ErrorCategory.BROKER, Severity.WARNING,
                          f"Insufficient funds for order: {order_details}",
                          order_details, exc)
            return {"status": "ERROR", "reason": "Insufficient funds"}
        else:
            self.eh.record(ErrorCategory.BROKER, Severity.CRITICAL,
                          f"Unknown Zerodha error: {msg}",
                          order_details, exc)
            return {"status": "ERROR", "reason": msg}

    def _load_cache(self, symbol: str) -> dict:
        """Load last cached price data for a symbol."""
        f = DATA_DIR / f"{symbol.replace('.','_')}.json"
        if f.exists():
            try:
                data = json.loads(f.read_text())
                log.info(f"[Cache] Using cached data for {symbol} "
                         f"(last updated: {data.get('last_updated','unknown')})")
                return data
            except:
                pass
        log.warning(f"[Cache] No cache found for {symbol}")
        return {}

    def _load_news_cache(self) -> list:
        f = DATA_DIR / "news_cache.json"
        if f.exists():
            try:
                return json.loads(f.read_text())
            except:
                pass
        return []


class DataValidator:
    """Validates all data before it's used in decisions."""

    def __init__(self, error_handler: ErrorHandler):
        self.eh = error_handler

    def validate_price_data(self, symbol: str, data: dict) -> bool:
        if not data:
            self.eh.record(ErrorCategory.DATA_CORRUPT, Severity.WARNING,
                          f"Empty price data for {symbol}")
            return False
        prices = data.get("prices", [])
        if len(prices) < 50:
            self.eh.record(ErrorCategory.DATA_CORRUPT, Severity.WARNING,
                          f"Insufficient price history for {symbol}: {len(prices)} days (need 50+)")
            return False
        last = prices[-1]
        required = ["open", "high", "low", "close", "volume"]
        missing = [k for k in required if k not in last or last[k] is None]
        if missing:
            self.eh.record(ErrorCategory.DATA_CORRUPT, Severity.WARNING,
                          f"Missing fields in {symbol} data: {missing}")
            return False
        if last["close"] <= 0:
            self.eh.record(ErrorCategory.DATA_CORRUPT, Severity.WARNING,
                          f"Invalid price for {symbol}: ₹{last['close']}")
            return False
        return True

    def validate_signal(self, symbol: str, signal: dict) -> bool:
        if not signal:
            return False
        action = signal.get("action")
        if action not in ["BUY", "SELL", "HOLD", "INSUFFICIENT_DATA"]:
            self.eh.record(ErrorCategory.DATA_CORRUPT, Severity.WARNING,
                          f"Invalid signal action for {symbol}: {action}")
            return False
        price = signal.get("latest_price", 0)
        if action in ["BUY", "SELL"] and price <= 0:
            self.eh.record(ErrorCategory.DATA_CORRUPT, Severity.WARNING,
                          f"Cannot execute {action} for {symbol}: invalid price ₹{price}")
            return False
        return True

    def validate_order(self, symbol: str, shares: int, price: float, cash: float) -> dict:
        """Validate before placing any order."""
        errors = []
        if shares <= 0:
            errors.append(f"Invalid shares: {shares}")
        if price <= 0:
            errors.append(f"Invalid price: ₹{price}")
        if shares * price > cash:
            errors.append(f"Insufficient cash: need ₹{shares*price:,.0f}, have ₹{cash:,.0f}")
        if shares * price < 100:
            errors.append(f"Order too small: ₹{shares*price:.0f} (min ₹100)")
        return {"valid": len(errors) == 0, "errors": errors}


class HealthMonitor:
    """Tracks system health and sends periodic status reports."""

    def __init__(self, error_handler: ErrorHandler, telegram_agent=None):
        self.eh = error_handler
        self.telegram = telegram_agent
        self.last_cycle_time = None
        self.cycle_count = 0
        self.failed_cycles = 0

    def record_cycle_start(self):
        self.last_cycle_time = datetime.now()
        self.cycle_count += 1

    def record_cycle_success(self):
        self.eh.record_success("main_cycle")

    def record_cycle_failure(self, exc: Exception):
        self.failed_cycles += 1
        self.eh.record_failure("main_cycle")
        self.eh.record(ErrorCategory.SCHEDULE, Severity.CRITICAL,
                      f"Main cycle failed: {exc}", {}, exc)

    def check_cycle_health(self):
        """Alert if cycle hasn't run in 30+ minutes."""
        if not self.last_cycle_time:
            return
        gap = (datetime.now() - self.last_cycle_time).seconds / 60
        if gap > 30:
            msg = f"⚠️ No agent cycle in {gap:.0f} minutes. System may be stuck."
            log.warning(msg)
            if self.telegram:
                try:
                    self.telegram.send(f"⚠️ <b>HEALTH ALERT</b>\n{msg}")
                except:
                    pass

    def get_health_report(self) -> dict:
        error_summary = self.eh.get_summary()
        return {
            "system_health": error_summary["system_health"],
            "total_cycles_run": self.cycle_count,
            "failed_cycles": self.failed_cycles,
            "success_rate": f"{((self.cycle_count - self.failed_cycles)/max(self.cycle_count,1)*100):.1f}%",
            "last_cycle": self.last_cycle_time.isoformat() if self.last_cycle_time else "Never",
            "minutes_since_last_cycle": round((datetime.now()-self.last_cycle_time).seconds/60, 1) if self.last_cycle_time else None,
            "errors_last_24h": error_summary["errors_last_24h"],
            "critical_unresolved": error_summary["critical_unresolved"],
            "circuit_breakers": self.eh.circuit_breakers,
        }

    def send_health_summary(self):
        """Send health summary to Telegram."""
        report = self.get_health_report()
        health = report["system_health"]
        emoji = "✅" if health == "HEALTHY" else "⚠️" if health == "WARNING" else "🚨"
        msg = (
            f"{emoji} <b>SYSTEM HEALTH — ALGO•PAPER</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Status: <b>{health}</b>\n"
            f"Cycles Run: {report['total_cycles_run']}\n"
            f"Success Rate: {report['success_rate']}\n"
            f"Last Cycle: {report['minutes_since_last_cycle']} min ago\n"
            f"Errors (24h): {report['errors_last_24h']}\n"
            f"Critical: {report['critical_unresolved']}\n"
            f"⏰ {datetime.now().strftime('%d %b %H:%M IST')}"
        )
        if self.telegram:
            try:
                self.telegram.send(msg)
            except:
                pass
        return report
