-- Qty additivity / stability guard for fact_sale_item (C2 root-cause fix).
--
-- Invariant: per order, sum(fact_sale_item.qty) must equal an INDEPENDENT sum of qty
-- computed straight from staging. If a re-run or a grain change inflates/deflates qty
-- (e.g. a fan-out join duplicating item lines), the per-order totals diverge and this
-- test fails. Mirrors fact_sale_item's INNER dim joins to isolate qty, not coverage.
-- dbt test passes only when zero rows are returned.

with truth as (
    select
        o._source_system as source_system,
        o.order_ref      as order_id,
        sum(o.qty)       as qty
    from {{ ref('stg_orders') }} o
    join {{ ref('dim_date') }}  d on o.sale_date  = d.date
    join {{ ref('dim_store') }} s on o.store_name = s.store_name
    where o.order_ref is not null and btrim(o.order_ref) <> ''
    group by o._source_system, o.order_ref
),

fact as (
    select source_system, order_id, sum(qty) as qty
    from {{ ref('fact_sale_item') }}
    group by source_system, order_id
)

select
    coalesce(f.source_system, t.source_system) as source_system,
    coalesce(f.order_id, t.order_id)           as order_id,
    f.qty as fact_qty,
    t.qty as truth_qty
from fact f
full outer join truth t
    on f.source_system = t.source_system and f.order_id = t.order_id
where coalesce(f.qty, 0) <> coalesce(t.qty, 0)
