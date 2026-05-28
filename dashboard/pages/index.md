---
title: Qargo Coffee — Network Dashboard
---

```sql current_month_summary
select
    sum(f.net_sales)                         as total_sales,
    sum(f.net_sales * s.royalty_rate)        as total_royalties
from gold.fact_sales f
join gold.dim_date  d on f.date_key  = d.date_key
join gold.dim_store s on f.store_key = s.store_key
where date_trunc('month', d.date) = (
    select date_trunc('month', max(d2.date))
    from gold.dim_date d2
    join gold.fact_sales f2 on d2.date_key = f2.date_key
)
```

```sql stores_this_month
select
    s.store_name,
    '/stores/' || s.store_name as store_url,
    sum(f.net_sales) as net_sales
from gold.fact_sales f
join gold.dim_date  d on f.date_key  = d.date_key
join gold.dim_store s on f.store_key = s.store_key
where date_trunc('month', d.date) = (
    select date_trunc('month', max(d2.date))
    from gold.dim_date d2
    join gold.fact_sales f2 on d2.date_key = f2.date_key
)
group by s.store_name
order by net_sales desc
```

```sql daily_last_30
select
    d.date,
    sum(f.net_sales) as net_sales
from gold.fact_sales f
join gold.dim_date d on f.date_key = d.date_key
where d.date >= (
    select max(d2.date) - interval '29 days'
    from gold.dim_date d2
    join gold.fact_sales f2 on d2.date_key = f2.date_key
)
group by d.date
order by d.date
```

```sql channel_mix
select
    dest.channel,
    round(sum(f.net_sales)::numeric, 2) as net_sales,
    sum(f.order_count)                  as order_count
from gold.fact_sales f
join gold.dim_destination dest on f.destination_key = dest.destination_key
join gold.dim_date d on f.date_key = d.date_key
where date_trunc('month', d.date) = (
    select date_trunc('month', max(d2.date))
    from gold.dim_date d2
    join gold.fact_sales f2 on d2.date_key = f2.date_key
)
and dest.channel <> 'Unknown'
group by dest.channel
order by net_sales desc
```

```sql top_employees
select
    e.employee_name,
    round(sum(f.net_sales)::numeric, 2)  as net_sales,
    sum(f.order_count)                   as order_count,
    round(avg(f.avg_ticket)::numeric, 2) as avg_ticket
from gold.fact_sales_by_employee f
join gold.dim_employee e on f.employee_key = e.employee_key
join gold.dim_date     d on f.date_key     = d.date_key
where date_trunc('month', d.date) = (
    select date_trunc('month', max(d2.date))
    from gold.dim_date d2
    join gold.fact_sales_by_employee f2 on d2.date_key = f2.date_key
)
and e.employee_name <> 'UNKNOWN'
group by e.employee_name
order by net_sales desc
limit 10
```

<BigValue
    data={current_month_summary}
    value=total_sales
    title="Network Sales — This Month"
    fmt=usd
/>
<BigValue
    data={current_month_summary}
    value=total_royalties
    title="Total Royalties — This Month"
    fmt=usd
/>

## Net Sales by Store

<BarChart
    data={stores_this_month}
    x=store_name
    y=net_sales
    title="Net Sales by Store — Current Month"
    sort=true
/>

<DataTable data={stores_this_month} link=store_url />

## Daily Network Sales — Last 30 Days

<LineChart
    data={daily_last_30}
    x=date
    y=net_sales
    title="Daily Total Sales"
/>

## Sales by Channel — This Month

<BarChart
    data={channel_mix}
    x=channel
    y=net_sales
    title="Net Sales by Channel"
/>

## Top 10 Employees — This Month

<DataTable data={top_employees} />
