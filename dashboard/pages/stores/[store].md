---
title: '{params.store}'
---

```sql this_month
select
    sum(f.net_sales)          as total_sales,
    count(distinct d.date)    as days_in_data
from gold.fact_sales f
join gold.dim_date  d on f.date_key  = d.date_key
join gold.dim_store s on f.store_key = s.store_key
where date_trunc('month', d.date) = (
    select date_trunc('month', max(d2.date))
    from gold.dim_date d2
    join gold.fact_sales f2 on d2.date_key = f2.date_key
)
and s.store_name = '${params.store}'
```

```sql projected
select
    round(
        (sum(f.net_sales) / nullif(count(distinct d.date), 0) * 30)::numeric,
    2) as projected_sales
from gold.fact_sales f
join gold.dim_date  d on f.date_key  = d.date_key
join gold.dim_store s on f.store_key = s.store_key
where date_trunc('month', d.date) = (
    select date_trunc('month', max(d2.date))
    from gold.dim_date d2
    join gold.fact_sales f2 on d2.date_key = f2.date_key
)
and s.store_name = '${params.store}'
```

```sql yoy
with ref as (
    select date_trunc('month', max(d.date)) as cur_month
    from gold.dim_date d
    join gold.fact_sales f on d.date_key = f.date_key
)
select
    sum(case when date_trunc('month', d.date) = r.cur_month
             then f.net_sales else 0 end)                         as current_sales,
    sum(case when date_trunc('month', d.date) = r.cur_month - interval '1 year'
             then f.net_sales else 0 end)                         as prior_year_sales,
    case
        when sum(case when date_trunc('month', d.date) = r.cur_month - interval '1 year'
                      then f.net_sales else 0 end) = 0 then null
        else round((
            (sum(case when date_trunc('month', d.date) = r.cur_month then f.net_sales else 0 end) -
             sum(case when date_trunc('month', d.date) = r.cur_month - interval '1 year' then f.net_sales else 0 end))
            / sum(case when date_trunc('month', d.date) = r.cur_month - interval '1 year' then f.net_sales else 0 end)
        )::numeric * 100, 1)
    end                                                            as yoy_pct
from gold.fact_sales f
join gold.dim_date  d on f.date_key  = d.date_key
join gold.dim_store s on f.store_key = s.store_key
cross join ref r
where s.store_name = '${params.store}'
```

```sql monthly_overlay
with ref as (
    select date_trunc('month', max(d.date)) as cur_month
    from gold.dim_date d
    join gold.fact_sales f on d.date_key = f.date_key
)
select
    extract(day from d.date)::int as day_of_month,
    sum(case when date_trunc('month', d.date) = r.cur_month
             then f.net_sales else 0 end) as this_month,
    sum(case when date_trunc('month', d.date) = r.cur_month - interval '1 month'
             then f.net_sales else 0 end) as last_month
from gold.fact_sales f
join gold.dim_date  d on f.date_key  = d.date_key
join gold.dim_store s on f.store_key = s.store_key
cross join ref r
where s.store_name = '${params.store}'
  and (
      date_trunc('month', d.date) = r.cur_month
      or date_trunc('month', d.date) = r.cur_month - interval '1 month'
  )
group by extract(day from d.date)
order by day_of_month
```

```sql daily_breakdown
select
    d.date,
    round(sum(case when p.revenue_center_name = 'Beverage' then f.net_sales else 0 end)::numeric, 2) as beverage,
    round(sum(case when p.revenue_center_name = 'Food'     then f.net_sales else 0 end)::numeric, 2) as food,
    round(sum(case when p.revenue_center_name = 'Retail'   then f.net_sales else 0 end)::numeric, 2) as retail,
    round(sum(f.net_sales)::numeric, 2)                                                               as total,
    sum(f.invoice_count)                                                                              as invoices,
    round((sum(f.net_sales) / nullif(sum(f.invoice_count), 0))::numeric, 2)                          as avg_ticket
from gold.fact_sales f
join gold.dim_date    d on f.date_key    = d.date_key
join gold.dim_store   s on f.store_key   = s.store_key
left join gold.dim_product p on f.product_key = p.product_key
where date_trunc('month', d.date) = (
    select date_trunc('month', max(d2.date))
    from gold.dim_date d2
    join gold.fact_sales f2 on d2.date_key = f2.date_key
)
and s.store_name = '${params.store}'
group by d.date
order by d.date
```

<BigValue data={this_month}    value=total_sales       title="Sales — This Month"     fmt=usd />
<BigValue data={projected}     value=projected_sales   title="Projected Month-End"    fmt=usd />
<BigValue data={yoy}           value=yoy_pct           title="vs Same Month Last Year" fmt=num1 />

## This Month vs Last Month

<LineChart
    data={monthly_overlay}
    x=day_of_month
    y={["this_month","last_month"]}
    title="Daily Sales — Month over Month"
/>

## Daily Breakdown

<DataTable data={daily_breakdown} />
