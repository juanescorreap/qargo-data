---
title: Trends & Temporal Analysis
---

```sql monthly_sales
select
    d.year,
    d.month,
    d.month_name,
    lpad(d.year::int::text, 4, '0') || '-' || lpad(d.month::int::text, 2, '0') as year_month,
    round(sum(f.order_net_sales)::numeric, 2)    as net_sales,
    sum(f.order_count)                           as order_count
from gold.fact_order f
join gold.dim_date d on f.date_key = d.date_key
group by d.year, d.month, d.month_name
order by d.year, d.month
```

```sql mom_growth
with monthly as (
    select
        d.year,
        d.month,
        d.month_name,
        lpad(d.year::int::text, 4, '0') || '-' || lpad(d.month::int::text, 2, '0') as year_month,
        round(sum(f.order_net_sales)::numeric, 2)     as net_sales,
        sum(f.order_count)                            as order_count
    from gold.fact_order f
    join gold.dim_date d on f.date_key = d.date_key
    group by d.year, d.month, d.month_name
),
with_lag as (
    select *,
        lag(net_sales)   over (order by year, month) as prev_net_sales,
        lag(order_count) over (order by year, month) as prev_order_count
    from monthly
)
select
    year_month,
    month_name,
    year,
    net_sales,
    order_count,
    prev_net_sales,
    round(((net_sales - prev_net_sales) / nullif(prev_net_sales, 0))::numeric, 4)                as mom_sales_pct,
    round(((order_count - prev_order_count) / nullif(prev_order_count, 0))::numeric, 4)          as mom_orders_pct
from with_lag
order by year, month
```

```sql yoy_comparison
select
    d.month,
    d.month_name,
    cast(d.year as text)                         as year,
    round(sum(f.order_net_sales)::numeric, 2)    as net_sales,
    sum(f.order_count)                           as order_count
from gold.fact_order f
join gold.dim_date d on f.date_key = d.date_key
where d.year in (2024, 2025, 2026)
group by d.year, d.month, d.month_name
order by d.month, d.year
```

```sql day_of_week
with daily as (
    select
        f.date_key,
        sum(f.order_net_sales)                                                 as net_sales,
        sum(f.order_count)                                                     as order_count
    from gold.fact_order f
    group by f.date_key
)
select
    d.day_of_week,
    d.day_name,
    round(avg(daily.net_sales)::numeric, 2)                                    as avg_net_sales,
    round(avg(daily.order_count)::numeric, 1)                                  as avg_orders,
    round((avg(daily.net_sales) / nullif(avg(daily.order_count), 0))::numeric, 2) as avg_ticket
from daily
join gold.dim_date d on daily.date_key = d.date_key
group by d.day_of_week, d.day_name
order by d.day_of_week
```

```sql weekend_vs_weekday
with daily as (
    select
        f.date_key,
        sum(f.order_net_sales) as net_sales,
        sum(f.order_count)     as order_count
    from gold.fact_order f
    group by f.date_key
)
select
    case when d.is_weekend then 'Weekend' else 'Weekday' end as day_type,
    round(avg(daily.net_sales)::numeric, 2)                  as avg_daily_sales,
    round(avg(daily.order_count)::numeric, 1)                as avg_daily_orders,
    round((avg(daily.net_sales) / nullif(avg(daily.order_count), 0))::numeric, 2) as avg_ticket
from daily
join gold.dim_date d on daily.date_key = d.date_key
group by d.is_weekend
order by d.is_weekend
```

```sql quarterly_sales
select
    d.year,
    d.quarter,
    d.year::int::text || ' Q' || d.quarter::int::text          as period,
    round(sum(f.order_net_sales)::numeric, 2)    as net_sales,
    sum(f.order_count)                           as order_count,
    round((sum(f.order_net_sales) / nullif(sum(f.order_count), 0))::numeric, 2) as avg_ticket
from gold.fact_order f
join gold.dim_date d on f.date_key = d.date_key
group by d.year, d.quarter
order by d.year, d.quarter
```

## Historical Net Sales by Month

<BarChart
    data={monthly_sales}
    x=year_month
    y=net_sales
    title="Monthly Net Sales"
    sort=false
/>

## Year-over-Year Comparison

<BarChart
    data={yoy_comparison}
    x=month_name
    y=net_sales
    series=year
    title="Monthly Sales 2024, 2025, 2026"
    sort=false
/>

## Month-over-Month Growth

<DataTable
    data={mom_growth}
    rows=24
/>

## Quarterly Summary

<BarChart
    data={quarterly_sales}
    x=period
    y=net_sales
    title="Net Sales by Quarter"
    sort=false
/>

<DataTable data={quarterly_sales} />

## Average Daily Sales by Day of Week

<BarChart
    data={day_of_week}
    x=day_name
    y=avg_net_sales
    title="Avg Daily Sales by Day of Week"
    sort=false
/>

<BarChart
    data={day_of_week}
    x=day_name
    y=avg_ticket
    title="Avg Ticket by Day of Week"
    sort=false
/>

<DataTable data={day_of_week} />

## Weekday vs Weekend

<BarChart
    data={weekend_vs_weekday}
    x=day_type
    y=avg_daily_sales
    title="Avg Daily Sales, Weekday vs Weekend"
/>

<DataTable data={weekend_vs_weekday} />
