{{ config(
    materialized='incremental',
    unique_key=['source_system', 'order_id', 'product_key'],
    on_schema_change='append_new_columns'
) }}

-- Grain: one row per (order, product) = the item-line grain of all three sources,
-- with same-product lines of an order collapsed and their quantities summed.
--   qty: LS2 -> real "Qty" (signed; negatives = returns). PAR -> 1.0 per line
--        (PAR exposes no quantity in CSV or API; documented approximation).
--
-- Items Sold is NET of returns (LS2 negative Qty lines subtract). Decided 2026-06-25,
-- consistent with the 'net sales' convention used elsewhere in reporting. A separate
-- gross "Items Returned" metric is backlog, not built here.
-- order_id = order_ref, the SAME key used by fact_order, so the two facts join cleanly
-- (every order_id here must exist in fact_order — see assert_fact_sale_item_has_parent_order).
-- This is the real "Items Sold" source: sum(qty). fact_sales (old) is untouched.

with item_lines as (
    select
        _source_system,
        order_ref,
        store_name,
        destination,
        product_name,
        sale_date,
        qty,
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

joined as (
    select
        d.date_key,
        s.store_key,
        coalesce(p.product_key, 0)        as product_key,
        coalesce(dest.destination_key, 0) as destination_key,
        il._source_system                 as source_system,
        il.order_ref                      as order_id,
        il.qty,
        il.net_sales
    from item_lines il
    inner join {{ ref('dim_date') }}        d    on il.sale_date                       = d.date
    inner join {{ ref('dim_store') }}       s    on il.store_name                      = s.store_name
    left  join {{ ref('dim_product') }}     p    on upper(trim(il.product_name))       = p.product_name
    left  join {{ ref('dim_destination') }} dest on coalesce(il.destination, 'UNKNOWN') = dest.destination_name
)

select
    date_key,
    store_key,
    product_key,
    destination_key,
    source_system,
    order_id,
    sum(qty)        as qty,
    sum(net_sales)  as item_net_sales
from joined
group by date_key, store_key, product_key, destination_key, source_system, order_id
