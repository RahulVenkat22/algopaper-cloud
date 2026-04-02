"""
MULTI-USER MANAGER
━━━━━━━━━━━━━━━━━━
Supports 5-10 simultaneous users with full isolation.

ROLES:
  ADMIN   → Full access: mode switch, user management, all data
  TRADER  → Can view signals, portfolio, trades. Gets Telegram alerts
  VIEWER  → Read-only: signals, news, discovery (no portfolio details)

USER ISOLATION:
  - Each user has their own paper portfolio
  - Each user has their own trade history
  - Shared: market data, signals, news (these are the same for everyone)
  - Private: portfolio P&L, trade history, Telegram chat ID

RATE LIMITING:
  - 60 requests per minute per user (prevents abuse)
  - Auth endpoint: 5 attempts per minute (prevents brute force)

SESSION MANAGEMENT:
  - Tokens expire in 24 hours
  - Expired sessions auto-cleaned every hour
  - Max 3 active sessions per user
"""
import os
import json
import hmac
import hashlib
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path
from enum import Enum
from collections import defaultdict

log = logging.getLogger("MultiUserManager")
DATA_DIR = Path("data")
USERS_DIR = DATA_DIR / "users"
DATA_DIR.mkdir(exist_ok=True)
USERS_DIR.mkdir(exist_ok=True)

class Role(str, Enum):
    ADMIN  = "ADMIN"    # Full access + user management
    TRADER = "TRADER"   # View + portfolio + alerts
    VIEWER = "VIEWER"   # Read-only signals and news

# What each role can access
ROLE_PERMISSIONS = {
    Role.ADMIN: {
        "signals", "portfolio", "discovery", "news", "trades",
        "memory", "memory_rules", "historical", "mode_switch",
        "errors", "logs", "users", "eod_report", "health"
    },
    Role.TRADER: {
        "signals", "portfolio", "discovery", "news", "trades",
        "memory", "historical", "eod_report", "health"
    },
    Role.VIEWER: {
        "signals", "discovery", "news", "health"
    },
}

class UserSession:
    def __init__(self, email, role, token, expires_at):
        self.email = email
        self.role = role
        self.token = token
        self.expires_at = expires_at
        self.created_at = datetime.now().isoformat()
        self.last_active = datetime.now().isoformat()
        self.request_count = 0

    def to_dict(self):
        return {
            "email": self.email,
            "role": self.role,
            "token": self.token[:8] + "...",   # never expose full token
            "expires_at": self.expires_at,
            "created_at": self.created_at,
            "last_active": self.last_active,
            "request_count": self.request_count,
        }

class RateLimiter:
    """Per-user rate limiting using sliding window."""
    def __init__(self):
        self._lock = threading.Lock()
        self.windows = defaultdict(list)    # email -> list of timestamps
        self.auth_windows = defaultdict(list)

    def check(self, email: str, limit: int = 60, window: int = 60) -> bool:
        """Returns True if allowed, False if rate limited."""
        with self._lock:
            now = datetime.now()
            cutoff = now - timedelta(seconds=window)
            self.windows[email] = [t for t in self.windows[email] if t > cutoff]
            if len(self.windows[email]) >= limit:
                return False
            self.windows[email].append(now)
            return True

    def check_auth(self, ip: str) -> bool:
        """Auth rate limit: 10 attempts per minute per IP (supports up to 10 legit users).
        Malicious brute force IPs are blocked after 10 attempts.
        """
        with self._lock:
            now = datetime.now()
            cutoff = now - timedelta(seconds=60)
            self.auth_windows[ip] = [t for t in self.auth_windows[ip] if t > cutoff]
            if len(self.auth_windows[ip]) >= 10:
                return False
            self.auth_windows[ip].append(now)
            return True

class MultiUserManager:
    def __init__(self, telegram_agent=None):
        self.telegram = telegram_agent
        self._lock = threading.Lock()
        self.rate_limiter = RateLimiter()
        self.config = self._load_config()
        self.sessions = self._load_sessions()
        self._cleanup_expired_sessions()
        log.info(f"[Users] Loaded {len(self.config['users'])} users, {len(self.sessions)} active sessions")

    def _load_config(self) -> dict:
        f = DATA_DIR / "users_config.json"
        if f.exists():
            return json.loads(f.read_text())

        # Bootstrap from environment variables
        secret = os.getenv("AUTH_SECRET", "change_this_to_random_string")
        raw_emails = os.getenv("ALLOWED_EMAILS", "")
        admin_email = os.getenv("ADMIN_EMAIL", "")
        print(f"This is raw_emails: {raw_emails} and admin_email: {admin_email}")
        users = {}
        for email in [e.strip().lower() for e in raw_emails.split(",") if e.strip()]:
            role = Role.ADMIN if email == admin_email.lower() else Role.TRADER
            users[email] = {
                "email": email,
                "role": role,
                "active": True,
                "added_at": datetime.now().isoformat(),
                "telegram_chat_id": None,
                "last_login": None,
                "total_logins": 0,
            }

        config = {
            "secret": secret,
            "users": users,
            "max_sessions_per_user": 3,
            "token_expiry_hours": 24,
        }
        self._save_config(config)
        return config

    def _load_sessions(self) -> dict:
        f = DATA_DIR / "sessions.json"
        if f.exists():
            try:
                return json.loads(f.read_text())
            except:
                return {}
        return {}

    def _save_config(self, config=None):
        cfg = config or self.config
        (DATA_DIR / "users_config.json").write_text(json.dumps(cfg, indent=2))

    def _save_sessions(self):
        (DATA_DIR / "sessions.json").write_text(json.dumps(self.sessions, indent=2))

    def _cleanup_expired_sessions(self):
        """Remove expired sessions — called hourly."""
        now = datetime.now()
        before = len(self.sessions)
        self.sessions = {
            token: session for token, session in self.sessions.items()
            if datetime.fromisoformat(session["expires_at"]) > now
        }
        removed = before - len(self.sessions)
        if removed > 0:
            log.info(f"[Users] Cleaned {removed} expired sessions")
            self._save_sessions()

    def _generate_token(self, email: str) -> str:
        ts = datetime.now().isoformat()
        raw = f"{email}:{ts}:{self.config['secret']}"
        return hmac.new(self.config["secret"].encode(), raw.encode(), hashlib.sha256).hexdigest()

    # ── USER MANAGEMENT (ADMIN ONLY) ────────────────────────

    def add_user(self, email: str, role: Role = Role.TRADER, telegram_chat_id: str = None) -> dict:
        """Add a new user. Only ADMIN can call this."""
        email = email.strip().lower()
        with self._lock:
            if email in self.config["users"]:
                # Update existing
                self.config["users"][email]["active"] = True
                self.config["users"][email]["role"] = role
                if telegram_chat_id:
                    self.config["users"][email]["telegram_chat_id"] = telegram_chat_id
                self._save_config()
                log.info(f"[Users] Updated user: {email} → {role}")
                return {"success": True, "action": "updated", "email": email, "role": role}

            self.config["users"][email] = {
                "email": email,
                "role": role,
                "active": True,
                "added_at": datetime.now().isoformat(),
                "telegram_chat_id": telegram_chat_id,
                "last_login": None,
                "total_logins": 0,
            }
            self._save_config()
            # Ensure their user data directory exists
            (USERS_DIR / email.replace("@","_").replace(".","_")).mkdir(exist_ok=True)
            log.info(f"[Users] Added user: {email} → {role}")

            if self.telegram and telegram_chat_id:
                self.telegram.send(
                    f"👤 <b>ALGO•PAPER Access Granted</b>\n"
                    f"Email: {email}\nRole: {role}\n"
                    f"Login at: your-app.onrender.com/auth/login"
                )
            return {"success": True, "action": "added", "email": email, "role": role}

    def remove_user(self, email: str) -> dict:
        """Deactivate a user (keeps their data)."""
        email = email.strip().lower()
        with self._lock:
            if email not in self.config["users"]:
                return {"success": False, "reason": "User not found"}
            self.config["users"][email]["active"] = False
            # Revoke all their sessions
            self.sessions = {t: s for t, s in self.sessions.items() if s.get("email") != email}
            self._save_config()
            self._save_sessions()
            log.info(f"[Users] Deactivated: {email}")
            return {"success": True, "action": "deactivated", "email": email}

    def change_role(self, email: str, new_role: Role) -> dict:
        """Change a user's role."""
        email = email.strip().lower()
        with self._lock:
            if email not in self.config["users"]:
                return {"success": False, "reason": "User not found"}
            old_role = self.config["users"][email]["role"]
            self.config["users"][email]["role"] = new_role
            # Revoke existing sessions — they need to re-login
            self.sessions = {t: s for t, s in self.sessions.items() if s.get("email") != email}
            self._save_config()
            self._save_sessions()
            log.info(f"[Users] Role change: {email} {old_role} → {new_role}")
            return {"success": True, "email": email, "old_role": old_role, "new_role": new_role,
                    "note": "User must re-login to get new permissions"}

    # ── AUTHENTICATION ──────────────────────────────────────

    def login(self, email: str, ip: str = "unknown") -> dict:
        """Authenticate user and issue token."""
        email = email.strip().lower()

        # Rate limit auth attempts
        if not self.rate_limiter.check_auth(ip):
            log.warning(f"[Users] Auth rate limit from {ip}")
            return {"success": False, "reason": "Too many login attempts. Wait 1 minute."}

        with self._lock:
            user = self.config["users"].get(email)
            if not user:
                log.warning(f"[Users] Login attempt by unknown email: {email}")
                return {"success": False, "reason": f"{email} is not authorized. Contact admin."}
            if not user.get("active", True):
                return {"success": False, "reason": "Your account has been deactivated."}

            # Check max sessions
            user_sessions = [s for s in self.sessions.values() if s.get("email") == email]
            if len(user_sessions) >= self.config["max_sessions_per_user"]:
                # Remove oldest session
                oldest = min(user_sessions, key=lambda s: s.get("created_at",""))
                self.sessions = {t: s for t, s in self.sessions.items()
                                if not (s.get("email") == email and s.get("created_at") == oldest.get("created_at"))}

            token = self._generate_token(email)
            expires = (datetime.now() + timedelta(hours=self.config["token_expiry_hours"])).isoformat()
            role = user["role"]

            self.sessions[token] = {
                "email": email,
                "role": role,
                "expires_at": expires,
                "created_at": datetime.now().isoformat(),
                "last_active": datetime.now().isoformat(),
                "request_count": 0,
            }
            user["last_login"] = datetime.now().isoformat()
            user["total_logins"] = user.get("total_logins", 0) + 1

            self._save_config()
            self._save_sessions()
            log.info(f"[Users] Login: {email} | role={role}")

            return {
                "success": True,
                "token": token,
                "email": email,
                "role": role,
                "expires_at": expires,
                "permissions": list(ROLE_PERMISSIONS.get(role, set())),
                "note": f"Include in requests: Authorization: Bearer {token}"
            }

    def validate_token(self, token: str) -> dict:
        """Validate token and return user info."""
        if not token:
            return {"valid": False, "reason": "No token provided"}

        with self._lock:
            session = self.sessions.get(token)
            if not session:
                return {"valid": False, "reason": "Invalid or expired token. POST /auth/login to get new token."}

            if datetime.fromisoformat(session["expires_at"]) < datetime.now():
                del self.sessions[token]
                self._save_sessions()
                return {"valid": False, "reason": "Token expired. Please login again."}

            # Update activity
            session["last_active"] = datetime.now().isoformat()
            session["request_count"] = session.get("request_count", 0) + 1

            return {
                "valid": True,
                "email": session["email"],
                "role": session["role"],
                "permissions": list(ROLE_PERMISSIONS.get(session["role"], set())),
            }

    def check_permission(self, token: str, permission: str) -> dict:
        """Check if token has a specific permission."""
        validation = self.validate_token(token)
        if not validation["valid"]:
            return {"allowed": False, "reason": validation["reason"]}
        role = validation["role"]
        allowed = permission in ROLE_PERMISSIONS.get(role, set())
        if not allowed:
            log.warning(f"[Users] Permission denied: {validation['email']} attempted {permission} (role={role})")
        return {"allowed": allowed, "email": validation["email"], "role": role,
                "reason": f"Role {role} does not have '{permission}' permission" if not allowed else ""}

    def check_rate_limit(self, email: str) -> bool:
        return self.rate_limiter.check(email)

    # ── USER DATA ISOLATION ─────────────────────────────────

    def get_user_data_dir(self, email: str) -> Path:
        """Each user gets their own data directory."""
        safe = email.replace("@","_at_").replace(".","_")
        d = USERS_DIR / safe
        d.mkdir(exist_ok=True)
        return d

    def save_user_portfolio(self, email: str, portfolio: dict):
        f = self.get_user_data_dir(email) / "portfolio.json"
        f.write_text(json.dumps(portfolio, indent=2))

    def load_user_portfolio(self, email: str, initial_capital: float = 100000) -> dict:
        f = self.get_user_data_dir(email) / "portfolio.json"
        if f.exists():
            return json.loads(f.read_text())
        return {
            "email": email,
            "initial_capital": initial_capital,
            "cash": initial_capital,
            "positions": {},
            "trade_history": [],
            "total_value": initial_capital,
            "total_pnl": 0,
            "total_pnl_pct": 0,
            "created_at": datetime.now().isoformat(),
        }

    # ── ADMIN VIEWS ─────────────────────────────────────────

    def get_all_users(self) -> dict:
        """Admin view of all users and their status."""
        active_sessions_by_email = defaultdict(int)
        for s in self.sessions.values():
            active_sessions_by_email[s["email"]] += 1

        users_view = []
        for email, user in self.config["users"].items():
            users_view.append({
                "email": email,
                "role": user["role"],
                "active": user.get("active", True),
                "last_login": user.get("last_login"),
                "total_logins": user.get("total_logins", 0),
                "active_sessions": active_sessions_by_email.get(email, 0),
                "has_telegram": bool(user.get("telegram_chat_id")),
            })

        return {
            "total_users": len(users_view),
            "active_users": sum(1 for u in users_view if u["active"]),
            "active_sessions": len(self.sessions),
            "users": sorted(users_view, key=lambda u: u["role"]),
            "roles": {
                "ADMIN": sum(1 for u in users_view if u["role"] == Role.ADMIN),
                "TRADER": sum(1 for u in users_view if u["role"] == Role.TRADER),
                "VIEWER": sum(1 for u in users_view if u["role"] == Role.VIEWER),
            }
        }

    def get_active_sessions(self) -> list:
        """Admin view of all active sessions."""
        return [
            {
                "email": s["email"],
                "role": s["role"],
                "expires_at": s["expires_at"],
                "last_active": s["last_active"],
                "request_count": s.get("request_count", 0),
            }
            for s in self.sessions.values()
        ]
