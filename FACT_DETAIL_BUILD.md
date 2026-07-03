# FACT_DETAIL_BUILD

Implementation of the two gold models approved in `FACT_DETAIL_DIAGNOSIS.md`, plus
rehabilitation of the dashboard metrics disabled in today's cutover. Build date:
2026-07-03. Data max sale date: **2026-06-30**.

---

## Models built

Both are gold, incremental, C5 `_ingested_at` watermark, `on_schema_change=append_new_columns`.
Independent of each other; either can build first.

| Model | Grain | unique_key | Rows |
|-------|-------|-----------|------|
| `gold.fact_order_detail` | one row per order | `source_system, order_id` | **288,801** |
| `gold.fact_by_employee`  | employee × store × day | `date_key, store_key, employee_key` | **11,805** |

### Row-count verification

- `fact_order_detail` = **288,801** — **exactly matches `fact_order`** (1:1 JOIN grain). ✅
- `fact_order` unchanged at **288,801**. ✅
- `fact_sale_item` unchanged: **455,205 rows / `sum(qty)` = 490,209**. ✅
  Note: the "490,209" figure in the build request is `sum(qty)` (items sold), not the
  row count (455,205). Both are unchanged — neither new model touches this table.

---

## `fact_by_employee` — UNKNOWN (employee_key = 0) distribution

The join key was normalized to `upper(trim(employee_name))` because `dim_employee`
stores names already `upper(trim())`-normalized while `stg_par2` emits `employee_name`
in raw case. A raw-case join matched only **4** employees and dumped **97.7%** of net
sales into UNKNOWN. Normalizing lifted named coverage to **245 employees / 90.1%** of
net sales.

| Bucket | Rows | % rows | Distinct emps | Net sales | % net sales |
|--------|-----:|-------:|--------------:|----------:|------------:|
| named (key ≠ 0)   | 9,630 | 81.6% | 245 | $2,553,540 | 90.1% |
| UNKNOWN (key = 0) | 2,175 | 18.4% |   1 |   $279,804 |  9.9% |

- The residual UNKNOWN bucket is orders with null/blank staff and any PAR API numeric
  IDs. In the **current** data there are **0** numeric-ID employee names, so the diagnosis's
  "PAR API numeric IDs" driver is not yet material — the real (now-fixed) driver was the
  case-normalization mismatch.
- `stg_par2` still emits `employee_name` un-normalized. The fix lives in the fact join
  (matching `dim_employee`'s own contract), so no shared staging model was modified.
  Normalizing `employee_name` in `stg_par2` is a recommended follow-up but out of this scope.

---

## Test results

- **dbt tests** (`fact_order_detail` + `fact_by_employee`): **8/8 PASS**
  (not_null on date_key, store_key, source_system, order_id / date_key, store_key,
  employee_key).
- **pytest**: **333 passed, 1 skipped** (as expected).
- Unchanged-totals check: `fact_order` 288,801 and `fact_sale_item` qty 490,209 both
  intact (see above).

---

## Dashboard rehabilitation — active tiles vs permanent placeholders

New Evidence sources: `dashboard/sources/gold/fact_order_detail.sql`,
`dashboard/sources/gold/fact_by_employee.sql`.

| Page | Tile | Status | Notes |
|------|------|--------|-------|
| `channels.md` | Delivery Leakage | ✅ **ACTIVE** | `fact_order` ⋈ `fact_order_detail`, channel = Delivery. LS2 → UNKNOWN, excluded. Most-recent-month. |
| `index.md` | Labor Efficiency | ✅ **ACTIVE** | `fact_by_employee`, net sales / active named employees. Excludes key=0. **Current-month** window (empty until July data lands, like its sibling KPIs). |
| `stores/[store].md` | Top Employees | ✅ **ACTIVE** | `fact_by_employee`, top 10 by net sales, current month, key≠0. |
| `operations.md` | Up-selling Leaderboard | ✅ **ACTIVE** | Highest avg ticket per employee, ≥20 orders, most-recent-month. |
| `operations.md` | Discount Audit Trail | ✅ **ACTIVE** | Σ discount per employee, most-recent-month. |
| `operations.md` | Shift Productivity | ⚠️ **APPROXIMATION** | No time/shift data → orders per employee-**day** shown instead of per-hour. |
| `operations.md` | Tip Performance Index | ⛔ **PERMANENT PLACEHOLDER** | `tip_amount` is a 0 literal in both feeds — not derivable. |

Timeframe choice: pages with existing "current month" sibling KPIs (`index`, `stores`)
use `current_date` for consistency (empty now — data ends 2026-06-30, fills on July
ingest, same as their neighbors). The brand-new `operations` page and `channels`
Delivery Leakage use the most-recent-month-in-data pattern so they populate immediately.

**Permanent placeholders (source data does not exist):**
- Tip Performance Index — no tip amount in PAR/LS2.
- Per-hour Shift Productivity — no time-of-sale/shift column anywhere.

**Out of scope but now unblocked (follow-up):** `data_quality.md` still has a disabled
"UNKNOWN employee" tracker referencing the dropped table; it can now be restored from
`fact_by_employee` (count of `employee_key = 0`). Not in the approved 4-page scope.

Reference-cleanliness: no active Evidence query does `FROM/JOIN gold.fact_sales*`
(verified by grep — only historical prose comments remain).

---

## Supabase size post-rebuild

- **Database total: 452 MB** (`pg_size_pretty(pg_database_size(current_database()))`).
- New objects: `fact_order_detail` 31 MB, `fact_by_employee` 1.3 MB.
  (Context: `fact_order` 28 MB, `fact_sale_item` 47 MB.)
