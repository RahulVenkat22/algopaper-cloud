# Zerodha API Setup — Go from Demo to Live

## Step 1 — Open Zerodha Account (if not already)
1. Go to: https://zerodha.com
2. Sign up → complete KYC (takes 1-2 days)
3. Fund your account with ₹1-2 lakh (from your investors)

## Step 2 — Subscribe to Kite Connect API
1. Go to: https://developers.kite.trade
2. Click "Create New App"
3. Fill: App name = AlgoPaper, App type = Personal
4. Redirect URL = https://your-render-app.onrender.com/auth/callback
5. Pay ₹2000/month subscription
6. You receive: API Key + API Secret

## Step 3 — Add to Render Environment Variables
| Key | Value |
|-----|-------|
| ZERODHA_API_KEY | your api key |
| ZERODHA_API_SECRET | your api secret |
| ZERODHA_ACCESS_TOKEN | generated daily (see Step 4) |

## Step 4 — Access Token (refreshes daily)
Access token expires every day. To automate this:
1. Visit: https://kite.zerodha.com/connect/login?api_key=YOUR_KEY
2. Login → you get a request_token in the URL
3. Exchange for access_token using your API secret
4. Paste in Render environment

(We can build auto-refresh for this as next step)

## Step 5 — Switch to Demo
Call: POST https://your-app.onrender.com/mode/demo

## Step 6 — Go Live (when ready)
Requirements auto-checked:
- Minimum 20 paper trades
- Win rate above 50%
Call: POST https://your-app.onrender.com/mode/live
