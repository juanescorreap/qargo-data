select
    _source_system,
    count(distinct order_id)                                                          as order_count,
    count(*)                                                                          as row_count,
    round(sum(net_sales)::numeric, 2)                                                 as net_sales,
    round(sum(tax_amount)::numeric, 2)                                                as tax_amount,
    round(sum(discount_total)::numeric, 2)                                            as discount_total,
    count(case when destination  is null then 1 end)                                  as null_destination,
    count(case when employee_name is null then 1 end)                                 as null_employee
from silver.stg_orders
group by _source_system
