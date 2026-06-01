{{ config(
    materialized='incremental',
    unique_key=['date_key', 'store_key', 'product_key', 'destination_key'],
    on_schema_change='append_new_columns'
) }}

with orders as (
    select
        sale_date,
        store_name,
        revenue_center,
        net_sales,
        order_id,
        tip_amount,
        destination,
        tax_amount,
        discount_total,
        product_name
    from {{ ref('stg_orders') }}
    {% if is_incremental() %}
    where sale_date > (
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
        coalesce(dest.destination_key, 0) as destination_key,
        coalesce(p.product_key, 0) as product_key,
        o.net_sales,
        o.order_id,
        o.tip_amount,
        o.tax_amount,
        o.discount_total
    from orders o
    inner join {{ ref('dim_date') }}        d    on o.sale_date                              = d.date
    inner join {{ ref('dim_store') }}       s    on o.store_name                             = s.store_name
    left  join {{ ref('dim_product') }}     p    on upper(trim(o.product_name))              = p.product_name
    left  join {{ ref('dim_destination') }} dest on coalesce(o.destination, 'UNKNOWN')       = dest.destination_name
)

select
    date_key,
    store_key,
    product_key,
    destination_key,
    sum(net_sales)                                                              as net_sales,
    count(distinct order_id)                                                    as order_count,
    sum(tip_amount)                                                             as tip_amount,
    sum(tax_amount)                                                             as tax_amount,
    sum(discount_total)                                                         as discount_total,
    round((sum(net_sales) / nullif(count(distinct order_id), 0))::numeric, 2)  as avg_ticket
from joined
group by date_key, store_key, product_key, destination_key
