"""
ZERODHA TOKEN REFRESH AGENT
━━━━━━━━━━━━━━━━━━━━━━━━━━
Zerodha access tokens expire every day at midnight.
This agent auto-refreshes them so the system never breaks overnight.

How it works:
1. At 8:00 AM IST every day, generates a new login URL
2. Sends it to admin via Telegram
3. Admin clicks → approves → token auto-updated
4. System continues trading without interruption

For fully automated refresh (no clicks):
- Requires Zerodha TOTP secret (2FA automation)
- Uncomment the TOTP section below
"""
import os
import requests
import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path

log = logging.getLogger("ZerodhaTokenAgent")
DATA_DIR = Path("data")

class ZerodhaTokenAgent:
    def __init__(self, telegram_agent=None):
        self.telegram = telegram_agent
        self.api_key = os.getenv("ZERODHA_API_KEY", "")
        self.api_secret = os.getenv("ZERODHA_API_SECRET", "")

    def get_login_url(self) -> str:
        """Generate the daily login URL for token refresh."""
        return f"https://kite.zerodha.com/connect/login?v=3&api_key={self.api_key}"

    def exchange_request_token(self, request_token: str) -> dict:
        """
        Exchange request_token (from redirect URL) for access_token.
        Call this after admin clicks the login link.
        """
        if not self.api_key or not self.api_secret:
            return {"success": False, "reason": "API key/secret not configured"}
        try:
            # Generate checksum
            checksum = hashlib.sha256(
                f"{self.api_key}{request_token}{self.api_secret}".encode()
            ).hexdigest()

            resp = requests.post(
                "https://api.kite.trade/session/token",
                headers={"X-Kite-Version": "3"},
                data={
                    "api_key": self.api_key,
                    "request_token": request_token,
                    "checksum": checksum,
                },
                timeout=10
            )
            data = resp.json()
            if data.get("status") == "success":
                access_token = data["data"]["access_token"]
                # Save to file for system to use
                token_file = DATA_DIR / "zerodha_token.json"
                token_file.write_text(json.dumps({
                    "access_token": access_token,
                    "refreshed_at": datetime.now().isoformat(),
                    "valid_until": datetime.now().strftime("%Y-%m-%d") + "T23:59:59",
                }))
                log.info("[Zerodha] Access token refreshed successfully")
                if self.telegram:
                    self.telegram.send(
                        "✅ <b>Zerodha Token Refreshed</b>\n"
                        "System is connected and ready for trading today."
                    )
                return {"success": True, "access_token": access_token}
            else:
                err = data.get("message", "Unknown error")
                log.error(f"[Zerodha] Token exchange failed: {err}")
                return {"success": False, "reason": err}
        except Exception as e:
            log.error(f"[Zerodha] Token refresh error: {e}")
            return {"success": False, "reason": str(e)}

    def send_daily_login_reminder(self):
        """Send login link to admin at 8 AM IST."""
        if not self.api_key:
            return
        login_url = self.get_login_url()
        msg = (
            "🔑 <b>ZERODHA DAILY TOKEN REFRESH</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Your Zerodha token needs daily refresh.\n\n"
            f"1️⃣ Click: {login_url}\n"
            "2️⃣ Login to Zerodha\n"
            "3️⃣ Copy the 'request_token' from redirect URL\n"
            f"4️⃣ POST to: your-app.onrender.com/auth/zerodha-refresh\n"
            "   Body: {{\"request_token\": \"YOUR_TOKEN\"}}\n\n"
            "⏰ Market opens at 9:15 AM IST"
        )
        if self.telegram:
            self.telegram.send(msg)
        log.info("[Zerodha] Daily token reminder sent")

    def get_current_token(self) -> str:
        """Get current valid access token."""
        # First check environment variable
        env_token = os.getenv("ZERODHA_ACCESS_TOKEN", "")
        if env_token:
            return env_token
        # Then check saved file
        token_file = DATA_DIR / "zerodha_token.json"
        if token_file.exists():
            data = json.loads(token_file.read_text())
            valid_until = datetime.fromisoformat(data.get("valid_until","2000-01-01"))
            if valid_until > datetime.now():
                return data.get("access_token","")
        return ""

    def is_token_valid(self) -> bool:
        return bool(self.get_current_token())
