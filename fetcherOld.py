import os
import sys
import json
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# Reconfigure stdout/stderr for Hebrew printing on Windows console
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')


# הגדרות נתיבים וכתובות API
BASE_URL = "https://apps.land.gov.il/MichrazimSite/api"
SEARCH_URL = f"{BASE_URL}/SearchApi/Search"
DETAILS_URL = f"{BASE_URL}/MichrazDetailsApi/Get"
YESHUVIM_URL = f"{BASE_URL}/YeshuvimApi/Get"
GENERAL_TABLES_URL = f"{BASE_URL}/GeneralTablesApi"

OUTPUT_FILE = "tenders.json"

# כותרות לבקשות HTTP כדי למנוע חסימה
HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Referer": "https://apps.land.gov.il/MichrazimSite/"
}

# הגדרות ריצה וסנכרון
CONCURRENCY_LIMIT = 5   # מספר בקשות במקביל
REQUEST_DELAY = 0.1     # השהייה קלה בין שליחת בקשות (בשניות)
NEWEST_LIMIT = 300      # מספר המכרזים החדשים/סגורים לפרסום שנוריד להם פרטים בריצה ראשונה

def fetch_lookups():
    """שליפת טבלאות עזר למיפוי קודי יישובים וסטטוסים"""
    yeshuv_map = {}
    status_map = {}
    
    # 1. שליפת יישובים
    try:
        print("טוען רשימת יישובים...")
        r = requests.get(YESHUVIM_URL, headers=HEADERS, timeout=15)
        r.raise_for_status()
        yeshuvim_data = r.json()
        for item in yeshuvim_data:
            semel = item.get("mtysvSemelYishuv")
            name = item.get("mtysvShemYishuv")
            if semel is not None and name:
                yeshuv_map[semel] = name.strip()
        print(f"נטענו {len(yeshuv_map)} יישובים בהצלחה.")
    except Exception as e:
        print(f"אזהרה: שגיאה בטעינת יישובים: {e}. יישובים יוצגו כקוד מספרי.")

    # 2. שליפת סטטוסים כלליים
    try:
        print("טוען טבלאות סטטוסים...")
        r = requests.get(GENERAL_TABLES_URL, headers=HEADERS, timeout=15)
        r.raise_for_status()
        general_data = r.json()
        for item in general_data:
            # TableID 237 מייצג את סטטוס המכרז המורחב
            if item.get("TableID") == 237:
                code = item.get("Code")
                val = item.get("Value")
                if code is not None and val:
                    status_map[code] = val.strip()
        print(f"נטענו {len(status_map)} סטטוסים בהצלחה.")
    except Exception as e:
        print(f"אזהרה: שגיאה בטעינת סטטוסים: {e}. סטטוסים יוצגו כקוד מספרי.")

    return yeshuv_map, status_map

def load_cached_tenders():
    """טעינת מכרזים קיימים מקובץ tenders.json כדי לחסוך פניות ל-API"""
    if not os.path.exists(OUTPUT_FILE):
        return {}
    try:
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # בניית מילון לפי מפתח מזהה מכרז
            return {item["id"]: item for item in data if "id" in item}
    except Exception as e:
        print(f"אזהרה: שגיאה בקריאת tenders.json הקיים ({e}). ייווצר קובץ חדש.")
        return {}

def format_date(date_str):
    """פרמוט תאריך לפורמט YYYY-MM-DD"""
    if not date_str:
        return None
    if len(date_str) >= 10 and date_str[4] == '-' and date_str[7] == '-':
        return date_str[:10]
    return date_str

def fetch_single_tender_details(tender_id):
    """שליפת פרטי מכרז ספציפי עבור קבלת המחיר"""
    url = f"{DETAILS_URL}?michrazID={tender_id}"
    try:
        time.sleep(REQUEST_DELAY) # מניעת עומס על השרת
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        data = r.json()
        # שליפת מחיר המינימום/סף
        return data.get("MechirSafMichraz")
    except Exception as e:
        print(f"שגיאה בשליפת פרטי מכרז {tender_id}: {e}")
        return None

def main():
    print("--- מתחיל תהליך איסוף מכרזי רמ\"י ---")
    
    # 1. טעינת נתונים קודמים מהקובץ
    cache = load_cached_tenders()
    print(f"נטענו {len(cache)} מכרזים מהקובץ המקומי.")
    
    # 2. שליפת מילוני עזר
    yeshuv_map, status_map = fetch_lookups()
    
    # 3. שליפת כל המכרזים (חיפוש כללי)
    search_payload = {"Uchlusiya": [], "ActiveQuickSearch": False, "ActiveMichraz": False}
    try:
        print("שולח בקשת חיפוש ל-API של רמ\"י...")
        r = requests.post(SEARCH_URL, headers=HEADERS, json=search_payload, timeout=20)
        r.raise_for_status()
        raw_tenders = r.json()
        print(f"התקבלו {len(raw_tenders)} מכרזים מהחיפוש.")
    except Exception as e:
        print(f"שגיאה קריטית: כשל בפנייה ל-API החיפוש: {e}")
        sys.exit(1)
        
    # מיון המכרזים מהחדש לישן לפי מזהה
    raw_tenders = sorted(raw_tenders, key=lambda x: x.get("MichrazID", 0), reverse=True)
    
    # זיהוי המזהים של ה-N החדשים ביותר (בשביל הגבלת הורדה בריצה ראשונה)
    newest_ids = set(t.get("MichrazID") for t in raw_tenders[:NEWEST_LIMIT] if t.get("MichrazID"))
    
    tenders_to_fetch_details = []
    processed_tenders = []
    
    # 4. מעבר על המכרזים והחלטה האם לשלוף מחיר מחדש
    for t in raw_tenders:
        t_id = t.get("MichrazID")
        if not t_id:
            continue
            
        status_code = t.get("StatusMichraz")
        status_name = status_map.get(status_code, str(status_code))
        
        # מיפוי שדות בסיסיים
        city_code = t.get("KodYeshuv")
        city_name = yeshuv_map.get(city_code, str(city_code)) if city_code else None
        
        # בחירת תאריך רלוונטי
        raw_date = t.get("PirsumDate") or t.get("PtichaDate") or t.get("SgiraDate")
        date_str = format_date(raw_date)
        
        shchuna = t.get("Shchuna", "").strip() if t.get("Shchuna") else None
        description = t.get("MichrazName", "").strip() if t.get("MichrazName") else None
        
        is_active = status_code in [1, 2] # 1: מפורסם, 2: פתוח להצעות
        
        # בדיקה האם המכרז קיים בזיכרון המטמון והסטטוס שלו לא השתנה
        cached = cache.get(t_id)
        
        # מחיר ברירת מחדל
        price = None
        should_fetch_price = False
        
        if cached:
            # אם קיים וסטטוס זהה - משתמשים במחיר השמור
            if cached.get("status_code") == status_code:
                price = cached.get("price")
            else:
                # הסטטוס השתנה (למשל נסגר או עודכן) - נרצה לשלוף מחדש
                should_fetch_price = True
        else:
            # מכרז חדש: שולפים פרטים אם הוא פעיל או שהוא מה-N החדשים ביותר
            if is_active or (t_id in newest_ids):
                should_fetch_price = True
        
        item = {
            "id": t_id,
            "description": description,
            "city": city_name,
            "shchuna": shchuna,
            "price": price,
            "date": date_str,
            "status": status_name,
            "status_code": status_code
        }
        
        if should_fetch_price:
            tenders_to_fetch_details.append(item)
        else:
            processed_tenders.append(item)

    # 5. שליפת פרטים/מחיר בצורה מקבילית ומבוקרת
    total_to_fetch = len(tenders_to_fetch_details)
    if total_to_fetch > 0:
        print(f"מבצע שליפת פרטים ומחיר עבור {total_to_fetch} מכרזים חדשים/פעילים/מעודכנים...")
        
        fetched_count = 0
        with ThreadPoolExecutor(max_workers=CONCURRENCY_LIMIT) as executor:
            # מיפוי ה-future לפריט המתאים
            future_to_item = {
                executor.submit(fetch_single_tender_details, item["id"]): item 
                for item in tenders_to_fetch_details
            }
            
            for future in as_completed(future_to_item):
                item = future_to_item[future]
                try:
                    price = future.result()
                    item["price"] = price
                except Exception as e:
                    print(f"שגיאה בקבלת תוצאה עבור מכרז {item['id']}: {e}")
                    
                processed_tenders.append(item)
                fetched_count += 1
                if fetched_count % 50 == 0 or fetched_count == total_to_fetch:
                    print(f"הושלמו {fetched_count} מתוך {total_to_fetch} שליפות פרטים.")
    else:
        print("לא נמצאו מכרזים חדשים או פעילים הדורשים שליפת מחיר.")

    # מיון סופי של כל המכרזים לפי מזהה בסדר יורד
    processed_tenders = sorted(processed_tenders, key=lambda x: x["id"], reverse=True)
    
    # 6. שמירה לקובץ ה-JSON
    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(processed_tenders, f, ensure_ascii=False, indent=2)
        print(f"הקובץ {OUTPUT_FILE} נשמר בהצלחה עם {len(processed_tenders)} מכרזים.")
    except Exception as e:
        print(f"שגיאה חמורה בשמירת קובץ ה-JSON: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
