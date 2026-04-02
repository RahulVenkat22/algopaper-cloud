"""
ALGO•PAPER v6 — Complete Production System
Multi-user + Roles + Rate Limiting + Error Handling + Auto Token Refresh
"""
import os, threading, schedule, time, logging, json
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import uvicorn

Path("logs").mkdir(exist_ok=True)
logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("logs/agent.log"), logging.StreamHandler()])
log = logging.getLogger("ALGOPAPER")

app = FastAPI(title="ALGO•PAPER v6 — Multi-User Trading System")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
DATA_DIR = Path("data"); DATA_DIR.mkdir(exist_ok=True)
WATCHLIST = os.getenv("WATCHLIST","RELIANCE.NS,TCS.NS,HDFCBANK.NS,INFY.NS,ICICIBANK.NS").split(",")

from agents.market_agent import MarketAgent
from agents.news_agent import NewsAgent
from agents.signal_agent import SignalAgent
from agents.discovery_agent import DiscoveryAgent
from agents.telegram_agent import TelegramAgent
from agents.portfolio_agent import PortfolioAgent
from agents.memory_agent import MemoryAgent
from agents.historical_agent import HistoricalIntelligenceAgent
from agents.live_trading_agent import LiveTradingAgent
from agents.eod_report_agent import EODReportAgent
from agents.error_handler import ErrorHandler, DataValidator, HealthMonitor, ErrorCategory, Severity
from agents.multi_user_manager import MultiUserManager, Role
from agents.zerodha_token_agent import ZerodhaTokenAgent

# ── Init all agents ─────────────────────────────────────────
telegram    = TelegramAgent()
error_h     = ErrorHandler(telegram_agent=telegram)
validator   = DataValidator(error_h)
health_mon  = HealthMonitor(error_h, telegram_agent=telegram)
memory      = MemoryAgent()
historical  = HistoricalIntelligenceAgent(memory_agent=memory)
live        = LiveTradingAgent(telegram_agent=telegram)
market      = MarketAgent(WATCHLIST)
news        = NewsAgent(WATCHLIST)
signal      = SignalAgent(WATCHLIST)
discovery   = DiscoveryAgent()
portfolio   = PortfolioAgent(telegram_agent=telegram, memory_agent=memory)
eod         = EODReportAgent(telegram_agent=telegram)
users       = MultiUserManager(telegram_agent=telegram)
zerodha_tok = ZerodhaTokenAgent(telegram_agent=telegram)

security = HTTPBearer(auto_error=False)

# ── Auth dependency factory ─────────────────────────────────
def require_permission(permission: str):
    def dependency(request: Request,
                   credentials: HTTPAuthorizationCredentials = Depends(security)):
        # Dev mode: no emails configured
        if not users.config["users"]:
            return {"email":"dev_mode","role":"ADMIN","permissions":["all"]}
        if not credentials:
            raise HTTPException(401, "Login first: POST /auth/login with your email")
        token = credentials.credentials
        # Rate limit
        session = users.sessions.get(token)
        if session and not users.check_rate_limit(session.get("email","")):
            raise HTTPException(429, "Too many requests. Limit: 60/minute")
        # Permission check
        result = users.check_permission(token, permission)
        if not result["allowed"]:
            raise HTTPException(403, result["reason"])
        return result
    return dependency

# ── PUBLIC endpoints ────────────────────────────────────────

@app.get("/")
def root():
    return {
        "app": "ALGO•PAPER v6",
        "status": "running",
        "mode": live.mode,
        "login": "POST /auth/login  body: {\"email\": \"your@email.com\"}",
        "docs": "/docs"
    }

@app.get("/health")
def health():
    return health_mon.get_health_report()

@app.post("/auth/login")
def login(request: Request, body: dict):
    email = body.get("email","").strip()
    if not email:
        raise HTTPException(400, "Email required")
    ip = request.client.host if request.client else "unknown"
    result = users.login(email, ip=ip)
    if not result["success"]:
        raise HTTPException(403, result["reason"])
    return result

@app.post("/auth/zerodha-refresh")
def zerodha_refresh(body: dict,
                    u=Depends(require_permission("mode_switch"))):
    """Admin exchanges Zerodha request_token for access_token."""
    req_token = body.get("request_token","").strip()
    if not req_token:
        raise HTTPException(400, "request_token required")
    return zerodha_tok.exchange_request_token(req_token)

# ── VIEWER+ endpoints ───────────────────────────────────────

@app.get("/signals")
def get_signals(u=Depends(require_permission("signals"))):
    f=DATA_DIR/"signals.json"
    return json.loads(f.read_text()) if f.exists() else {"error":"No signals yet"}

@app.get("/discovery")
def get_discovery(u=Depends(require_permission("discovery"))):
    f=DATA_DIR/"discovery.json"
    return json.loads(f.read_text()) if f.exists() else {"error":"Not run yet"}

@app.get("/news")
def get_news(u=Depends(require_permission("news"))):
    f=DATA_DIR/"news_cache.json"
    return json.loads(f.read_text()) if f.exists() else {"error":"No news"}

# ── TRADER+ endpoints ───────────────────────────────────────

@app.get("/portfolio")
def get_portfolio(u=Depends(require_permission("portfolio"))):
    """Returns per-user portfolio."""
    email = u.get("email","shared")
    if email in ("dev_mode","shared"):
        return portfolio.get_summary()
    return users.load_user_portfolio(email)

@app.get("/trades")
def get_trades(u=Depends(require_permission("trades"))):
    p = portfolio.get_summary()
    return {"trades":p.get("trade_history",[])[-20:],
            "pnl":p.get("total_pnl"),"win_rate":p.get("win_rate")}

@app.get("/memory")
def get_memory(u=Depends(require_permission("memory"))):
    return memory.get_insights()

@app.get("/historical")
def get_historical(u=Depends(require_permission("historical"))):
    return {"initialized":historical.intel.get("initialized"),
            "lessons":len(historical.intel.get("pre_loaded_lessons",[])),
            "context":historical.get_current_context()}

@app.get("/report/eod")
def trigger_eod(u=Depends(require_permission("eod_report"))):
    _send_eod(); return {"status":"EOD report sent to Telegram"}

# ── ADMIN-ONLY endpoints ────────────────────────────────────

@app.get("/users")
def get_users(u=Depends(require_permission("users"))):
    return users.get_all_users()

@app.get("/users/sessions")
def get_sessions(u=Depends(require_permission("users"))):
    return {"sessions": users.get_active_sessions()}

@app.post("/users/add")
def add_user(body: dict, u=Depends(require_permission("users"))):
    email = body.get("email","")
    role  = body.get("role", Role.TRADER)
    chat_id = body.get("telegram_chat_id")
    if not email: raise HTTPException(400,"email required")
    return users.add_user(email, role, chat_id)

@app.post("/users/remove")
def remove_user(body: dict, u=Depends(require_permission("users"))):
    email = body.get("email","")
    if not email: raise HTTPException(400,"email required")
    return users.remove_user(email)

@app.post("/users/role")
def change_role(body: dict, u=Depends(require_permission("users"))):
    email = body.get("email","")
    role  = body.get("role","")
    if not email or not role: raise HTTPException(400,"email and role required")
    if role not in [Role.ADMIN, Role.TRADER, Role.VIEWER]:
        raise HTTPException(400, f"role must be one of: ADMIN, TRADER, VIEWER")
    return users.change_role(email, role)

@app.get("/mode")
def get_mode(u=Depends(require_permission("mode_switch"))): return live.get_status()

@app.post("/mode/paper")
def set_paper(u=Depends(require_permission("mode_switch"))): return live.switch_to_paper()

@app.post("/mode/demo")
def set_demo(u=Depends(require_permission("mode_switch"))): return live.switch_to_demo()

@app.post("/mode/live")
def set_live(u=Depends(require_permission("mode_switch"))):
    return live.switch_to_live(portfolio.get_summary())

@app.get("/errors")
def get_errors(u=Depends(require_permission("errors"))): return error_h.get_summary()

@app.get("/memory/rules")
def get_rules(u=Depends(require_permission("memory_rules"))):
    return {"rules":memory.memory.get("rule_adjustments",[]),
            "thresholds":memory.memory.get("learned_thresholds",{})}

@app.get("/logs")
def get_logs(u=Depends(require_permission("logs"))):
    f=Path("logs/agent.log")
    return {"logs":f.read_text().splitlines()[-100:]} if f.exists() else {"logs":[]}

@app.get("/report/health")
def trigger_health(u=Depends(require_permission("health"))):
    return health_mon.send_health_summary()

# ── Agent cycles ────────────────────────────────────────────

def run_cycle():
    if error_h.circuit_open("main_cycle"):
        log.warning("Circuit open — skipping cycle"); return
    health_mon.record_cycle_start()
    try:
        hist_ctx    = historical.get_current_context()
        market_data = market.fetch_all()
        news.fetch_all()
        prices = {s:d["prices"][-1]["close"] for s,d in market_data.items() if d and d.get("prices")}
        memory.follow_up_news_outcomes(prices)
        raw = signal.generate_all()
        adjusted = {}
        for sym, sig in raw.items():
            if not validator.validate_signal(sym, sig): continue
            adj = memory.adjust_signal(sig)
            adj["historical_context"] = historical.get_stock_historical_context(sym)
            adj["seasonal_note"] = hist_ctx.get("seasonal_pattern",{}).get("pattern","")
            adjusted[sym] = adj
        (DATA_DIR/"signals.json").write_text(json.dumps(adjusted,indent=2))
        actions = portfolio.execute_signals(adjusted, live_trader=live)
        if actions: log.info(f"Actions: {actions}")
        health_mon.record_cycle_success()
        log.info(f"=== CYCLE OK | mode={live.mode} ===")
    except Exception as e:
        health_mon.record_cycle_failure(e)

def run_discovery():
    if error_h.circuit_open("discovery"): return
    try:
        result = discovery.scan()
        picks = result.get("top_picks",[])
        if picks: telegram.alert_discovery(picks)
        error_h.record_success("discovery")
    except Exception as e:
        error_h.record_failure("discovery")
        log.error(f"Discovery error: {e}")

def _send_eod():
    try:
        f=DATA_DIR/"signals.json"
        sigs=json.loads(f.read_text()) if f.exists() else {}
        eod.generate_and_send(portfolio.get_summary(), sigs, memory.get_insights())
    except Exception as e: log.error(f"EOD error: {e}")

def scheduler_loop():
    schedule.every(15).minutes.do(run_cycle)
    schedule.every(6).hours.do(run_discovery)
    schedule.every().day.at("02:30").do(zerodha_tok.send_daily_login_reminder)  # 8 AM IST
    schedule.every().day.at("03:30").do(lambda: telegram.daily_summary(portfolio.get_summary(), {}))  # 9 AM IST
    schedule.every().day.at("10:30").do(_send_eod)                              # 4 PM IST
    schedule.every().day.at("05:00").do(health_mon.send_health_summary)         # 10:30 AM IST
    schedule.every().hour.do(users._cleanup_expired_sessions)                   # clean sessions
    schedule.every().sunday.at("04:00").do(lambda: telegram.send(memory.get_telegram_weekly_report()))

    log.info("Loading historical intelligence...")
    historical.initialize(WATCHLIST)
    telegram.startup_message(WATCHLIST)
    run_cycle()
    run_discovery()
    log.info(f"ALL SYSTEMS GO | v6 | mode={live.mode} | users={len(users.config['users'])}")

    while True:
        schedule.run_pending()
        health_mon.check_cycle_health()
        time.sleep(30)

threading.Thread(target=scheduler_loop, daemon=True).start()

if __name__=="__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT",8000)), reload=False)
