# LS2_BUG_REPORT — C4-style cross-store clobber in `raw_ls2`

> **STATUS: FIXED (2026-07-03).** Latent (not-yet-materialized) cross-store clobbering
> bug in the LS2 bronze loader, same shape as C4. Fixed by scoping the incremental
> DELETE by store. Live proof + full test suite green.

Reference playbook: `C4_DIAGNOSIS.md` / `C4_REMEDIATION.md`.

---

## PHASE 1 — Diagnosis (read-only)

### 1. The LS2 writer & its DELETE

- **Active writer:** `LS2CSVIngester` (`ingestion/sources/csv.py`) driven by the generic
  `FileBasedLoader` (`ingestion/loader.py`), wired in `ingestion/run.py`.
- **File grain:** ONE store per file. `Location` is derived from the filename
  (`_store_name_from_ls_filename`, e.g. `...qargocoffeeberkeley...` → `Qargo Coffee Berkeley`).
- **The DELETE (pre-fix, `loader.py`):**
  ```sql
  DELETE FROM bronze."raw_ls2" WHERE "Date" BETWEEN :min_d AND :max_d
  ```
  **Date-range only — NO `WHERE Location = ...`.**

- **Can a store-A file delete store-B rows?** **YES.** `raw_ls2` is a single shared table
  across all stores. Loading store A's file runs a date-range-only DELETE (wiping *every*
  store's rows in A's date span), then appends only store A's rows. Any other store with
  data in that overlapping range is destroyed. This is the exact C4 clobber shape — here
  caused by an under-scoped DELETE rather than two writers with incompatible predicates.

- **More than one writer on `raw_ls2`?** **No.** Only `LS2CSVIngester` is wired in
  `run.py`. `ingestion/sources/excel.py::LS2Ingester` also names `raw_ls2` but is **dead
  code** — it imports `BaseIngester`, which is not defined in `ingestion/base.py` (only
  `FileBasedIngester` exists), and it is never instantiated in `run.py`. So the LS2 fix is
  simpler than C4: no table split needed, just scope the one writer's DELETE.

### 2. Diagnostic SELECT — `bronze.raw_ls2` by store

| Store | min_date | max_date | rows | distinct_days | span_days |
|-------|----------|----------|-----:|--------------:|----------:|
| Qargo Coffee Berkeley | 2026-04-01 | 2026-05-31 | 27,726 | 61 | 61 |

**One store only.** distinct_days (61) == span_days (61) → no internal date gaps.

### 3. Has the bug materialized?

**No — not yet.** Only a single store (Berkeley) has ever been loaded, so there was no
second store for its file to clobber, and Berkeley's own range is gap-free. Exactly like
C4 (which had "0 clobbered store-days" pre-fix): this is a **preventive** fix of a real,
present code defect. The instant a second store's LS2 file with an overlapping date range
is loaded, it would silently delete Berkeley's overlapping rows.

**Decision:** the code-level defect is confirmed (matching C4's latent-bug standard), so
Phase 2 proceeded.

---

## PHASE 2 — Fix

### 4–5. Implementation — scope the DELETE by store (in the generic loader)

The generic loader is shared with PAR CSV, whose date-range DELETE is *safe*
(`raw_par2_csv` holds a single source). So the fix is **opt-in per ingester**, not a
blanket change:

- **`ingestion/base.py`** — new optional `scope_column` property on `FileBasedIngester`,
  default `None` (unscoped = current behavior; safe for single-source tables).
- **`ingestion/sources/csv.py`** — `LS2CSVIngester.scope_column` returns `"Location"`.
  (`PAR2CSVIngester` inherits the `None` default → PAR behavior unchanged.)
- **`ingestion/loader.py`** — when `scope_column` is set, the loader resolves the file's
  single partition value and appends `AND "<col>" = :scope_val` to the DELETE:
  ```sql
  DELETE FROM bronze."raw_ls2"
  WHERE "Date" BETWEEN :min_d AND :max_d AND "Location" = :scope_val
  ```
  A **safety guard** raises `ValueError` if a file resolves to ≠1 store value, refusing to
  run an under-scoped DELETE rather than silently clobbering.

Full-refresh path (whole-table DROP) is unaffected — full refresh is intentional.

### 6–7. Live proof (real DB, synthetic row, cleaned up)

Injected a synthetic row for a **different** store (`Qargo Coffee Zztestsentinel`) dated
`2026-04-15` — inside Berkeley's range — then reprocessed Berkeley's files incrementally
(watermark cleared so the DELETE+append runs):

```
baseline: total=27726 berkeley=27726
synthetic row inserted (store=Qargo Coffee Zztestsentinel, date=2026-04-15): count=1
[ls2] reloaded 27726 rows (15387 + 12339)

=== RESULTS ===
PROOF (non-interference): synthetic other-store row survived Berkeley load: True  (before=1, after=1)
IDEMPOTENCY:            berkeley count stable after reprocess:            True  (before=27726, after=27726)
cleanup: sentinel rows remaining=0, raw_ls2 total=27726
```

- **Non-interference (the firebomb):** the other-store row **survived** the Berkeley load
  (1 → 1). Pre-fix, the date-range-only DELETE (`Date BETWEEN 2026-04-01 AND 2026-04-30`,
  no `Location`) would have removed it.
- **Idempotency:** reprocessing Berkeley left its count unchanged (27,726 → 27,726) — no
  accumulation, no loss.
- Synthetic row cleaned up; `raw_ls2` back to 27,726.

### 8. `dbt run --select stg_ls2 --full-refresh`

`stg_ls2` = **25,186** rows ✅ (matches expected). `stg_orders` view rebuilt in the same
run (a `stg_ls2` full-refresh CASCADE-drops the dependent view).

### 9. Full test suites

- **pytest: 336 passed, 1 skipped** (was 333; +3 new loader tests for scoped DELETE:
  unscoped-has-no-store-predicate, scoped-adds-store-predicate, multi-value-file-raises).
- **dbt test: 58 PASS, 0 ERROR.**
- Unchanged downstream totals: `fact_order` **288,801**, `fact_sale_item` qty **490,209**,
  `raw_ls2` **27,726**.

---

## Summary

| Item | Result |
|------|--------|
| Bug confirmed (code-level) | ✅ date-range-only DELETE, no store scope |
| Materialized? | ❌ not yet (single store loaded) — preventive fix |
| Fix | scope incremental DELETE by `Location` (opt-in `scope_column`) |
| PAR affected? | No — inherits `scope_column = None`, behavior unchanged |
| Non-interference proof | ✅ other-store row survives |
| Idempotency proof | ✅ no accumulation/loss |
| pytest / dbt test | ✅ 336 / 58, all green |

Fix lives in the generic loader but is opt-in, so it is available to any future
one-partition-per-file source, not just LS2.
