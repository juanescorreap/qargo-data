# C4 — Forensic Diagnosis: Concurrent Writers on `bronze.raw_par2`

> **Read-only diagnosis.** No ingestion code modified, no pipeline run, no commits. Data-evidence
> queries could not execute (see §3 blocker); all code findings cite `file:line` from real source.

## Executive Summary (severity + fix complexity)

1. **Confirmed: two live writers share `bronze.raw_par2` with incompatible DELETE predicates.** CSV
   loader deletes by **date-range only, all stores, all sources** (`loader.py:63-69`); API writer
   deletes by **`Location`+`Date`** (`par_api.py:360`). Neither scopes by `_source_system`.
2. **Clobbering is deterministic, not merely a race.** Loading one monthly CSV wipes *every* API row
   for that whole month across *all* stores before re-appending CSV-only data; every nightly API run
   wipes the trailing store-day of any overlapping CSV. Silent — no error, real data loss.
3. **Blast radius is asymmetric:** CSV-after-API = whole-month × all-stores (catastrophic);
   API-after-CSV = single store-day (narrow). Both orders destroy data.
4. **Root cause = shared physical table + no coordination.** No lock, no in-progress flag, no
   `_source_system` predicate; the watermark (`watermark.py`) tracks *files only*, so the API is
   invisible to it and vice-versa. Grains also differ (CSV item-line vs API top-level OrderEntry).
5. **Severity HIGH / P0** (matches AUDIT.md:150). **Fix complexity: LOW** to stop the bleeding
   (~2-line `_source_system` predicate on both DELETEs, no schema change); **MEDIUM** for full
   idempotency (line-level key column + silver precedence + likely data cleanup before any UNIQUE).

---

## 1. Mapping of Writers on `raw_par2`

Table confirmed as `bronze.raw_par2` (dbt source `qargo/models/bronze/sales/sources.yml:7`;
target_table `raw_par2` in `csv.py:21` and `par_api.py:363`).

| # | Writer | File:line | SQL operation | Invocation |
|---|--------|-----------|---------------|------------|
| A | API writer `write_raw_par2` | `ingestion/par_api.py:349-364` | `DELETE FROM bronze.raw_par2 WHERE "Location"=:s AND "Date"=:d` (`:360`) then `df.to_sql(... if_exists="append")` (`:363`) | Per store/day via `process_store` (`:428`). **CI automatic** nightly — `.github/workflows/daily_pipeline.yml:100-106` step "Ingest PAR API data" (cron `0 8 * * *`, `:5`). Also **manual**: `python ingestion/par_api.py [--date ...]`. |
| B | CSV loader `FileBasedLoader.load` for `PAR2CSVIngester` | `ingestion/loader.py:15` (+ `csv.py:15-50`) | Incremental: `DELETE FROM bronze."raw_par2" WHERE "Date" BETWEEN :min_d AND :max_d` (`:63-69`) then `to_sql(... append)` (`:73`). Full-refresh: `DROP TABLE IF EXISTS bronze."raw_par2" CASCADE` (`:26`). | Via `ingestion/run.py:19,51`. **CI automatic** — `daily_pipeline.yml:87-98` step "Load new data into Supabase" runs `python ingestion/run.py` when `data/DDBB_*.csv` present. Also **manual local**: `python ingestion/run.py`. |

**Sibling writer (not `raw_par2`, but forensically critical):**

- `write_entries` → `bronze.raw_par2_entries` (`par_api.py:367-390`, DELETE `store_name`+`business_date`
  `:384-388`). Separate table, **has `PRIMARY KEY (order_id, entry_id)`** (`:344`). The CSV loader
  never touches it → it retains the *full* API history and is the ground-truth oracle for §3.

**Additional writers checked — none live:**

- `ingestion/sources/excel.py:11` `PAR2Ingester` (target `raw_par2`) and `ingestion/sources/api.py:8`
  `APIIngester` both `from ..base import BaseIngester`, but `ingestion/base.py` defines **only**
  `FileBasedIngester` — `BaseIngester` does not exist. **Dead/broken code**: would `ImportError` if
  imported; not referenced by `run.py` (`:14,19`) or anywhere live. Not writers.
- `scripts/*.py` — local xlsx/csv analysis only; no `raw_par2` writes (grep clean).
- No notebooks in repo.

**Concurrency note:** in one CI job the steps are *sequential* (B at `:87` then A at `:100`), so the
"concurrency" framing is imprecise — the damage lands even single-threaded because the DELETE
predicates are incompatible. True concurrent overlap is *also* possible (manual local `run.py` during
the CI cron, or two API runs), but is not required to trigger loss.

---

## 2. Anatomy of the Conflict

### Writer A — API (`par_api.py:349-364`)
- **Deletes:** exactly one store-day — `WHERE "Location"=:s AND "Date"=:d`. No `_source_system` filter,
  so it removes CSV rows for that store-day too.
- **Inserts:** one row per **top-level `OrderEntry`** (`build_raw_par2_rows:288-325`; `Is Modifier`
  always `False` `:319`, modifiers excluded). Columns forced NULL: `Item Name`, `Item PLU`,
  `Discount Total`, `Promotion Total`, `Has Employee Discount`, `Has Customer` (`:305-318`).
  `Revenue Center = DayPartId` (wrong mapping, per AUDIT.md:33). `_source_system='par_api'`,
  `_source_file=None`.

### Writer B — CSV (`loader.py:53-79`, `csv.py:31-50`)
- **Deletes:** the **entire date span of the file** — `WHERE "Date" BETWEEN min AND max`, computed
  from the dataframe (`loader.py:49-50`). A monthly `DDBB_*.csv` ⇒ whole month, **all stores, all
  sources**. No `Location`, no `_source_system` filter. Full-refresh path `DROP TABLE ... CASCADE`
  (`:26`) nukes everything.
- **Inserts:** one row per **CSV item-line** (`Closed Date/Time`→`Date` as `dt.date`, `csv.py:36-37`),
  full column set incl. `Item Name`, `Discount Total`, `Order ID`. `_source_system='par2'`.

### Coordination between them: **none**
- No lock, no "ingestion in progress" flag.
- `WatermarkManager` (`watermark.py`) = `ingestion.processed_files` keyed by `(source_name, filename)`
  — tracks **file-based sources only**. API writes no file, never reads/writes this table. So the two
  writers are mutually invisible. (`ingestion/sql/init_schemas.sql:4` defines a separate date-based
  `ingestion.watermarks` that the current loader doesn't even use.)
- No UNIQUE/PK on `raw_par2` — it's materialised by `to_sql` (`loader.py:72-79`) with no constraint.
  DELETE-then-append is used as a hand-rolled upsert, but the two predicates don't align.

### Exact clobbering scenarios
**Scenario A — CSV after API (normal monthly path, CATASTROPHIC).**
API writes daily per-store rows all month → analyst drops `DDBB_<Month>.csv` into `data/`, commits →
next CI run `run.py` sees a new file → `DELETE WHERE "Date" BETWEEN month_start AND month_end` wipes
**every API row for that month, every store, every source** → inserts CSV rows. Any (store,date) the
API captured but the CSV omits (store missing from export, partial day, API-only orders) is **lost
silently**. Even on overlap, granular API rows are replaced by CSV grain.

**Scenario B — API after CSV (narrow).**
CSV month already loaded → API backfill for an in-month date
(`python ingestion/par_api.py --date <in-month>`) → `DELETE WHERE Location=X AND Date=D` wipes CSV
rows for that store-day → inserts sparse null-heavy API rows. One store-day corrupted.

**Symmetry:** both orders lose data; blast radius is **asymmetric** — A = month × all-stores, B =
one store-day. In steady state, the nightly API run (A-then-B sequence in CI) re-overwrites the
*trailing* store-day of any already-loaded CSV month every night.

---

## 3. Real Impact in Current Data — **NOT VERIFIED (connection blocked)**

Attempted read-only SELECTs against Supabase; **could not execute**:
1. libpq (both `psql` and `psycopg2`) rewrites the host to an abstract unix socket
   `@@7887@aws-1-us-east-1.pooler.supabase.com/.s.PGSQL.6543` → `Connection refused`. Raw Python TCP
   to `aws-1-us-east-1.pooler.supabase.com:6543` **succeeds** (`18.213.155.45`), so it's a
   libpq-interception shim in this environment, not a network outage.
2. Forcing TCP via `hostaddr=<ip>` reaches the pooler but auth fails:
   `FATAL: password authentication failed for user "postgres"` — consistent with a **stale/rotated
   `.env` password** (see `[[credential-topology]]`). Password not fixable read-only.

**Diagnostic queries ready to run once a working read-only connection exists** (saved,
SELECT-only). The decisive one exploits that `raw_par2_entries` is never deleted by the CSV loader,
so it holds API store-days that clobbering removed from `raw_par2`:

```sql
-- SMOKING GUN: store-days the API ingested (entries table) that have NO api rows left in raw_par2
SELECT e.store_name, e.business_date, count(*) AS entry_rows
FROM bronze.raw_par2_entries e
LEFT JOIN (
    SELECT DISTINCT "Location" AS loc, "Date" AS dt
    FROM bronze.raw_par2 WHERE "_source_system" = 'par_api'
) p ON p.loc = e.store_name AND p.dt = e.business_date
WHERE p.loc IS NULL
GROUP BY 1, 2 ORDER BY 2 DESC;              -- any rows = API data clobbered out of raw_par2
```

Supporting queries (also ready): counts by `_source_system` with min/max `Date`; `(Location,Date)`
carrying both sources (double-count risk); duplicate `(Order ID, Item ID)` groups (idempotency /
UNIQUE-violation check); NULL `Order ID` rows by source; `processed_files` history for `par2`.
Full script: `scratchpad/diag.py`.

**Expected symptoms if clobbering already occurred:** (a) non-empty smoking-gun result above; (b)
`par_api` row count far below `raw_par2_entries` count for the same date span; (c) whole months where
`raw_par2` shows only `_source_system='par2'` despite API having run daily; (d) trailing store-day
flipping from `par2` to `par_api`.

---

## 4. Root-Cause Analysis

- **Why the conflict exists:** the two writers were built independently against the same physical
  table with different natural units. The file loader is generic and can only assume a *date range*
  (a file spans one), so it deletes by range. The API fetches *per store per day*, so it deletes by
  store-day. Neither was taught the other exists.
- **Broken assumption:** "only one source writes `raw_par2`." The CSV path predates the API path;
  adding the API (both feed bronze per the architecture) silently violated the implicit single-writer
  assumption. No `_source_system` scoping was added to compensate.
- **Where the fix lives — all three layers, in priority order:**
  1. **Writer logic (P0):** each DELETE must be scoped to its own source.
  2. **Coordination / silver precedence:** decide which source is authoritative per `(store,date)` so
     coexisting rows don't double-count downstream.
  3. **Schema (idempotency):** a real line-level unique key so upsert is possible — but the current
     columns can't form one (see §5).

---

## 5. Proposed Fix (not implemented)

**Does an UPSERT alone solve it? No.** UPSERT needs a shared, line-unique key, and `raw_par2` has
none today:
- `(Order ID, Item ID)` is **not** line-unique — an order can contain the same `Item ID` twice (two
  identical drinks) as two entries. The API *has* a unique `entry_id`, but `build_raw_par2_rows`
  **drops it** (not a `raw_par2` column, `par_api.py:300-324`); the CSV has no entry id at all.
- Keying on `_source_system` too lets both sources coexist (kills cross-clobber) but then **double
  counts** the same real sale from CSV *and* API — so the key alone doesn't decide authority.

**Recommended natural key (once a line id exists):**
`(_source_system, "Order ID", "Item ID", line_seq)` — where `line_seq` = API `entry_id` (add the
column) / CSV `row_number() over (partition by "Order ID","Item ID")`.

**Minimal root-cause plan:**
1. **P0, stop-the-bleeding (~2 lines, no schema change):** add `AND "_source_system" = :src` to both
   DELETEs — `par_api.py:360` (`src='par_api'`) and `loader.py:65-68`
   (`src = ingester.source_name`). Each writer now only ever deletes its own rows; cross-source loss
   ends immediately. Low risk.
2. **Silver precedence:** in `stg_par2`, pick one authoritative source per `(store,date)` (e.g. CSV
   when present else API) so the now-coexisting rows don't double count.
3. **Idempotency (MEDIUM):** carry `entry_id`/`line_seq` into `raw_par2`; then optionally add
   `UNIQUE (_source_system, "Order ID", "Item ID", line_seq)` + `INSERT ... ON CONFLICT DO UPDATE`.

**Would current data violate a UNIQUE constraint? Almost certainly — migration is NOT clean.**
Duplicate `(Order ID, Item ID)` groups are expected (repeat items), and API rows can have NULL
`Order ID` (nullable in `build_raw_par2_rows`). Any UNIQUE add must be **preceded by a
data-cleanup/backfill** (dedup + line_seq assignment). Confirm exact violation counts with §3 queries
`dup (Order ID,Item ID)` and `NULL Order ID by source` before attempting the constraint.

**Cheaper structural alternative:** split physical tables `raw_par2_csv` / `raw_par2_api` and UNION in
`stg_par2` (removes the shared-table coupling entirely; larger dbt change to `stg_par2.sql` +
`sources.yml`). Matches AUDIT.md:40's suggestion.
