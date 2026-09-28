#!/usr/bin/env python3
"""
alerts.py — אזעקות טלגרם
רץ ב-GitHub Actions כל 30 דקות (בשעה +15 דקות לעומת update_data).
בודק תנועות חריגות בשוק ושולח לבוט שלך רק אזעקות חדשות (אנטי-ספאם).

דורש secrets ב-GitHub:
  TELEGRAM_TOKEN    · הטוקן מ-BotFather
  TELEGRAM_CHAT_ID  · ה-chat ID שלך

אם ה-secrets חסרים הסקריפט מדפיס הודעה ויוצא ב-0 (לא נופל).
"""
import json, os, urllib.request, urllib.parse
from datetime import datetime, timezone

BASE = "https://api.binance.com"
TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
STATE_PATH = "data/alerts_state.json"

# ספי אזעקה
BIG_MOVE = 8.0        # % שינוי ב-24ש
HUGE_MOVE = 15.0      # % שינוי ב-24ש
MIN_VOL = 50_000_000  # נפח מינימלי ב-$ כדי לסנן רעש
COOLDOWN_HOURS = 6    # אותה אזעקה לא חוזרת תוך X שעות

def get(path):
    req = urllib.request.Request(BASE + path, headers={"User-Agent": "crypto-alerts/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

def send_telegram(text):
    url = ("https://api.telegram.org/bot" + TOKEN + "/sendMessage?" +
           urllib.parse.urlencode({
               "chat_id": CHAT_ID,
               "text": text,
               "parse_mode": "HTML",
               "disable_web_page_preview": "true"
           }))
    req = urllib.request.Request(url, headers={"User-Agent": "crypto-alerts/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

def load_state():
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except Exception:
        return {"sent": {}}

def save_state(state):
    os.makedirs("data", exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, ensure_ascii=False)

def fmt_usd(v):
    if v >= 1e9: return f"${v/1e9:.2f}B"
    if v >= 1e6: return f"${v/1e6:.0f}M"
    return f"${v/1e3:.0f}K"

def main():
    if not TOKEN or not CHAT_ID:
        print("SKIP: TELEGRAM_TOKEN / TELEGRAM_CHAT_ID secrets not set. "
              "Add them in Settings > Secrets and variables > Actions.")
        return

    state = load_state()
    sent = state.get("sent", {})
    now = datetime.now(timezone.utc)

    tickers = [t for t in get("/api/v3/ticker/24hr") if t["symbol"].endswith("USDT")]
    tickers.sort(key=lambda t: float(t["quoteVolume"]), reverse=True)

    messages = []
    for t in tickers[:100]:
        sym = t["symbol"].replace("USDT", "")
        chg = float(t["priceChangePercent"])
        vol = float(t["quoteVolume"])
        price = float(t["lastPrice"])
        if vol < MIN_VOL:
            continue
        if abs(chg) < BIG_MOVE:
            continue

        key = sym
        last_sent = sent.get(key)
        if last_sent:
            try:
                hours = (now - datetime.fromisoformat(last_sent)).total_seconds() / 3600
                if hours < COOLDOWN_HOURS:
                    continue
            except Exception:
                pass

        emoji = "🚀" if chg > 0 else "🔴"
        level = "חריגה מאסיבית" if abs(chg) >= HUGE_MOVE else "תנועה חריגה"
        action = ("לא רודפים. מחכים ל-retest עם נפח." if chg > HUGE_MOVE
                  else "סריקת כניסה אפשרית רק עם אימות נפח ו-stop מתחת לתמך.")
        text = (f"{emoji} <b>{sym}</b> {level}\n"
                f"שינוי 24ש: <b>{chg:+.2f}%</b>\n"
                f"מחיר: ${price:,.4g}\n"
                f"נפח: {fmt_usd(vol)}\n"
                f"{action}")
        messages.append((key, text))
        sent[key] = now.isoformat()

    for key, text in messages[:5]:
        try:
            send_telegram(text)
            print("sent:", key)
        except Exception as e:
            print("telegram failed:", e)

    # ניקוי state ישן
    cutoff = 24
    for k in list(sent.keys()):
        try:
            h = (now - datetime.fromisoformat(sent[k])).total_seconds() / 3600
            if h > cutoff:
                del sent[k]
        except Exception:
            del sent[k]

    state["sent"] = sent
    save_state(state)
    print(f"OK: {len(messages)} alert(s)")

if __name__ == "__main__":
    main()
