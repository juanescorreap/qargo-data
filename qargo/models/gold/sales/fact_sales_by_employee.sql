{{ config(
    materialized='incremental',
    unique_key=['date_key', 'store_key', 'employee_key'],
    on_schema_change='append_new_columns'
) }}

with orders as (
    select
        sale_date,
        store_name,
        employee_name,
        net_sales,
        order_id,
        tip_amount,
        tax_amount,
        discount_total,
        _ingested_at
    from {{ ref('stg_orders') }}
    {% if is_incremental() %}
    where _ingested_at > (  -- C5: load-time watermark (was sale_date)
        select coalesce(max(_ingested_at), '2000-01-01'::timestamptz) from {{ this }}
    )
    {% endif %}
),

joined as (
    select
        d.date_key,
        s.store_key,
        coalesce(emp.employee_key, 0) as employee_key,
        o.net_sales,
        o.order_id,
        o.tip_amount,
        o.tax_amount,
        o.discount_total,
        o._ingested_at
    from orders o
    inner join {{ ref('dim_date') }}     d   on o.sale_date                          = d.date
    inner join {{ ref('dim_store') }}    s   on o.store_name                         = s.store_name
    left  join {{ ref('dim_employee') }} emp on coalesce(o.employee_name, 'UNKNOWN') = emp.employee_name
)

select
    date_key,
    store_key,
    employee_key,
    sum(net_sales)                                                              as net_sales,
    count(distinct order_id)                                                    as order_count,
    sum(tip_amount)                                                             as tip_amount,
    sum(tax_amount)                                                             as tax_amount,
    sum(discount_total)                                                         as discount_total,
    round((sum(net_sales) / nullif(count(distinct order_id), 0))::numeric, 2)  as avg_ticket,
    max(_ingested_at)                                                           as _ingested_at
from joined
group by date_key, store_key, employee_key
