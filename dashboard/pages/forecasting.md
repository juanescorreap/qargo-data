---
title: Forecasting & Predictive Analytics
---

```sql forecast_projection
with recent_30 as (
    select
        sum(f.net_sales)              as sales_30d,
        count(distinct d.date)        as days_with_data
    from gold.fact_sales f
    join gold.dim_date d on f.date_key = d.date_key
    where d.date > current_date - interval '30 days'
      and d.date < current_date
),
current_month_actuals as (
    select
        coalesce(sum(f.net_sales), 0) as mtd_sales,
        count(distinct d.date)        as days_reported
    from gold.fact_sales f
    join gold.dim_date d on f.date_key = d.date_key
    where date_trunc('month', d.date) = date_trunc('month', current_date)
),
days_in_month as (
    select extract(days from
        date_trunc('month', current_date) + interval '1 month' - interval '1 day'
    )::int as total_days
)
select
    round(a.mtd_sales::numeric, 2)                                                          as mtd_sales,
    a.days_reported,
    round((r.sales_30d / nullif(r.days_with_data, 0))::numeric, 2)                         as daily_run_rate,
    d.total_days,
    round(
        (a.mtd_sales + (r.sales_30d / nullif(r.days_with_data, 0)) * (d.total_days - a.days_reported))::numeric,
        2
    )                                                                                       as projected_monthly
from current_month_actuals a, recent_30 r, days_in_month d
```

## Sales Forecast — Current Month

<BigValue data={forecast_projection} value=mtd_sales        title="Month-to-Date Sales"        fmt=usd />
<BigValue data={forecast_projection} value=daily_run_rate   title="Daily Run Rate (L-30D avg)"  fmt=usd />
<BigValue data={forecast_projection} value=projected_monthly title="Projected Month-End Total"  fmt=usd />

```sql forecast_chart
with daily as (
    select
        d.date,
        sum(f.net_sales) as net_sales
    from gold.fact_sales f
    join gold.dim_date d on f.date_key = d.date_key
    where d.date >= current_date - interval '59 days'
      and d.date < current_date
    group by d.date
),
run_rate as (
    select round((sum(net_sales) / nullif(count(distinct date), 0))::numeric, 2) as daily_avg
    from daily
    where date >= current_date - interval '30 days'
),
projected as (
    select
        d.date,
        r.daily_avg as projected_sales
    from gold.dim_date d
    cross join run_rate r
    where d.date >= current_date
      and d.date <= date_trunc('month', current_date) + interval '1 month' - interval '1 day'
)
select date, net_sales, null::numeric as projected_sales from daily
union all
select date, null::numeric, projected_sales from projected
order by date
```

<LineChart
    data={forecast_chart}
    x=date
    y={["net_sales","projected_sales"]}
    title="Actual (L-60D) + Projected Remainder of Month"
    yFmt=usd
/>

---

```sql yoy_comparison
-- C1 cutover: orders from fact_order (net_sales = order-level, sums identically)
with ref as (
    select
        date_trunc('month', max(d.date)) as last_complete_month
    from gold.dim_date d
    join gold.fact_order f on d.date_key = f.date_key
    where d.date < date_trunc('month', current_date)
)
select
    strftime(r.last_complete_month, '%B %Y')             as period_label,
    sum(case when date_trunc('month', d.date) = r.last_complete_month
             then f.order_net_sales else 0 end)          as current_year_sales,
    sum(case when date_trunc('month', d.date) = r.last_complete_month - interval '1 year'
             then f.order_net_sales else 0 end)          as prior_year_sales,
    sum(case when date_trunc('month', d.date) = r.last_complete_month
             then f.order_count else 0 end)              as current_year_orders,
    sum(case when date_trunc('month', d.date) = r.last_complete_month - interval '1 year'
             then f.order_count else 0 end)              as prior_year_orders,
    round(
        (
            sum(case when date_trunc('month', d.date) = r.last_complete_month then f.order_net_sales else 0 end)
          - sum(case when date_trunc('month', d.date) = r.last_complete_month - interval '1 year' then f.order_net_sales else 0 end)
        )::numeric
        / nullif(sum(case when date_trunc('month', d.date) = r.last_complete_month - interval '1 year' then f.order_net_sales else 0 end), 0)
        * 100,
        1
    )                                                    as yoy_sales_growth_pct
from gold.fact_order f
join gold.dim_date d on f.date_key = d.date_key
cross join ref r
group by r.last_complete_month
```

## Year-over-Year Comparison — Most Recent Completed Month

<BigValue data={yoy_comparison} value=current_year_sales    title="This Year Net Sales"       fmt=usd />
<BigValue data={yoy_comparison} value=prior_year_sales      title="Prior Year Net Sales"      fmt=usd />
<BigValue data={yoy_comparison} value=yoy_sales_growth_pct  title="YoY Growth %"                      />

```sql yoy_monthly
select
    d.month,
    d.month_name,
    cast(d.year as text)                         as year,
    round(sum(f.order_net_sales)::numeric, 2)    as net_sales,
    sum(f.order_count)                           as order_count
from gold.fact_order f
join gold.dim_date d on f.date_key = d.date_key
where d.year in (extract(year from current_date)::int - 1, extract(year from current_date)::int)
group by d.year, d.month, d.month_name
order by d.month, d.year
```

<BarChart
    data={yoy_monthly}
    x=month_name
    y=net_sales
    series=year
    title="Monthly Sales — Current Year vs Prior Year"
    yFmt=usd
/>

---

```sql weekday_profiling
select
    d.day_name,
    d.day_of_week                                                                               as dow_num,
    p.revenue_center_name,
    round(avg(daily_product.net_sales)::numeric, 2)                                            as avg_daily_sales
from (
    select
        f.date_key,
        f.product_key,
        sum(f.net_sales) as net_sales
    from gold.fact_sales f
    group by f.date_key, f.product_key
) daily_product
join gold.dim_date    d on daily_product.date_key    = d.date_key
join gold.dim_product p on daily_product.product_key = p.product_key
where d.day_of_week in (1, 7)
  and p.revenue_center_name in ('Beverage','Food','Retail')
group by d.day_name, d.day_of_week, p.revenue_center_name
order by d.day_of_week, p.revenue_center_name
```

## Weekday Profiling — Monday vs Sunday Category Mix

<BarChart
    data={weekday_profiling}
    x=day_name
    y=avg_daily_sales
    series=revenue_center_name
    title="Avg Daily Sales by Category — Monday vs Sunday"
    yFmt=usd
/>
