# ☁️ ALGO•PAPER CLOUD — Deployment Guide
### Free cloud hosting on Render.com | No credit card needed

---

## What You Get After Deployment

Your system will run 24/7 in the cloud at a URL like:
```
https://algopaper-cloud.onrender.com
```

Available endpoints:
| URL | What it shows |
|-----|--------------|
| /signals | BUY/SELL/HOLD for your 5 stocks |
| /discovery | Top 3-5 stocks predicted to rise next 1-2 weeks |
| /news | Latest news + sentiment for all stocks |
| /portfolio | Paper trading P&L tracker |
| /health | System health check |

---

## Step 1 — Create GitHub Account (if you don't have one)
1. Go to https://github.com
2. Sign up (free)
3. Create a new repository called `algopaper-cloud`
4. Upload all files from this folder

**Easy way to upload:**
- Click "Add file" → "Upload files"
- Drag the entire algopaper_cloud folder contents
- Click "Commit changes"

---

## Step 2 — Create Render Account (Free)
1. Go to https://render.com
2. Sign up with your GitHub account (one click)
3. No credit card needed for free tier

---

## Step 3 — Deploy on Render
1. Click "New +" → "Web Service"
2. Connect your GitHub repo `algopaper-cloud`
3. Render auto-detects render.yaml settings
4. Click "Create Web Service"
5. Wait ~3 minutes for first deploy

---

## Step 4 — Add Your API Keys
In Render dashboard → Your Service → Environment:

| Key | Value | Where to get |
|-----|-------|-------------|
| NEWS_API_KEY | your_key | newsapi.org (free) |
| WATCHLIST | RELIANCE.NS,TCS.NS,... | customize your stocks |
| PAPER_CAPITAL | 100000 | your paper trading amount |

---

## Step 5 — Access Your Live System
After deploy, open your Render URL:
```
https://algopaper-cloud.onrender.com/signals
https://algopaper-cloud.onrender.com/discovery
```

---

## ⚠️ Free Tier Limitations
- Service sleeps after 15 min of no traffic
- **Solution:** Use UptimeRobot (free) to ping /health every 5 min
  → Go to uptimerobot.com → Add monitor → paste your /health URL
  → This keeps it awake 24/7 for FREE

---

## What Each Agent Does (Cloud Version)

### Market Agent — Every 15 minutes
- Connects to Yahoo Finance (no API key needed)
- Downloads real NSE price data
- Stores in data/ folder

### News Agent — Every 60 minutes
- Scans Google News RSS for each stock
- Keywords: company name, CEO name, NSE symbol
- Also monitors: RBI decisions, NIFTY, crude oil, global events
- Scores each article: POSITIVE / NEGATIVE / NEUTRAL

### Signal Agent — After every market/news update
- Combines: technical indicators + news sentiment + global mood
- Score system: -10 to +10
- BUY if score ≥ 3, SELL if ≤ -3, HOLD otherwise

### Discovery Agent — Every 6 hours ⭐ NEW
- Scans 100+ NSE stocks (not just your watchlist)
- Finds stocks with: volume surge + price momentum + bullish MA alignment
- Predicts top 3-5 stocks for next 1-2 weeks
- Completely automated — you just check /discovery

---

## Upgrading Later (When Ready)

When paper trading proves profitable and you have investor capital:

| Plan | Cost | What you get |
|------|------|-------------|
| Render Starter | $7/month | No sleep, faster |
| Render Standard | $25/month | More RAM for bigger universe |
| Add Zerodha Kite API | Free | Real trade execution |

---

## Alternative Free Cloud Options

| Platform | Free Tier | Notes |
|----------|-----------|-------|
| **Render.com** ✅ | 750 hrs/month | Recommended, easiest |
| Railway.app | $5 credit free | Good alternative |
| Fly.io | 3 shared VMs | Slightly complex setup |
| Replit | Always-on (paid) | Easiest but limited free |

---

## ⚠️ Disclaimer
Paper trading only. All signals are for educational purposes.
Not financial advice. Validate for 3+ months before real money.
