-- Additivity regression guard for fact_order (C1 root-cause fix).
--
-- Invariant: summing fact_order.order_count across the table must equal an
-- INDEPENDENT distinct count of real orders computed straight from staging.
-- If anyone re-introduces a sub-order grain (e.g. adds product_key to fact_order),
-- one order would spread across N rows, sum(order_count) would exceed the true
-- distinct count, and this test fails.
--
-- Compared per date_key (mirrors fact_order's INNER joins to dim_date/dim_store so
-- the test isolates additivity, not dimension coverage). Returns offending days;
-- dbt test passes only when zero rows are returned.

with truth as (
    -- independent: one row per real (source, order) mapped to its date
    select max(d.date_key) as date_key
    from {{ ref('stg_orders') }} o
    join {{ ref('dim_date') }}  d on o.sale_date  = d.date
    join {{ ref('dim_store') }} s on o.store_name = s.store_name
    where o.order_ref is not null and btrim(o.order_ref) <> ''
    group by o._source_system, o.order_ref
),

truth_by_day as (
    select date_key, count(*) as distinct_orders
    from truth
    group by date_key
),

fact_by_day as (
    select date_key, sum(order_count) as summed_orders
    from {{ ref('fact_order') }}
    group by date_key
)

select
    coalesce(f.date_key, t.date_key) as date_key,
    f.summed_orders,
    t.distinct_orders
from fact_by_day f
full outer join truth_by_day t on f.date_key = t.date_key
where coalesce(f.summed_orders, 0) <> coalesce(t.distinct_orders, 0)
