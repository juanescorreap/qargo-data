select
    _source_system                                                        as source,
    to_char(date_trunc('month', sale_date), 'YYYY-MM')                   as year_month,
    round(sum(net_sales)::numeric, 2)                                    as net_sales,
    count(distinct order_id)                                             as order_count
from silver.stg_orders
where net_sales > 0
group by _source_system, date_trunc('month', sale_date)
order by date_trunc('month', sale_date), _source_system
