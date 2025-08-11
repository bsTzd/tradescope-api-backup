# TradeScope Indicators Plus API

A tiny Flask API that returns:
- Live price (dual-source: Alpha Vantage + optional Yahoo/RapidAPI)
- Last 300 OHLCV bars for the chosen intraday interval
- Locally computed indicators: EMA50, EMA200, RSI(14), MACD(12,26,9)

## Endpoints
- `/` health check
- `/get-indicators-plus?symbol=SPY&interval=5min`

## Deploy on Render
1. Push this folder to a public GitHub repo.
2. On render.com → **New Web Service** → connect the repo.
3. Build command: `pip install -r requirements.txt`
4. Start command: `python app.py`
5. Env Vars: set `ALPHA_VANTAGE_KEY` (required). Optionally `YF_API_KEY` for RapidAPI Yahoo Finance.

## Local run
```
pip install -r requirements.txt
export ALPHA_VANTAGE_KEY=YOUR_KEY
python app.py
```
