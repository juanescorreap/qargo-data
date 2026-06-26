# Phase 2b — fact_sale_item build (C2 root-cause fix) — ✅ CLOSED

> Scope: build `fact_sale_item` only. `fact_sales` (old, live) and `fact_order` (2a) untouched. No dashboard changes (sub-thread 3). Date: 2026-06-25.

## Business decision (closed 2026-06-25): Items Sold = NET of returns

"Items Sold" is **net of returns** — LS2 negative `Qty` lines (returns/refunds, 1,664 rows) subtract from the total, consistent with the 'net sales' convention used elsewhere in reporting. So `sum(qty)` = 566,602 is a **net** figure.

Formalized in:
- `fact_sale_item.sql` header comment (explicit decision + date).
- `schema.yml` → `fact_sale_item.qty` column `description`: states "Items Sold, NET of returns", explains LS2 signed Qty vs PAR 1.0/line, and notes `qty` can be negative at row level (no `is_non_negative`).

No separate "Items Returned" metric is built here → **[BACKLOG PENDIENTE]** (build only if the business asks; does not block C1+C2). `fact_sale_item` already carries the signed LS2 lines, so a future gross/returned split is derivable without re-modeling.

Tests after formalization: **12 PASS** (schema not_null on `fact_order`/`fact_sale_item` + 3 singular: qty-additive, parent-order, order-additive). Python suite: 333 passed, 1 skipped.

**Phase 2b is CLOSED.** C1 (`fact_order`, 2a) + C2 (`fact_sale_item`, 2b) root causes both resolved at the model layer. Remaining: sub-thread 3 (dashboard cutover) and the adjacent C3 items (API product/tax), independent of this close.

## Executive summary (5 lines)
1. **Qty availability: LS2 yes, PAR no.** `raw_ls2.Qty` is real (double, 0 nulls, integer values, signed). PAR has **no** quantity in either CSV (20 cols, none) or API (`OrderEntry` parses none). Decision: LS2 → real `Qty`; PAR → `qty = 1.0` per item line (documented approximation).
2. Root cause fixed at source: `stg_ls2` was dropping `Qty`; now exposed (`qty`), plus `stg_par2` emits `qty = 1.0`. `fact_sale_item` is **one row per (order, product)** with `sum(qty)` — the first real units measure in the stack.
3. Both regression tests **PASS**: qty additivity (per-order sum == independent staging sum) and referential integrity (every `fact_sale_item` order exists in `fact_order` — 0 orphans).
4. **New real "Items Sold" = 566,602 units** vs the old mislabeled tile **524,238** (= `sum(order_count)`). These are **different metrics** (units vs inflated order count) — reported as contrast, not better/worse.
5. `fact_sale_item` reconciles to `fact_order`: both see exactly **328,862** distinct orders.

---

## 1. Qty availability per source (investigated, not assumed)

| Source | Qty available? | Where / evidence | Decision |
|---|---|---|---|
| **PAR CSV** | **No** | CSV header has 20 cols, none quantity (`Price/Net Sales/...`, no Qty); `raw_par2` schema confirms | `qty = 1.0` per line |
| **PAR API** | **No** | `OrderEntry` parsing pulls `ItemNetSales/ItemGrossSales/DisplayPrice` only — no quantity field (`par_api.py:269-283`) | `qty = 1.0` per line |
| **LS2** | **Yes** | `raw_ls2.Qty` (double precision); over SALE/UPDATE non-modifier rows: 23,820 rows, **0 nulls, all integer, range −2..5**, 1,664 non-positive (returns/refunds), sum = 21,279 | real signed `Qty` |

**Decision for PAR (no real qty):** use `qty = 1.0` per item line — **not** NULL-and-exclude. Justification: PAR's native grain is already one row per item line (modifiers/voids filtered out in `stg_par2`), so each row genuinely represents at least one item; `1.0` is the only defensible value and keeps PAR in the Items-Sold metric. This **under**counts only if a single PAR line legitimately bundled multiple identical units — which PAR's export structure gives no way to detect. Documented as a known approximation, not hidden.

**LS2 signed Qty:** negatives (returns/refunds, 1,664 rows) are kept, so `sum(qty)` is **net** items sold (21,279). Flagged so the dashboard label can say "net of returns" at cutover if desired.

---

## 2. fact_sale_item design

- **Grain:** one row per `(source_system, order_id, product_key)` — item-line grain with same-product lines of an order collapsed (qty summed). `unique_key=['source_system','order_id','product_key']`.
- **Columns:** `date_key`, `store_key`, `product_key`, `destination_key`, `source_system`, `order_id` (= `order_ref`, same key as `fact_order`), `qty` (sumable), `item_net_sales`.
- **Source:** `stg_orders` (item-line grain), inner joins to `dim_date`/`dim_store` (mirrors `fact_sales`/`fact_order` coverage), left joins to `dim_product`/`dim_destination` (`coalesce(...,0)`).
- **Root-cause fix:** `Qty` exposed in `stg_ls2` (was dropped) and `qty=1.0` added to `stg_par2`. Both carried via `stg_orders` (`select *`). `fact_sales` and `fact_order` select explicit columns and never reference `qty`, so both are **unchanged** (verified — their order/row counts identical, all tests green). Staging `--full-refresh`ed to backfill `qty` across history.

`fact_sale_item.sql` in `qargo/models/gold/sales/`. `fact_sales.sql` and `fact_order.sql` **not modified**.

---

## 3. Regression tests (both PASS)

| Test | Asserts | Result |
|---|---|---|
| `assert_fact_sale_item_qty_additive.sql` | per-order `sum(qty)` in fact == independent `sum(qty)` from staging (no inflation/deflation on re-run or fan-out) | **PASS** |
| `assert_fact_sale_item_has_parent_order.sql` | every `(source_system, order_id)` in fact_sale_item exists in `fact_order` (no orphan item lines) | **PASS** |

`assert_fact_order_additive` (2a) re-run: still **PASS**. Full Python suite: **333 passed, 1 skipped**.

---

## 4. Numerical contrast — NOT a like-for-like comparison

| Metric | Value | Nature |
|---|---|---|
| OLD dashboard "Items Sold" = `sum(fact_sales.order_count)` | **524,238** | inflated, non-additive **order** count, mislabeled as items |
| NEW Items Sold = `sum(fact_sale_item.qty)` | **566,602** | real item **units** (LS2 net of returns; PAR 1/line) |
| by source (qty) | par2 545,323 · ls2 21,279 | |
| distinct orders in fact_sale_item | 328,862 | == `fact_order` (referential ✓) |

These two numbers measure **different things** (units sold vs an inflated order count) and must not be read as an improvement or regression. They are shown only so the magnitude of the visual change at cutover is understood: the tile value moves from ~524k to ~567k and changes meaning from "orders (double-counted)" to "items (real units)".

---

## 5. New findings
- **PAR has no quantity anywhere** (CSV or API) — the biggest data-quality gap for true Items Sold. PAR Items-Sold is line-count, not unit-count, until/unless the PAR API `OrderEntry` exposes a Quantity field (worth checking the raw SOAP payload in a future spike). Roadmap item.
- **LS2 has 1,664 return/void lines (negative Qty)** included in the signed sum. Decide at cutover whether "Items Sold" should be gross or net of returns.
- Adjacent bugs from the diagnosis (API `Item Name=None` → `product_key=0`; API order-tax copied per line) are **not** touched here and are **not** inherited as new defects — `fact_sale_item` does not use tax, and `product_key=0` rows still aggregate correctly by qty (they just land in UNKNOWN product, a pre-existing C3 issue).

## Files changed
- `qargo/models/silver/sales/stg_ls2.sql` — expose `qty` (real `Qty`)
- `qargo/models/silver/sales/stg_par2.sql` — add `qty = 1.0`
- `qargo/models/gold/sales/fact_sale_item.sql` — new
- `qargo/tests/assert_fact_sale_item_qty_additive.sql` — new
- `qargo/tests/assert_fact_sale_item_has_parent_order.sql` — new
