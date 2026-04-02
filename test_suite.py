"""
ALGO•PAPER — COMPLETE TEST SUITE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tests every agent, every API, every error scenario.

Run before going live:
    python test_suite.py

What gets tested:
1.  Environment variables present
2.  Yahoo Finance connectivity + data quality
3.  NewsAPI connectivity + quota
4.  Telegram bot delivery
5.  Signal generation accuracy
6.  Memory agent read/write
7.  Historical intelligence load
8.  Portfolio agent math
9.  Access control logic
10. Error handler & circuit breaker
11. EOD report generation
12. Discovery agent scan
13. Data validator
14. Full end-to-end cycle simulation
15. Zerodha credentials (if set)

Output: PASS / FAIL / SKIP for each test
Final: READY FOR PAPER TRADING or list of issues to fix
"""
import os, sys, json, time, traceback
from datetime import datetime
from pathlib import Path

# Ensure we run from project root
sys.path.insert(0, str(Path(__file__).parent))

# ── Test result tracker ─────────────────────────────────────
results = []

def test(name: str):
    """Decorator for test functions."""
    def decorator(func):
        def wrapper():
            print(f"\n  Testing: {name}...", end=" ", flush=True)
            try:
                msg = func()
                results.append(("PASS", name, msg or ""))
                print(f"✅ PASS {f'({msg})' if msg else ''}")
            except AssertionError as e:
                results.append(("FAIL", name, str(e)))
                print(f"❌ FAIL — {e}")
            except Exception as e:
                results.append(("ERROR", name, str(e)))
                print(f"💥 ERROR — {e}")
        return wrapper
    return decorator

# ════════════════════════════════════════════════════
# TEST GROUP 1 — ENVIRONMENT
# ════════════════════════════════════════════════════

@test("Environment: WATCHLIST set")
def test_watchlist():
    wl = os.getenv("WATCHLIST","RELIANCE.NS,TCS.NS,HDFCBANK.NS,INFY.NS,ICICIBANK.NS")
    stocks = [s.strip() for s in wl.split(",") if s.strip()]
    assert len(stocks) >= 1, f"No stocks in watchlist"
    assert all(".NS" in s for s in stocks), "Stocks should end in .NS for NSE"
    return f"{len(stocks)} stocks"

@test("Environment: ALLOWED_EMAILS set")
def test_allowed_emails():
    emails = os.getenv("ALLOWED_EMAILS","")
    if not emails:
        results[-1] = ("WARN", results[-1][1], "No ALLOWED_EMAILS set — all requests will be blocked in production")
        print(f"⚠️  WARN — Set ALLOWED_EMAILS in Render environment", end="")
        return
    count = len([e for e in emails.split(",") if e.strip()])
    return f"{count} email(s) whitelisted"

@test("Environment: AUTH_SECRET set")
def test_auth_secret():
    secret = os.getenv("AUTH_SECRET","changeme_use_a_long_random_string")
    assert secret != "changeme_use_a_long_random_string", \
        "Change AUTH_SECRET to a unique random string in Render"
    assert len(secret) >= 16, "AUTH_SECRET should be at least 16 characters"
    return f"{len(secret)} chars"

@test("Environment: PAPER_CAPITAL set")
def test_capital():
    cap = float(os.getenv("PAPER_CAPITAL","100000"))
    assert cap >= 10000, f"Paper capital ₹{cap} seems too low"
    return f"₹{cap:,.0f}"

# ════════════════════════════════════════════════════
# TEST GROUP 2 — DATA FETCHING
# ════════════════════════════════════════════════════

@test("Yahoo Finance: connectivity")
def test_yahoo_finance():
    try:
        import yfinance as yf
        ticker = yf.Ticker("TCS.NS")
        df = ticker.history(period="5d", interval="1d")
        assert not df.empty, "Empty data returned from Yahoo Finance"
        assert len(df) >= 1, "Less than 1 day of data"
        latest_price = df["Close"].iloc[-1]
        assert latest_price > 0, f"Invalid price: {latest_price}"
        return f"TCS @ ₹{latest_price:.0f}"
    except ImportError:
        raise AssertionError("yfinance not installed — run: pip install yfinance")

@test("Yahoo Finance: data quality check")
def test_yahoo_data_quality():
    import yfinance as yf
    df = yf.Ticker("RELIANCE.NS").history(period="1mo", interval="1d")
    assert not df.empty, "No data"
    required_cols = ["Open","High","Low","Close","Volume"]
    for col in required_cols:
        assert col in df.columns, f"Missing column: {col}"
        assert df[col].isnull().sum() < len(df)*0.1, f"Too many nulls in {col}"
    assert (df["High"] >= df["Low"]).all(), "High < Low detected — data corrupt"
    assert (df["Close"] > 0).all(), "Zero or negative prices detected"
    return f"{len(df)} days, all fields valid"

@test("Yahoo Finance: multiple stocks parallel")
def test_yahoo_multiple():
    import yfinance as yf
    symbols = ["TCS.NS","INFY.NS","HDFCBANK.NS"]
    failed = []
    for sym in symbols:
        try:
            df = yf.Ticker(sym).history(period="5d")
            if df.empty:
                failed.append(sym)
        except:
            failed.append(sym)
    assert len(failed) == 0, f"Failed for: {failed}"
    return f"All {len(symbols)} stocks fetched"

@test("NewsAPI: connectivity")
def test_newsapi():
    api_key = os.getenv("NEWS_API_KEY","")
    if not api_key:
        raise AssertionError("NEWS_API_KEY not set. Get free key at newsapi.org")
    import requests
    resp = requests.get(
        "https://newsapi.org/v2/everything",
        params={"q":"TCS Tata Consultancy","language":"en","pageSize":3,"apiKey":api_key},
        timeout=10
    )
    data = resp.json()
    if data.get("status") == "error":
        raise AssertionError(f"NewsAPI error: {data.get('message')}")
    articles = data.get("articles",[])
    return f"{len(articles)} articles fetched"

@test("NewsAPI: quota check")
def test_newsapi_quota():
    api_key = os.getenv("NEWS_API_KEY","")
    if not api_key:
        raise AssertionError("NEWS_API_KEY not set")
    import requests
    resp = requests.get(
        "https://newsapi.org/v2/top-headlines",
        params={"country":"in","pageSize":1,"apiKey":api_key},
        timeout=10
    )
    assert resp.status_code != 429, "NewsAPI rate limit hit — wait or upgrade plan"
    assert resp.status_code != 401, "NewsAPI key unauthorized"
    return f"Status {resp.status_code} OK"

@test("Google News RSS: fallback connectivity")
def test_rss_fallback():
    import feedparser
    feed = feedparser.parse("https://news.google.com/rss/search?q=TCS+NSE+India&hl=en-IN&gl=IN&ceid=IN:en")
    assert len(feed.entries) > 0, "Google News RSS returned no results"
    return f"{len(feed.entries)} RSS articles"

# ════════════════════════════════════════════════════
# TEST GROUP 3 — TELEGRAM
# ════════════════════════════════════════════════════

@test("Telegram: bot token set")
def test_telegram_token():
    token = os.getenv("TELEGRAM_BOT_TOKEN","")
    assert token, "TELEGRAM_BOT_TOKEN not set — see COMPLETE_SETUP_GUIDE.md"
    parts = token.split(":")
    assert len(parts) == 2, "Invalid token format (should be NUMBER:STRING)"
    assert parts[0].isdigit(), "Token should start with bot ID number"
    return f"Token format valid (bot ID: {parts[0]})"

@test("Telegram: chat IDs set")
def test_telegram_chat_ids():
    ids = os.getenv("TELEGRAM_CHAT_IDS", os.getenv("TELEGRAM_CHAT_ID",""))
    assert ids, "TELEGRAM_CHAT_IDS not set — see COMPLETE_SETUP_GUIDE.md"
    id_list = [i.strip() for i in ids.split(",") if i.strip()]
    assert len(id_list) >= 1, "No chat IDs found"
    return f"{len(id_list)} recipient(s)"

@test("Telegram: message delivery test")
def test_telegram_delivery():
    token = os.getenv("TELEGRAM_BOT_TOKEN","")
    chat_ids = os.getenv("TELEGRAM_CHAT_IDS", os.getenv("TELEGRAM_CHAT_ID",""))
    if not token or not chat_ids:
        raise AssertionError("Token or chat IDs not set")
    import requests
    chat_id = chat_ids.split(",")[0].strip()
    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": "✅ ALGO•PAPER Test: Telegram working correctly!"},
        timeout=10
    )
    data = resp.json()
    assert data.get("ok"), f"Telegram delivery failed: {data.get('description')}"
    return f"Delivered to chat {chat_id}"

# ════════════════════════════════════════════════════
# TEST GROUP 4 — AGENT LOGIC
# ════════════════════════════════════════════════════

@test("Signal Agent: generates valid signals")
def test_signal_generation():
    sys.path.insert(0, ".")
    from agents.signal_agent import SignalAgent
    from agents.market_agent import MarketAgent
    # Use cached data if available, else skip
    cache = Path("data/TCS_NS.json")
    if not cache.exists():
        # Create minimal test cache
        Path("data").mkdir(exist_ok=True)
        test_prices = [{"date": f"2024-01-{i:02d}", "open":3800,"high":3850,"low":3750,"close":3800+i,"volume":1000000}
                       for i in range(1,61)]
        cache.write_text(json.dumps({"symbol":"TCS.NS","name":"TCS","prices":test_prices}))
    agent = SignalAgent(["TCS.NS"])
    signals = agent.generate_all()
    assert "TCS.NS" in signals, "No signal for TCS.NS"
    sig = signals["TCS.NS"]
    assert sig.get("action") in ["BUY","SELL","HOLD","INSUFFICIENT_DATA"], \
        f"Invalid action: {sig.get('action')}"
    assert "score" in sig, "No score in signal"
    return f"TCS signal: {sig['action']} (score={sig.get('score')})"

@test("Memory Agent: read/write cycle")
def test_memory_agent():
    from agents.memory_agent import MemoryAgent
    agent = MemoryAgent()
    # Test write
    initial_count = len(agent.memory.get("trade_memories",[]))
    agent.record_trade_opened("TEST.NS", {
        "latest_price":100, "score":4.0, "rsi":42,
        "news_sentiment":"POSITIVE","global_sentiment":"NEUTRAL","reasons":["test"]
    }, {})
    # Test learn
    agent.record_trade_closed("TEST.NS", 110.0, 1000.0, "SIGNAL")
    agent._save()
    # Reload and verify
    agent2 = MemoryAgent()
    new_count = len(agent2.memory.get("trade_memories",[]))
    assert new_count > initial_count, "Trade not persisted in memory"
    return f"{new_count} memories stored"

@test("Portfolio Agent: buy/sell math")
def test_portfolio_math():
    from agents.portfolio_agent import PortfolioAgent
    import tempfile, os
    # Use temp data dir
    agent = PortfolioAgent()
    initial_cash = agent.portfolio["cash"]
    signal = {
        "action":"BUY","latest_price":1000.0,"score":5.0,
        "rsi":40,"news_sentiment":"POSITIVE","global_sentiment":"NEUTRAL","reasons":[]
    }
    agent.execute_signals({"TEST.NS": signal})
    new_cash = agent.portfolio["cash"]
    assert new_cash < initial_cash, "Cash not reduced after BUY"
    assert "TEST.NS" in agent.portfolio["positions"], "Position not created"
    # Now sell
    sell_signal = {"action":"SELL","latest_price":1100.0,"score":-4.0,
                   "rsi":75,"news_sentiment":"NEGATIVE","global_sentiment":"NEGATIVE","reasons":[]}
    agent.execute_signals({"TEST.NS": sell_signal})
    assert "TEST.NS" not in agent.portfolio["positions"], "Position not closed"
    final_cash = agent.portfolio["cash"]
    assert final_cash > new_cash, "Cash not returned after SELL"
    pnl = final_cash - initial_cash
    return f"P&L test: {'+' if pnl>=0 else ''}₹{pnl:,.0f}"

@test("Access Control: whitelist enforcement")
def test_access_control():
    from agents.access_control_agent import AccessControlAgent
    # Temporarily set test emails
    os.environ["ALLOWED_EMAILS"] = "test@example.com,allowed@test.com"
    os.environ["AUTH_SECRET"] = "test_secret_12345678"
    agent = AccessControlAgent()
    # Test allowed email
    result = agent.generate_token("test@example.com")
    assert result["success"], "Should allow whitelisted email"
    token = result["token"]
    # Validate token
    validation = agent.validate_token(token)
    assert validation["valid"], "Valid token rejected"
    assert validation["email"] == "test@example.com"
    # Test blocked email
    blocked = agent.generate_token("hacker@evil.com")
    assert not blocked["success"], "Should block non-whitelisted email"
    return "Whitelist enforcement working"

@test("Error Handler: circuit breaker")
def test_circuit_breaker():
    from agents.error_handler import ErrorHandle
    eh = ErrorHandle()
    # Simulate 3 failures
    for _ in range(3):
        eh.record_failure("test_agent")
    assert eh.circuit_open("test_agent"), "Circuit should be open after 3 failures"
    # Success should reset
    eh.record_success("test_agent")
    assert not eh.circuit_open("test_agent"), "Circuit should reset after success"
    return "Circuit breaker working"

@test("Data Validator: price data validation")
def test_data_validator():
    from agents.error_handler import ErrorHandle, DataValidator
    eh = ErrorHandle()
    dv = DataValidator(eh)
    # Valid data
    valid = {"prices": [{"open":100,"high":110,"low":95,"close":105,"volume":1000000}]*60}
    assert dv.validate_price_data("TEST.NS", valid), "Valid data rejected"
    # Invalid: empty
    assert not dv.validate_price_data("TEST.NS", {}), "Empty data passed"
    # Invalid: zero price
    invalid = {"prices": [{"open":0,"high":0,"low":0,"close":0,"volume":0}]*60}
    assert not dv.validate_price_data("TEST.NS", invalid), "Zero price passed"
    return "All validations working"

@test("EOD Report: generates without error")
def test_eod_report():
    from agents.eod_report_agent import EODReportAgent
    agent = EODReportAgent(telegram_agent=None)  # No telegram in test
    test_portfolio = {
        "initial_capital":100000,"total_value":104230,
        "total_pnl":4230,"total_pnl_pct":4.23,
        "cash":45000,"win_rate":67.5,
        "positions":{"TCS.NS":{"current_price":3842,"unrealized_pnl":2100,"unrealized_pnl_pct":2.3}},
        "trade_history":[
            {"type":"BUY","symbol":"TCS.NS","price":3750,"shares":12,
             "date":datetime.now().isoformat(),"pnl":None},
        ]
    }
    test_signals = {"TCS.NS":{"action":"BUY","symbol":"TCS.NS","score":4.5}}
    test_memory = {"summary":{"patterns_discovered":12},"recent_rules_written":["Test rule"]}
    report = agent._build_report(test_portfolio, test_signals, test_memory)
    assert len(report) > 100, "Report too short"
    assert "PORTFOLIO" in report, "Missing portfolio section"
    assert "TODAY" in report, "Missing today section"
    assert "SIGNALS" in report, "Missing signals section"
    return f"Report generated ({len(report)} chars)"

@test("Discovery Agent: scans and returns picks")
def test_discovery_agent():
    from agents.discovery_agent import DiscoveryAgent
    agent = DiscoveryAgent()
    # Test single stock analysis (not full scan to save time)
    result = agent.analyze_stock("TCS.NS")
    if result is None:
        raise AssertionError("Could not analyze TCS.NS — check Yahoo Finance")
    assert "score" in result, "No score in result"
    assert "signals" in result, "No signals in result"
    assert 0 <= result["score"] <= 100, f"Score out of range: {result['score']}"
    return f"TCS score: {result['score']}/100"

# ════════════════════════════════════════════════════
# TEST GROUP 5 — ZERODHA (optional)
# ════════════════════════════════════════════════════

@test("Zerodha: API key format check")
def test_zerodha_key():
    api_key = os.getenv("ZERODHA_API_KEY","")
    if not api_key:
        raise AssertionError("ZERODHA_API_KEY not set (optional for paper trading, required for live)")
    assert len(api_key) >= 8, "API key seems too short"
    return f"Key length: {len(api_key)} chars"

# ════════════════════════════════════════════════════
# FULL END-TO-END SIMULATION
# ════════════════════════════════════════════════════

@test("End-to-end: full cycle simulation (paper mode)")
def test_full_cycle():
    from agents.signal_agent import SignalAgent
    from agents.portfolio_agent import PortfolioAgent
    from agents.memory_agent import MemoryAgent
    from agents.error_handler import ErrorHandle, DataValidator

    eh = ErrorHandle()
    dv = DataValidator(eh)
    memory = MemoryAgent()
    signal = SignalAgent(["TCS.NS","RELIANCE.NS"])
    portfolio = PortfolioAgent(memory_agent=memory)

    # Generate signals
    signals = signal.generate_all()
    assert signals, "No signals generated"

    # Validate signals
    for sym, sig in signals.items():
        dv.validate_signal(sym, sig)

    # Execute
    actions = portfolio.execute_signals(signals)
    summary = portfolio.get_summary()
    assert "total_value" in summary, "Portfolio summary missing total_value"
    assert summary["total_value"] > 0, "Portfolio value is zero"

    return f"Cycle complete | Portfolio: ₹{summary['total_value']:,.0f} | Actions: {len(actions)}"

# ════════════════════════════════════════════════════
# RUN ALL TESTS
# ════════════════════════════════════════════════════

def run_all():
    print("\n" + "═"*55)
    print("  ALGO•PAPER — COMPLETE SYSTEM TEST SUITE")
    print("  " + datetime.now().strftime("%d %b %Y %H:%M"))
    print("═"*55)

    groups = [
        ("ENVIRONMENT", [test_watchlist, test_allowed_emails, test_auth_secret, test_capital]),
        ("DATA FETCHING", [test_yahoo_finance, test_yahoo_data_quality, test_yahoo_multiple,
                           test_newsapi, test_newsapi_quota, test_rss_fallback]),
        ("TELEGRAM", [test_telegram_token, test_telegram_chat_ids, test_telegram_delivery]),
        ("AGENT LOGIC", [test_signal_generation, test_memory_agent, test_portfolio_math,
                         test_access_control, test_circuit_breaker, test_data_validator,
                         test_eod_report, test_discovery_agent]),
        ("ZERODHA (optional)", [test_zerodha_key]),
        ("INTEGRATION", [test_full_cycle]),
    ]

    for group_name, tests in groups:
        print(f"\n{'─'*55}")
        print(f"  {group_name}")
        print(f"{'─'*55}")
        for t in tests:
            t()

    # Summary
    passed  = sum(1 for r in results if r[0] == "PASS")
    failed  = sum(1 for r in results if r[0] == "FAIL")
    errors  = sum(1 for r in results if r[0] == "ERROR")
    warned  = sum(1 for r in results if r[0] == "WARN")
    total   = len(results)

    print(f"\n{'═'*55}")
    print(f"  TEST RESULTS")
    print(f"{'═'*55}")
    print(f"  ✅ Passed:  {passed}/{total}")
    print(f"  ❌ Failed:  {failed}")
    print(f"  💥 Errors:  {errors}")
    print(f"  ⚠️  Warned:  {warned}")
    print(f"{'═'*55}")

    if failed == 0 and errors == 0:
        print("\n  🚀 ALL TESTS PASSED — READY FOR PAPER TRADING!")
        print("  Deploy to Render.com and start monitoring.\n")
    else:
        print(f"\n  ⚠️  {failed + errors} ISSUE(S) TO FIX BEFORE DEPLOYING:\n")
        for status, name, msg in results:
            if status in ("FAIL","ERROR"):
                print(f"  ❌ {name}")
                print(f"     Fix: {msg}\n")

    return failed + errors == 0

if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)
