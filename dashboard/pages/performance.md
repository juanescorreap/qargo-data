---
title: Store Performance
---

```sql store_ranking_this_month
select
    s.store_name,
    round(sum(f.net_sales)::numeric, 2)                                                           as net_sales,
    sum(f.order_count)                                                                             as order_count,
    round(avg(f.avg_ticket)::numeric, 2)                                                          as avg_ticket,
    round(sum(f.net_sales * s.royalty_rate)::numeric, 2)                                          as royalty_due,
    round((sum(f.tip_amount)   / nullif(sum(f.net_sales), 0) * 100)::numeric, 2)                  as tip_pct,
    round((sum(f.discount_total) / nullif(sum(f.net_sales + f.discount_total), 0) * 100)::numeric, 2) as discount_pct
from gold.fact_sales f
join gold.dim_store s on f.store_key = s.store_key
join gold.dim_date  d on f.date_key  = d.date_key
where date_trunc('month', d.date) = (
    select date_trunc('month', max(d2.date))
    from gold.dim_date d2
    join gold.fact_sales f2 on d2.date_key = f2.date_key
)
group by s.store_name, s.royalty_rate
order by net_sales desc
```

```sql royalties_ytd
select
    s.store_name,
    s.royalty_rate,
    round(sum(f.net_sales)::numeric, 2)                          as net_sales,
    round(sum(f.net_sales * s.royalty_rate)::numeric, 2)         as royalty_due
from gold.fact_sales f
join gold.dim_store s on f.store_key = s.store_key
join gold.dim_date  d on f.date_key  = d.date_key
where d.year = extract(year from current_date)::int
group by s.store_name, s.royalty_rate
order by royalty_due desc
```

```sql avg_ticket_comparison
select
    s.store_name,
    round(avg(f.avg_ticket)::numeric, 2) as avg_ticket,
    sum(f.order_count)                   as order_count
from gold.fact_sales f
join gold.dim_store s on f.store_key = s.store_key
join gold.dim_date  d on f.date_key  = d.date_key
where date_trunc('month', d.date) = (
    select date_trunc('month', max(d2.date))
    from gold.dim_date d2
    join gold.fact_sales f2 on d2.date_key = f2.date_key
)
group by s.store_name
order by avg_ticket desc
```

```sql discount_efficiency
select
    s.store_name,
    round(sum(f.net_sales)::numeric, 2)                                                               as net_sales,
    round(sum(f.discount_total)::numeric, 2)                                                          as discount_total,
    round((sum(f.discount_total) / nullif(sum(f.net_sales + f.discount_total), 0) * 100)::numeric, 2) as discount_pct,
    round((sum(f.net_sales) + sum(f.discount_total))::numeric, 2)                                     as gross_sales
from gold.fact_sales f
join gold.dim_store s on f.store_key = s.store_key
join gold.dim_date  d on f.date_key  = d.date_key
where date_trunc('month', d.date) = (
    select date_trunc('month', max(d2.date))
    from gold.dim_date d2
    join gold.fact_sales f2 on d2.date_key = f2.date_key
)
group by s.store_name
order by discount_pct desc
```

```sql store_monthly_trend
select
    s.store_name,
    d.year || '-' || lpad(d.month::text, 2, '0') as year_month,
    round(sum(f.net_sales)::numeric, 2)           as net_sales
from gold.fact_sales f
join gold.dim_store s on f.store_key = s.store_key
join gold.dim_date  d on f.date_key  = d.date_key
where d.year >= extract(year from current_date)::int - 1
group by s.store_name, d.year, d.month
order by d.year, d.month
```

## Store Ranking, This Month

<DataTable data={store_ranking_this_month} />

<BarChart
    data={store_ranking_this_month}
    x=store_name
    y=net_sales
    title="Net Sales by Store, This Month"
    sort=true
/>

## Avg Ticket by Store, This Month

<BarChart
    data={avg_ticket_comparison}
    x=store_name
    y=avg_ticket
    title="Avg Ticket by Store"
    sort=true
/>

## Royalties Due, Year to Date

<DataTable data={royalties_ytd} />

<BarChart
    data={royalties_ytd}
    x=store_name
    y=royalty_due
    title="Royalty Due YTD by Store"
    sort=true
/>

## Discount Efficiency by Store, This Month

<DataTable data={discount_efficiency} />

<BarChart
    data={discount_efficiency}
    x=store_name
    y=discount_pct
    title="Discount % by Store (lower is better)"
    sort=true
/>

## Monthly Sales Trend by Store

<LineChart
    data={store_monthly_trend}
    x=year_month
    y=net_sales
    series=store_name
    title="Monthly Net Sales by Store"
/>
