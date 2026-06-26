# Phase 2a — fact_order build (C1 root-cause fix)

> Scope: build `fact_order` only. `fact_sales` untouched (still live for the dashboard until sub-thread 3). No Qty/items work (that's 2b). Date: 2026-06-25.

## Executive summary (5 lines)
1. **LS2 has a real order id after all:** `Reference` (per-receipt). `Account` (current `stg_ls2` order_id) groups **~5.5 orders each** (max 100) → it undercounts. Decision: `fact_order` keys LS2 on `Reference`, PAR on `Order ID`.
2. `fact_order` is one row per real order with `order_count = 1` literal → `sum(order_count)` is **additive by construction** (no product grain to spread an order across).
3. Additivity regression test (`assert_fact_order_additive`) **PASSES**; `fact_order` total **equals** an independent distinct-order count from staging (328,862 == 328,862).
4. New order count **328,862** vs old inflated `fact_sales` **524,238** → **37.3% lower**, exactly the expected direction (old over-counted). Never higher → no new bug.
5. New finding (for 2b/roadmap): `raw_ls2` **does** carry a `Qty` column — quantity data exists, just dropped at staging today.

---

## 1. LS2 order_id decision (investigated, not assumed)

Inspected the full `bronze.raw_ls2` schema (not just the columns `stg_ls2` maps). Candidate id columns: `Identifier`, `Reference`, `Account`. Cardinality over 26,257 SALE/UPDATE rows:

| Column | Distinct | Lines per value | Meaning |
|---|---|---|---|
| `Identifier` | 26,257 (= rows) | 1.0 | **row/line id** — too fine |
| `Reference` | 23,919 | ~1.10 | **per-receipt / transaction** — real order grain |
| `Account` | 6,909 | avg **5.48 references/account** (max 100) | **customer/account** — groups many orders |

`Reference`: **0 null/blank**, and **globally unique** (`count(distinct Reference)` = `count(distinct (Location,Reference))` = 23,919) → safe standalone order key.

**Decision: LS2 `order_id` = `Reference`.** It is a strictly better, available identifier; `Account` collapses ~5.5 real orders into one. This is not a model limitation — the data has a real transaction id; `stg_ls2` simply mapped the wrong column.

**Implementation choice:** to avoid changing `fact_sales` behaviour, I did **not** repoint `stg_ls2.order_id`. Instead I added a new `order_ref` column to both staging models:
- `stg_par2.sql` → `"Order ID" as order_ref`
- `stg_ls2.sql`  → `"Reference" as order_ref`

`stg_orders` is `select *` so it carries `order_ref`; `fact_sales`/`fact_sales_by_employee` select explicit columns and **never reference `order_ref`**, so their output is unchanged. Staging was `--full-refresh`ed to backfill `order_ref` across history (stg_ls2: 23,820 rows; stg_par2: 545,323).

---

## 2. fact_order design

- **Grain:** one row per real order = `(source_system, order_id)` where `order_id = order_ref` (PAR `Order ID` / LS2 `Reference`). `unique_key=['source_system','order_id']`.
- **Columns:** `date_key`, `store_key`, `destination_key`, `source_system`, `order_id`, `order_net_sales` (= sum of the order's item-line net sales), `order_count` (**literal `1`**).
- **Additivity:** `order_count` is `1` by construction, not a `count(distinct)`. The model has **no product grain**, so an order cannot be split across product cells — the exact C1 mechanism is structurally impossible here.
- **Build:** reads `stg_orders` (item-line grain), rolls up to order grain via `group by source_system, order_ref` with `max(store/destination/date)` (constant within an order) and `sum(net_sales)`, then joins dims (`dim_date`/`dim_store` inner, `dim_destination` left → `coalesce(...,0)`).

`fact_order.sql` in `qargo/models/gold/sales/` alongside `fact_sales.sql`. `fact_sales.sql` was **not** modified.

---

## 3. Additivity regression test

`qargo/tests/assert_fact_order_additive.sql` (dbt singular test). Independently counts distinct `(source, order_ref)` per `date_key` straight from `stg_orders` (mirroring `fact_order`'s inner dim joins to isolate additivity, not coverage), and compares to `sum(fact_order.order_count)` per day. Returns offending days; passes only at zero rows. **If anyone re-adds a sub-order grain (e.g. `product_key`), an order spreads to N rows, the sum exceeds the true count, and this test fails loudly.**

**Result: PASS** (`dbt test --select assert_fact_order_additive` → `1 of 1 PASS`).

Full Python suite after the staging change: **333 passed, 1 skipped**.

---

## 4. Old vs new (fact_sales untouched, read-only comparison)

| Metric | Value |
|---|---|
| OLD `sum(fact_sales.order_count)` (inflated, non-additive) | **524,238** |
| NEW `sum(fact_order.order_count)` | **328,862** |
| Independent staging distinct orders | **328,862** |
| `new == independent truth` | **True** |
| Reduction | **−195,376 (37.3% lower)** |
| New by source | par2 = 307,156 · ls2 = 21,706 |

New is **lower** than old (old over-counted by ~59%), as predicted — not higher, so no new inflation bug. The new total reconciles exactly to an independently computed distinct-order count.

---

## 5. New findings / roadmap notes

- **`raw_ls2.Qty` exists** — quantity is in the raw data; `stg_ls2` drops it. Feeds Phase 2b (true "Items Sold" = SUM(Qty)). `raw_par2` has no Qty column (PAR API/CSV are item-line grain, qty implied 1 per line); confirm PAR Qty availability in 2b.
- **`stg_ls2` mis-mapped `order_id` to `Account`** is a pre-existing data-modeling bug (not introduced here). `fact_sales` still uses it (LS2 orders undercounted there) until sub-thread 3 migrates pages to `fact_order`. Documented, not silently fixed, to keep `fact_sales` behaviour frozen this sub-thread.
- **Not touched:** `dashboard/` (sub-thread 3), Qty/items (2b), `fact_sales.sql`.

## Files changed
- `qargo/models/silver/sales/stg_par2.sql` — added `order_ref`
- `qargo/models/silver/sales/stg_ls2.sql` — added `order_ref` (= `Reference`)
- `qargo/models/gold/sales/fact_order.sql` — new
- `qargo/tests/assert_fact_order_additive.sql` — new
