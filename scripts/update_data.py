#!/usr/bin/env python3
update_data.py — שכבת הדאטא של הדשבורד
רץ ב-GitHub Actions כל 30 דקות.
Binance חוסמת שרתי GitHub (HTTP 451), לכן: Bybit קודם, Binance גיבוי, CoinCap אחרון.
"""
import json, urllib.request, os, statistics
from datetime import datetime, timezone

BINANCE = "https://api.binance.com"
BYBIT = "https://api.bybit.com"
COINCAP = "https://api.coincap.io"
DATA_DIR = "data"
SKIP = {"USDCUSDT","FDUSDUSDT","TUSDUSDT","DAIUSDT","EURUSDT","TRYUSDT",
        "USDPUSDT","EURIUSDT","WBTCUSDT","XUSDUSDT"}
FUNDING_WANT = ["BTC","ETH","SOL","BNB","XRP","DOGE","ADA","AVAX","LINK","DOT"]
CANDLE_SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
CANDLE_INTERVALS = {"1h": "60", "4h": "240"}
FIAT_SKIP = {"USDT","USDC","DAI","FDUSD","TUSD"}

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "crypto-dashboard/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

def tickers_bybit():
    j = get(BYBIT + "/v5/market/tickers?category=spot")
    coins = []
    for t in j["result"]["list"]:
        s = t["symbol"]
        if not s.endswith("USDT") or s in SKIP:
            continue
        coins.append({
            "symbol": s,
            "price": float(t["lastPrice"]),
            "c24h": float(t["price24hPcnt"]) * 100,
            "vol": float(t.get("turnover24h") or 0),
            "hi": float(t.get("highPrice24h") or 0),
            "lo": float(t.get("lowPrice24h") or 0),
        })
    return coins

def tickers_binance():
    j = get(BINANCE + "/api/v3/ticker/24hr")
    return [{
        "symbol": t["symbol"],
        "price": float(t["lastPrice"]),
        "c24h": float(t["priceChangePercent"]),
        "vol": float(t["quoteVolume"]),
        "hi": float(t["highPrice"]), "lo": float(t["lowPrice"]),
    } for t in j if t["symbol"].endswith("USDT") and t["symbol"] not in SKIP]

def tickers_coincap():
    j = get(COINCAP + "/v2/assets?limit=150")
    return [{
        "symbol": c["symbol"] + "USDT",
        "price": float(c["priceUsd"]),
        "c24h": float(c.get("changePercent24Hr") or 0),
        "vol": float(c.get("volumeUsd24Hr") or 0),
        "hi": 0, "lo": 0,
    } for c in j["data"] if c["symbol"] not in FIAT_SKIP]

def get_tickers():
    for name, fn in [("bybit", tickers_bybit), ("binance", tickers_binance),
                     ("coincap", tickers_coincap)]:
        try:
            coins = fn()
            if coins:
                print("tickers source:", name)
                return coins
        except Exception as e:
            print(name, "failed:", e)
    raise RuntimeError("all ticker sources failed")

def klines(symbol, interval="1h", limit=200):
    iv = CANDLE_INTERVALS.get(interval)
    if iv:
        try:
            j = get(f"{BYBIT}/v5/market/kline?category=spot&symbol={symbol}"
                    f"&interval={iv}&limit={limit}")
            rows = j["result"]["list"]
            rows = rows[::-1]
            return [[float(v) for v in r[:6]] for r in rows]
        except Exception as e:
            print("bybit klines failed:", symbol, e)
    k = get(f"{BINANCE}/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}")
    return [[float(v) for v in x[:6]] for x in k]

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
        h, l, pc = k[i][2], k[i][3], k[i-1][4]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    a = statistics.mean(trs[:period])
    for i in range(period, len(trs)):
        a = (a * (period - 1) + trs[i]) / period
    close = k[-1][4]
    return a / close * 100 if close else 0.0

def vol_z(vols, lookback=20):
    if len(vols) < lookback * 2:
        return 0.0
    recent = statistics.mean(vols[-lookback:])
    hist = vols[:-lookback]
    mu, sd = statistics.mean(hist), statistics.pstdev(hist)
    return (recent - mu) / sd if sd else 0.0

def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    coins = get_tickers()
    coins.sort(key=lambda t: t["vol"], reverse=True)
    top = coins[:100]

    tickers_out = [{
        "name": t["symbol"].replace("USDT", ""),
        "price": t["price"],
        "c24h": t["c24h"],
        "c1h": 0, "c7d": 0,
        "vol": t["vol"],
        "hi": t["hi"], "lo": t["lo"],
        "mc": 0
    } for t in top]

    top50 = top[:50]
    up = sum(1 for t in top50 if t["c24h"] > 0)
    vol_sum = sum(t["vol"] for t in top50)
    avg = statistics.mean(t["c24h"] for t in top50) if top50 else 0
    btc = next((t for t in top if t["symbol"] == "BTCUSDT"), None)

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
                  "btc": btc["price"] if btc else 0})
    out["snapshots"] = snaps[-90:]

    inds = []
    for t in top[:10]:
        sym = t["symbol"]
        try:
            k = klines(sym)
            vols = [x[5] for x in k]
            closes = [x[4] for x in k]
            inds.append({
                "sym": sym.replace("USDT", ""),
                "price": t["price"],
                "rsi": round(rsi(closes), 1),
                "atrPct": round(atr_pct(k), 2),
                "volZ": round(vol_z(vols), 2),
            })
        except Exception as e:
            print(f"skip indicators {sym}: {e}")
    out["indicators"] = inds

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

    candles = {}
    for sym in CANDLE_SYMS:
        for iv_name in CANDLE_INTERVALS:
            try:
                k = klines(sym, iv_name, 100)
                candles[sym + "_" + iv_name] = [
                    {"t": int(x[0]), "o": x[1], "h": x[2],
                     "l": x[3], "c": x[4], "v": x[5]}
                    for x in k]
            except Exception as e:
                print(f"skip candles {sym} {iv_name}: {e}")
    out["candles"] = candles

    out["tickers"] = tickers_out
    out["updated"] = datetime.now(timezone.utc).isoformat()
    with open(path, "w") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"OK: {len(tickers_out)} tickers")

if __name__ == "__main__":
    main()
