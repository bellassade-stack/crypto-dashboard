# מרכז פיקוד קריפטו

דשבורד מסחר יומי. עצמאי, בלי שרת, בלי תלות ב-VPN.

## איך זה עובד

הדשבורד (index.html) קורא את `data/market.json` שנכתב על ידי GitHub Actions.
ה-Actions רץ על שרתי GitHub בארה"ב, שם Binance פתוחה, לכן הדאטא תמיד זמין גם
אם הרשת שלך חוסמת את בורסות הקריפטו.

## הפעלה ב-3 שלבים

### 1. repo ב-GitHub
1. צור repo חדש (public) ב-github.com
2. העלה את כל הקבצים מהתיקייה הזו (index.html, scripts/, .github/)
3. **Settings → Pages → Deploy from branch → main** (אופציונלי, אם רוצים גם כתובת GitHub)
4. **Settings → Secrets and variables → Actions → New repository secret:**
   - לא חובה לשלב הבסיסי. (לטלגרם: TELEGRAM_TOKEN + TELEGRAM_CHAT_ID)

### 2. הפעלת האוטומציה
1. לך ללשונית **Actions** ב-repo
2. לחץ על **update-market-data** → **Enable workflow** (או Run workflow)
3. חזור על זה גם עם **weekly-backtest**
4. אחרי הריצה הראשונה ייווצר `data/market.json`

### 3. חיבור לנטיפלי
1. ב-netlify.com: **Add new site → Import an existing project → GitHub**
2. בחר את ה-repo
3. Build command: (ריק) · Publish directory: `/` (השורש)
4. **Deploy** — וזהו.

כעת כל פעם שה-Actions דוחף נתונים חדשים, נטיפלי מעדכן את האתר אוטומטית
(Deploy settings → Build hooks / auto-deploy on push — מופעל כברירת מחדל).

## מה קורה בכל ריצה של Actions

| תדירות | מה |
|---|---|
| כל 30 דקות | tickers (100 מטבעות), snapshot יומי, אינדיקטורים, funding, נרות BTC/ETH |
| שבועי (ראשון 00:00) | backtest של 2 אסטרטגיות על 30 יום נרות |

## אזעקות טלגרם (אופציונלי)

1. ב-BotFather צור בוט (/newbot) וקבל טוקן
2. שלח לבוט /start, אז פתח בדפדפן:
   `https://api.telegram.org/bot<TOKEN>/getUpdates` וחלץ את chat.id
3. הוסף את השניים כ-secrets ב-GitHub (שמות בדיוק: TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)
4. הוסף workflow שלישי עם scripts/alerts.py (זמין בהמשך)

## מבנה הקבצים

```
index.html              הדשבורד (הכול בקובץ אחד)
scripts/update_data.py  שולף דאטא וכותב data/market.json
scripts/backtest.py     בקטסט שבועי → data/backtest.json
.github/workflows/      מתזמני GitHub Actions
data/                   נוצר אוטומטית על ידי Actions
```

## הערות

- התיק האישי, היומן וההיסטוריה נשמרים ב-localStorage של הדפדפן בלבד
- אין כאן ייעוץ השקעות — כלי מידע וסינון מערכתי בלבד
- סיכון מומלץ: 1% מהחשבון לעסקה, stop loss תמיד
