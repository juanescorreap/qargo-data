# C3 — Remediation Report: PAR API product/category enrichment (Option B)

Fix for C3 (`C3_DIAGNOSIS.md`): API rows lost product dimension → `product_key = 0 (UNKNOWN)`.
Scope = **Option B only** (CSV catalog as interim lookup) + neutralize the `Revenue Center = DayPartId`
impact on category. **dbt-only** — `par_api.py` untouched. GetItem (Option A) and the writer-level
DayPartId fix remain backlog.

## Executive Summary

- Root cause was source-shape (GetOrders returns only `ItemId`), so the fix is a **join, not a
  parser edit**. New `dim_item_catalog` maps `ItemId → product` from `raw_par2_csv`; `stg_par2` joins
  it to enrich API rows.
- The 2 current API rows now resolve to **real products & categories** (was UNKNOWN/Other):
  `ALL BUTTER CROISSANT → Food`, `24 OZ ICED DRIP COFFEE → Beverage`, real `product_key`s.
- **Facts unchanged:** `fact_order` order_count = **328,862**, `fact_sale_item` qty = **566,602**
  (no fan-out). dbt **60/60 tests PASS**, pytest **333 passed**.

## 1. Layer decision — `dim_item_catalog` in **silver**

Placed in `qargo/models/silver/sales/dim_item_catalog.sql`, **not gold**. `stg_par2` (silver) consumes
it; a gold placement would make silver depend on gold while gold already depends on silver →
`silver → gold → silver` cycle (dbt would refuse to build). It is a *derived/deduped* lookup (not raw
bronze), so silver — sitting between the bronze source and the `stg_par2` transform — is the correct
home. Materialized as a **table** (overriding the silver default `incremental`), since it is a full
rebuild/dedup, not an append; 966 rows, cheap.

## 2. Distinguishing a DayPartId from a real Revenue Center

Evidence (SELECTs on the real data):

| Source | `Revenue Center` values |
|---|---|
| `raw_par2_csv` | `Beverages`, `FOOD`, `RETAIL`, `NO TAX MENU ITEM`, `Unknown`, `Combos` — all **descriptive** |
| `raw_par2_csv` purely-numeric (`~ '^[0-9]+$'`) | **0 rows** |
| `raw_par2_api` | `640207795` — a **numeric DayPartId** |

So the discriminator is a purely-numeric regex. In `stg_par2`:

```sql
case when b."Revenue Center" ~ '^[0-9]+$' then cat.revenue_center   -- API DayPartId → catalog value
     else b."Revenue Center" end as eff_revenue_center               -- CSV keeps its own
```

Because CSV `Revenue Center` is **never** numeric (0 rows), CSV rows always keep their own value — the
substitution only ever fires for API rows. Category is then derived from `eff_revenue_center` with the
existing `like '%beverage%' / '%food%' / '%retail%' / '%combo%'` ladder.

Product name uses the same guard implicitly via coalesce (CSV name is non-null, so its own value wins):
```sql
coalesce(upper(trim(b."Item Name")), cat.item_name) as eff_item_name
```

## 3. Before / after — `product_name` NULL on API rows

| | `stg_par2` par_api rows | of which `product_name` NULL |
|---|---|---|
| **Before** | 0 correctly-labelled (the 2 rows were mislabelled `par2` with NULL name in the pre-C4 build) | 2 |
| **After** (`--full-refresh`) | **2** (`par_api`) | **0** |

The 2 API rows in `stg_par2` after the fix:
```
DEFAULT | 2026-05-27 | ALL BUTTER CROISSANT   | Food     | par_api
DEFAULT | 2026-05-27 | 24 OZ ICED DRIP COFFEE | Beverage | par_api
```

`dim_item_catalog` = 966 items (1 row per `Item ID`, unique).

## 4. Tests

- **dbt: 60/60 PASS** (57 prior + 3 new: `dim_item_catalog` not_null/unique `item_id`, not_null
  `item_name`). 0 errors.
- **pytest: 333 passed, 1 skipped.**

### Build-order note (not a C3 defect)
`dbt run --select stg_par2 --full-refresh` **cascade-dropped the dependent view `silver.stg_orders`**
(Postgres `DROP TABLE … CASCADE` on the full-refresh). Rebuilt it (`dbt run --select stg_orders …`)
before the facts. Worth remembering: any future `stg_par2 --full-refresh` must be followed by
`stg_orders` (and downstream) — or run `--select stg_par2+`.

## 5. Fact totals — unchanged (no fan-out)

The catalog join is on a **unique** `item_id` (enforced by test), so it cannot multiply rows. Verified
by full-refreshing both facts and comparing to baseline:

| Metric | Baseline | After C3 | Δ |
|---|---|---|---|
| `fact_order` sum(order_count) | 328,862 | **328,862** | 0 ✅ |
| `fact_sale_item` sum(qty) | 566,602 | **566,602** | 0 ✅ |
| `fact_sale_item` row count | 526,282 | 526,283 | **+1** (see below) |

The `fact_sale_item` **qty total is identical**; row count rose by 1 because the 2 API entries
previously collapsed into a single `product_key = 0` row (both UNKNOWN, same order) and now split into
2 distinct real products — quantity is conserved, attribution is corrected. This is the fix working,
not inflation.

> Why the facts were re-run: after enriching silver, the incremental `fact_sale_item` still held the 2
> sandbox rows stale-labelled `par2` (date 2026-05-27 is below the fact watermark, so a normal
> incremental run won't re-ingest them). The `assert_fact_sale_item_qty_additive` test correctly caught
> the silver-vs-fact divergence. A `--full-refresh` of the two facts reconciled it **without changing
> totals** — which is also the definitive fan-out check.

## 6. Items / Menu / Category page status

- The 2 API `fact_sale_item` rows now carry **real `product_key`s** — `24 OZ ICED DRIP COFFEE`
  (`555298872`) and `ALL BUTTER CROISSANT` (`1836539809`) — and categories Beverage / Food, so
  Items / Menu / Category pages will show them as real products instead of UNKNOWN/Other.
- Residual: 2 `fact_sale_item` rows remain `product_key = 0` — these are **pre-existing `par2` (CSV)**
  rows with genuinely NULL `Item Name` (Item ID absent from the catalog / null). Unrelated to C3; not
  regressed by this fix.
- Impact scale today is tiny (2 sandbox rows) but the mechanism is now correct for **any future
  API-primary date**, which was the structural point of C3.

---

## Commits
```
9aefc4b feat(silver): add dim_item_catalog for PAR ItemId→product enrichment (C3)
68087c7 fix(silver): enrich API rows product/category via dim_item_catalog (C3)
```

## BACKLOG PENDIENTE (no en este sub-hilo)
- **Option A:** implement a PAR `GetItem` SOAP call for a canonical, durable `ItemId` catalog (covers
  items never seen in CSV; swaps the lookup source, `stg_par2` join stays identical).
- **DayPartId writer fix** (`par_api.py:314`/`:277`): low priority now — category no longer depends on
  it after C3.
- **PAR API Access Token** leaked in `docs/…Welcome Letter…Refresh.pdf` (P1): rotate + purge history
  (user action, outside repo).
- **Watermark/late-data** (C5): the fact re-ingestion gap that surfaced here (silver ahead of fact
  below the watermark) is exactly the C5 concern.
