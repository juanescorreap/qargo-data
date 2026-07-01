# C4 — Remediation Report: Split `raw_par2` into per-source tables

> **STATUS: CLOSED (2026-07-01).** Old `bronze.raw_par2` dropped after 1:1 migration;
> source entry removed from `sources.yml`; post-DROP dbt (16 models + 57 tests) and pytest
> (333) all PASS. See "Step 7 — Close-out" below.


Root-cause fix for the C4 clobbering bug (see `C4_DIAGNOSIS.md`). Approved approach:
split the shared `bronze.raw_par2` into `raw_par2_csv` (Writer B only) and `raw_par2_api`
(Writer A only), UNION in `bronze_par2` with **CSV-over-API precedence**.

## Executive Summary

- Two writers no longer share a physical table → the incompatible DELETE predicates can
  no longer touch each other's rows. **Clobbering is structurally impossible now.**
- Historical data migrated 1:1: `raw_par2_csv`=**1,081,650**, `raw_par2_api`=**2**, sum
  =**1,081,652** = old `raw_par2` total. Old table then **DROPPED** (Step 7); post-DROP
  dbt + pytest all PASS.
- Verified: pytest **333 passed**, dbt **16 models + 57 tests PASS**, API-writer &
  CSV-loader idempotency proven, and a live replay of the old clobbering scenario shows
  API rows now survive a CSV load (3/3 proofs).
- New finding: the **`SUPABASE_DB_URL` embedded password is stale**; the working
  credential is `SUPABASE_PASSWORD`. Local `par_api.py`/`run.py` (which use the URL) would
  fail auth locally. Flagged, not fixed (out of C4 scope).
- `entry_id` was trivially recoverable and is now carried on `raw_par2_api` for future
  line-level idempotency.

---

## Step 1 — New tables (DDL)

Both tables carry the full 23-column `raw_par2` schema (UNION-compatible) **plus**
`entry_id text` (populated by API, NULL for CSV). Full DDL committed at
`ingestion/sql/raw_par2_split.sql`. Shape:

```sql
CREATE TABLE IF NOT EXISTS bronze.raw_par2_csv ( <23 raw_par2 cols>, "entry_id" text );
CREATE TABLE IF NOT EXISTS bronze.raw_par2_api ( <23 raw_par2 cols>, "entry_id" text );
CREATE INDEX idx_raw_par2_csv_date ON bronze.raw_par2_csv ("Date");
CREATE INDEX idx_raw_par2_api_date ON bronze.raw_par2_api ("Date");
```
Column types match `raw_par2` exactly (`"Item ID" bigint`, `"Item PLU"/"Price"/...` double
precision, `"Order ID" text`, `"_ingested_at" timestamp`, booleans for the flags).

## Step 2 — API writer (`ingestion/par_api.py`)

- `write_raw_par2` now targets `bronze.raw_par2_api`. DELETE stays `WHERE "Location"=:s AND
  "Date"=:d` — safe and self-scoped because the table holds only API rows.
- `build_raw_par2_rows` now carries `entry_id` (from the PAR `OrderEntry` Id already parsed
  in `parse_orders`, `par_api.py:274`). **`entry_id` was recoverable with no parser change.**
- **Idempotency test (real DB, tagged synthetic store, cleaned up):**
  ```
  run1 inserted=3 table_count=3
  run2 inserted=3 table_count=3   → IDEMPOTENT
  entry_id populated rows: 3
  ```

## Step 3 — CSV loader (`ingestion/sources/csv.py`)

- `PAR2CSVIngester.target_table` → `raw_par2_csv`. The generic `loader.py` needed **no
  change** (it keys off `ingester.target_table`); the range DELETE + full-refresh DROP now
  act on `raw_par2_csv` only — never on `raw_par2_api` or the old table.
- **Idempotency test (real DB, date 2099-01-01, cleaned up):**
  ```
  after load A                     : count=1  orders=['A1']
  after load B (re-export same date): count=1  orders=['B1']   (range-delete replaced A)
  after 3rd run (all processed)    : count=1                   (watermark no-op)
  → NO ACCUMULATION
  ```

## Step 4 — dbt (`bronze_par2`, `stg_par2`, dims, `sources.yml`)

- `bronze_par2.sql` is the single PAR combining point: `raw_par2_csv UNION ALL
  (raw_par2_api WHERE (Location,Date) NOT covered by CSV)` → every store/date from exactly
  one source, CSV authoritative.
- `stg_par2.sql`: passes through real `_source_system` (`'par2'`|`'par_api'`) instead of the
  hardcoded `'par2'`.
- `dim_product` / `dim_destination` / `dim_employee`: repointed from `source('bronze',
  'raw_par2')` to `ref('bronze_par2')` so dimensions stay fresh once writers target the
  split tables (they previously read the now-frozen old table — a latent staleness bug this
  fixes).
- `sources.yml`: added `raw_par2_csv` + `raw_par2_api`; `raw_par2` marked **DEPRECATED**
  (kept for transition).
- **`dbt run` (all 15 models + hook): PASS=16, ERROR=0.** dims rebuilt off unified source:
  `dim_product`=6109, `dim_employee`=251, `dim_destination`=15, `dim_store`=21. Incremental
  models `INSERT 0 0` (historical already materialized — no double-count).
- Note: 4-thread `dbt run` intermittently errored on connection saturation **in this sandbox
  only** (libpq socket-shim + transaction pooler); `--threads 1` is clean. Not a fix issue;
  CI runs `--threads 4` on normal networking.

## Step 5 — Historical migration

Smoking gun **pre-migration = 0** clobbered store-days (API had only 2 sandbox rows on
2026-05-27, so the bug had **not yet materialized** — this was a preventive fix). Migration
by `_source_system` (SQL committed at `ingestion/sql/c4_migrate_raw_par2.sql`, empty-target
guard):

| Table | Rows | Source |
|-------|------|--------|
| `raw_par2_csv` | 1,081,650 | old `raw_par2` where `_source_system='par2'` |
| `raw_par2_api` | 2 | old `raw_par2` where `_source_system='par_api'` |
| **sum** | **1,081,652** | = old `raw_par2` total ✅ |

`entry_id` NULL for all historical rows (old table never had it). **Old `raw_par2` left
intact — not dropped/truncated.**

## Step 6 — Final verification

- **pytest: 333 passed, 1 skipped.**
- **dbt: 16 models PASS, 57 tests PASS** (0 errors, single-thread).
- **Post-fix clobbering replay** (live, synthetic 2099 data, cleaned up) — reproduces the
  exact old failure and shows it can no longer destroy data:
  ```
  API rows for 2099-03-01: before CSV load=2, after CSV load=2
  PROOF 1 — CSV load did NOT clobber API rows:            True
  PROOF 2 — bronze_par2 precedence CSV-over-API, 1 row:   True   [('par2','S_CSV')]
  PROOF 3 — API-only store/date preserved as fallback:    True   [par_api]
  ```
- **Post-fix smoking gun (vs `raw_par2_api`): 0** clobbered store-days.
- Final counts: `raw_par2_csv`=1,081,650, `raw_par2_api`=2, `bronze_par2` view=1,081,652,
  old `raw_par2`=1,081,652 (intact).

## Step 7 — Close-out (DROP old table)

User authorized deprecation on 2026-07-01. Actions:
- Pre-check: `grep` confirmed no live model references `source('bronze','raw_par2')` (dims +
  `bronze_par2` read the split tables; only comments/one-time migration SQL mention the name).
  `dbt parse` clean after removing the source.
- `raw_par2` entry **removed** from `sources.yml` (not "deprecated" — removed).
- `DROP TABLE bronze.raw_par2` executed (was 1,081,652 rows). Verified gone; split tables
  intact (`raw_par2_csv`=1,081,650, `raw_par2_api`=2); `bronze_par2` view still =1,081,652.
- **Post-DROP verification — all PASS:**
  - `dbt run`: **PASS=16, ERROR=0**
  - `dbt test`: **PASS=57, ERROR=0**
  - `pytest`: **333 passed, 1 skipped**
  - Confirms nothing referenced the dropped table.

Commit: `chore(bronze): drop deprecated raw_par2, remove from sources (C4 close)`.

**C4 is CLOSED.**

## State of old `bronze.raw_par2`

- **DROPPED** (2026-07-01). Data fully migrated 1:1 beforehand; no live consumers remained.

## BACKLOG PENDIENTE (no arreglado en esta sesión)

1. **`SUPABASE_DB_URL` en `.env` tiene password stale post-rotación** — `par_api.py` y
   `run.py` fallarán auth si usan la URL directa. Corregir manualmente en `.env` con el mismo
   valor ya confirmado en `SUPABASE_PASSWORD` (28-char). Verificar también el GitHub Actions
   secret `SUPABASE_DB_URL`. (Working cred confirmado esta sesión = `SUPABASE_PASSWORD`.)
2. **`entry_id` now on `raw_par2_api`** (NULL for CSV/historical). Enables a future
   `UNIQUE (_source_system, "Order ID", "Item ID", entry_id)` + `ON CONFLICT` upsert — but
   note 90,905 duplicate `(Order ID, Item ID)` groups exist in CSV history, so any UNIQUE
   add still needs a `line_seq` for CSV and a data-cleanup pass first (not a clean migration).
3. **dbt `raw_par2` source** retained in `sources.yml` only for transition/comparison; remove
   it together with the DROP once deprecation is confirmed.

## Commits

```
9563ca2 refactor(bronze): split raw_par2 into raw_par2_csv + raw_par2_api (C4)
37c4015 refactor(silver): union split raw_par2 tables with CSV precedence (C4)
ea3e48a chore(bronze): migrate historical raw_par2 data to split tables (C4)
```
`raw_par2` DROP intentionally **not** committed — awaiting user confirmation.
