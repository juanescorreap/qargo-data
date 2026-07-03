{{ config(
    materialized='incremental',
    unique_key=['source_system', 'order_id'],
    on_schema_change='append_new_columns'
) }}

-- Grain: ONE row per real order (per source) = SAME grain as fact_order, designed for
-- a clean 1:1 JOIN on (source_system, order_id). fact_order carries the additive order
-- count + net sales; this model carries the per-order MONEY EXTRAS (discount/tax/tip)
-- that fact_order/fact_sale_item deliberately omit. Together they restore the metrics
-- that used to live in the dropped fact_sales (Delivery Leakage, etc.).
--
-- Source limitations (documented, not bugs):
--   tip_amount  -> ALWAYS 0. Both stg_par2 and stg_ls2 hardcode 0.0 (the POS feeds
--                  expose no tip). Column kept for forward-compatibility.
--   destination -> NULL for every LS2 order (ls2 has no destination), so LS2 orders
--                  resolve to destination_key = 0 (UNKNOWN).

with order_lines as (
    select
        _source_system,
        order_ref,
        store_name,
        destination,
        sale_date,
        discount_total,
        tax_amount,
        tip_amount,
        _ingested_at
    from {{ ref('stg_orders') }}
    where order_ref is not null and btrim(order_ref) <> ''
    {% if is_incremental() %}
      -- C5: watermark on load time. delete+insert on unique_key replaces reprocessed
      -- orders (whole partitions reload together).
      and _ingested_at > (
          select coalesce(max(_ingested_at), '2000-01-01'::timestamptz) from {{ this }}
      )
    {% endif %}
),

-- Roll item-lines UP to order grain. store/destination/date are constant within an
-- order; max() picks that single value. Money columns SUM across the order's lines.
order_agg as (
    select
        _source_system          as source_system,
        order_ref               as order_id,
        max(store_name)         as store_name,
        max(destination)        as destination,
        max(sale_date)          as sale_date,
        sum(discount_total)     as discount_total,
        sum(tax_amount)         as tax_amount,
        sum(tip_amount)         as tip_amount,
        max(_ingested_at)       as _ingested_at
    from order_lines
    group by _source_system, order_ref
)

select
    d.date_key,
    s.store_key,
    coalesce(dest.destination_key, 0) as destination_key,
    o.source_system,
    o.order_id,
    o.discount_total,
    o.tax_amount,
    o.tip_amount,
    o._ingested_at
from order_agg o
inner join {{ ref('dim_date') }}        d    on o.sale_date                        = d.date
inner join {{ ref('dim_store') }}       s    on o.store_name                       = s.store_name
left  join {{ ref('dim_destination') }} dest on coalesce(o.destination, 'UNKNOWN')  = dest.destination_name
