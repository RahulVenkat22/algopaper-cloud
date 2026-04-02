# 📱 ALGO•PAPER — Complete Setup Guide
### Every step. Every API key. Zero manual trading.

---

## OVERVIEW — What You Need (All Free)

| Service | Purpose | Cost |
|---------|---------|------|
| GitHub | Store your code | Free |
| Render.com | Run 24/7 in cloud | Free |
| newsapi.org | Real stock news | Free |
| Telegram | Phone alerts (BUY/SELL) | Free |
| UptimeRobot | Keep cloud awake 24/7 | Free |

Total cost: ₹0

---

## PART 1 — TELEGRAM BOT SETUP
*This sends BUY/SELL alerts directly to your phone*

### Step 1.1 — Create your Telegram Bot
1. Open Telegram app on your phone
2. Search for: **@BotFather**
3. Tap on BotFather → tap START
4. Type: `/newbot`
5. It asks: "What name?" → type: `AlgoPaper Trading Bot`
6. It asks: "What username?" → type: `algopaper_yourname_bot`
   (must end in _bot, must be unique)
7. BotFather replies with your **BOT TOKEN** — looks like:
   ```
   7234567890:AAHdqTcvCHhvQHh5z6AX-V8Qz1234567890
   ```
8. **SAVE THIS TOKEN** — you need it later

### Step 1.2 — Get your Chat ID
1. Search for your new bot in Telegram (the username you created)
2. Tap START
3. Send any message like: `hello`
4. Now open this URL in your phone browser (replace YOUR_TOKEN):
   ```
   https://api.telegram.org/botYOUR_TOKEN/getUpdates
   ```
5. You will see JSON. Find: `"chat":{"id":123456789}`
6. **SAVE THAT NUMBER** — that is your CHAT_ID

### Step 1.3 — Add second number (optional)
- The other person also opens your bot and sends a message
- Fetch getUpdates again — you'll see a second chat id
- Add both IDs in your .env as: `TELEGRAM_CHAT_IDS=111111,222222`

### Step 1.4 — Test your bot
Open this URL (replace TOKEN and CHAT_ID):
```
https://api.telegram.org/botYOUR_TOKEN/sendMessage?chat_id=YOUR_CHAT_ID&text=AlgoPaper+Connected!
```
You should receive "AlgoPaper Connected!" on Telegram ✅

---

## PART 2 — NEWS API SETUP

### Step 2.1 — Sign up
1. Go to: https://newsapi.org
2. Click "Get API Key" (top right)
3. Fill form: name, email, password
4. Check your email → click verify link
5. Log in → your API key is on the dashboard

**API Key looks like:** `a1b2c3d4e5f6789012345678901234ab`

### Step 2.2 — Free tier limits
- 100 requests/day (our system uses ~12/day) ✅
- No credit card needed ✅

---

## PART 3 — GITHUB SETUP

### Step 3.1 — Create account
1. Go to: https://github.com
2. Click "Sign up"
3. Enter email, password, username
4. Verify email

### Step 3.2 — Create repository
1. Click "+" (top right) → "New repository"
2. Name: `algopaper-cloud`
3. Set to: **Public**
4. Click "Create repository"

### Step 3.3 — Upload your files
1. Click "Add file" → "Upload files"
2. Open the algopaper_cloud folder on your computer
3. Select ALL files and folders inside it
4. Drag them into the GitHub upload area
5. Scroll down → click "Commit changes"

---

## PART 4 — RENDER.COM DEPLOYMENT

### Step 4.1 — Create account
1. Go to: https://render.com
2. Click "Get Started for Free"
3. Click "Continue with GitHub" (easiest)
4. Authorize Render to access your GitHub

### Step 4.2 — Deploy your app
1. Click "New +" → "Web Service"
2. Find `algopaper-cloud` repo → click "Connect"
3. Settings (Render auto-fills from render.yaml):
   - Name: algopaper-cloud
   - Runtime: Python
   - Build: `pip install -r requirements.txt`
   - Start: `python main.py`
4. Click "Create Web Service"
5. Wait 3-5 minutes → status turns GREEN ✅

### Step 4.3 — Add your API keys
In Render dashboard → your service → "Environment" tab:

Click "Add Environment Variable" for each:

| Key | Value |
|-----|-------|
| `NEWS_API_KEY` | your newsapi.org key |
| `TELEGRAM_BOT_TOKEN` | your BotFather token |
| `TELEGRAM_CHAT_IDS` | your chat id (e.g. 123456789) |
| `WATCHLIST` | RELIANCE.NS,TCS.NS,HDFCBANK.NS,INFY.NS,ICICIBANK.NS |
| `PAPER_CAPITAL` | 100000 |

Click "Save Changes" → app auto-restarts

### Step 4.4 — Your live URLs
After deploy, your app runs at:
```
https://algopaper-cloud.onrender.com/signals
https://algopaper-cloud.onrender.com/discovery
https://algopaper-cloud.onrender.com/portfolio
```

---

## PART 5 — KEEP IT RUNNING 24/7 (UptimeRobot)

Free tier Render sleeps after 15 min. Fix this:

1. Go to: https://uptimerobot.com
2. Sign up (free)
3. Click "Add New Monitor"
4. Type: HTTP(s)
5. URL: `https://algopaper-cloud.onrender.com/health`
6. Interval: Every 5 minutes
7. Click "Create Monitor"

Now your system NEVER sleeps ✅

---

## PART 6 — WHAT HAPPENS AUTOMATICALLY

Once live, every day you will receive Telegram alerts like:

```
🚀 ALGO•PAPER SIGNAL
━━━━━━━━━━━━━━━━━━
Stock: TCS.NS
Action: BUY
Score: +6.5/10
Price: ₹3,842
RSI: 38 (oversold)
News: POSITIVE
Reason: SMA crossover + volume surge + positive earnings news
━━━━━━━━━━━━━━━━━━
📊 Paper Portfolio: ₹1,04,230 (+4.2%)
```

```
⭐ DISCOVERY ALERT
━━━━━━━━━━━━━━━━━━
New Stock Found: COFORGE.NS
Score: 78/100
Price: ₹1,420
Outlook: 1-2 weeks upside
Why: Volume 2.3x average + bullish MA alignment + IT sector momentum
━━━━━━━━━━━━━━━━━━
Add to watchlist? Reply /add COFORGE.NS
```

```
🔴 SELL SIGNAL
━━━━━━━━━━━━━━━━━━
Stock: INFY.NS
Action: SELL
Reason: RSI overbought (78) + negative news sentiment
Paper P&L on this trade: +₹2,340 ✅
```

---

## YOUR COMPLETE API KEYS CHECKLIST

Before going live, confirm you have all these:

- [ ] Telegram Bot Token (from @BotFather)
- [ ] Telegram Chat ID (from getUpdates URL)
- [ ] NewsAPI Key (from newsapi.org)
- [ ] GitHub repo created and files uploaded
- [ ] Render.com deployed and green
- [ ] UptimeRobot monitor added

**Yahoo Finance — NO KEY NEEDED** (built into yfinance library, free)

---

## ⚠️ PAPER TRADING RULES (Strict Algorithm)

The agent follows these rules automatically — no manual intervention:

1. **Always buy with max 95% of available cash** (keep 5% reserve)
2. **Sell immediately** when score drops below -3
3. **Stop loss**: Auto-sell if position drops 5% from buy price
4. **Never hold** a stock with 2 consecutive SELL signals
5. **Discovery stocks**: Only enter if score ≥ 60/100
6. **No overnight leverage** — paper cash only

---

## ⚠️ DISCLAIMER
All trading is PAPER (simulated) only until you manually enable live trading.
Not financial advice. Validate signals for minimum 3 months before real capital.
