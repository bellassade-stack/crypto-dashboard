#!/usr/bin/env python3
"""
update_data.py — שכבת הדאטא של הדשבורד
רץ ב-GitHub Actions כל 30 דקות. בלי ספריות חיצוניות, בלי מפתח API.

כותב data/market.json הכולל:
  tickers    · 100 המטבעות המובילים (מחיר, שינוי 24ש, נפח, high/low)
  snapshots  · snapshot יומי של השוק (עד 90 יום אחורה)
  indicators · RSI(14), ATR(14)% , volume z-score ל-top 10
  funding    · funding rates מ-Bybit
  candles    · 100 נרות 1ש של BTC ו-ETH (לגרף)
"""
import json, urllib.request, os, statistics
from datetime import datetime, timezone

BASE = "https://api.binance.com"
BYBIT = "https://api.bybit.com"
DATA_DIR = "data"
SKIP = {"USDCUSDT","FDUSDUSDT","TUSDUSDT","DAIUSDT","EURUSDT","TRYUSDT",
        "USDPUSDT","EURIUSDT","WBTCUSDT","XUSDUSDT"}
FUNDING_WANT = ["BTC","ETH","SOL","BNB","XRP","DOGE","ADA","AVAX","LINK","DOT"]
CANDLE_SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
CANDLE_INTERVALS = ["1h", "4h"]

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "crypto-dashboard/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

def klines(symbol, interval="1h", limit=200):
    return get(f"{BASE}/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}")

def rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i-1]
        gains.append(max(d, 0)); losses.append(max(-d, 0))
    ag = statistics.mean(gains[:period]); al = statistics.mean(losses[:period])
    for i in range(period, len(gains)):
        ag = (ag * (period - 1) + gains[i]) / period
        al = (al * (period - 1) + losses[i]) / period
    if al == 0:
        return 100.0
    return 100 - 100 / (1 + ag / al)

def atr_pct(k, period=14):
    if len(k) < period + 1:
        return 0.0
    trs = []
    for i in range(1, len(k)):
        h, l, pc = float(k[i][2]), float(k[i][3]), float(k[i-1][4])
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    atr = statistics.mean(trs[:period])
    for i in range(period, len(trs)):
        atr = (atr * (period - 1) + trs[i]) / period
    close = float(k[-1][4])
    return atr / close * 100 if close else 0.0

def vol_z(vols, lookback=20):
    if len(vols) < lookback * 2:
        return 0.0
    recent = statistics.mean(vols[-lookback:])
    hist = vols[:-lookback]
    mu, sd = statistics.mean(hist), statistics.pstdev(hist)
    return (recent - mu) / sd if sd else 0.0

def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    tickers = get(BASE + "/api/v3/ticker/24hr")
    coins = [t for t in tickers
             if t["symbol"].endswith("USDT") and t["symbol"] not in SKIP]
    coins.sort(key=lambda t: float(t["quoteVolume"]), reverse=True)
    top = coins[:100]

    # 1. tickers לדשבורד
    tickers_out = [{
        "name": t["symbol"].replace("USDT", ""),
        "price": float(t["lastPrice"]),
        "c24h": float(t["priceChangePercent"]),
        "c1h": 0, "c7d": 0,
        "vol": float(t["quoteVolume"]),
        "hi": float(t["highPrice"]), "lo": float(t["lowPrice"]),
        "mc": 0
    } for t in top]

    # 2. snapshot יומי
    top50 = coins[:50]
    up = sum(1 for t in top50 if float(t["priceChangePercent"]) > 0)
    vol_sum = sum(float(t["quoteVolume"]) for t in top50)
    avg = statistics.mean(float(t["priceChangePercent"]) for t in top50) if top50 else 0
    btc = next((t for t in coins if t["symbol"] == "BTCUSDT"), None)

    path = os.path.join(DATA_DIR, "market.json")
    out = {"updated": datetime.now(timezone.utc).isoformat(),
           "tickers": [], "snapshots": [], "indicators": [], "funding": {}, "candles": {}}
    if os.path.exists(path):
        with open(path) as f:
            try:
                old = json.load(f)
                out["snapshots"] = old.get("snapshots", [])
            except Exception:
                pass

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    snaps = [s for s in out["snapshots"] if s.get("d") != today]
    snaps.append({"d": today, "up": up, "dn": len(top50) - up,
                  "vol": int(vol_sum), "avg": round(avg, 2),
                  "btc": float(btc["lastPrice"]) if btc else 0})
    out["snapshots"] = snaps[-90:]

    # 3. אינדיקטורים ל-top 10
    inds = []
    for t in coins[:10]:
        sym = t["symbol"]
        try:
            k = klines(sym)
            vols = [float(x[5]) for x in k]
            closes = [float(x[4]) for x in k]
            inds.append({
                "sym": sym.replace("USDT", ""),
                "price": float(t["lastPrice"]),
                "rsi": round(rsi(closes), 1),
                "atrPct": round(atr_pct(k), 2),
                "volZ": round(vol_z(vols), 2),
            })
        except Exception as e:
            print(f"skip indicators {sym}: {e}")
    out["indicators"] = inds

    # 4. funding מ-Bybit
    try:
        j = get(BYBIT + "/v5/market/tickers?category=linear")
        funding = {}
        for t in j.get("result", {}).get("list", []):
            s = t["symbol"].replace("USDT", "")
            if s in FUNDING_WANT:
                funding[s] = float(t["fundingRate"])
        out["funding"] = funding
    except Exception as e:
        print("funding failed:", e)

    # 5. נרות לגרף (5 מטבעות × 2 טווחים, 100 נרות כל אחד)
    candles = {}
    for sym in CANDLE_SYMS:
        for interval in CANDLE_INTERVALS:
            try:
                k = klines(sym, interval, 100)
                candles[sym + "_" + interval] = [
                    {"t": int(x[0]), "o": float(x[1]), "h": float(x[2]),
                     "l": float(x[3]), "c": float(x[4]), "v": float(x[5])}
                    for x in k]
            except Exception as e:
                print(f"skip candles {sym} {interval}: {e}")
    out["candles"] = candles

    out["tickers"] = tickers_out
    out["updated"] = datetime.now(timezone.utc).isoformat()
    with open(path, "w") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"OK: {len(tickers_out)} tickers, {len(out['snapshots'])} snapshots, "
          f"{len(inds)} indicators, {len(out['funding'])} funding, "
          f"{len(out['candles'])} candle sets")

if __name__ == "__main__":
    main()
