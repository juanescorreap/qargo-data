# FACT_DETAIL_DIAGNOSIS

Read-only diagnosis for rebuilding the two gold models that rehabilitate the
metrics disabled in today's cutover (drop of `fact_sales` +
`fact_sales_by_employee`). No models or pages were modified.

Sources inspected:
- `qargo/models/silver/sales/stg_par2.sql`
- `qargo/models/silver/sales/stg_ls2.sql`
- `qargo/models/silver/sales/stg_orders.sql`
- `qargo/models/gold/sales/fact_order.sql`, `fact_sale_item.sql`
- `qargo/models/gold/dimensions/dim_employee.sql`
- Dropped defs recovered from git `378457f^`: `fact_sales.sql`, `fact_sales_by_employee.sql`
- Pages: `index.md`, `channels.md`, `stores/[store].md`, `operations.md`

---

## 1. Columns available in `stg_orders`

`stg_orders` is `select * from stg_par2 UNION ALL select * from stg_ls2` — a view.
UNION ALL requires identical column lists, so both staging models expose the **same
16 columns in the same order**. Grain = **one row per item line** (not per order).

| # | Column | Type | par2 source | ls2 source | Notes |
|---|--------|------|-------------|------------|-------|
| 1 | `sale_date` | date | `cast("Date")` | `cast("Date")` | date only, **no time-of-day** |
| 2 | `store_name` | text | `"Location"` normalized | `"Location"` normalized | both |
| 3 | `revenue_center` | text | from `"Revenue Center"`/catalog | from `"Group"` | Beverage/Food/Retail/Other |
| 4 | `net_sales` | numeric | `"Net Sales"` | `"FinalPrice"` | both |
| 5 | `order_id` | text | `"Order ID"` | `"Account"` | ls2 `Account` groups ~5.5 orders (undercount) |
| 6 | `order_ref` | text | `"Order ID"` | `"Reference"` | **true per-order key** (used by fact_order/fact_sale_item) |
| 7 | `qty` | numeric | `1.0` literal | `"Qty"` (signed) | par2 has NO real qty; ls2 negatives = returns |
| 8 | `tip_amount` | numeric | **`0.0` literal** | **`0.0` literal** | **NOT from source in either** — see below |
| 9 | `destination` | text | `"Destination"` | **`null::text`** | **par2 only**; ls2 always NULL |
| 10 | `employee_name` | text | `"Employee Name"` | `"Staff"` | both, but see API caveat below |
| 11 | `tax_amount` | numeric | `"Taxes"` | `"TaxAmount"` | both |
| 12 | `discount_total` | numeric | `"Discount Total"` | `"Discount"` | both |
| 13 | `product_name` | text | eff item name | `"Item"` | both |
| 14 | `product_canonical_name` | text | derived | derived | both |
| 15 | `_source_system` | text | `'par2'` \| `'par_api'` | `'ls2'` | C4 split |
| 16 | `_ingested_at` | timestamptz | `"_ingested_at"` | `"_ingested_at"` | C5 load-time watermark |

### Confirmations requested

- **`discount_total` exists?** YES — both sources (par2 `"Discount Total"`, ls2 `"Discount"`).
- **`tax_amount` exists?** YES — both sources (par2 `"Taxes"`, ls2 `"TaxAmount"`).
- **`tip_amount` exists?** **NO — not from source.** Hardcoded `0.0` literal in BOTH
  `stg_par2.sql` (line 61) and `stg_ls2.sql` (line 40). The column is present but
  carries no real data. **Any tip metric is unrecoverable from current sources.**
- **`employee_key` / `employee_name`?** `employee_name` YES in both. `employee_key`
  does NOT exist in staging — it is produced by a lookup join to `dim_employee`
  (`abs(hashtext(employee_name))`). **Caveat:** PAR **API** rows write numeric employee
  IDs into `"Employee Name"`; `dim_employee` explicitly excludes numeric-only names
  (`!~ '^[0-9]+$'`), so API rows resolve to `employee_key = 0` (UNKNOWN). Real names
  come from PAR **CSV** and LS2 only.
- **Any employee-grain column?** Only `employee_name` (line-grain). There is **no**
  shift, clock-in/out, hours-worked, or time-of-sale column anywhere. Employee grain
  is reconstructable to (date × store × employee) at best — never to shift/hour.

---

## 2. Placeholders — what each needs exactly

### `index.md` — Labor Efficiency (lines 188–196)
- Metric: `Net Sales / Active Employee Count` per store.
- Needs: **employee grain** (to count distinct employees per store/month) + `net_sales`.
- Original source: `fact_sales_by_employee` (grain date×store×employee).
- Derivable: **YES** — `net_sales` and distinct-employee count both come from the
  employee grain. Subject to the UNKNOWN-employee caveat for API rows.

### `channels.md` — Delivery Leakage (lines 55–63)
- Metric: `Net Sales` vs `Discount Total` for 3rd-party delivery channels.
- Needs: `net_sales` + `discount_total` at **destination/channel grain**
  (join `dim_destination`).
- Original source: `fact_sales` (carried `discount_total` + `destination_key`).
- Derivable: **YES for par2**, but `destination` is **NULL for all ls2 rows** →
  ls2 discounts land in the UNKNOWN destination (`destination_key = 0`). Delivery
  channels in this dataset are PAR-sourced, so leakage-by-channel is functional;
  document that ls2 contributes only to the UNKNOWN bucket.

### `stores/[store].md` — Top Employees (lines 180–188)
- Metric: top employees for the store this month (implicitly by net sales / avg ticket).
- Needs: **employee grain** — `net_sales`, `order_count` per employee per store.
- Original source: `fact_sales_by_employee`.
- Derivable: **YES** (same caveat: API rows = UNKNOWN).

### `operations.md` — entire page (all queries removed, lines 5–18)
Four tiles, all on employee grain:
| Tile | Metric | Needs | Derivable? |
|------|--------|-------|-----------|
| Up-selling Leaderboard | highest avg ticket per employee | `net_sales / order_count` per employee | **YES** |
| Tip Performance Index | `tip_amount / net_sales` per employee | `tip_amount` | **NO** — tip_amount is `0.0` literal |
| Shift Productivity | orders per employee **per hour** | orders + **hours worked / time-of-sale** | **NO** — no time or shift data |
| Discount Audit Trail | total `discount_total` per employee | `discount_total` per employee | **YES** |

---

## 3. Design of `fact_order_detail`

- **Buildable from `stg_orders` directly?** YES. All inputs (`net_sales`,
  `discount_total`, `tax_amount`, `tip_amount`, `destination`, `order_ref`) are in
  staging. Same dependency set as `fact_order`.
- **Grain: one row per real order** = `(source_system, order_id)` where
  `order_id = order_ref`. Mirrors `fact_order` exactly, so the two join 1:1 on
  `(source_system, order_id)`. (Staging is item-line grain; roll up to order grain
  by summing the money columns.)
- **Columns:**
  - `date_key`, `store_key`, `destination_key`, `source_system`, `order_id`
  - `discount_total` = `sum(discount_total)` per order
  - `tax_amount` = `sum(tax_amount)` per order
  - `tip_amount` = `sum(tip_amount)` → **always 0** (source limitation, keep column
    so the model is forward-compatible when tips are ingested)
  - `_ingested_at` (= `max(_ingested_at)`)
  - (`order_net_sales` optional — already in `fact_order`; omit to avoid duplication,
    or include for standalone use.)
- **Interaction with `fact_order`:** JOIN, not independent. Same grain and same key →
  clean `f.order_id = fod.order_id AND f.source_system = fod.source_system`. Delivery
  Leakage can then aggregate `fact_order.order_net_sales` + `fact_order_detail.discount_total`
  by `destination_key`.
- **NULL / limitation columns:**
  - `tip_amount` — 0 for **all** rows (both sources).
  - `destination_key` = 0 (UNKNOWN) for **all ls2 orders** (`destination` NULL).
  - par2/par_api orders carry real destination.

---

## 4. Design of `fact_by_employee`

- **`employee_key` in `stg_orders`?** No — needs the `dim_employee` lookup
  (`coalesce(emp.employee_key, 0)` on `employee_name`), exactly as the dropped
  `fact_sales_by_employee` did.
- **Real grain available: (date × store × employee)** = `(date_key, store_key,
  employee_key)`. This is the finest employee grain the data supports. **No** per-shift
  or per-hour grain exists (no time column). One row per employee per store per day.
- **operations.md metrics derivable?**
  - Up-selling (avg ticket/employee): **YES** — `net_sales / order_count`.
  - Discount audit (Σ discount/employee): **YES** — `sum(discount_total)`.
  - Tip index: **NO** — `tip_amount` is 0.
  - Shift productivity (orders/employee/hour): **NO** — no hours/time. Best possible
    downgrade is orders/employee/**day**, not /hour.
- **Columns:**
  - `date_key`, `store_key`, `employee_key`
  - `net_sales` = `sum(net_sales)`
  - `order_count` = `count(distinct order_id)` (use `order_ref` for the true key)
  - `discount_total` = `sum(discount_total)`
  - `tax_amount` = `sum(tax_amount)`
  - `tip_amount` = `sum(tip_amount)` → **always 0**
  - `avg_ticket` = `net_sales / nullif(order_count,0)`
  - `_ingested_at` = `max(_ingested_at)`
- **Completely missing / underivable columns:**
  - `tip_amount` (0 literal) → Tip Performance Index cannot be built.
  - any hours-worked / shift / time-of-sale → Shift Productivity per hour cannot be built.
  - `employee_key = 0` (UNKNOWN) absorbs **all PAR API rows** (numeric IDs) — employee
    leaderboards are meaningful for PAR CSV + LS2 named staff only.

---

## 5. Implementation proposal

### Model A — `gold.fact_order_detail`
- **Layer / grain:** gold; **one row per order** `(source_system, order_id)`.
- **Available (confirmed):** `date_key`, `store_key`, `destination_key`,
  `source_system`, `order_id`, `discount_total`, `tax_amount`.
- **NULL by source limitation:** `tip_amount` (all 0); `destination_key`=0 for all ls2.
- **Incremental:** same C5 pattern as `fact_order` — `incremental`,
  `unique_key=['source_system','order_id']`, watermark
  `_ingested_at > (select coalesce(max(_ingested_at),'2000-01-01') from {{ this }})`,
  `on_schema_change='append_new_columns'`. (fact_order uses default/merge strategy;
  match it.)
- **Row estimate:** = row count of `fact_order` (1:1). Same order universe.

### Model B — `gold.fact_by_employee`
- **Layer / grain:** gold; **date × store × employee** `(date_key, store_key,
  employee_key)`. Effectively the dropped `fact_sales_by_employee` rebuilt.
- **Available (confirmed):** `net_sales`, `order_count`, `discount_total`,
  `tax_amount`, `avg_ticket`.
- **NULL by source limitation:** `tip_amount` (all 0); `employee_key=0` bucket holds
  all PAR API rows; no per-hour grain.
- **Incremental:** same C5 pattern; `unique_key=['date_key','store_key','employee_key']`,
  `_ingested_at` watermark, `append_new_columns` — identical to the dropped model
  (recover from git `378457f^:.../fact_sales_by_employee.sql` as the starting point;
  it already implements exactly this).
- **Row estimate:** ≈ distinct (date × store × employee) combinations. Coarser than
  fact_order (many orders collapse per employee-day), but widened by the employee
  dimension. Order-of-magnitude similar to the old `fact_sales_by_employee` table.

### Build order & dependencies
- The two models are **independent of each other** — no cross-dependency.
- Both depend only on already-built upstreams: `stg_orders`, `dim_date`, `dim_store`,
  `dim_destination` (A), `dim_employee` (B). All exist. Either can build first.
- `fact_order_detail` is meant to be **queried alongside** `fact_order` (JOIN on
  `source_system, order_id`), but does not depend on it at build time.

### Cross-cutting caveats to surface on the pages
1. **Tip metrics are dead** until tips are ingested upstream — do not rebuild the Tip
   Performance Index tile; leave a documented placeholder. Same for **Shift Productivity
   per hour** (no time data). These two `operations.md` tiles stay disabled even after
   both models land.
2. **Delivery Leakage** works for PAR channels; LS2 discounts fall in UNKNOWN
   destination — annotate the tile.
3. **Employee leaderboards** exclude PAR API rows (numeric IDs → UNKNOWN) — annotate.
