with order_categories as (
    select
        o.order_id,
        o.sale_date,
        max(case when p.revenue_center_name = 'Beverage' then 1 else 0 end) as has_beverage,
        max(case when p.revenue_center_name = 'Food'     then 1 else 0 end) as has_food
    from silver.stg_orders o
    join gold.dim_product p on upper(trim(o.product_name)) = p.product_name
    where o.net_sales > 0
    group by o.order_id, o.sale_date
)
select
    to_char(date_trunc('month', sale_date), 'YYYY-MM')                               as year_month,
    date_trunc('month', sale_date)::date                                              as month_date,
    count(*) filter (where has_beverage = 1)                                          as beverage_orders,
    count(*) filter (where has_beverage = 1 and has_food = 1)                        as paired_orders,
    round(
        count(*) filter (where has_beverage = 1 and has_food = 1)::numeric
        / nullif(count(*) filter (where has_beverage = 1), 0),
        4
    )                                                                                 as attachment_rate_pct
from order_categories
group by date_trunc('month', sale_date)
order by date_trunc('month', sale_date)
