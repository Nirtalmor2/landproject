# פרויקט land: תוכנית פיתוח טכנית
מטרה: מערכת אוטומטית לניטור ואגירת מכרזי רמ"י.

## 1. הגדרות API (חובה לשימוש בקוד)
- **URL:** https://apps.land.gov.il/MichrazimSite/api/SearchApi/Search
- **Method:** POST
- **Payload:** {"Uchlusiya": [], "ActiveQuickSearch": false, "ActiveMichraz": false}
- **Headers:** - Content-Type: application/json
    - User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36
    - Referer: https://apps.land.gov.il/MichrazimSite/

## 2. שלבי פיתוח (לביצוע ע"י ה-AI)

### שלב א': Backend (Python)
- יצירת `fetcher.py`.
- ביצוע בקשת POST ל-API עם ה-Headers וה-Payload שצוינו.
- טיפול ב-JSON המתקבל: חילוץ השדות (`id`, `city`, `price`, `date`) ושמירה לקובץ `tenders.json` (פורמט UTF-8).
- הוספת מנגנון טיפול בשגיאות (Network/Request errors).

### שלב ב': Frontend (HTML/JS)
- יצירת `index.html`.
- שימוש ב-DataTables.net להצגת הנתונים מתוך `tenders.json`.
- הוספת יכולות חיפוש ומיון בטבלה.

### שלב ג': GitHub Automation
- יצירת `workflow` להרצה אוטומטית של הסקריפט (GitHub Actions).
- הגדרת GitHub Pages להצגת האתר.

## 3. הנחיה למפתח (AI Instructions)
- אל תציע תיאוריות – כתוב קוד בלבד.
- כל קובץ צריך להיות מוכן להרצה.
- הקוד חייב להיות עמיד (Robust) ולכלול הערות קצרות.
- עברית בקבצי JSON חייבת להישמר תקינה (ensure_ascii=False).