"""
ACCESS CONTROL AGENT
━━━━━━━━━━━━━━━━━━━━
Only whitelisted email addresses can access the application.
Everyone else gets blocked — 403 Forbidden.

How it works:
- API endpoints protected by Bearer token authentication
- Token is tied to email address
- Only emails in ALLOWED_EMAILS list can generate tokens
- Tokens expire every 24 hours for security

Setup:
  Add to Render environment:
  ALLOWED_EMAILS=you@gmail.com,partner@gmail.com,investor@gmail.com
  AUTH_SECRET=any_random_long_string_you_choose
"""
import os
import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger("AccessControl")
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

class AccessControlAgent:
    def __init__(self):
        raw = os.getenv("ALLOWED_EMAILS", "")
        self.allowed_emails = [e.strip().lower() for e in raw.split(",") if e.strip()]
        self.secret = os.getenv("AUTH_SECRET", "changeme_use_a_long_random_string")
        self.sessions = self._load_sessions()

        if not self.allowed_emails:
            log.warning("[Access] No ALLOWED_EMAILS set — all access blocked!")
        else:
            log.info(f"[Access] Whitelist loaded: {len(self.allowed_emails)} email(s)")

    def _load_sessions(self) -> dict:
        f = DATA_DIR / "sessions.json"
        if f.exists():
            return json.loads(f.read_text())
        return {}

    def _save_sessions(self):
        (DATA_DIR / "sessions.json").write_text(json.dumps(self.sessions, indent=2))

    def is_email_allowed(self, email: str) -> bool:
        return email.strip().lower() in self.allowed_emails

    def generate_token(self, email: str) -> dict:
        """Generate access token for a whitelisted email."""
        if not self.is_email_allowed(email):
            return {"success": False, "reason": f"{email} is not in the allowed list"}

        # Create token: HMAC of email + date + secret
        today = datetime.now().strftime("%Y-%m-%d")
        raw = f"{email}:{today}:{self.secret}"
        token = hmac.new(self.secret.encode(), raw.encode(), hashlib.sha256).hexdigest()

        expires = (datetime.now() + timedelta(hours=24)).isoformat()
        self.sessions[token] = {
            "email": email,
            "created_at": datetime.now().isoformat(),
            "expires_at": expires,
        }
        self._save_sessions()
        log.info(f"[Access] Token issued for {email}")
        return {"success": True, "token": token, "expires_at": expires, "email": email}

    def validate_token(self, token: str) -> dict:
        """Validate a Bearer token. Returns email if valid."""
        if not token:
            return {"valid": False, "reason": "No token provided"}

        session = self.sessions.get(token)
        if not session:
            return {"valid": False, "reason": "Invalid token"}

        # Check expiry
        expires = datetime.fromisoformat(session["expires_at"])
        if datetime.now() > expires:
            del self.sessions[token]
            self._save_sessions()
            return {"valid": False, "reason": "Token expired. Request a new one via /auth/login"}

        return {"valid": True, "email": session["email"]}

    def get_whitelist_status(self) -> dict:
        return {
            "allowed_emails": self.allowed_emails,
            "total_allowed": len(self.allowed_emails),
            "active_sessions": len(self.sessions),
            "how_to_add": "Add emails to ALLOWED_EMAILS env variable in Render, comma separated",
        }
