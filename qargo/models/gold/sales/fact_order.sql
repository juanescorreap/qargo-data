{{ config(
    materialized='incremental',
    unique_key=['source_system', 'order_id'],
    on_schema_change='append_new_columns'
) }}

-- Grain: ONE row per real order (per source).
--   PAR  -> order_ref = "Order ID"  (real POS order id)
--   LS2  -> order_ref = "Reference" (real per-receipt transaction id; NOT Account,
--           which groups ~5.5 orders and undercounts — see DIAGNOSIS_C1_C2.md / FACT_ORDER_BUILD.md)
-- order_count is a literal 1, so sum(order_count) is ADDITIVE by construction across
-- any dimension. This model deliberately has NO product grain, so an order can never
-- be split across product cells the way fact_sales does (the C1 root cause).

with order_lines as (
    select
        _source_system,
        order_ref,
        store_name,
        destination,
        sale_date,
        net_sales
    from {{ ref('stg_orders') }}
    where order_ref is not null and btrim(order_ref) <> ''
    {% if is_incremental() %}
      and sale_date > (
          select coalesce(max(d.date), '2000-01-01'::date)
          from {{ this }} f
          join {{ ref('dim_date') }} d on f.date_key = d.date_key
      )
    {% endif %}
),

-- Roll item-lines UP to order grain. store/destination/date are constant within an
-- order; max() picks that single value while guaranteeing exactly one row per order.
order_agg as (
    select
        _source_system          as source_system,
        order_ref               as order_id,
        max(store_name)         as store_name,
        max(destination)        as destination,
        max(sale_date)          as sale_date,
        sum(net_sales)          as order_net_sales
    from order_lines
    group by _source_system, order_ref
)

select
    d.date_key,
    s.store_key,
    coalesce(dest.destination_key, 0) as destination_key,
    o.source_system,
    o.order_id,
    o.order_net_sales,
    1 as order_count
from order_agg o
inner join {{ ref('dim_date') }}        d    on o.sale_date                        = d.date
inner join {{ ref('dim_store') }}       s    on o.store_name                       = s.store_name
left  join {{ ref('dim_destination') }} dest on coalesce(o.destination, 'UNKNOWN')  = dest.destination_name
