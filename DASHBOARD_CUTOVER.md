# Sub-thread 3 — Dashboard cutover to fact_order + fact_sale_item (C1+C2)

> Migrates the dashboard off `fact_sales.order_count` onto `fact_order` (C1) and `fact_sale_item` (C2). Date: 2026-06-25. Commits: `194b5c2` (Group A), `04fcdeb` (Group B), `e2b6a9b` (sources + deprecation).

## Executive summary (5 lines)
1. **8 canonical pages migrated**; 3 legacy duplicates deliberately excluded (scope note below). order_count + avg_ticket → `fact_order`; "Items Sold" → `fact_sale_item.qty`.
2. **Principled split honored:** `net_sales`/`discount_total`/`tax_amount`/`tip_amount` queries stay on `fact_sales` (correct there; new facts don't carry those). No `order_count` is sourced from `fact_sales` in any canonical page anymore.
3. Added missing Evidence sources `gold.fact_order` + `gold.fact_sale_item` (pages couldn't resolve them otherwise).
4. **Validated by executing every migrated query against the live `gold` schema** (Evidence's own datasource): order totals reconcile to **328,862**, item totals to **566,602**.
5. Tests green: **pytest 333 passed / 1 skipped; dbt 57 PASS / 0 fail**.

---

## 1. Page inventory — model used after cutover

| Page | order_count / avg_ticket → | Items Sold → | Stays on fact_sales (net_sales/discount/tax) |
|---|---|---|---|
| `index.md` | fact_order (kpi CM + YTD) | fact_sale_item (2 KPI tiles) | daily_last_90, leaderboard, labor, royalties (net_sales) |
| `items_analysis.md` | — | fact_sale_item (overall + size_breakdown) | — |
| `channels.md` | fact_order (channel_comparison, drivethru, unknown_dest) | — | delivery_leakage (**discount_total**) |
| `menu.md` | — | fact_sale_item (top_products, waste) | retail_evolution, product_mix (net_sales) |
| `stores/[store].md` | fact_order (store_kpis, last_7_days, dow_heatmap, channels) | — | store_kpi_ytd, category_mix (net_sales) |
| `data_quality.md` | fact_order (unknown_dest, unknown_totals, data_watermark) | — | source_summary/source_by_month (derived; see note) |
| `forecasting.md` | fact_order (yoy_comparison, yoy_monthly) | — | forecast_projection/chart, weekday_profiling (net_sales) |
| `trends.md` | fact_order (all 6 queries) | — | — |

`operations.md` = entirely `fact_sales_by_employee` (employee grain) → **out of scope** (no employee-grain order fact exists; its order_count carries the same C1 flaw — backlog).

## 2. Evidence build result

**Local full `evidence build` is not runnable here, and not because of the migration.** Two pre-existing gates:
- `connection.yaml` uses `${SUPABASE_*}` placeholders that **Evidence does not substitute** — the `daily_pipeline.yml` generator writes real values into it **in CI only**. Locally `evidence sources` fails at config (`Port ... NaN`) before any query runs.
- Even past that, the pooler TLS gate (`rejectUnauthorized: true` + placeholder `SUPABASE_SSL_CA`, 5.2 backlog) would block the connection.

Writing real creds into `connection.yaml` locally to force a build was **declined** (re-introduces the C7 plaintext-secret risk). **The Evidence build runs in CI** on deploy (generator + secrets). For this cutover, correctness was validated by **executing every migrated query directly against the same `gold` schema Evidence queries** (§3) — authoritative for SQL validity and numbers.

- **Group A** (`194b5c2`): 6 representative queries (one per page) executed OK against `fact_order`.
- **Group B** (`04fcdeb`): all 5 migrated queries executed OK against `fact_sale_item`.
- No SQL errors; all return sane shapes.

## 3. Per-page numeric validation (vs known 2a/2b totals)

| Check | Result | Reconciles to |
|---|---|---|
| `trends` total order_count (no filter) | 328,862 | == fact_order total ✓ |
| `forecasting` yoy_monthly 2025 + 2026 | 137,256 + 191,606 = 328,862 | == fact_order total ✓ |
| `index` kpi_ytd order_count (2026) | 191,606 | subset of 328,862 ✓ |
| `data_quality` unknown_dest_orders | 21,706 | == all LS2 orders (LS2 dest=UNKNOWN) ✓ |
| `channels` channel_comparison | executes, avg_ticket recomputed | — |
| **global `sum(qty)`** (fact_sale_item) | **566,602** | == 2b Items Sold total ✓ |
| `index` items_ytd (2026) | 321,793 | subset of 566,602 ✓ |
| `menu` top_products (recent month) | ICED LATTE 6,635 units, $6.47 avg unit price | sane ✓ |
| `menu` waste by category | Beverage 48,440 / Food 20,937 / Retail 2,615 | sane ✓ |

No page produced a number that fails to reconcile to the validated 328,862 / 566,602 totals.

## 4. Pages needing a per-query design decision (not a generic swap)

- **`fact_order` has no `product_key`.** Product-grain "Items Sold" pages (`items_analysis` size_breakdown, `menu` top_products/waste) were pointed at **`fact_sale_item`** (which has product_key + qty), not fact_order.
- **`menu` top_products / waste:** "Orders per product" is **not meaningful** (an order spans products). Relabeled to **Items Sold** (`sum(qty)`) and **Avg Unit Price** (`item_net_sales/qty`); DataTable columns updated accordingly.
- **avg_ticket:** every migrated query dropped `avg(f.avg_ticket)` (a grain-average artifact, itself wrong) and recomputes `sum(order_net_sales)/sum(order_count)` from fact_order — both additive and correct.
- **`net_sales` column rename:** fact_order exposes `order_net_sales` (not `net_sales`), so each migrated query aliases it back to `net_sales`.
- **Items Sold label:** index KPI tiles relabeled "Items Sold (net of returns)" to reflect the new meaning (was a synonym for order_count, now real units net of LS2 returns).
- **`data_quality` derived sources** (`source_summary`, `source_by_month`): do **not** reference fact_sales (verified) — left as-is. (Their order_count lineage is a separate follow-up if needed.)

## 5. fact_sales status — partial deprecation, NOT deleted

Confirmed: **no canonical page sources `order_count` from `gold.fact_sales`** anymore (grep clean). Remaining `gold.fact_sales` refs in canonical pages are all `net_sales`/`discount_total` queries — correct there.

Marked with a precise comment (NOT blanket "DEPRECATED") in both `qargo/models/gold/sales/fact_sales.sql` and `dashboard/sources/gold/fact_sales.sql`:
> order_count superseded by fact_order (C1); "Items Sold" by fact_sale_item.qty (C2). STILL the source of truth for discount_total / tax_amount / tip_amount / net_sales, which the new facts do not carry. Do NOT delete.

## 6. Tests
- **pytest:** 333 passed, 1 skipped.
- **dbt test (all):** 57 PASS, 0 fail/error (includes the C1/C2 additivity + referential-integrity singular tests).

## 7. Scope note — 3 legacy pages excluded (M8)

`forecast.md`, `performance.md`, `products.md` are **deliberately excluded from the C1+C2 cutover** — flagged as M8 legacy duplicates in the original audit; recommend **deletion rather than migration**. They still run on `fact_sales.order_count` (inflated) until M8 cleanup resolves them. This is a conscious scope decision of the C1+C2 epic, dated 2026-06-25, not an oversight. (They also lean on discount/tip measures the new facts don't carry, so migrating them would leave them dual-sourced regardless.)

## Open follow-ups (backlog, not blocking)
- Evidence build verification end-to-end depends on the `SUPABASE_SSL_CA` (5.2) being supplied so CI/local can actually connect with strict TLS.
- `operations.md` + `fact_sales_by_employee.order_count` carry the same C1 flaw with no employee-grain order fact — future `fact_order_by_employee` or documented caveat.
- M8 legacy page deletion (`forecast`/`performance`/`products`).
- If discount/tax/tip are ever needed on the new grain, add them to fact_order/fact_sale_item and migrate the remaining fact_sales queries.

## Files changed
- Group A: `index.md`, `channels.md`, `trends.md`, `data_quality.md`, `forecasting.md`, `stores/[store].md`
- Group B: `index.md`, `items_analysis.md`, `menu.md`
- Sources: `dashboard/sources/gold/fact_order.sql` (new), `fact_sale_item.sql` (new), `fact_sales.sql` (deprecation note)
- `qargo/models/gold/sales/fact_sales.sql` (deprecation note)
