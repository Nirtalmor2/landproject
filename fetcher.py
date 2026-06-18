import os
import sys
import json
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from multiprocessing import Process

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

BASE_URL = "https://apps.land.gov.il/MichrazimSite/api"
SEARCH_URL = f"{BASE_URL}/SearchApi/Search"
DETAILS_URL = f"{BASE_URL}/MichrazDetailsApi/Get"
YESHUVIM_URL = f"{BASE_URL}/YeshuvimApi/Get"
GENERAL_TABLES_URL = f"{BASE_URL}/GeneralTablesApi"

HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Referer": "https://apps.land.gov.il/MichrazimSite/"
}

CONCURRENCY_LIMIT = 5
REQUEST_DELAY = 0.1
NEWEST_LIMIT = 300


def fetch_lookups():
    yeshuv_map = {}
    status_map = {}

    try:
        print("Loading yeshuvim list...")
        r = requests.get(YESHUVIM_URL, headers=HEADERS, timeout=15)
        r.raise_for_status()
        yeshuvim_data = r.json()
        for item in yeshuvim_data:
            semel = item.get("mtysvSemelYishuv")
            name = item.get("mtysvShemYishuv")
            if semel is not None and name:
                yeshuv_map[semel] = name.strip()
        print(f"Loaded {len(yeshuv_map)} yeshuvim.")
    except Exception as e:
        print(f"Warning: failed to load yeshuvim: {e}")

    try:
        print("Loading status tables...")
        r = requests.get(GENERAL_TABLES_URL, headers=HEADERS, timeout=15)
        r.raise_for_status()
        general_data = r.json()
        for item in general_data:
            if item.get("TableID") == 237:
                code = item.get("Code")
                val = item.get("Value")
                if code is not None and val:
                    status_map[code] = val.strip()
        print(f"Loaded {len(status_map)} statuses.")
    except Exception as e:
        print(f"Warning: failed to load statuses: {e}")

    return yeshuv_map, status_map


def format_date(date_str):
    if not date_str:
        return None
    if len(date_str) >= 10 and date_str[4] == '-' and date_str[7] == '-':
        return date_str[:10]
    return date_str


def fetch_single_tender_details(tender_id):
    url = f"{DETAILS_URL}?michrazID={tender_id}"
    try:
        time.sleep(REQUEST_DELAY)
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        data = r.json()
        return data.get("MechirSafMichraz")
    except Exception as e:
        print(f"Error fetching details for tender {tender_id}: {e}")
        return None


def fetch_tenders(is_active, output_filename):
    print(f"{'='*60}")
    label = "ACTIVE" if is_active else "HISTORICAL"
    print(f"Starting {label} tenders fetch -> {output_filename}")
    print(f"{'='*60}")

    yeshuv_map, status_map = fetch_lookups()

    search_payload = {
        "Uchlusiya": [],
        "ActiveQuickSearch": False,
        "ActiveMichraz": is_active,
        "YiudMichraz": [4]
    }

    try:
        print(f"Sending search request (ActiveMichraz={is_active})...")
        r = requests.post(SEARCH_URL, headers=HEADERS, json=search_payload, timeout=30)
        r.raise_for_status()
        raw_tenders = r.json()
        print(f"Received {len(raw_tenders)} tenders.")
    except Exception as e:
        print(f"Critical error: search request failed: {e}")
        return

    raw_tenders = sorted(raw_tenders, key=lambda x: x.get("MichrazID", 0), reverse=True)

    newest_ids = set(t.get("MichrazID") for t in raw_tenders[:NEWEST_LIMIT] if t.get("MichrazID"))

    tenders_to_fetch_details = []
    processed_tenders = []

    for t in raw_tenders:
        t_id = t.get("MichrazID")
        if not t_id:
            continue

        status_code = t.get("StatusMichraz")
        status_name = status_map.get(status_code, str(status_code))

        city_code = t.get("KodYeshuv")
        city_name = yeshuv_map.get(city_code, str(city_code)) if city_code else None

        raw_date = t.get("PirsumDate") or t.get("PtichaDate") or t.get("SgiraDate")
        date_str = format_date(raw_date)

        shchuna = t.get("Shchuna", "").strip() if t.get("Shchuna") else None
        description = t.get("MichrazName", "").strip() if t.get("MichrazName") else None

        item = {
            "id": t_id,
            "description": description,
            "city": city_name,
            "shchuna": shchuna,
            "price": None,
            "date": date_str,
            "status": status_name,
            "status_code": status_code
        }

        tenders_to_fetch_details.append(item)

    total_to_fetch = len(tenders_to_fetch_details)
    if total_to_fetch > 0:
        print(f"Fetching details for {total_to_fetch} tenders...")
        fetched_count = 0
        with ThreadPoolExecutor(max_workers=CONCURRENCY_LIMIT) as executor:
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
                    print(f"Error getting result for tender {item['id']}: {e}")
                processed_tenders.append(item)
                fetched_count += 1
                if fetched_count % 50 == 0 or fetched_count == total_to_fetch:
                    print(f"Progress: {fetched_count}/{total_to_fetch} detail fetches completed.")
    else:
        print("No tenders to fetch details for.")

    processed_tenders = sorted(processed_tenders, key=lambda x: x["id"], reverse=True)

    try:
        with open(output_filename, "w", encoding="utf-8") as f:
            json.dump(processed_tenders, f, ensure_ascii=False, indent=2)
        print(f"Successfully saved {len(processed_tenders)} tenders to {output_filename}.")
    except Exception as e:
        print(f"Critical error saving {output_filename}: {e}")


def main():
    print("Starting concurrent ILA tender fetcher...")
    print(f"Using YiudMichraz=[4] filter for all requests.\n")

    p_historical = Process(target=fetch_tenders, args=(False, "tenders_results.json"))
    p_active = Process(target=fetch_tenders, args=(True, "tenders_active.json"))

    p_historical.start()
    p_active.start()

    p_historical.join()
    p_active.join()

    print("\nBoth streams completed successfully.")
    print("Output files: tenders_results.json (historical), tenders_active.json (active)")


if __name__ == "__main__":
    main()
