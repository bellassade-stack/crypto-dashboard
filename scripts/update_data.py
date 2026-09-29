#!/usr/bin/env python3
# update_data.py - market data pipeline for the crypto dashboard.
# Runs on GitHub Actions every 30 minutes. No API keys needed.
# Sources that allow US cloud traffic: CoinGecko -> Kraken -> CoinCap
# (Binance returns 451, Bybit geo-blocks cloud IPs.)

import json, os, statistics, urllib.request
from datetime import datetime, timezone

COINGECKO = "https://api.coingecko.com/api/v3"
COINBASE = "https://api.exchange.coinbase.com"
KRAKEN = "https://api.kraken.com/0/public"
COINCAP = "https://api.coincap.io/v2"
DATA_DIR = "data"

FIAT = {"USDT", "USDC", "DAI", "FDUSD", "TUSD", "USD", "EUR"}
FUNDING_WANT = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "AVAX", "LINK", "DOT"]
CANDLE_SYMS = ["BTC", "ETH", "SOL", "XRP", "DOGE"]
KRAKEN_PAIRS = {"BTC": "XXBTZUSD", "ETH": "XETHZUSD", "XRP": "XRPUSD",
                "SOL": "SOLUSD", "DOGE": "XDGUSD", "ADA": "ADAUSD",
                "AVAX": "AVAXUSD", "LINK": "LINKUSD", "DOT": "DOTUSD",
                "LTC": "XLTCZUSD"}
KRAKEN_NAME = {"XXBT": "BTC", "XETH": "ETH", "XLTC": "LTC",
               "XXRP": "XRP", "XDG": "DOGE"}


def get(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "crypto-dashboard/1.0",
        "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def tickers_coingecko():
    url = (COINGECKO + "/coins/markets?vs_currency=usd&order=volume_desc"
           "&per_page=100&page=1&sparkline=false"
           "&price_change_percentage=1h,24h,7d")
    j = get(url)
    out = []
    for c in j:
        sym = (c.get("symbol") or "").upper()
        if sym in FIAT:
            continue
        vol = c.get("total_volume") or 0
        if vol < 1000000:
            continue
        out.append({
            "name": sym,
            "price": c.get("current_price") or 0,
            "c1h": c.get("price_change_percentage_1h_in_currency") or 0,
            "c24h": c.get("price_change_percentage_24h") or 0,
            "c7d": c.get("price_change_percentage_7d_in_currency") or 0,
            "vol": vol,
            "hi": c.get("high_24h") or 0,
            "lo": c.get("low_24h") or 0,
        })
    return out


def kraken_base(pair_key):
    if pair_key.endswith("ZUSD"):
        base = pair_key[:-4]
    elif pair_key.endswith("USD"):
        base = pair_key[:-3]
    else:
        base = pair_key
    return KRAKEN_NAME.get(base, base)


def tickers_kraken():
    ap = get(KRAKEN + "/AssetPairs")
    keys, wsname = [], {}
    for k, v in ap.get("result", {}).items():
        ws = v.get("wsname") or ""
        if v.get("status") != "online" or "/" not in ws:
            continue
        base, quote = ws.split("/")
        if quote != "USD" or base in FIAT:
            continue
        if "." in base or len(base) > 6:
            continue
        keys.append(k)
        wsname[k] = base
    out = []
    for i in range(0, len(keys), 40):
        chunk = keys[i:i + 40]
        j = get(KRAKEN + "/Ticker?pair=" + ",".join(chunk))
        for k, t in j.get("result", {}).items():
            try:
                last = float(t["c"][0])
                opn = float(t["o"][0])
                out.append({
                    "name": wsname.get(k, kraken_base(k)),
                    "price": last,
                    "c1h": 0,
                    "c24h": (last - opn) / opn * 100 if opn else 0,
                    "c7d": 0,
                    "vol": float(t["v"][1]),
                    "hi": float(t["h"][0]),
                    "lo": float(t["l"][0]),
                })
            except Exception:
                continue
    return out


def tickers_coincap():
    j = get(COINCAP + "/assets?limit=150")
    out = []
    for c in j.get("data", []):
        sym = (c.get("symbol") or "").upper()
        if sym in FIAT:
            continue
        out.append({
            "name": sym,
            "price": float(c.get("priceUsd") or 0),
            "c1h": 0,
            "c24h": float(c.get("changePercent24Hr") or 0),
            "c7d": 0,
            "vol": float(c.get("volumeUsd24Hr") or 0),
            "hi": 0, "lo": 0,
        })
    return out


def get_tickers():
    for name, fn in [("coingecko", tickers_coingecko),
                     ("kraken", tickers_kraken),
                     ("coincap", tickers_coincap)]:
        try:
            coins = fn()
            if coins:
                print("tickers source:", name, "coins:", len(coins))
                return coins
        except Exception as e:
            print(name, "FAILED:", repr(e))
    raise RuntimeError("all ticker sources failed")


def candles_coinbase(sym, gran=3600):
    j = get(COINBASE + "/products/" + sym + "-USD/candles?granularity=" + str(gran))
    rows = [[r[0], r[3], r[2], r[1], r[4], r[5]] for r in j]
    rows.sort(key=lambda r: r[0])
    return rows


def candles_kraken(sym, minutes=60):
    pair = KRAKEN_PAIRS[sym]
    j = get(KRAKEN + "/OHLC?pair=" + pair + "&interval=" + str(minutes))
    rows = j["result"][pair]
    return [[int(r[0]), float(r[1]), float(r[2]), float(r[3]),
             float(r[4]), float(r[6])] for r in rows]


def klines_1h(sym, limit=200):
    try:
        rows = candles_coinbase(sym)
        if rows:
            return rows[-limit:]
    except Exception as e:
        print("coinbase candles failed", sym, repr(e))
    rows = candles_kraken(sym, 60)
    return rows[-limit:]


def resample_4h(rows):
    out = []
    for i in range(0, len(rows) - 3, 4):
        ch = rows[i:i + 4]
        out.append({
            "t": int(ch[0][0]), "o": ch[0][1],
            "h": max(r[2] for r in ch), "l": min(r[3] for r in ch),
            "c": ch[-1][4], "v": sum(r[5] for r in ch)})
    return out


def rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    ag = statistics.mean(gains[:period])
    al = statistics.mean(losses[:period])
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
        h, l, pc = k[i][2], k[i][3], k[i - 1][4]
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


def get_funding():
    try:
        j = get("https://api.bybit.com/v5/market/tickers?category=linear")
        funding = {}
        for t in j.get("result", {}).get("list", []):
            s = t["symbol"].replace("USDT", "")
            if s in FUNDING_WANT:
                funding[s] = float(t["fundingRate"])
        return funding
    except Exception as e:
        print("funding unavailable:", repr(e))
        return {}


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    coins = get_tickers()
    coins.sort(key=lambda t: t["vol"], reverse=True)
    top = coins[:100]

    tickers_out = []
    seen = set()
    for t in top:
        if t["name"] in seen:
            continue
        seen.add(t["name"])
        tickers_out.append({
            "name": t["name"], "price": t["price"],
            "c1h": t["c1h"], "c24h": t["c24h"], "c7d": t["c7d"],
            "vol": t["vol"], "hi": t["hi"], "lo": t["lo"], "mc": 0})

    top50 = tickers_out[:50]
    up = sum(1 for t in top50 if t["c24h"] > 0)
    vol_sum = sum(t["vol"] for t in top50)
    avg = statistics.mean(t["c24h"] for t in top50) if top50 else 0
    btc = next((t for t in tickers_out if t["name"] == "BTC"), None)

    path = os.path.join(DATA_DIR, "market.json")
    out = {"updated": datetime.now(timezone.utc).isoformat(),
           "tickers": [], "snapshots": [], "indicators": [],
           "funding": {}, "candles": {}}
    if os.path.exists(path):
        try:
            with open(path) as f:
                out["snapshots"] = json.load(f).get("snapshots", [])
        except Exception:
            pass

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    snaps = [s for s in out["snapshots"] if s.get("d") != today]
    snaps.append({"d": today, "up": up, "dn": len(top50) - up,
                  "vol": int(vol_sum), "avg": round(avg, 2),
                  "btc": btc["price"] if btc else 0})
    out["snapshots"] = snaps[-90:]

    inds = []
    for t in tickers_out[:10]:
        sym = t["name"]
        if sym not in KRAKEN_PAIRS and sym not in CANDLE_SYMS:
            continue
        try:
            k = klines_1h(sym)
            vols = [x[5] for x in k]
            closes = [x[4] for x in k]
            inds.append({"sym": sym, "price": t["price"],
                         "rsi": round(rsi(closes), 1),
                         "atrPct": round(atr_pct(k), 2),
                         "volZ": round(vol_z(vols), 2)})
        except Exception as e:
            print("skip indicators", sym, repr(e))
    out["indicators"] = inds

    out["funding"] = get_funding()

    candles = {}
    for sym in CANDLE_SYMS:
        try:
            rows = klines_1h(sym, 100)
            candles[sym + "USDT_1h"] = [
                {"t": int(x[0]), "o": x[1], "h": x[2],
                 "l": x[3], "c": x[4], "v": x[5]} for x in rows]
            candles[sym + "USDT_4h"] = resample_4h(rows)
        except Exception as e:
            print("skip candles", sym, repr(e))
    out["candles"] = candles

    out["tickers"] = tickers_out
    out["updated"] = datetime.now(timezone.utc).isoformat()
    with open(path, "w") as f:
        json.dump(out, f, ensure_ascii=False)
    print("OK:", len(tickers_out), "tickers,",
          len(out["snapshots"]), "snapshots,",
          len(inds), "indicators,",
          len(out["funding"]), "funding,",
          len(candles), "candle sets")


if __name__ == "__main__":
    main()
