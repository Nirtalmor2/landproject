# Work Plan: Enrich Tender Data with Winner & Parcel Details

## Goal
Extend the existing fetcher and frontend to capture 5 new data fields from the ILA API: Block/Parcel, Winning Price, Development Costs, Winner Identity, and Number of Bidders.

---

## Phase 1: Backend — Extend `fetcher.py`

### 1.1 Refactor `fetch_single_tender_details()`
**Current:** Returns only `MechirSafMichraz` (float).  
**Target:** Return a **full parcel-level object** with all fields from the `Tik[]` array.

New return structure:
```python
{
    "parcels": [
        {
            "gush": "7815",
            "helka": "440",
            "area_sqm": 515,
            "built_area_sqm": ...,
            "housing_capacity": 1,
            "threshold_price": 168300.0,
            "appraised_value": ...,
            "winning_price": 365618.0,
            "development_costs": 111726,
            "winner_name": "שם הזוכה",
            "bidder_count": 4,
            "bids": [365618.0, 327000.0, 311556.0, ...]
        }
    ]
}
```

### 1.2 Map `GushHelka[]` array
Each parcel has `GushHelka[]` — an array of block/parcel pairs. Concatenate into display strings (e.g., `"7815 / 440"`).

### 1.3 Handle active vs. historical
- **Historical tenders** (StatusMichraz=5,7): All fields available.
- **Active tenders** (StatusMichraz=1,2): Block/Parcel and costs available; winner fields will be `null`.
- `fetcher.py` already has separate active/historical streams — augment both.

### 1.4 Concurrency & rate limiting
Keep the existing `ThreadPoolExecutor(max_workers=5)` + `REQUEST_DELAY`. The details endpoint already handles this — we just extract more fields.

### 1.5 Output schema change
`tenders_active.json` and `tenders_results.json` gain a new `"parcels"` array per tender:

```json
{
  "id": 20260639,
  "description": "639/2026",
  "city": "תל אביב יפו",
  "shchuna": "ברנט 18",
  "price": 7760000.0,
  "date": "2026-06-15",
  "status": "פתוח להגשת הצעות",
  "status_code": 2,
  "parcels": [
    {
      "gush": "7815",
      "helka": "440",
      "area_sqm": 515,
      "winning_price": null,
      "development_costs": 111726,
      "winner_name": null,
      "bidder_count": 0,
      "bids": []
    }
  ]
}
```

---

## Phase 2: Frontend — Update `index.html`

### 2.1 New columns in DataTable
Add the following columns (visible only in the relevant tabs):

| Column | Source | Tab |
|--------|--------|-----|
| גוש / חלקה | `parcels[].gush` + `parcels[].helka` | Active + Historical |
| מחיר זכייה | `parcels[].winning_price` | Historical (null in Active) |
| הוצאות פיתוח | `parcels[].development_costs` | Active + Historical |
| שם הזוכה | `parcels[].winner_name` | Historical |
| מספר מציעים | `parcels[].bidder_count` | Historical |

### 2.2 Multi-parcel handling
If a tender has multiple parcels, show the first parcel inline and add a "+N more" badge with a tooltip/popover listing all parcels.

### 2.3 Column visibility control
- **Active Tenders tab:** Show Block/Parcel, Development Costs.  
- **Less Relevant tab:** Same as Active.  
- **Historical Results tab:** Show all 5 columns.  
- Keep the existing Notes and Actions columns.

### 2.4 Currency formatting
Winning Price and Development Costs should use the existing `formatCurrency()` helper.

---

## Phase 3: Testing & Validation

### 3.1 Run fetcher
```bash
python fetcher.py
```
Verify that `tenders_active.json` and `tenders_results.json` contain the new `"parcels"` array with correct data.

### 3.2 Check historical data
Pick a few historical tenders (status_code=5) and verify:
- `parcels[].winner_name` is a non-null string
- `parcels[].winning_price` is a positive number
- `parcels[].bidder_count` ≥ 1
- `parcels[].gush` / `parcels[].helka` are populated

### 3.3 Check active data
Verify that active tenders have `winner_name = null`, `winning_price = null`, and `bidder_count = 0`.

### 3.4 Frontend smoke test
Open `index.html` and confirm new columns render correctly, multi-parcel badges work, and formatting is consistent.

---

## Phase 4: Optional Enhancements

### 4.1 Bid history viewer
Add an expandable row (DataTables child row) for historical tenders showing the full bid list (`parcels[].bids`).

### 4.2 Statistics
Add new stat cards: "ממוצע מחיר זכייה", "סה"כ הוצאות פיתוח", "ממוצע מציעים למכרז".

### 4.3 Filter by winner
Add a winner name filter dropdown in the historical tab.

---

## Files to Modify
| File | Change |
|------|--------|
| `fetcher.py` | Expand `fetch_single_tender_details()` to extract all parcel fields |
| `index.html` | Add 5 new columns, handle multi-parcel display |
| `plan.md` | This file — keep updated as plan evolves |

## Files Unchanged
| File | Reason |
|------|--------|
| `.github/workflows/*` | No changes needed — GitHub Actions runs `fetcher.py` already |
| `tenders_active.json` | Schema evolves but filename stays |
| `tenders_results.json` | Schema evolves but filename stays |
