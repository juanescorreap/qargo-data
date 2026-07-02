# C5 — Diagnosis: incremental watermark silently drops late / retroactive data

> Read-only. No code/model modified, no pipeline run, no commits. DB touched with SELECTs only.

## Executive Summary (5 lines)

1. **The problem lives in the dbt incremental layer (silver `stg_*` + gold facts), NOT bronze.**
   Bronze ingestion is watermarked by *filename* (`processed_files`) + `DELETE`-by-date/`INSERT`, so it
   absorbs late files, backfills and retro corrections correctly. Every silver/gold model instead
   gates on `sale_date > max(sale_date)` — a *business-date* high-water mark.
2. **Most-likely-in-prod:** late monthly CSV and API backfill. Evidence: **99% of `raw_par2_csv`
   (1,071,036/1,081,650) and 98% of `raw_ls2` rows were ingested >2 days after their sale_date** — the
   batch model means data *routinely* lands well below the current watermark.
3. **Truly silent boundary = bronze→silver** (no test compares them; silver `append` just skips old
   dates). silver→gold divergence is partially caught by the additivity tests (they fired in C3).
4. A manual mitigation already exists (`make migrate-csv/migrate-full` force `--full-refresh`) but it's
   **incomplete** (omits `fact_order`/`fact_sale_item`) and **not in the daily CI** (`dbt run`, no refresh).
5. **Fix complexity: LOW–MEDIUM.** At ~1M rows a full rebuild is seconds; the minimal robust fix is a
   load-timestamp watermark (`_ingested_at`) + keyed merge, or scheduled full-refresh of silver+gold.

---

## 1. Watermark map

**Two independent watermark systems.**

**(a) Bronze — filename-based, date-agnostic (correct for late data).**
- `WatermarkManager` tracks processed *files* in `ingestion.processed_files (source_name, filename)`
  (`ingestion/watermark.py:24-44`), consulted by the loader (`loader.py:31` `get_processed`, `:88`
  `mark_processed`). A late CSV = a new filename → processed regardless of its dates; the loader then
  `DELETE … WHERE "Date" BETWEEN min AND max` + `INSERT` (`loader.py:63-79`) so its date range is
  refreshed in place.
- API writer has no watermark at all: `write_raw_par2` does `DELETE … WHERE "Location"=:s AND
  "Date"=:d` + insert (`par_api.py:357-364`), so `par_api.py --date <past>` always writes.
- **`ingestion.watermarks (source_name, last_loaded_date)` (`init_schemas.sql:4-8`) is DEAD** — nothing
  reads/writes it (grep: only the loader's `WatermarkManager`/`processed_files` is used). Confirms the
  C4 note still holds.
- ⇒ **Bronze never silently drops late/backfilled/retro data.**

**(b) dbt incremental — `sale_date` high-water mark (the C5 defect).** Every incremental model uses the
same predicate: `sale_date > coalesce(max(sale_date), '2000-01-01')`:

| Model | Layer | Strategy | Watermark predicate |
|---|---|---|---|
| `stg_par2` | silver | **append** | `cast("Date") > max(sale_date)` — `stg_par2.sql` (is_incremental block) |
| `stg_ls2` | silver | **append** | `cast("Date") > max(sale_date)` — `stg_ls2.sql:48-52` |
| `fact_order` | gold | incremental (unique_key `source_system,order_id`) | `sale_date > max(d.date)` — `fact_order.sql:25-31` |
| `fact_sale_item` | gold | incremental (unique_key `…,product_key`) | `sale_date > max(d.date)` — `fact_sale_item.sql:31-37` |
| `fact_sales` | gold | incremental (unique_key `date/store/product/dest`) | `sale_date > max(d.date)` — `fact_sales.sql:26-32` |
| `fact_sales_by_employee` | gold | incremental (unique_key `date/store/emp`) | `sale_date > max(d.date)` — `fact_sales_by_employee.sql:18-24` |

`stg_orders` is a plain `view` (union of the two stg models, `stg_orders.sql`); dims are `table`
(full rebuild each run). The two silver `append` models are the **first gate**: a date they skip never
reaches gold at all.

## 2. Silent-loss scenarios

For all four, **bronze keeps the data**; loss occurs in the dbt layer under a plain `dbt run`.

| Scenario | Where it's lost | Silent? |
|---|---|---|
| **(a) Late monthly CSV** (May CSV arrives June, after API ran all May) | Bronze OK (new file, delete+insert). **silver `stg_par2` append** skips May (`May ≤ max=June`) → gold never sees it. Worse: silver still holds the *stale* API-May rows appended in May, and post-C4 bronze precedence flips May to CSV-authoritative, so silver is both **stale and missing**. | **Fully silent** — no bronze→silver test exists. |
| **(b) Retroactive silver correction** (C3 enrichment) | Silver force-refreshed (had it); **gold facts** skip `date ≤ max` → stale. | Semi — the `assert_fact_sale_item_qty_additive` test (compares fact vs `stg_orders`) **fired**, which is how C3 caught it. |
| **(c) Manual backfill** (`par_api.py --date 2026-01-15` today) | Bronze OK. **silver append** skips Jan 15 (`< max`) → gold never sees it. | **Fully silent.** |
| **(d) API delayed by POS outage** (business date lands days late) | Same as (c): if the late date `≤ max`, silver append drops it. | **Fully silent.** |

Key asymmetry: scenarios **a/c/d are dropped at SILVER** (append), so silver == gold (both miss) →
the additivity tests **pass** → nothing alerts. Only **b** (silver ahead of gold) trips a test. There
is **no coverage/freshness test at the bronze→silver boundary**, so the most common cases are silent.

## 3. Current-data impact (SELECTs)

**Watermarks are currently aligned** — because C3 just `--full-refresh`ed silver + both facts:

```
bronze raw_par2_csv max Date  2026-05-28   silver stg_par2 max  2026-05-28   fact_order max            2026-05-28
bronze raw_par2_api max Date  2026-05-27   silver stg_ls2  max  2026-05-26   fact_sale_item max        2026-05-28
bronze raw_ls2      max Date  2026-05-26                                     fact_sales / _by_employee 2026-05-28
```
- Dates in `bronze_par2` (417) vs `stg_par2` (417) → **0 missing**.
- `(source, sale_date)` in `stg_orders` not in `fact_order` → **0**.
- Orders in `stg_orders` `≤ fact_order` watermark absent from fact → **0**.

So **no residual gap right now** — but that is an artifact of the manual full-refresh, not the
pipeline. The structural risk is proven by the arrival pattern:

```
raw_par2_csv: 1,071,036 / 1,081,650 rows (99%) ingested >2 days after sale_date
raw_ls2     :    25,717 /     26,257 rows (98%) ingested >2 days after sale_date
raw_par2_api:         0 / 2                       (daily API, near-real-time)
```
Under plain incremental `dbt run`, this batch pattern means late-relative-to-sale_date data is the
**norm**, not the exception — every monthly CSV load is a "scenario (a)".

**Feasibility note for the fix:** silver `stg_par2/stg_ls2/stg_orders` **do not carry `_ingested_at`**
(they expose `_source_system` only) — so a load-timestamp watermark requires threading `_ingested_at`
through the stg models first.

## 4. Root-cause analysis

- **Not bronze.** Bronze correctly re-ingests late/backfilled/retro data (filename watermark +
  delete/insert). The dead `ingestion.watermarks` table is a red herring.
- **The dbt incremental predicate keys on `sale_date` (business date), not load time.** Late/retro
  rows carry an OLD `sale_date` but a NEW `_ingested_at`; `sale_date > max(sale_date)` structurally
  cannot see them. Compounded in silver by `incremental_strategy='append'`, which can't even *update*
  an existing date if reprocessed.
- **Operational band-aid, incomplete + out of CI.** `make migrate-csv` force-refreshes
  `stg_par2 fact_sales fact_sales_by_employee` (`Makefile:20-21`) — but **omits `fact_order` and
  `fact_sale_item`** (the C1/C2 facts added later), so a CSV loaded via that target leaves those two
  stale. The **daily CI runs plain `dbt run`** (`.github/workflows/daily_pipeline.yml:117`, no
  `--full-refresh`), so the automated path has no mitigation at all.
- ⇒ Problem is **dbt-layer (silver + gold together)**; bronze needs no change.

## 5. Proposed fix (not implemented)

Three tiers; pick by data-growth horizon. All keep bronze untouched.

**Option 1 — Load-timestamp watermark + keyed merge (root-cause, recommended long-term).**
- Thread `_ingested_at` through `stg_par2`/`stg_ls2` (select it from bronze) so `stg_orders` carries it.
- Change every incremental predicate to `_ingested_at > (select max(_ingested_at) from {{this}})`.
- Switch silver `stg_*` from `append` to a keyed strategy (`delete+insert`/`merge`) so a reprocessed
  date **updates** instead of duplicating; gold facts already have `unique_key` (delete+insert), so
  they upsert correctly once the predicate lets late rows through.
- **Idempotent?** Yes — merge on the unique keys; re-running the same batch converges.
- **Detects late data?** Yes — anything with a fresh `_ingested_at` is processed, regardless of
  business date. Files: 6 models. MEDIUM.

**Option 2 — Bounded lookback window (cheap interim).**
- Predicate `sale_date > max(sale_date) - interval 'N days'` (e.g. 35 to cover a monthly CSL cycle),
  with silver switched to `delete+insert` for the window (append would duplicate).
- **Idempotent?** Yes with delete+insert. **Detects?** Only within N days; older backfills still lost.
  Cheapest; good stopgap. LOW.

**Option 3 — Full-refresh silver+gold on the automated path (simplest, viable at this scale).**
- Make the daily CI run `dbt run` **without** incremental for these models (materialize the facts as
  `table`, or run `--full-refresh`). Observed cost: full silver+gold rebuild ≈ 1–2 min at ~1M rows
  (facts rebuild in single-digit seconds each). **Idempotent** by construction. **Detects?** N/A — it
  just always recomputes, so nothing is ever missed. Trade-off: daily recompute cost grows with data.

**Independent vs joined:** bronze needs **no** change (already correct), so the bronze and dbt fixes
are independent — do only the dbt side. Within dbt, silver and gold **must move together**: fixing the
predicate in gold while silver still `append`-drops the date achieves nothing (silver is the first
gate). Also **complete the mitigation**: add `fact_order` + `fact_sale_item` to `make migrate-csv`
regardless of which option is chosen.

**Detection (do alongside any option):** add a freshness/coverage test at the **bronze→silver**
boundary (e.g. assert every `(source, sale_date)` in `bronze_par2`/`bronze_ls2` with rows exists in
`stg_orders`) so late-CSV/backfill drops turn CI **red** instead of silent — closing the one gap the
existing additivity tests don't cover.
