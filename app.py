from flask import Flask, request, jsonify
import os, requests

app = Flask(__name__)

# --- Environment Keys ---
ALPHA_VANTAGE_KEY = os.getenv("ALPHA_VANTAGE_KEY", "")
YF_API_KEY = os.getenv("YF_API_KEY", None)  # optional (Yahoo Finance via RapidAPI)

AV_BASE = "https://www.alphavantage.co/query"
YF_BASE = "https://yfapi.net/v6/finance/quote"

# --- Indicator helpers ---
def ema(series, period):
    if len(series) < period: return None
    k = 2 / (period + 1)
    e = sum(series[:period]) / period
    for px in series[period:]:
        e = px * k + e * (1 - k)
    return e

def rsi(series, period=14):
    if len(series) < period + 1: return None
    gains, losses = [], []
    for i in range(1, period + 1):
        ch = series[i] - series[i - 1]
        gains.append(max(ch, 0)); losses.append(-min(ch, 0))
    ag = sum(gains) / period; al = sum(losses) / period
    for i in range(period + 1, len(series)):
        ch = series[i] - series[i - 1]
        g = max(ch, 0); l = -min(ch, 0)
        ag = (ag * (period - 1) + g) / period
        al = (al * (period - 1) + l) / period
    if al == 0: return 100.0
    rs = ag / al
    return 100 - (100 / (1 + rs))

def macd(series, fast=12, slow=26, signal=9):
    if len(series) < slow + signal: return None, None, None
    def ema_series(xs, p):
        k = 2 / (p + 1)
        out = []
        e = sum(xs[:p]) / p
        out.extend([None] * (p - 1) + [e])
        for px in xs[p:]:
            e = px * k + e * (1 - k)
            out.append(e)
        return out
    e_fast = ema_series(series, fast)
    e_slow = ema_series(series, slow)
    macd_line = [ (f - s) if f is not None and s is not None else None
                  for f, s in zip(e_fast, e_slow) ]
    ml = [m for m in macd_line if m is not None]
    if len(ml) < signal: return None, None, None
    k = 2 / (signal + 1)
    sig = sum(ml[:signal]) / signal
    sig_series = [sig]
    for v in ml[signal:]:
        sig = v * k + sig * (1 - k)
        sig_series.append(sig)
    macd_last = ml[-1]
    signal_last = sig_series[-1]
    hist_last = macd_last - signal_last
    return macd_last, signal_last, hist_last

# --- Data sources ---
def get_av_intraday(symbol, interval="5min"):
    url = f"{AV_BASE}?function=TIME_SERIES_INTRADAY&symbol={symbol}&interval={interval}&outputsize=full&apikey={ALPHA_VANTAGE_KEY}"
    r = requests.get(url, timeout=30)
    js = r.json()
    key = f"Time Series ({interval})"
    if key not in js:
        raise ValueError(js.get("Note") or js.get("Error Message") or "Alpha Vantage response error")
    items = sorted(js[key].items(), key=lambda x: x[0])[-300:]  # last 300 bars
    ohlcv, closes, last_ts = [], [], None
    for ts, row in items:
        o = float(row["1. open"]); h = float(row["2. high"])
        l = float(row["3. low"]);  c = float(row["4. close"])
        v = int(float(row["5. volume"]))
        ohlcv.append({"t": ts, "o": o, "h": h, "l": l, "c": c, "v": v})
        closes.append(c); last_ts = ts
    return ohlcv, closes, last_ts

def get_av_price(symbol):
    r = requests.get(f"{AV_BASE}?function=GLOBAL_QUOTE&symbol={symbol}&apikey={ALPHA_VANTAGE_KEY}", timeout=15)
    js = r.json()
    return float(js["Global Quote"]["05. price"])

def get_yf_quote(symbol):
    if not YF_API_KEY: return None
    headers = {"X-RapidAPI-Key": YF_API_KEY}
    r = requests.get(f"{YF_BASE}?symbols={symbol}", headers=headers, timeout=15)
    try:
        return float(r.json()["quoteResponse"]["result"][0]["regularMarketPrice"])
    except Exception:
        return None

# --- Endpoints ---
@app.route("/", methods=["GET"])
def root():
    return jsonify({"ok": True, "routes": ["/get-indicators-plus?symbol=AAPL&interval=5min"]})

@app.route("/get-indicators-plus", methods=["GET"])
def get_indicators_plus():
    symbol = request.args.get("symbol", "").upper().strip()
    interval = request.args.get("interval", "5min")
    if not symbol:
        return jsonify({"error": "symbol is required"}), 400
    if not ALPHA_VANTAGE_KEY:
        return jsonify({"error": "ALPHA_VANTAGE_KEY not set"}), 500
    try:
        ohlcv, closes, last_ts = get_av_intraday(symbol, interval)
        ema50  = ema(closes, 50)
        ema200 = ema(closes, 200)
        rsi14  = rsi(closes, 14)
        macd_line, macd_sig, macd_hist = macd(closes, 12, 26, 9)
        rsi_state = "Overbought" if (rsi14 is not None and rsi14 > 70) else ("Oversold" if (rsi14 is not None and rsi14 < 30) else "Neutral")
        macd_state = None
        if macd_line is not None and macd_sig is not None:
            macd_state = "Bullish" if macd_line > macd_sig else "Bearish"

        price_av = get_av_price(symbol)
        price_yf = get_yf_quote(symbol)
        chosen_price = price_av
        chosen_source = "av"
        diff_bps = None
        if price_yf is not None:
            diff_bps = abs(price_av - price_yf) / ((price_av + price_yf) / 2) * 10000
            if diff_bps > 10:
                chosen_price = price_yf
                chosen_source = "yf"

        return jsonify({
            "symbol": symbol,
            "interval": interval,
            "as_of": last_ts,
            "market_state": "UNKNOWN",
            "price": chosen_price,
            "price_source": chosen_source,
            "price_av": price_av,
            "price_yf": price_yf,
            "price_diff_bps": diff_bps,
            "indicators": {
                "ema50": ema50,
                "ema200": ema200,
                "rsi": rsi14,
                "rsi_state": rsi_state,
                "macd": macd_line,
                "macd_signal": macd_sig,
                "macd_hist": macd_hist,
                "macd_state": macd_state
            },
            "ohlcv": ohlcv
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
