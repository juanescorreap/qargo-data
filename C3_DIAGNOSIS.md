# C3 — Diagnosis: PAR API rows lose product dimension (`product_key = 0 / UNKNOWN`)

> Read-only. No ingestion code modified, no PAR SOAP call made, no commits. DB touched with
> SELECTs only. Adjacent bug `Revenue Center = DayPartId` (`par_api.py:314`/`:277`) noted, not fixed.

## Executive Summary (5 lines)

1. **Not a parser bug.** `GetOrders` (Sales2.svc) returns each line as an `OrderEntry` carrying only
   `ItemId` (a foreign key) — no item name / PLU / category. `build_raw_par2_rows` can't discard
   what the payload never contains; it correctly forces `Item Name=None` (`par_api.py:305-306`).
2. **It's a source-shape issue:** the product dimension lives in a *different* PAR service — the
   Settings/Menu catalog (`GetItem`, per the Welcome Letter) — which the code never calls.
3. **Most viable fix (now):** enrich `ItemId → product` from the **CSV catalog already in the DB**
   (`raw_par2_csv`: 966 items, all named); join in `stg_par2` on `Item ID`. Zero new API calls.
4. **Complexity: LOW–MEDIUM** (one dbt lookup model + a join). Long-term-correct option (implement
   `GetItem`) is MEDIUM and covers items not yet seen in any CSV.
5. **Impact today is latent** (only 2 sandbox API rows, not even in silver yet) but **structural**:
   every future API-primary date would render all products as UNKNOWN.

---

## 1. Anatomy of the PAR API payload

**The SOAP call.** `PARSoapClient` exposes exactly two actions: `GetCurrentBusinessDate`
(`par_api.py:87`) and **`GetOrders`** (`par_api.py:91-110`). `get_orders` builds a
`Sales2/ISalesWebService2/GetOrders` request with `BusinessDate`, `ExcludeOpenOrders`, `PriceRollUp`
(`:100-108`). **There is no catalog/menu/settings call anywhere in the client** — no `GetItem`,
`GetMenu`, `GetItems`. So the only thing ever fetched is transactional orders.

**The parser.** `parse_orders` walks `Orders.Order` → `Entries.OrderEntry` (`:240,:268`). For each
entry it extracts (`par_api.py:272-283`):

```
entry_id, item_id (ItemId), revenue_center_id (DayPartId),
net_sales (ItemNetSales), gross_sales (ItemGrossSales),
display_price (DisplayPrice), is_voided, is_deleted
```

No `ItemName` / `ItemDescription` / `Plu` / `Category` field is read — because none is present in the
`OrderEntry` node (the code comment at `:276` already flags that even `RevenueCenterId` isn't exposed
here). `build_raw_par2_rows` then hard-nulls the product columns (`par_api.py:304-306`):

```python
"Item ID":   entry.get("item_id"),   # the only product reference available (an FK)
"Item Name": None,                    # :305 — not in payload
"Item PLU":  None,                    # :306 — not in payload
```

**Sample / fixture payload:** none in the repo. No `.xml`/`.json` fixture, no `par_api`/`GetOrders`
test (`grep` clean). The only external reference is the Welcome Letter PDF (`docs/…Refresh.pdf`) and
the "zeep-based reference client" the code comments cite (`:227,:245`) — that client is not vendored.
The PDF's Phase 3 explicitly lists **"Settings-related calls like `GetItem` … every 15 mins/1 hour/
1 day"** and integration types "Labor, **Menuboard**, Order Submission" — i.e. item/menu metadata is
a *separate settings service*, distinct from the sales `GetOrders` we call.

## 2. Is the product data in the payload?

| Hypothesis | Verdict | Evidence |
|---|---|---|
| **(a)** API returns name/PLU/category but `build_raw_par2_rows` discards it | **NO** | Parser `:272-283` only reads `ItemId/DayPartId/$ fields`; there is nothing named to discard. Forced-None at `:305-306` is a consequence, not a drop. |
| **(b)** Data is in a different endpoint/field of the *same* call | **PARTIAL / different call** | Not another `GetOrders` field — the metadata lives in the **Settings/Menu catalog (`GetItem`)**, a call the client doesn't implement (only `GetOrders`, `:91`). |
| **(c)** `GetOrders` genuinely doesn't return product dimension at `OrderEntry` level | **YES (root)** | `OrderEntry` exposes `ItemId` (FK) only; name/PLU/category resolve via the item catalog keyed by `ItemId`. |

**Conclusion:** (c) is the root cause, with the resolution path being (b)'s separate catalog service.
`GetOrders` returns a *reference* (`ItemId`); the human-readable product dimension must be **joined
in** from a catalog. This is **not** a parsing defect.

## 3. Enrichment options (since it's a source-shape issue)

| Option | Exists? | Viability |
|---|---|---|
| **A. PAR `GetItem` settings/catalog call** | Yes (PDF Phase 3) | **Canonical, long-term correct.** Returns item defs (name/PLU/category) by `ItemId`, independent of sales, low call frequency. Cost: implement a new SOAP action + a `dim`/seed refresh. MEDIUM effort; needs sandbox validation. Covers *all* items incl. brand-new ones. |
| **B. CSV monthly as `ItemId→product` lookup** | **Yes, already in DB** | **Cheapest, works today.** `raw_par2_csv` = 966 distinct `Item ID`, **all 966 named** (0 null Item ID). Both current API `Item ID`s resolve via CSV (2/2). Same PAR `ItemId` namespace across sources → join key aligns. Caveat 1: **112/966 `Item ID`s map to >1 distinct name** → need a tie-break (latest/most-frequent). Caveat 2: only covers items that have appeared in some CSV; a net-new API-only item stays UNKNOWN until the next monthly CSV. LOW effort. |
| **C. Existing CPQ/recipe catalog / seeds** | **No usable one** | Only `seeds/product_campaign_map.csv` (canonical-name→campaign) and `dim_product` keyed by `hashtext(product_name)` — neither is keyed by `ItemId`, so neither can resolve an API `ItemId`. Not viable as-is. |

**Recommendation:** B now (interim, uses data on hand), A as the durable fix. B also doubles as the
validation set for A.

## 4. Current dashboard impact

Diagnostic SELECTs (read-only) against `bronze.raw_par2_api` / `raw_par2_csv` / silver / gold:

- **`raw_par2_api`:** 2 rows, **both `Item Name` NULL, both `Item PLU` NULL**, `Date` span
  **2026-05-27 → 2026-05-27**, 2 distinct `Item ID`, 1 store (`DEFAULT` = sandbox). `Revenue Center`
  = `640207795` (a DayPartId — confirms the adjacent bug).
- **CSV catalog coverage:** `raw_par2_csv` = 1,081,650 rows, 966 distinct `Item ID`, all named.
- **Enrichment check:** 2/2 API `Item ID`s exist in the CSV catalog with a name → key alignment
  confirmed. Ambiguity: 112 `Item ID`s carry multiple names in CSV.
- **`dim_product`:** the sentinel row `(product_key=0, product_name='UNKNOWN')` exists — the funnel
  for any NULL/blank `product_name`.
- **`stg_par2`:** 545,323 rows, all `_source_system='par2'` (CSV); the 2 API rows are **not yet in
  silver** (incremental threshold `sale_date > max`, and 2026-05-27 ≤ current max), so the dashboard
  shows *nothing* from API today.

**Mechanism (why API dates → UNKNOWN):** `stg_par2` sets `product_name = upper(trim("Item Name"))`
(`stg_par2.sql:35`). API `Item Name` is NULL → `product_name` NULL. `dim_product` is keyed by
`product_name` (`dim_product.sql`); `fact_sale_item`/facts join name→key, and a NULL name resolves to
`product_key = 0 (UNKNOWN)`. Category is likewise derived from `Revenue Center` (`stg_par2.sql:18-24`)
= DayPartId for API rows → `'Other'`. So Items / Menu / Category pages render fully for CSV dates and
collapse to UNKNOWN/Other for API-primary dates. **Latent now, structural for any future API-only day.**

## 5. Proposed fix (not implemented)

**Root cause = missing product-catalog join, not a parser edit.** Do NOT try to "un-None" lines
`par_api.py:305-306` — there is no field to read from `GetOrders`.

**Recommended minimal fix (Option B, interim):**
1. New dbt model `dim_item_catalog` (or seed refresh): `SELECT "Item ID", <pick-one name/plu/
   revenue_center>` from `raw_par2_csv`, deduped to one row per `Item ID`. Tie-break the 112 ambiguous
   IDs by most-recent (`max("Date")`) or most-frequent name.
2. In `stg_par2.sql`, `LEFT JOIN dim_item_catalog ON "Item ID"` and `coalesce("Item Name",
   catalog.item_name)` for `product_name`, and derive category from the catalog's revenue_center when
   the row's own `Revenue Center` is a DayPartId (i.e. API rows). No change to the API writer.

**Durable fix (Option A):** implement a `GetItem` SOAP action + a scheduled catalog load into a
canonical `dim_item_catalog` keyed by `ItemId`; the `stg_par2` join stays identical (source of the
lookup swaps from CSV to the real catalog). Covers new items CSV hasn't seen yet.

**Interaction with the adjacent `Revenue Center = DayPartId` bug (`par_api.py:314`/`:277`):**
they are the **same defect family** — `GetOrders` gives references/day-part, not descriptive
dimension. The catalog enrichment above **also resolves category** for API rows (category comes from
the item catalog, not the DayPartId), so fixing C3 this way *neutralizes the impact* of the DayPartId
mapping on categorisation. The writer-level DayPartId→RevenueCenter correction becomes low-priority
(only matters if something reads the raw `Revenue Center` value directly). **Design C3 and the
Revenue-Center category together (shared catalog join); keep the writer DayPartId fix as a separate,
lower-priority sub-thread.**

**Complexity:** Option B = **LOW** (1 model + 1 join, no writer/API change, no schema migration).
Option A = **MEDIUM** (new SOAP call + sandbox validation + scheduling).

---

## Security side-finding (out of C3 scope — flag)

`docs/PAR POS API Welcome Letter_QargoCoffee_Refresh.pdf` (page 4) contains a **plaintext PAR API
Access Token** committed to the repo (`J0flLsIYVU2PH+Qg/kxuoQ==`). This is a live-looking credential in
git history (likely equals `PAR_ACCESS_TOKEN`). Recommend treating as leaked: rotate the PAR token via
API Support and purge the PDF from history — same playbook as the 2026-06-25 Supabase incident. P1,
separate thread.
