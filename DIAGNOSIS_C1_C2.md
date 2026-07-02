# Diagnosis — C1 (order_count non-additive) & C2 (Items Sold wrong)

> **Phase: DIAGNOSIS ONLY.** No models, schema, or migrations changed. Evidence-based (real SQL/code cited), not assumed. Date: 2026-06-25.

## Executive summary (5 lines)

1. **C1 confirmed.** `fact_sales.order_count = count(distinct order_id)` computed **per grain** day×store×product×channel (`fact_sales.sql:53,59`); the dashboard then does `sum(f.order_count)` (e.g. `index.md:24`). Because one `order_id` repeats across every product- and channel-row of the same order, `sum(order_count)` re-counts each order N times.
2. The audit's *specific* mechanism guess is **REFUTED**: `order_count` is **not** a pre-aggregated source column — it is a `count(distinct)` evaluated at an item-line rollup and then summed again downstream. Same symptom, different cause.
3. **C2 confirmed and is a DISTINCT bug.** "Items Sold" = `sum(f.order_count)` (`index.md:58,64`; `items_analysis.md:48,79`) — it shows the C1 order metric, not items. **No quantity exists in the pipeline at all:** `Qty` is never ingested into silver and there is no `qty`/`item_count` measure in any dbt model.
4. **C1 and C2 are NOT the same root cause.** Fixing C1 (making order_count additive) would make "Items Sold" display the correct *order* count — still not items. True items-sold needs a *new* measure (SUM(Qty) or item-line count) that the model does not have and `fact_sales` has aggregated away.
5. **Blast radius is broad:** 11 dashboard pages consume `sum(f.order_count)`; every `avg_ticket` is derived from it. Fix scope spans `stg_par2`/`stg_ls2`, `fact_sales`, the API row-builder, and all consuming pages.

---

## 1. Grain mapping per source

All three sources land in `bronze.raw_par2`/`raw_ls2`; `bronze_par2`/`bronze_ls2` are pass-through `select *` (`bronze_par2.sql:1`, `bronze_ls2.sql:1`). `stg_orders` is a plain `union all` of `stg_par2` + `stg_ls2` (`stg_orders.sql:3-5`).

| Source | Raw grain | order_id semantics | Qty? | Evidence |
|---|---|---|---|---|
| **PAR CSV (monthly)** | **one row per item line** (non-modifier) | real POS `Order ID` | dropped before silver | `stg_par2.sql:27` (`"Order ID" as order_id`), filters `Is Modifier = false`, `Voided = false` (`:39-40`) |
| **PAR API (daily)** | **one row per `OrderEntry`** (= item line) | real order `Id` | **absent at source** | `par_api.py:298-324` loops `for entry in entries`, one `rows.append` per entry; `"Order ID": entry["order_id"]` (`:320`) |
| **LS2 (Lightspeed CSV)** | **one row per item line** (non-modifier) | **`Account`** — a check/account number, NOT an order id | present in raw, dropped at silver | `stg_ls2.sql:32` (`"Account" as order_id`), filter `Group not ilike '%modifier%'` (`:44`) |

**Key cross-source inconsistencies found:**
- **Grain is actually consistent** — all three are item-line grain. So the double-counting is *not* caused by mixing order-grain and item-grain rows.
- **`order_id` semantics are NOT consistent.** PAR (CSV + API) = a true per-order id. **LS2 = `Account`** (`stg_ls2.sql:32`), which is a customer/check account, not an order. `count(distinct order_id)` on LS2 counts distinct *accounts*.
- **PAR API injects two extra defects** (relevant downstream, not strictly C1):
  - `"Item Name": None` (`par_api.py:305`) → every API row joins to `product_key = 0 (UNKNOWN)` in `fact_sales.sql:43`. (This is C3, noted for context.)
  - `"Taxes": order.get("tax")` (`par_api.py:310`) — the **order-level** tax is copied onto **every** entry row, so `sum(tax_amount)` over a multi-item order multiplies the tax. Separate tax double-count, flagged here.

---

## 2. Facts model trace — where order_count comes from

`fact_sales.sql`:
- Grain: `unique_key=['date_key','store_key','product_key','destination_key']` (`:3`), enforced by `group by date_key, store_key, product_key, destination_key` (`:59`).
- `order_count` is **computed in the fact model**, not inherited: `count(distinct order_id) as order_count` (`:53`).
- `avg_ticket` is also pre-computed per grain: `sum(net_sales)/nullif(count(distinct order_id),0)` (`:57`).
- Source rows come from `stg_orders` (item-line grain) via `orders`→`joined` (`:7-45`); `order_id` survives into `joined` (`:37`) and is consumed only by the `count(distinct)`.

**Hypothesis test (audit step 2):** *"order_count is a pre-aggregated source field; summing it across item rows of one order counts that order N times."*
→ **REFUTED as stated.** `order_count` is **not** carried from the source. The true mechanism:
- `count(distinct order_id)` is correct **within** a single (day,store,product,channel) cell.
- But one physical order spreads across multiple cells: different `product_key` per item, and potentially multiple `destination_key`. So the same `order_id` is counted **once per cell it touches**.
- The dashboard's `sum(f.order_count)` (`index.md:24`, `operations.md:14`, etc.) then adds those per-cell counts → **the order is counted once for every distinct (product,channel) it contains.** An order with 3 distinct products in 1 channel ⇒ counted 3×.
- `fact_sales_by_employee.sql` has the identical pattern at grain day×store×employee (`:48,54`).

This is a genuine **non-additivity of a distinct-count across a star-schema rollup**, not an inherited-column bug.

---

## 3. "Items Sold" / Qty trace

**Metric definition (Evidence):**
- `index.md:24` `sum(f.order_count) as order_count`; `:58` `<BigValue value=order_count title="Items Sold" />`; `:64` same for YTD.
- `items_analysis.md:48` `sum(f.order_count) as items_sold`; `:79` same; rendered as `Items Sold` columns (`:67,124`).

So **"Items Sold" is literally `sum(f.order_count)`** — the C1-inflated order metric, re-labeled. It uses **neither** item quantity **nor** item-line count.

**Does any quantity exist?**
- `grep -rniE "qty|quantity" ingestion/` → **empty.** `Qty` is never mapped on ingest.
- `grep -rniE "qty|quantity|item_count|line_count|units" qargo/models/` → **empty.** No quantity/line measure anywhere in bronze/silver/gold.
- The LS2 CSV ingester keeps all columns (`csv.py:82` `read_csv` with no `usecols`; only filters rows `:88` and adds metadata `:91-95`), so a `Qty`-like column may physically survive into `bronze.raw_ls2` — **but `stg_ls2`'s SELECT (`:7-40`) never selects it**, so it dies at silver. PAR API never produces a quantity at all (`build_raw_par2_rows`, `par_api.py:300-324`).
- Even an item-**line** count is unrecoverable from `fact_sales`: the `group by` (`fact_sales.sql:59`) collapses item lines, and no `count(*)`/`sum(1)` line-measure is kept.

**LS2 `Account`-as-order_id effect (audit step 3):**
- `count(distinct order_id)` on LS2 = `count(distinct Account)`. If one `Account` spans **multiple real orders** (repeat customer, open tab, loyalty account), those orders **merge into one** → LS2 order_count is an **undercount**. It never *fragments* an order (one order = one account at one moment).
- Direction is **opposite** to PAR's `sum`-overcount. So the two sources distort the same column in different directions, and any blended "Items Sold"/avg_ticket mixes an inflated PAR figure with a deflated LS2 figure.

---

## 4. Are C1 and C2 the same root cause?

**No — related, not identical. Two bugs sharing one visible column (`sum(order_count)`).**

| | C1 | C2 |
|---|---|---|
| Symptom | `sum(order_count)`, avg_ticket, leaderboards inflated | "Items Sold" doesn't reflect items |
| Root cause | `count(distinct order_id)` evaluated per sub-grain, then summed across grains (`fact_sales.sql:53,59` → `index.md:24`) | (a) wrong measure chosen — `order_count` shown as items (`index.md:58`); (b) **no quantity/line measure exists** — `Qty` never ingested, item lines aggregated away |
| LS2 angle | LS2 `order_id=Account` undercounts orders (`stg_ls2.sql:32`) | same column, so inherits the undercount |

**Justification from the SQL:** if C1 is fixed so that the order count is additive (e.g. a true `count(distinct order_id)` at order grain), the number under the "Items Sold" tile becomes a correct **order** count — still not an item count, because nothing in the model carries item quantity. Conversely, implementing true items-sold (SUM(Qty) or line count) does nothing for avg_ticket/leaderboard correctness, which depends on the *order* count. **The grain fix and the quantity fix are independent.** They only *appear* unified because the dashboard happens to point the "Items Sold" tile at `order_count`.

---

## 5. Dashboard impact (change radius for Phase 2)

Pages/queries consuming `sum(f.order_count)` (or the `items_sold` alias built from it):

| Page | Lines | Use |
|---|---|---|
| `index.md` | 24, 40, 58, 64 | KPI cards: "Items Sold", "Items Sold YTD", avg_ticket (CM + YTD) |
| `items_analysis.md` | 48, 67, 79, 109, 124 | "Items Sold" table + size breakdown |
| `operations.md` | 14, 33, 56, 86, 95–97 | Orders, orders/day, productivity |
| `trends.md` | 12, 27, 35, 43–46, 57, 70, 78–79, 91, 98–99, 112–113 | MoM orders, avg_ticket trends |
| `channels.md` | 9, 90, 107, 132–136 | Orders by channel, unknown-dest % |
| `products.md` | 10, 57, 76, 93–97 | Orders by product, unknown % |
| `menu.md` | 57, 107 (+ `attachment_rate_monthly` source) | Orders; attach-rate uses order_id grain in a derived source (see note) |
| `performance.md` | 9, 44 | Orders |
| `stores/[store].md` | 8, 36, 73, 78, 143, 170, 180, 199 | avg_ticket, daily orders, channel/product orders |
| `forecasting.md` | 102, 104, 132 | YoY order volume, forecast base |
| `data_quality.md` | 8, 19, 27, 50, 60–64, 76–80, 91 | "Total Orders", unknown-employee/dest % |

- **Every `avg_ticket` in the dashboard** is `sum(net_sales)/sum(order_count)` (e.g. `index.md:25,41`, `stores/[store].md:8`) → all understated by the C1 inflation.
- Ratio metrics (`unknown % = order_count_subset / order_count_total`, e.g. `channels.md:132-136`, `data_quality.md:60-64`) are **less** wrong (both sides inflated) but not exactly right, since numerator and denominator inflate by different per-cell factors.
- **Note:** `menu.md` attachment rate reads a derived source `attachment_rate_monthly` (not `fact_sales`); per `CLAUDE.md` it needs an order_id-level self-join, but `fact_sales` has no `order_id` column (aggregated away at `:59`). That source must hit `stg_orders`/silver directly — verify separately; it's adjacent to this fix but not the same query.

---

## 6. Proposed fix (proposal only — Phase 2)

**Target grain — split the single fact into two, by natural grain:**

- **`fact_sale_item`** — one row per item line (the natural grain of all three sources). Additive measures only: `net_sales`, **`qty`** (newly ingested), `item_line_count = 1`, per-line `tax`/`discount`. Keys: `order_id` (consistent), `date/store/product/destination/employee`. "Items Sold" = `sum(qty)` (or `sum(item_line_count)` until Qty is trusted).
- **`fact_order`** — one row per order (grain = `order_id`). Order-level measures: order `net_sales`, `tax`, `tip`, and an additive **`order_count = 1`**. True order count = `count(*)` / `sum(order_count)`; avg_ticket = `order net_sales / order_count`. This makes order_count additive by construction and kills C1.
- *Alternative (lighter):* keep one item-grain fact but **stop pre-computing `count(distinct)`**; carry `order_id` into the fact and let Evidence compute `count(distinct order_id)` at query time. Viable since Evidence runs SQL at build; but it forces every page to change to `count(distinct order_id)` and still needs a separate Qty measure — so the two-fact split is cleaner.

**Models/code that would change (for scoping, not now):**
- `ingestion/par_api.py` — carry an item **quantity** per `OrderEntry` and stop copying order-level `Taxes` onto every entry (`:310`); emit per-order tax once (feeds `fact_order`).
- `ingestion/sources/csv.py` / `stg_par2.sql` / `stg_ls2.sql` — select/propagate `Qty`; **resolve LS2 `order_id`** to a real order key or explicitly document that LS2 has no order id and treat `Account` accordingly (its order_count is an account-count).
- `fact_sales.sql` — re-grain to `fact_sale_item` + add `fact_order` (or remove the pre-aggregated `count(distinct)`); `fact_sales_by_employee.sql` mirrors the change.
- All 11 dashboard pages in §5 — point order metrics at `fact_order.order_count` (additive) and "Items Sold" at `fact_sale_item.qty`; relabel the current "Items Sold" tile (`index.md:58,64`) to "Orders" if Qty is not yet trusted.
- Add dbt tests: `unique` on each new fact's grain + `relationships` to dims (none exist today), and a reconciliation check that `sum(order_count)` over `fact_order` equals `count(distinct order_id)` over `fact_sale_item`.

**Out of scope of C1/C2 but adjacent (flag for the same PR):** API `product_key=0` (C3, `par_api.py:305`) and API tax duplication (`par_api.py:310`).
