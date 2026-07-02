# C5 — Remediation Report: load-timestamp watermark + keyed merge

Fix for C5 (`C5_DIAGNOSIS.md`): the dbt incremental layer keyed on `sale_date`, silently dropping
late / retroactive / backfilled rows. Approved **Option 1**. Bronze business logic untouched (only the
`_ingested_at` metadata column promoted); the fix lives in silver + gold dbt models.

## Executive Summary

- Incremental watermark moved from **business date (`sale_date`) → load time (`_ingested_at`)** across
  the 2 silver stg models and 4 gold facts; silver strategy switched `append → delete+insert`.
- **Fire test passed:** a row dated **2025-01-01** (18 months below the watermark) with a fresh
  `_ingested_at` was picked up by a **plain incremental `dbt run`** (no full-refresh) and flowed to
  `stg_par2` → `fact_sale_item` (qty 566,602 → 566,603). The old predicate would have dropped it.
- Two **bronze→silver coverage tests** now turn the previously-silent drop into a CI failure.
- **dbt 62/62 tests PASS**, **pytest 333 passed**, fact invariants held (**328,862 / 566,602**).

## 1. `unique_key` decision (silver `delete+insert`)

**No clean line-level key exists in silver** — `stg_par2`/`stg_ls2` carry `order_ref` and
`product_name` but no line id (PAR `Item ID`/`entry_id` are dropped in staging), so two identical
product lines in an order are indistinguishable. A surrogate line key was rejected (the task's
guidance, and it wouldn't handle line *deletions* on reprocessing anyway).

**Chosen key: `['store_name', 'sale_date']` — a partition key, for both stg models.** Justification:
- The bronze **reload grain is a whole partition**: the CSV loader `DELETE`s a date range and
  re-inserts every row (`loader.py:63-79`); the API writer `DELETE`s a whole `Location`+`Date` and
  re-inserts (`par_api.py:357-364`). So whenever a `(store, date)` is reprocessed, **all** its rows
  arrive together with a uniform fresh `_ingested_at` — the batch is always partition-complete.
  `delete+insert` on `(store_name, sale_date)` therefore replaces the partition wholesale (the
  "insert_overwrite by partition" pattern; dbt-postgres has no native `insert_overwrite`, so
  `delete+insert` is the correct expression).
- **`_source_system` is deliberately excluded.** When a late CSV supersedes prior API rows for the
  same `(store, date)` (bronze_par2 CSV-over-API precedence), a source-scoped key would leave the stale
  API rows orphaned; the partition key deletes both sources and re-inserts the current single-source
  truth. (bronze_par2 guarantees one source per `(Location, Date)`, so this never collapses two
  legitimately-coexisting sources.)
- Gold facts keep their **existing** `unique_key`s (order-grained and cell-grained); those groups are
  always within one `(store, date)` partition, so partition-complete reloads keep the aggregates
  complete.

## 2. Fire test (real late-data proof)

Inserted one synthetic `raw_par2_csv` row: real store (`Qargo Coffee Westerville, OH`), real product
(`8 Oz Cortado`), **`Date = 2025-01-01`** (below the 2026-05-28 watermark; an empty partition, so no
collateral), **`_ingested_at = now()`**, tagged `Order ID = _C5_LATE_TEST`. Then a **plain incremental
`dbt run`** (no `--full-refresh`):

```
stg_par2               INSERT 0 1
fact_order             INSERT 0 1
fact_sale_item         INSERT 0 1
fact_sales             INSERT 0 1
fact_sales_by_employee INSERT 0 1
→ synthetic row present in stg_par2 / fact_sale_item / fact_order
→ fact_sale_item qty 566,602 → 566,603   (the late row was processed)
```

Under the old `sale_date` watermark this row (`2025-01-01 ≤ max`) would have been silently dropped.
Synthetic row then removed from every layer; **totals restored to 566,602 / 328,862** (verified).

## 3. Test results

- **dbt `test`: 62/62 PASS** (60 prior + 2 new coverage tests), 0 errors.
- **pytest: 333 passed, 1 skipped.**
- Coverage tests (`assert_bronze_par2_silver_coverage`, `assert_bronze_ls2_silver_coverage`) PASS =
  no current bronze→silver gap. They mirror the silver row filters (Voided / Is Modifier / Net Sales;
  modifier-group / FinalPrice) so legitimately-filtered dates aren't false positives.

## 4. Fact invariants (unchanged — enrichment/watermark only, no fan-out)

| Metric | Expected | After C5 |
|---|---|---|
| `fact_order` sum(order_count) | 328,862 | **328,862** ✅ |
| `fact_sale_item` sum(qty) | 566,602 | **566,602** ✅ |

Silver counts also unchanged (`stg_par2` 545,323, `stg_ls2` 23,820).

## 5. Makefile `migrate-csv`

Completed: now full-refreshes **all** incremental models — added `stg_ls2`, `fact_order`,
`fact_sale_item` (the last two were missing, leaving the C1/C2 facts stale after a late CSV). Post-C5
a plain `dbt run` also absorbs late CSVs via `_ingested_at`, so this target is now belt-and-braces
rather than the sole mitigation.

## 6. New findings

1. **`_ingested_at` already existed in bronze** (populated by the writers) as `timestamp without time
   zone`; C5 promoted it to `timestamptz` + `DEFAULT now()`. The bronze views (`bronze_par2`,
   `bronze_ls2`) depend on the column, so they were dropped for the `ALTER` and rebuilt by dbt
   (`ingestion/sql/c5_ingested_at_timestamptz.sql`).
2. **`csv.py` used deprecated naive `datetime.utcnow()`** — switched to `pd.Timestamp.now(tz="UTC")`.
   `par_api.py` was already tz-aware (`pd.Timestamp.now("UTC")`).
3. **Operational reminder (unchanged behaviour):** a `--full-refresh` of `stg_par2` cascade-drops the
   `stg_orders` view; rebuild `stg_orders` + facts after (or use `--select stg_par2+`).
4. **LS2 bronze has a C4-style latent bug** (out of C5 scope): the shared `raw_ls2` table is loaded by
   per-store files but the loader `DELETE`s by date range across all stores. Not addressed here; worth
   a separate ticket.

## Commits
```
b781dce feat(bronze): add _ingested_at timestamptz to raw tables (C5)
1db5b1e feat(silver): thread _ingested_at through stg models (C5)
04a9ec1 fix(silver): switch incremental watermark to _ingested_at (C5)
5f4c302 fix(gold): update fact predicates to pass late-arriving rows (C5)
51f15d4 test(coverage): add bronze→silver gap detection tests (C5)
9103d0c fix(makefile): add fact_order + fact_sale_item to migrate-csv (C5)
```

## Design note — bronze vs dbt independence
Bronze needed **no** logic change (its filename watermark + delete/insert already absorb late data), so
the bronze and dbt fixes are independent; only the dbt side was changed. Within dbt, silver and gold
had to move **together** — fixing gold while silver still `append`-dropped the date would achieve
nothing, since silver is the first gate.
