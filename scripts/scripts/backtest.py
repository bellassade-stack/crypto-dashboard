#!/usr/bin/env python3
"""
backtest.py — בדיקת שתי אסטרטגיות על נרות אמיתיים (1ש, 30 יום)
  1. breakout: כניסת לונג בסגירה מעל מקסימום 20 הנרות הקודמים + נפח > 1.5x ממוצע
  2. meanrev: כניסת לונג ב-RSI(14) < 30, יציאה ב-RSI > 55

כותב data/backtest.json שהדשבורד מציג בטאב המלצות. רץ שבועי.
מקור נרות: Bybit קודם (Binance חוסמת שרתי GitHub עם 451).
"""
import json, urllib.request, os, statistics
from datetime import datetime, timezone

BYBIT = "https://api.bybit.com"
BINANCE = "https://api.binance.com"
FEE = 0.002  # כניסה + יציאה

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "crypto-dashboard/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

def klines(symbol, limit=720):
    try:
        j = get(f"{BYBIT}/v5/market/kline?category=spot&symbol={symbol}"
                f"&interval=60&limit={min(limit, 1000)}")
        rows = j["result"]["list"]
        rows = rows[::-1]
        return [[float(v) for v in r[:6]] for r in rows]
    except Exception:
        pass
    k = get(f"{BINANCE}/api/v3/klines?symbol={symbol}&interval=1h&limit={limit}")
    return [[float(v) for v in x[:6]] for x in k]

def tickers():
    try:
        j = get(BYBIT + "/v5/market/tickers?category=spot")
        coins = [{"symbol": t["symbol"], "vol": float(t.get("turnover24h") or 0)}
                 for t in j["result"]["list"] if t["symbol"].endswith("USDT")]
        if coins:
            return coins
    except Exception:
        pass
    j = get(BINANCE + "/api/v3/ticker/24hr")
    return [{"symbol": t["symbol"], "vol": float(t["quoteVolume"])}
            for t in j if t["symbol"].endswith("USDT")]

def rsi(closes, period=14):
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i-1]
        gains.append(max(d, 0)); losses.append(max(-d, 0))
    ag = statistics.mean(gains[:period]); al = statistics.mean(losses[:period])
    for i in range(period, len(gains)):
        ag = (ag * (period - 1) + gains[i]) / period
        al = (al * (period - 1) + losses[i]) / period
    return 100 - 100 / (1 + ag / al) if al else 100.0

def atr(k, period=14):
    trs = []
    for i in range(1, len(k)):
        h, l, pc = k[i][2], k[i][3], k[i-1][4]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    a = statistics.mean(trs[:period])
    for i in range(period, len(trs)):
        a = (a * (period - 1) + trs[i]) / period
    return a

def backtest_breakout(k):
    trades = []
    for i in range(21, len(k) - 24):
        hh = max(x[2] for x in k[i-20:i])
        vavg = statistics.mean(x[5] for x in k[i-20:i])
        if k[i][4] > hh and k[i][5] > 1.5 * vavg:
            entry = k[i][4]; a = atr(k[:i+1])
            stop = entry - 2 * a
            for j in range(i + 1, min(i + 25, len(k))):
                if k[j][3] <= stop:
                    trades.append((stop / entry - 1 - FEE) * 100); break
                if k[j][4] < statistics.mean(x[4] for x in k[j-20:j]):
                    trades.append((k[j][4] / entry - 1 - FEE) * 100); break
            else:
                j = min(i + 24, len(k) - 1)
                trades.append((k[j][4] / entry - 1 - FEE) * 100)
    return trades

def backtest_meanrev(k):
    closes = [x[4] for x in k]
    trades = []
    i = 15
    while i < len(k) - 2:
        j = i + 1
        if rsi(closes[:i+1]) < 30:
            entry = k[i][4]; a = atr(k[:i+1])
            stop = entry - 2 * a
            for j in range(i + 1, len(k)):
                if k[j][3] <= stop:
                    trades.append((stop / entry - 1 - FEE) * 100); break
                if rsi(closes[:j+1]) > 55:
                    trades.append((k[j][4] / entry - 1 - FEE) * 100); break
        i = j + 1 if j > i else i + 1
    return trades

def stats(name, symbol, trades, days):
    if not trades:
        return None
    wins = [t for t in trades if t > 0]
    gw = sum(wins); gl = abs(sum(t for t in trades if t <= 0))
    return {"strategy": name, "symbol": symbol, "trades": len(trades),
            "winRate": round(len(wins) / len(trades) * 100, 1),
            "expectancy": round(statistics.mean(trades), 2),
            "profitFactor": round(gw / gl, 2) if gl else None,
            "days": days}

def main():
    os.makedirs("data", exist_ok=True)
    coins = tickers()
    coins.sort(key=lambda t: t["vol"], reverse=True)
    results = []
    for t in coins[:15]:
        sym = t["symbol"]
        try:
            k = klines(sym)
            for name, fn in [("breakout", backtest_breakout), ("meanrev", backtest_meanrev)]:
                r = stats(name, sym.replace("USDT", ""), fn(k), 30)
                if r and r["trades"] >= 5:
                    results.append(r)
            print("done", sym)
        except Exception as e:
            print("skip", sym, e)
    with open("data/backtest.json", "w") as f:
        json.dump({"updated": datetime.now(timezone.utc).isoformat(),
                   "results": results}, f, ensure_ascii=False)
    print(f"OK: {len(results)} strategy-results")

if __name__ == "__main__":
    main()
